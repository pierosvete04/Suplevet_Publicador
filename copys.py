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
_VERBOS = r"^(ayuda|ayudan|apoya|apoyan|mejora|reduce|fortalece|protege|cuida|aporta|favorece|regenera|conserva|refuerza)\b"


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
    indice = {}
    for r in rutas:
        indice.setdefault(_clave(Path(r).parent.parent.name if Path(r).parent.name == "Guion" else Path(r).parent.name), r)
    # sesiones agrupadas en la Sala (11/10 + 13/10): todas usan el guion de la sesión que lo tiene
    grupos = nucleo.leer_json(PRODUCCION / "editor" / "grupos.json", {})
    for g in grupos.values():
        guion = indice.get(_clave(g.get("guion")))
        for s in g.get("sesiones") or []:
            if guion:
                indice.setdefault(_clave(s), guion)
    _memo.update(cuando=time.time(), indice=indice)
    return indice


_guiones = {}


def guion_de(prod):
    r = _indice().get(_clave(prod))
    if not r:
        return None
    firma = Path(r).stat().st_mtime
    if _guiones.get(r, (None,))[0] != firma:
        _guiones[r] = (firma, nucleo.leer_json(r, {}))
    return _guiones[r][1]


def _ids(codigo, guion):
    """De «S03-C1-H2-CTA1» saca (C1, C1_H2, C1_CTA1 o CTA1). Sin C<n> («SUPLEVET H3 1012»), el primer cuerpo con ese hook."""
    piezas = guion.get("piezas", {})
    c = re.search(r"(?:^|[-_ ])(C\d+)(?=[-_ ]|$)", codigo, re.I)
    h = re.search(r"(?:^|[-_ ])H(\d+)(?=[-_ ]|$)", codigo, re.I)
    t = re.search(r"(?:^|[-_ ])(CTA[\w]*?)(?=[-_ ]|$)", codigo, re.I)
    cuerpo = c.group(1).upper() if c else None
    if not cuerpo and h:
        cuerpo = next((k.split("_")[0] for k in piezas if re.fullmatch(rf"C\d+_H{h.group(1)}", k)), None)
    cuerpo = cuerpo or next((k for k, v in piezas.items() if v.get("tipo") == "cuerpo"), None)
    hook = f"{cuerpo}_H{h.group(1)}" if h and cuerpo else None
    cta = None
    if t:
        tt = t.group(1).upper()
        cta = next((k for k in (f"{cuerpo}_{tt}", tt) if k in piezas), None)
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
    TRANSCRIPCIONES.mkdir(parents=True, exist_ok=True)
    cache.write_text(texto, encoding="utf-8")
    return texto


def _frases(texto):
    return [f.strip() for f in re.split(r"(?<=[.!?…])\s+", texto or "") if len(f.strip()) > 3]


# ---------- Armar el copy ----------

def _sin_saludo(t):
    """«Estimado médico veterinario, …» es para decirlo; escrito se lee mejor «Veterinario, …»."""
    t = re.sub(r"^\s*(estimad[oa]s?\s+)?(médic[oa]s?\s+)?veterinari([oa]s?)\s*,\s*", lambda m: "Veterinario, ", t, flags=re.I)
    return t.strip()


def _beneficio(f):
    f = re.sub(r"^(y|además|también|siempre)\s*,?\s*", "", f.strip(), flags=re.I)
    f = re.sub(r"^suplevet\s+", "", f, flags=re.I)
    f = f.rstrip(".")
    return f[:1].upper() + f[1:] if f else f


def _cortar(t, n):
    if len(t) <= n:
        return t
    t = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return t + "…"


def _tipo(t):
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def generar(pieza, variante=0, transcribir=True, nivel=None):
    """{instagram, facebook, tiktok, youtube_titulo, youtube, fuente} para una pieza de Listos. Vacío si no hay de dónde."""
    codigo, prod = pieza.get("codigo") or "", pieza.get("produccion") or ""
    guion = guion_de(prod)
    gancho, tipo, partes, cierre_guion, tags, publico = "", "", [], "", "", ""
    if guion:
        piezas, cps = guion.get("piezas", {}), guion.get("copies", {})
        cuerpo, hook, cta = _ids(codigo, guion)
        publico = "B2B" if "veterin" in (guion.get("publico") or "").lower() else "B2C"
        if hook and hook in piezas:
            tipo = piezas[hook].get("tipo", "")
            gancho = cps.get("hooks", {}).get(hook) or _sin_saludo(piezas[hook].get("texto", ""))
        partes = (piezas.get(cuerpo) or {}).get("partes") or _frases((piezas.get(cuerpo) or {}).get("texto"))
        if cta:
            cierre_guion = piezas[cta].get("texto", "")
        tags = (cps.get("cuerpos", {}).get(cuerpo) or {}).get("hashtags", "")
        fuente = "guion"
    else:
        texto = transcripcion(pieza["archivos"][0], transcribir) if pieza.get("tipo") == "video" else None
        if not texto:
            return {}
        fr = _frases(texto)
        # lo hablado es largo: el hook es la primera idea, cortada en la primera coma después de unas palabras
        primera = _sin_saludo(fr[0]) if fr else ""
        corte = re.search(r"^(.{25,95}?)[,;:]\s", primera)
        gancho, partes = (corte.group(1) if corte else _cortar(primera, 95)), fr[1:]
        publico = "B2B" if re.search(r"veterin|pacientes|consulta", texto, re.I) else "B2C"
        fuente = "transcripción"
    if not gancho and not partes:
        return {}
    v = variante
    emojis = EMOJI.get(_tipo(tipo), EMOJI_DEF)
    em = emojis[v % len(emojis)]
    if not gancho:
        gancho = _beneficio(partes[0])
    gancho = gancho.strip()
    if nivel == "TOFU" and "suplevet" in gancho.lower():      # TOFU: la marca no va en la primera línea
        gancho = re.sub(r"\s*suplevet\s*", " ", gancho, flags=re.I).strip()
    primera = f"{em} {gancho}"
    # beneficios: las frases que empiezan con «ayuda», «apoya»… (después de sacar «Y», «Suplevet»), enteras y cortas
    buenos = [b for b in (_beneficio(f) for f in partes) if re.match(_VERBOS, b, re.I) and len(b) <= 110]
    if not buenos and fuente == "guion":
        buenos = [_cortar(_beneficio(f), 100) for f in partes[1:3]]
    if buenos:
        k = v % len(buenos)
        buenos = buenos[k:] + buenos[:k]           # otra cuenta, otro orden
    lista = "\n".join(f"✅ {b}" for b in buenos[:3])
    cierres = CIERRE[publico or "B2C"]
    cierre = cierres[v % len(cierres)] if v or not cierre_guion else f"👉 {cierre_guion.rstrip('.')}."
    tags = tags or TAGS[publico or "B2C"]
    tags_l = tags.split()
    ig = "\n\n".join(x for x in (primera, lista, cierre, tags) if x)
    fb = "\n\n".join(x for x in (primera, lista, cierre, " ".join(tags_l[:3])) if x)
    tt = "\n\n".join(x for x in (primera, f"✅ {buenos[0]}" if buenos else "", cierre, " ".join(tags_l[:5])) if x)
    titulo = _cortar(re.sub(r"\s+", " ", gancho), 90)
    titulo = f"{titulo} #shorts" if len(titulo) <= 91 else titulo
    yt = "\n\n".join(x for x in (gancho, lista, cierre, tags + " #shorts") if x)
    return {"instagram": ig, "facebook": fb, "tiktok": tt, "youtube_titulo": titulo, "youtube": yt, "fuente": fuente}


def aplicar(pub, cp):
    """Pone el copy generado en cada red de una publicación de la cola."""
    for red, r in pub["redes"].items():
        if cp.get(red):
            r["copy"] = cp[red]
    if "youtube" in pub["redes"] and cp.get("youtube_titulo"):
        pub["redes"]["youtube"]["titulo"] = cp["youtube_titulo"]
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
        nucleo.guardar_cola(c)
        return p
