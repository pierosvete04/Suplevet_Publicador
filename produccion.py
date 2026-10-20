"""Conexión con producción: los videos que la Sala deja listos en V.FINALES de cada producción.

Lee las carpetas de producción (la de Drive «EDICIÓN DE VIDEOS» y la copia de la Sala) sin que tengas que importar
nada a mano. En la pestaña Listos eliges cuáles, a qué redes y cuándo, y pasan juntos a la cola.
"""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import nucleo

FINALES = ("V.FINALES", "VIDEOS FINALES", "listos")
EXT_VIDEO = (".mp4", ".mov")
EXT_FOTO = (".png", ".jpg", ".jpeg", ".webp")
DRIVE_ID = "1l4PyMCGfv0PvAIFTlcySbgcfBuN64ciu"   # carpeta compartida EDICIÓN DE VIDEOS


def carpetas():
    """Las carpetas donde viven las producciones. Si no configuraste ninguna, se buscan solas."""
    propias = [c for c in nucleo.config().get("carpetas_produccion") or [] if c]
    if propias:
        return [Path(c) for c in propias if Path(c).is_dir()]
    candidatas = []
    for letra in "GHIJKLMNOPDEF":
        candidatas += [Path(f"{letra}:/.shortcut-targets-by-id/{DRIVE_ID}/EDICIÓN DE VIDEOS"),
                       Path(f"{letra}:/Mi unidad/EDICIÓN DE VIDEOS"), Path(f"{letra}:/My Drive/EDICIÓN DE VIDEOS")]
    raiz = nucleo.PUBLICACION.parent      # REDES SOCIALES - SUPLEVET
    candidatas += [raiz / "1_PRODUCCION" / "editor" / "drive", raiz / "1_PRODUCCION" / "editor" / "datos" / "drive"]
    vistas, out = set(), []
    for c in candidatas:
        try:
            if c.is_dir() and c.resolve() not in vistas:
                vistas.add(c.resolve())
                out.append(c)
        except OSError:
            pass
    return out


def _carpeta_finales(prod):
    for nombre in FINALES:
        f = prod / nombre
        if f.is_dir():
            return f
    return None


_memo = {"cuando": 0, "datos": None}


def listos(forzar=False):
    """Lo mismo que _leer, guardado 20 segundos: la pantalla pide portadas y videos muchas veces seguidas."""
    if forzar or not _memo["datos"] or time.time() - _memo["cuando"] > 20:
        _memo.update(cuando=time.time(), datos=_leer())
    return _memo["datos"]


def _leer():
    """{producciones: [{nombre, raiz, piezas: [...]}]} con lo que hay en V.FINALES y si ya está en la cola."""
    en_cola = {}
    for p in nucleo.cola()["publicaciones"]:
        for a in p.get("archivos", []):
            en_cola[os.path.normcase(a)] = p
    vistos, prods = set(), []
    for raiz in carpetas():
        try:
            hijos = sorted([h for h in raiz.iterdir() if h.is_dir() and not h.name.startswith(("_", "."))],
                           key=lambda h: h.stat().st_mtime, reverse=True)
        except OSError:
            continue
        for prod in hijos:
            fin = _carpeta_finales(prod)
            if not fin or prod.name in vistos:   # la misma producción en Drive y en la copia de la Sala: va una vez
                continue
            piezas = []
            for v in sorted(fin.iterdir()):
                if v.suffix.lower() in EXT_VIDEO and v.is_file():
                    piezas.append(_pieza_video(prod, v, en_cola))
            # carruseles: una subcarpeta con fotos dentro de V.FINALES
            for sub in sorted(x for x in fin.iterdir() if x.is_dir()):
                fotos = sorted(f for f in sub.iterdir() if f.suffix.lower() in EXT_FOTO)
                if fotos:
                    piezas.append(_pieza_carrusel(prod, sub, fotos, en_cola))
            if piezas:
                vistos.add(prod.name)
                prods.append({"nombre": prod.name, "raiz": str(raiz), "piezas": piezas})
    return {"producciones": prods, "carpetas": [str(c) for c in carpetas()]}


def _ya(rutas, en_cola):
    p = next((en_cola[os.path.normcase(str(r))] for r in rutas if os.path.normcase(str(r)) in en_cola), None)
    return {"id": p["id"], "fecha": p.get("fecha"), "aprobado": p.get("aprobado")} if p else None


def _pieza_video(prod, v, en_cola):
    jpg = next((v.with_suffix(e) for e in (".jpg", ".png", ".jpeg") if v.with_suffix(e).exists()), None)
    txt = v.with_suffix(".txt")
    st = v.stat()
    return {"ruta": str(v), "codigo": v.stem, "tipo": "video", "produccion": prod.name, "archivos": [str(v)],
            "portada": str(jpg) if jpg else None, "copy": nucleo._leer_txt_copy(txt) if txt.exists() else {},
            "tamano_mb": round(st.st_size / 1048576, 1), "creado": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
            "en_cola": _ya([v], en_cola)}


def _pieza_carrusel(prod, sub, fotos, en_cola):
    txt = sub / "copy.txt"
    return {"ruta": str(sub), "codigo": sub.name, "tipo": "carrusel", "produccion": prod.name, "archivos": [str(f) for f in fotos],
            "portada": str(fotos[0]), "copy": nucleo._leer_txt_copy(txt) if txt.exists() else {},
            "tamano_mb": round(sum(f.stat().st_size for f in fotos) / 1048576, 1),
            "creado": datetime.fromtimestamp(sub.stat().st_mtime).isoformat(timespec="minutes"), "en_cola": _ya(fotos, en_cola)}


def archivos_permitidos():
    """Para que la pantalla pueda mostrar las portadas y los videos de Listos."""
    out = set()
    for prod in listos()["producciones"]:
        for p in prod["piezas"]:
            out.update(p["archivos"])
            if p["portada"]:
                out.add(p["portada"])
    return out


def _huecos(dia, horas, ocupadas):
    """Los próximos horarios libres, día por día, saltando los que ya tienen una pieza."""
    while True:
        for h in horas:
            f = dia.strftime("%Y-%m-%d") + "T" + h
            if f not in ocupadas:
                ocupadas.add(f)
                yield f
        dia += timedelta(days=1)


def _fechas(n, modo, desde, por_dia, tipos):
    """Fechas para las piezas. repartir: llena los horarios de cada día desde «desde». ahora: todas ya."""
    cfg = nucleo.config()
    if modo == "ahora":
        return [datetime.now().strftime("%Y-%m-%dT%H:%M")] * n
    horas = cfg["horarios_video"][:max(1, int(por_dia or len(cfg["horarios_video"])))]
    try:
        dia = datetime.strptime(desde, "%Y-%m-%d")
    except (TypeError, ValueError):
        dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ocupadas = {p.get("fecha") for p in nucleo.cola()["publicaciones"]}
    videos, carruseles = _huecos(dia, horas, ocupadas), _huecos(dia, [cfg["horario_carrusel"]], ocupadas)
    return [next(carruseles if t == "carrusel" else videos) for t in tipos]


def a_la_cola(rutas, redes, cuentas=None, modo="repartir", desde=None, por_dia=None, aprobar=False):
    """Pasa a la cola las piezas elegidas, con las redes y cuentas que marcaste. Devuelve lo que entró."""
    if not rutas:
        raise ValueError("Elige al menos un video")
    if not redes:
        raise ValueError("Elige al menos una red")
    todas = {p["ruta"]: p for prod in listos(forzar=True)["producciones"] for p in prod["piezas"]}
    elegidas = [todas[r] for r in rutas if r in todas and not todas[r]["en_cola"]]
    if not elegidas:
        raise ValueError("Esos videos ya están en la cola")
    fechas = _fechas(len(elegidas), modo, desde, por_dia, [p["tipo"] for p in elegidas])
    nuevas, trabadas = [], []
    with nucleo._candado:
        c = nucleo.cola()
        codigos = {p["codigo"] for p in c["publicaciones"]}
        for p, fecha in zip(elegidas, fechas):
            codigo = p["codigo"] if p["codigo"] not in codigos else f"{p['produccion'].split()[0]}-{p['codigo']}"
            codigos.add(codigo)
            pieza = {"codigo": codigo, "tipo": p["tipo"], "archivos": p["archivos"], "copy_borrador": p["copy"],
                     "portada": p["portada"]}
            pub = nucleo.nueva_publicacion(pieza, Path("/"))
            pub["archivos"] = p["archivos"]
            pub["portada"] = p["portada"]
            pub["produccion"] = p["produccion"]
            pub.pop("dia", None)
            pub.pop("_desde", None)
            pub["fecha"] = fecha
            for red, r in pub["redes"].items():
                r["activa"] = red in redes
                if (cuentas or {}).get(red):
                    r["cuenta"] = cuentas[red]
            if aprobar:
                pub["aprobado"] = True
                prohibidas = [a for a in nucleo.revisar_copy(pub) if "pide evitar" in a]
                if prohibidas:
                    pub["aprobado"] = False
                    trabadas.append(codigo)
            c["publicaciones"].append(pub)
            nuevas.append(pub)
        nucleo.guardar_cola(c)
    _memo["datos"] = None
    nucleo.anotar(f"Desde producción: {len(nuevas)} piezas a la cola para {', '.join(redes)} · {modo}"
                  + (f" · sin aprobar por palabras prohibidas: {trabadas}" if trabadas else ""))
    if modo == "ahora" and aprobar:
        import threading
        for pub in nuevas:
            if pub.get("aprobado"):
                for red in redes:
                    if red in pub["redes"]:
                        threading.Thread(target=nucleo.publicar, args=(pub["id"], red), daemon=True).start()
    return {"nuevas": len(nuevas), "trabadas": trabadas, "fechas": [n["fecha"] for n in nuevas]}
