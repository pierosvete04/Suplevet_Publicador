"""Copys: el publicador escribe el copy de cada video a partir de su guion.

Busca el produccion.json de la producción del video (Guion/ de la sesión, la copia de la Sala o 1_PRODUCCION/semanas),
encuentra el hook, el cuerpo y el CTA del video por su código (C1-H2-CTA1) y arma un copy por red:
- Primera línea: el hook escrito del guion (o el hablado, más corto), directo y con un emoji según el tipo de hook.
- Dos o tres beneficios del cuerpo, cortos, con ✅.
- El cierre del CTA y los hashtags del cuerpo.
Cada cuenta recibe una variante distinta (otro orden de beneficios, otro emoji, otro cierre) para no repetir texto.
Sin guion, transcribe el audio del video (si está faster-whisper) y usa su primera frase como hook.
"""
import glob
import hashlib
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import nucleo

PRODUCCION = nucleo.PUBLICACION.parent / "1_PRODUCCION"
TRANSCRIPCIONES = nucleo.PUBLICACION / "transcripciones"

EMOJI = {"pregunta": ["🤔", "❓", "👀"], "dato": ["📊", "🔬", "📌"], "problema": ["⚠️", "😟", "👀"], "error": ["❌", "🚫", "⚠️"],
         "lista": ["📋", "👇", "✍️"], "contraintuitivo": ["🤯", "💡", "👀"], "segmentacion": ["🩺", "📣", "👋"],
         "bucle abierto": ["👀", "🔍", "⏳"], "creencia": ["💡", "🤯", "📌"], "promesa": ["✨", "🔥", "💪"],
         "numero": ["🔢", "📊", "👇"], "contra": ["🚫", "❌", "🤯"], "producto": ["🐾", "✨", "💪"]}
EMOJI_DEF = ["👉", "🐾", "🔥"]
CIERRE = {"B2B": ["👉 Escríbenos por WhatsApp y te contamos más.", "📲 ¿Quieres evaluarlo en tu consulta? Escríbenos por WhatsApp.",
                  "👇 Déjanos tu consultorio por WhatsApp y te visitamos."],
          "B2C": ["👉 Pídelo por WhatsApp, te lo llevamos.", "📲 Escríbenos por WhatsApp y te asesoramos gratis.",
                  "👇 Comenta «QUIERO» y te escribimos."]}
TAGS = {"B2B": "#veterinario #medicinaveterinaria #suplevet #nutricionveterinaria #perros #gatos",
        "B2C": "#perros #mascotas #suplevet #perrosfelices #saludcanina #gatos"}
_VERBOS = (r"^(ayuda|ayudan|apoya|apoyan|mejora|reduce|fortalece|protege|cuida|aporta|favorece|regenera|conserva|refuerza|"
           r"tiene|tienen|contiene|trae|mantiene|aumenta)\b")


def _clave(n):
    """«11／10 SESIÓN» y «11 10 SESIÓN» son la misma producción."""
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower())


# ---------- Guiones ----------

_memo = {"cuando": 0, "indice": {}}


def _indice():
    """{clave de producción: produccion.json}, guardado un minuto."""
    if time.time() - _memo["cuando"] < 60:
        return _memo["indice"]
    import produccion
    rutas = []
    for raiz in produccion.carpetas():
        rutas += glob.glob(str(Path(raiz) / "*" / "Guion" / "produccion.json")) + glob.glob(str(Path(raiz) / "*" / "produccion.json"))
    for base in (PRODUCCION / "editor" / "drive", PRODUCCION / "editor" / "datos" / "drive"):
        rutas += glob.glob(str(base / "*" / "Guion" / "produccion.json"))
    rutas += glob.glob(str(PRODUCCION / "semanas" / "*" / "produccion.json"))
    import salas
    indice = {_clave(nombre): str(r) for nombre, r in salas.guiones().items()}   # los de Drive, lo mismo que la Sala
    for r in rutas:
        sesion = Path(r).parent.parent if Path(r).parent.name == "Guion" else Path(r).parent
        indice.setdefault(_clave(sesion.parent.name) + "|" + _clave(sesion.name), r)
        indice.setdefault(_clave(sesion.name), r)
    # sesiones agrupadas en la Sala (11/10 + 13/10): todas usan el guion de la sesión que lo tiene
    grupos = salas.grupos() or nucleo.leer_json(PRODUCCION / "editor" / "grupos.json", {})
    for g in grupos.values():
        guion = indice.get(_clave(g.get("guion")))
        for s in g.get("sesiones") or []:
            if guion:
                indice.setdefault(_clave(s), guion)
    _memo.update(cuando=time.time(), indice=indice)
    return indice


_guiones = {}


def guion_de(prod, proyecto=None):
    ind = _indice()
    r = (proyecto and ind.get(_clave(proyecto) + "|" + _clave(prod))) or ind.get(_clave(prod)) or (proyecto and ind.get(_clave(proyecto)))
    if not r:
        return None
    firma = Path(r).stat().st_mtime
    if _guiones.get(r, (None,))[0] != firma:
        _guiones[r] = (firma, nucleo.leer_json(r, {}))
    return _guiones[r][1]


def _ids(codigo, guion):
    """De «S03-C1-H2-CTA1» saca (C1, C1_H2, C1_CTA1 o CTA1); de «P2H1», (C2, C2_H1, …). Sin cuerpo en el nombre
    («SUPLEVET H3 1012»), el primer cuerpo con ese hook. Sin CTA en el nombre, el del cuerpo (C1_CTA o CTA1 para C1)."""
    piezas = guion.get("piezas", {})
    cuerpo, h, tt = nucleo.partes_codigo(codigo)
    if cuerpo and cuerpo not in piezas:
        cuerpo = None
    num = lambda k: int(re.match(r"C(\d+)", k).group(1)) if re.match(r"C\d+", k) else 999   # noqa: E731
    if not cuerpo and h:
        cuerpo = next((k.split("_")[0] for k in sorted(piezas, key=num) if re.fullmatch(rf"C\d+_{h}", k)), None)
    cuerpo = cuerpo or next((k for k in sorted(piezas, key=num) if piezas[k].get("tipo") == "cuerpo"), None)
    hook = f"{cuerpo}_{h}" if h and cuerpo else None
    if tt:   # «CTA-A» del nombre puede estar en el guion como «CTA-A» o «CTA_A»
        alt = {tt, tt.replace("-", "_"), tt.replace("_", "-")}
        cands = [f"{cuerpo}_{x}" for x in sorted(alt)] + sorted(alt)
    else:
        cands = (f"{cuerpo}_CTA", f"CTA{(cuerpo or '')[1:]}", "CTA")
    cta = next((k for k in cands if k in piezas or k in (guion.get("copies") or {}).get("ctas", {})), None)
    return cuerpo, hook, cta


# ---------- Transcripción (videos sin guion) ----------

def _ffmpeg():
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    for f in sorted(glob.glob(str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe")), reverse=True):
        return f
    return None


_modelo = None


def transcripcion(video, hacer=True):
    """Texto hablado del video, guardado en 2_PUBLICACION/transcripciones. None si no se puede transcribir.
    hacer=False: solo la que ya está guardada (para mostrar rápido)."""
    if not Path(video).is_file():   # sigue en Drive: se baja recién al publicar
        return None
    st = Path(video).stat()
    cache = TRANSCRIPCIONES / (hashlib.md5(f"{video}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest() + ".txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    if not hacer:
        return None
    global _modelo
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    ff = _ffmpeg()
    if not ff:
        return None
    if _modelo is None:
        _modelo = WhisperModel("small", device="cpu", compute_type="int8")
    pcm = subprocess.run([ff, "-hide_banner", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    segs, _ = _modelo.transcribe(np.frombuffer(pcm, dtype=np.float32), language="es", vad_filter=True,
                                 initial_prompt="Suplevet, WhatsApp, calostro, omega 3, veterinario, tu perro, tu mascota")
    texto = " ".join(s.text.strip() for s in segs).strip()
    texto = re.sub(r"\bsu ?ple ?[bv]et\b", "Suplevet", texto, flags=re.I)
    texto = re.sub(r"\bsu\s+suplevet\b", "Suplevet", texto, flags=re.I)
    TRANSCRIPCIONES.mkdir(parents=True, exist_ok=True)
    cache.write_text(texto, encoding="utf-8")
    return texto


def _frases(texto):
    return [f.strip() for f in re.split(r"(?<=[.!?…])\s+", texto or "") if len(f.strip()) > 3]


def _clausulas(texto):
    """El cuerpo en ideas enteras: corta en los puntos y antes de «, tiene…» / «, ayuda…». Las «partes» del guion no
    sirven: son trozos de subtítulo que terminan a mitad de frase («tiene zinc y vitaminas que cuidan su piel y»)."""
    out = []
    for f in _frases(texto):
        out += re.split(r",\s+(?=(?:y\s+)?(?:tiene|tienen|contiene|ayuda|ayudan|apoya|apoyan|mejora|reduce|cuida|protege|refuerza)\b)",
                        f, flags=re.I)
    return [x.strip() for x in out if len(x.strip()) > 3]


def _texto(x):
    """Un copy del guion puede venir como texto o como {"texto": …}."""
    return (x.get("texto") if isinstance(x, dict) else x) or ""


# ---------- Armar el copy ----------

def _sin_saludo(t):
    """«Estimado médico veterinario, …» es para decirlo; escrito se lee mejor «Veterinario, …»."""
    t = re.sub(r"^\s*(estimad[oa]s?\s+)?(médic[oa]s?\s+)?veterinari([oa]s?)\s*,\s*", lambda m: "Veterinario, ", t, flags=re.I)
    return t.strip()


def _beneficio(f):
    f = re.sub(r"^(y|además|también|siempre)\s*,?\s*", "", f.strip(), flags=re.I)
    f = re.sub(r"^suplevet\s+", "", f, flags=re.I)
    f = re.sub(r"\s+(y|e|de|que|con|para)$", "", f.rstrip(" .,;:"), flags=re.I)
    return f[:1].upper() + f[1:] if f else f


def _cortar(t, n):
    if len(t) <= n:
        return t
    t = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return t + "…"


def _corto(t, n=110):
    """Un beneficio largo se corta en su última coma antes de n letras (queda una idea entera); si no hay, con «…»."""
    if len(t) <= n:
        return t
    i = t.rfind(", ", 40, n)
    return t[:i] if i > 0 else _cortar(t, n)


def _con_punto(t):
    """Termina la frase con punto, salvo que ya termine en «?», «!», «.» o «…» (nada de «?.»)."""
    t = t.strip()
    return t if not t or t[-1] in "?!.…»\"" else t + "."


def _sin_marca(t):
    """Saca «Suplevet» de una frase (TOFU) sin dejarla rota: «… de tus pacientes con Suplevet.» → «… de tus pacientes.»"""
    t = re.sub(r"\s*\b(?:con|de|a|y|por|en)?\s*suplevet\b", "", t, flags=re.I)
    t = re.sub(r"\s+([.,;:?!])", r"\1", re.sub(r"\s{2,}", " ", t)).strip(" ,;:")
    return t[:1].upper() + t[1:] if t else t


def _publico(guion, pieza):
    """B2B (veterinarios) o B2C (dueños): lo que diga el guion; si no lo dice, la pieza (del brief); si tampoco,
    lo que dicen sus hooks y cuerpos."""
    for x in (guion.get("publico"), pieza.get("publico")):
        if x:
            return "B2B" if re.search(r"veterin|b2b", str(x), re.I) else "B2C"
    textos = " ".join(str(v.get("texto", "")) for v in (guion.get("piezas") or {}).values() if isinstance(v, dict))
    vets = len(re.findall(r"\bveterinari|\bpacientes?\b|\bconsulta\b|\bcl[ií]nica\b", textos, re.I))
    duenos = len(re.findall(r"\btu (?:perro|gato|mascota|peludo)\b", textos, re.I))
    return "B2B" if vets > duenos else "B2C"


def _tipo(t):
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def generar(pieza, variante=0, transcribir=True, nivel=None):
    """{instagram, facebook, tiktok, youtube_titulo, youtube, fuente} para una pieza de Listos. Vacío si no hay de dónde."""
    codigo, prod = pieza.get("codigo") or "", pieza.get("produccion") or ""
    guion = guion_de(prod, pieza.get("proyecto"))
    gancho, tipo, partes, cierre_guion, cierre_escrito, del_cuerpo, tags, publico = "", "", [], "", "", "", "", ""
    hablado, titulo_guion = "", ""
    if guion:
        piezas, cps = guion.get("piezas", {}), guion.get("copies") or {}
        cuerpo, hook, cta = _ids(codigo, guion)
        publico = _publico(guion, pieza)
        if hook and hook in piezas:
            tipo = piezas[hook].get("tipo", "")
            hablado = _sin_saludo(piezas[hook].get("texto", ""))
            gancho = _texto((cps.get("hooks") or {}).get(hook)) or hablado
            titulo_guion = _texto((cps.get("youtube_titulos") or {}).get(hook)).strip()
        pc = piezas.get(cuerpo) or {}
        partes = _clausulas(pc.get("texto") or " ".join(pc.get("partes") or []))
        if cta:
            cierre_escrito = _texto((cps.get("ctas") or {}).get(cta))     # el copy del CTA que escribió el guionista
            cierre_guion = (piezas.get(cta) or {}).get("texto", "")       # lo que dice el video
            if len(cierre_guion) > 200:   # guiones de rondas juntan varios CTA en uno: solo las dos primeras frases
                cierre_guion = " ".join(_frases(cierre_guion)[:2])[:200]
        escrito = (cps.get("cuerpos") or {}).get(cuerpo) or {}
        del_cuerpo = _texto(escrito).strip()                               # el copy del cuerpo que escribió el guionista
        tags = escrito.get("hashtags", "") if isinstance(escrito, dict) else ""
        fuente = "guion"
    else:
        texto = transcripcion(pieza["archivos"][0], transcribir) if pieza.get("tipo") == "video" else None
        if not texto:
            return {}
        # el audio suele salir «¿Por qué su Suplevet es…?»: el «su» sobra
        texto = re.sub(r"\bsu\s+suplevet\b", "Suplevet", texto, flags=re.I)
        fr = _frases(texto)
        # lo hablado es largo: el hook es la primera idea, cortada en la primera coma después de unas palabras
        primera = _sin_saludo(fr[0]) if fr else ""
        corte = re.search(r"^(.{25,95}?)[,;:]\s", primera)
        gancho, partes = (corte.group(1) if corte else _cortar(primera, 95)), _clausulas(" ".join(fr[1:]))
        publico = "B2B" if re.search(r"veterin|pacientes|consulta", texto, re.I) else "B2C"
        fuente = "transcripción"
    if not gancho and not partes:
        return {}
    v = variante
    # cada variante cambia varias cosas a la vez (emoji, hook escrito o hablado, orden de beneficios, cierre) con
    # ciclos de distinto largo, así la variante 3 no sale igual a la 0
    emojis = EMOJI.get(_tipo(tipo), EMOJI_DEF)
    em = emojis[v % len(emojis)]
    if hablado and gancho != hablado and len(hablado) <= 160 and v % 2:
        gancho = hablado                          # otra cuenta: el hook como se dice en el video
    if not gancho:
        gancho = _beneficio(partes[0])
    gancho = re.sub(r"\bsu\s+suplevet\b", "Suplevet", gancho.strip(), flags=re.I)
    if nivel == "TOFU" and "suplevet" in gancho.lower():      # TOFU: la marca no va en la primera línea
        gancho = _sin_marca(gancho)
    primera = f"{em} {gancho}"
    # beneficios: las ideas que empiezan con «ayuda», «tiene»… (después de sacar «Y», «Suplevet»), enteras y cortas
    buenos = []
    for b in (_beneficio(f) for f in partes):
        if re.match(_VERBOS, b, re.I) and len(b) <= 160 and _corto(b) not in buenos:
            buenos.append(_corto(b))
    if not buenos and fuente == "guion":
        buenos = [_corto(_beneficio(f)) for f in partes[1:3] if not re.match(r"se llama", _beneficio(f), re.I)]
    # lo que ya dice el copy escrito del cuerpo no se repite como ✅
    bajo = del_cuerpo.lower()
    buenos = [b for b in buenos if b.lower()[:30] not in bajo]
    if buenos:
        k = v % len(buenos)
        buenos = buenos[k:] + buenos[:k]           # otra cuenta, otro orden
    lista = "\n".join(f"✅ {b}" for b in buenos[:3])
    # sin beneficios ni nada que diga qué es: una línea fija con la marca (si no, el copy no nombra el producto)
    if "suplevet" not in (lista + " " + del_cuerpo).lower():
        lista = "\n".join(x for x in (lista, "🐾 Suplevet: suplemento en polvo que mezclas con su comida.") if x)
    # cierre: nada si el copy del cuerpo ya lo trae; si no, va rotando entre el CTA escrito, el que dice el video y
    # los de siempre (el escrito primero)
    if re.search(r"whatsapp|comenta|escr[ií]benos", del_cuerpo, re.I):
        cierre = ""
    else:
        cierres = [x for x in (cierre_escrito, _con_punto(f"{['👉', '📲', '👇'][v % 3]} {cierre_guion}") if cierre_guion else "") if x]
        cierres += [c for c in CIERRE[publico or "B2C"] if not cierres or v % 4 >= 2]
        cierre = cierres[(v // 2) % len(cierres)] if cierres else ""
    tags = tags or TAGS[publico or "B2C"]
    tags_l = tags.split()
    ig = "\n\n".join(x for x in (primera, lista, del_cuerpo, cierre, tags) if x)
    fb = "\n\n".join(x for x in (primera, lista, del_cuerpo, cierre, " ".join(tags_l[:3])) if x)
    tt = "\n\n".join(x for x in (primera, del_cuerpo or (lista.split("\n")[0] if lista else ""), cierre, " ".join(tags_l[:5])) if x)
    # título de YouTube: el que escribió el guionista para ese hook; si no hay, el hook (sin emoji) + #shorts
    if titulo_guion:
        titulo = _sin_marca(titulo_guion) if nivel == "TOFU" else titulo_guion
        titulo = _cortar(titulo, 100)
    else:
        titulo = _cortar(re.sub(r"\s+", " ", gancho), 90)
        titulo = f"{titulo} #shorts" if len(titulo) <= 91 else titulo
    yt = "\n\n".join(x for x in (gancho, lista, del_cuerpo, cierre, tags + " #shorts") if x)
    return {"instagram": ig, "facebook": fb, "tiktok": tt, "youtube_titulo": titulo, "youtube": yt, "fuente": fuente}


def aplicar(pub, cp):
    """Pone el copy generado en cada red de una publicación de la cola."""
    for red, r in pub["redes"].items():
        if cp.get(red) and r.get("estado") not in nucleo.EN_FIRME:   # lo que ya salió conserva el copy con que salió
            r["copy"] = cp[red]
    yt = pub["redes"].get("youtube")
    if yt is not None and cp.get("youtube_titulo") and yt.get("estado") not in nucleo.EN_FIRME:
        yt["titulo"] = cp["youtube_titulo"]
    pub["copy_fuente"] = cp.get("fuente")
    return pub


def rehacer(pid):
    """Vuelve a escribir el copy de una pieza de la cola con la variante siguiente."""
    import produccion
    with nucleo._candado:
        c = nucleo.cola()
        p = nucleo.buscar(c, pid)
        if not p:
            raise ValueError("No existe esa publicación")
        pieza = {"codigo": p["codigo"], "produccion": p.get("produccion", ""), "archivos": p["archivos"], "tipo": p["tipo"]}
        todas = {pz["archivos"][0]: pz for prod in produccion.listos()["producciones"] for pz in prod["piezas"]}
        pieza["codigo"] = todas.get(p["archivos"][0], {}).get("codigo", p["codigo"])   # el código original, sin prefijo
        p["copy_variante"] = p.get("copy_variante", 0) + 1
        cp = generar(pieza, p["copy_variante"], nivel=p.get("nivel"))
        if not cp:
            raise ValueError("No encontré el guion de este video ni pude transcribirlo")
        aplicar(p, cp)
        if p.get("aprobado") and nucleo.faltas(p):   # el copy nuevo no pasa la revisión: queda por revisar
            p["aprobado"] = False
        nucleo.guardar_cola(c)
        return p
