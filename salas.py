"""Conexión con las dos salas por Drive: lo mismo que ven la Sala de edición y la Sala de diseño.

Lee la carpeta del proyecto de Drive («EDICIÓN DE VIDEOS», la misma cuenta de las tres apps) con rclone:
- Videos terminados de la Sala de edición: <producción>/[<día o sesión>/]V.FINALES/[DIA_X/]*.mp4 (+ .jpg y .txt).
- Posts y carruseles de la Sala de diseño: DISEÑO/<mes>/<semana>/<pieza>/FINAL/L*.png (+ copy.txt y pieza.json).
- Briefs de la estrategia: _SEMANAS/<semana>/brief.json.

Solo se bajan solos los archivos chicos (portadas, copys, guiones, pieza.json). Los videos y las láminas se bajan
cuando se van a ver o a publicar. Todo queda en <datos>/drive con las mismas carpetas que en Drive.
Si el archivo ya está en la PC (Drive para escritorio o la copia de trabajo de una sala), se usa ese y no se baja.
Sin conexión, se usa lo último que se leyó (drive_inventario.json).
"""
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import nucleo

CACHE = nucleo.PUBLICACION / "drive"
INVENTARIO = nucleo.PUBLICACION / "drive_inventario.json"
FINALES = ("V.FINALES", "VIDEOS FINALES", "listos")
EXT_VIDEO = (".mp4", ".mov")
EXT_FOTO = (".png", ".jpg", ".jpeg", ".webp")
DRIVE_ID = "1l4PyMCGfv0PvAIFTlcySbgcfBuN64ciu"   # carpeta compartida EDICIÓN DE VIDEOS (Drive para escritorio)
INCLUIR = ["**/V.FINALES/**", "**/VIDEOS FINALES/**", "DISEÑO/**/FINAL/**", "DISEÑO/**/pieza.json",
           "**/Guion/produccion.json", "_SEMANAS/**/brief.json", "_SALA/grupos.json"]
CHICOS = (".jpg", ".jpeg", ".txt", ".json")   # se bajan al leer; lo demás, cuando hace falta
DIAS = {"LUN": 1, "MAR": 2, "MIE": 3, "MIÉ": 3, "JUE": 4, "VIE": 5, "SAB": 6, "SÁB": 6, "DOM": 7}

_memo = {"cuando": 0, "lista": None, "fuente": None, "error": None}
_candado = threading.Lock()
_candado_bajar = threading.Lock()


# ---------- Semanas (la misma cuenta que la Sala de diseño y la estrategia) ----------

def _base():
    b = nucleo.config().get("semana_base") or {}
    return int(b.get("numero", 1)), date.fromisoformat(b.get("lunes", "2026-10-05"))


def semana_de(dia):
    """date → «S03». La del lunes 19/10/2026 es la S03."""
    num, lunes = _base()
    return f"S{num + (dia - lunes).days // 7:02d}"


def lunes_de_semana(codigo):
    num, lunes = _base()
    return lunes + timedelta(days=7 * (int(codigo[1:]) - num))


# ---------- Dónde puede estar ya el archivo en esta PC ----------

_espejos = {"cuando": 0, "lista": None}


def espejos():
    """Carpetas de la PC que tienen la misma forma que el proyecto de Drive (se miran cada 30 s: revisar 13 letras de
    disco en cada pregunta hacía lenta la pantalla con la cola llena)."""
    if _espejos["lista"] is not None and time.time() - _espejos["cuando"] < 30:
        return list(_espejos["lista"])
    _espejos.update(lista=_buscar_espejos(), cuando=time.time())
    return list(_espejos["lista"])


def _buscar_espejos():
    out = []
    for c in nucleo.config().get("carpetas_produccion") or []:
        if c:
            out.append(Path(c))
    for letra in "GHIJKLMNOPDEF":
        out += [Path(f"{letra}:/.shortcut-targets-by-id/{DRIVE_ID}/EDICIÓN DE VIDEOS"),
                Path(f"{letra}:/Mi unidad/EDICIÓN DE VIDEOS"), Path(f"{letra}:/My Drive/EDICIÓN DE VIDEOS")]
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    out += [local / "SalaSuplevet" / "datos" / "drive", local / "SalaDiseno" / "datos" / "drive"]
    raiz = nucleo.PUBLICACION.parent      # REDES SOCIALES - SUPLEVET, cuando el publicador corre ahí
    out += [raiz / "1_PRODUCCION" / "editor" / "drive", raiz / "1_PRODUCCION" / "editor" / "datos" / "drive"]
    vistas, buenas = set(), []
    for c in out:
        try:
            if c.is_dir() and c.resolve() not in vistas:
                vistas.add(c.resolve())
                buenas.append(c)
        except OSError:
            pass
    return buenas


def _en_pc(rel, tam=None):
    """El archivo de Drive «rel» si ya está en la PC con el mismo tamaño (bajado aquí o en otro lado)."""
    for raiz in [CACHE, *espejos()]:
        f = raiz / rel
        try:
            if f.is_file() and (tam is None or f.stat().st_size == tam):
                return f
        except OSError:
            pass
    return None


def ruta_local(rel, tam=None):
    """Dónde está (o va a estar) el archivo: la copia que ya hay en la PC o su lugar en <datos>/drive."""
    return _en_pc(rel, tam) or (CACHE / rel)


# ---------- Leer Drive ----------

def _conectado():
    import cuenta
    try:
        return cuenta.estado().get("conectado")
    except Exception:
        return False


def _leer_drive():
    import cuenta
    args = ["lsjson", "proyecto:", "-R", "--files-only", "--fast-list", "--no-mimetype"]
    for i in INCLUIR:
        args += ["--include", i]
    lista = json.loads(cuenta.rc(*args, timeout=180) or "[]")
    return [{"rel": x["Path"], "tam": x.get("Size"), "mod": (x.get("ModTime") or "")[:19], "id": x.get("ID")} for x in lista]


def _leer_pc():
    """Sin Drive: lo mismo, pero mirando las carpetas de la PC."""
    vistos, out = set(), []
    for raiz in espejos():
        for f in raiz.rglob("*"):
            try:
                rel = f.relative_to(raiz).as_posix()
                if rel in vistos or not f.is_file() or not _sirve(rel):
                    continue
                st = f.stat()
            except OSError:
                continue
            vistos.add(rel)
            out.append({"rel": rel, "tam": st.st_size, "mod": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return out


def _sirve(rel):
    partes = rel.split("/")
    if any(p in FINALES for p in partes[:-1]):
        return True
    if partes[0] == "DISEÑO" and ("FINAL" in partes[:-1] or partes[-1] == "pieza.json"):
        return True
    return rel.endswith("/Guion/produccion.json") or (partes[0] == "_SEMANAS" and partes[-1] == "brief.json") \
        or rel == "_SALA/grupos.json"


def inventario(forzar=False):
    """[{rel, tam, mod}] de lo que hay en Drive (guardado 3 minutos). Baja los archivos chicos que falten."""
    with _candado:
        if not forzar and _memo["lista"] is not None and time.time() - _memo["cuando"] < 180:
            return _memo["lista"]
        lista, fuente, error = None, "pc", None
        if _conectado():
            try:
                lista, fuente = _leer_drive(), "drive"
                nucleo.escribir_json(INVENTARIO, {"leido": datetime.now().isoformat(timespec="seconds"), "archivos": lista})
            except Exception as e:
                error = str(e)
                nucleo.anotar(f"Drive: no pude leer el proyecto ({e}); uso lo último que leí")
                guardado = nucleo.leer_json(INVENTARIO, {})
                if guardado.get("archivos"):
                    lista, fuente = guardado["archivos"], "guardado"
        if lista is None:
            lista = _leer_pc()
        if fuente != "pc":
            faltan = [x["rel"] for x in lista if x["rel"].lower().endswith(CHICOS) and not _en_pc(x["rel"], x["tam"])]
            if faltan:
                try:
                    bajar(faltan)
                except Exception as e:
                    nucleo.anotar(f"Drive: no pude bajar {len(faltan)} archivos chicos: {e}")
        _memo.update(cuando=time.time(), lista=lista, fuente=fuente, error=error)
        return lista


def ultima():
    """Lo último que se leyó, sin salir a Drive (para lo que se pregunta muchas veces seguidas: briefs y guiones)."""
    if _memo["lista"] is not None:
        return _memo["lista"]
    return nucleo.leer_json(INVENTARIO, {}).get("archivos") or []


def estado():
    return {"fuente": _memo["fuente"], "error": _memo["error"], "conectado": _conectado(),
            "leido": datetime.fromtimestamp(_memo["cuando"]).isoformat(timespec="minutes") if _memo["cuando"] else None}


def bajar(rels):
    """Baja de Drive esos archivos (rutas dentro del proyecto) a <datos>/drive, en una sola llamada."""
    import cuenta
    rels = sorted(set(rels))
    if not rels:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    cuenta.rc("copy", "proyecto:", str(CACHE), "--files-from-raw", "-", "--no-traverse", timeout=1800,
              entrada="\n".join(rels) + "\n")


def asegurar(pub):
    """Antes de subir una publicación: que sus archivos estén en la PC (los de Drive se bajan ahora)."""
    with _candado_bajar:   # una bajada a la vez: si no, el mismo video se baja dos veces encima
        faltan = [rel for ruta, rel in zip(pub.get("archivos") or [], pub.get("drive") or []) if rel and not os.path.isfile(ruta)]
        if faltan:
            nucleo.anotar(f"Bajando de Drive {len(faltan)} archivo(s) de {pub.get('codigo')}")
            bajar(faltan)
    perdidos = [os.path.basename(r) for r in pub.get("archivos") or [] if not os.path.isfile(r)]
    if perdidos:
        raise FileNotFoundError(f"No encuentro {', '.join(perdidos)} (ni en la PC ni en Drive)")


# ---------- Armar las piezas ----------

def _leer_txt(rel, tam=None):
    f = _en_pc(rel, tam)
    return nucleo._leer_txt_copy(f) if f else {}


def _json(rel, tam=None):
    f = _en_pc(rel, tam)
    return nucleo.leer_json(f, {}) if f else {}


def piezas(forzar=False):
    """Todo lo terminado en las dos salas: [{rel, codigo, tipo, semana, proyecto, produccion, dia, archivos, drive, …}]."""
    lista = inventario(forzar)
    por_rel = {x["rel"]: x for x in lista}
    guiones = {x["rel"].rsplit("/Guion/", 1)[0]: x for x in lista if x["rel"].endswith("/Guion/produccion.json")}
    out = []
    # --- videos de la Sala de edición
    for x in lista:
        rel = x["rel"]
        partes = rel.split("/")
        # solo los videos terminados: nada de las partes sueltas ni de los clips largos cortados (CLIPS …) ni lo reemplazado
        if not rel.lower().endswith(EXT_VIDEO) or any(p == "POR_PARTES" or p.startswith(("CLIPS ", "_")) for p in partes[:-1]):
            continue
        i = next((k for k, p in enumerate(partes) if p in FINALES), None)
        if i is None or i == 0:
            continue
        prod_rel = "/".join(partes[:i])                 # «P04 …» o «P02 …/11／10 SESIÓN»
        proyecto = partes[0]
        if not re.match(r"P\d+", proyecto, re.I):       # carpetas sueltas viejas (exportes de antes de P01…)
            continue
        base = rel.rsplit(".", 1)[0]
        jpg = next((por_rel[base + e] for e in (".jpg", ".png", ".jpeg") if base + e in por_rel), None)
        txt = por_rel.get(base + ".txt")
        dia = next((int(m.group(1)) for p in partes[i + 1:-1] for m in [re.match(r"DIA_(\d+)", p)] if m), None)
        guion = _json(guiones[prod_rel]["rel"], guiones[prod_rel]["tam"]) if prod_rel in guiones else \
            (_json(guiones[proyecto]["rel"], guiones[proyecto]["tam"]) if proyecto in guiones else {})
        paq = _json(f"{'/'.join(partes[:-1])}/paquete.json")   # lo que deja la Sala al exportar (si es nueva)
        de_paq = next((p for p in paq.get("piezas", []) if p.get("archivo") == partes[-1]), {})
        codigo = partes[-1].rsplit(".", 1)[0].strip()
        semana = _semana_valida(de_paq.get("semana")) or _semana_valida(guion.get("semana")) or _semana_por_fecha(x["mod"])
        out.append({
            "rel": rel, "codigo": codigo, "tipo": "video", "semana": semana, "proyecto": proyecto,
            "carpeta": "/".join(partes[i:-1]),   # «V.FINALES» o «V.FINALES/DIA_1»
            "produccion": partes[i - 1], "dia": de_paq.get("dia_sugerido") or dia,
            "cuerpo": de_paq.get("cuerpo"), "nivel": de_paq.get("nivel"), "publico": de_paq.get("publico"),
            "archivos": [str(ruta_local(rel, x["tam"]))], "drive": [rel],
            "portada": str(ruta_local(jpg["rel"], jpg["tam"])) if jpg else None,
            "mini": rel if not jpg and x.get("id") else None,   # sin portada: la miniatura que hace Google Drive
            "copy": de_paq.get("copy_borrador") or (_leer_txt(txt["rel"], txt["tam"]) if txt else {}),
            "tamano_mb": round((x["tam"] or 0) / 1048576, 1), "creado": x["mod"][:16],
        })
    # --- posts y carruseles de la Sala de diseño
    carpetas = {}
    for x in lista:
        partes = x["rel"].split("/")
        if partes[0] == "DISEÑO" and len(partes) >= 6 and partes[4] == "FINAL":
            carpetas.setdefault("/".join(partes[:4]), []).append(x)
    for pieza_rel, archivos in carpetas.items():
        fotos = sorted((a for a in archivos if a["rel"].lower().endswith(EXT_FOTO)), key=lambda a: a["rel"])
        if not fotos:
            continue
        partes = pieza_rel.split("/")
        meta = _json(pieza_rel + "/pieza.json", (por_rel.get(pieza_rel + "/pieza.json") or {}).get("tam"))
        sem_carpeta = partes[2]
        semana = _semana_valida(meta.get("semana")) or _semana_valida(sem_carpeta.split(" · ")[0]) or _semana_por_fecha(fotos[0]["mod"])
        nombre = partes[3].split(" · ")
        dia = DIAS.get(nombre[0].upper()) if len(nombre) > 1 else None
        txt = next((a for a in archivos if a["rel"].endswith("/copy.txt")), None)
        copy = _leer_txt(txt["rel"], txt["tam"]) if txt else {}
        if meta.get("copy") and not copy:
            copy = {"instagram": meta["copy"]}
        out.append({
            "rel": pieza_rel, "codigo": meta.get("codigo") or f"{semana}-D-{nombre[1] if len(nombre) > 1 else partes[3]}",
            "titulo": meta.get("titulo") or (nombre[-1] if nombre else partes[3]),
            "tipo": "carrusel", "clase": "post" if len(fotos) == 1 else "carrusel", "semana": semana, "proyecto": "DISEÑO",
            "produccion": sem_carpeta, "dia": meta.get("dia") if isinstance(meta.get("dia"), int) else dia,
            "nivel": meta.get("nivel"), "publico": meta.get("publico"), "acompana": meta.get("acompaña") or [],
            "video": meta.get("video") or "",   # el video de la Sala de edición con el que se hizo (ruta en Drive)
            "archivos": [str(ruta_local(a["rel"], a["tam"])) for a in fotos], "drive": [a["rel"] for a in fotos],
            "portada": str(ruta_local(fotos[0]["rel"], fotos[0]["tam"])),
            "copy": copy, "tamano_mb": round(sum(a["tam"] or 0 for a in fotos) / 1048576, 1),
            "creado": max(a["mod"] for a in fotos)[:16],
        })
    return out


def _semana_valida(s):
    m = re.fullmatch(r"S(\d{1,3})", (s or "").strip().upper())
    return f"S{int(m.group(1)):02d}" if m else None


def _semana_por_fecha(mod):
    try:
        return semana_de(datetime.fromisoformat(mod[:19]).date())
    except (TypeError, ValueError):
        return None


def semanas(lista_piezas):
    """Las semanas con algo listo o con brief, de la más nueva a la más vieja: [{codigo, nombre, desde, hasta, piezas}]."""
    nombres = {}
    for x in ultima():
        partes = x["rel"].split("/")
        if partes[0] == "_SEMANAS" and len(partes) > 1:
            c = _semana_valida(partes[1].split(" · ")[0])
            if c:
                nombres[c] = partes[1]
        elif partes[0] == "DISEÑO" and len(partes) > 2:
            c = _semana_valida(partes[2].split(" · ")[0])
            if c and c not in nombres:
                nombres[c] = " · ".join(partes[2].split(" · ")[:2])
    cuenta = {}
    for p in lista_piezas:
        if p.get("semana"):
            cuenta[p["semana"]] = cuenta.get(p["semana"], 0) + 1
    out = []
    for c in sorted(set(nombres) | set(cuenta), key=lambda s: int(s[1:]), reverse=True):
        lunes = lunes_de_semana(c)
        out.append({"codigo": c, "nombre": nombres.get(c) or c, "desde": lunes.isoformat(),
                    "hasta": (lunes + timedelta(days=6)).isoformat(), "piezas": cuenta.get(c, 0)})
    return out


def briefs():
    """Los brief.json de _SEMANAS que ya están en la PC."""
    out = []
    for x in ultima():
        if x["rel"].startswith("_SEMANAS/") and x["rel"].endswith("/brief.json"):
            f = _en_pc(x["rel"], x["tam"])
            if f:
                out.append(f)
    return out


def guiones():
    """{nombre de la carpeta que tiene Guion/: ruta local de produccion.json} de lo que hay en Drive."""
    out = {}
    for x in ultima():
        if x["rel"].endswith("/Guion/produccion.json"):
            f = _en_pc(x["rel"], x["tam"])
            if f:
                out[x["rel"].rsplit("/Guion/", 1)[0].split("/")[-1]] = f
    return out


MINIS = nucleo.PUBLICACION / "miniaturas"


def miniatura(rel):
    """La miniatura que Google Drive arma para un video sin portada (se baja una vez y queda guardada)."""
    import hashlib
    import urllib.request
    import cuenta
    x = next((a for a in ultima() if a["rel"] == rel and a.get("id")), None)
    if not x or not rel.lower().endswith(EXT_VIDEO):
        raise FileNotFoundError("Ese video no está en Drive")
    destino = MINIS / (hashlib.sha1(rel.encode()).hexdigest()[:16] + ".jpg")
    if not destino.exists():
        link = cuenta.api_drive(f"files/{x['id']}?fields=thumbnailLink").get("thumbnailLink", "")
        if not link:
            raise FileNotFoundError("Google Drive todavía no tiene miniatura de este video")
        link = re.sub(r"=s\d+$", "=s640", link)
        with urllib.request.urlopen(urllib.request.Request(link, headers={"Authorization": f"Bearer {cuenta.token()}"}), timeout=30) as r:
            MINIS.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(r.read())
    return destino


def grupos():
    f = _en_pc("_SALA/grupos.json")
    return nucleo.leer_json(f, {}) if f else {}
