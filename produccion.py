"""Conexión con producción: lo que la Sala de edición y la Sala de diseño dejan terminado en Drive.

Lo lee salas.py desde la carpeta del proyecto de Drive (la misma cuenta de las tres apps): los videos de V.FINALES
de cada producción y los posts y carruseles de DISEÑO/…/FINAL. En la pestaña Listos eliges la semana y el
proyecto, marcas cuáles, a qué redes y cuándo, y pasan juntos a la cola.
"""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import nucleo
import salas


def carpetas():
    """Las carpetas de la PC con la forma del proyecto de Drive (para los guiones y por si no hay conexión)."""
    return salas.espejos()


_memo = {"cuando": 0, "datos": None}


def listos(forzar=False):
    """Lo mismo que _leer, guardado 20 segundos: la pantalla pide portadas y videos muchas veces seguidas."""
    if forzar or not _memo["datos"] or time.time() - _memo["cuando"] > 20:
        _memo.update(cuando=time.time(), datos=_leer(forzar))
    return _memo["datos"]


def _leer(forzar=False):
    """{producciones: [{nombre, tipo, piezas}], semanas, drive} con lo terminado en las salas y si ya está en la cola."""
    en_cola = {}
    for p in nucleo.cola()["publicaciones"]:
        for a in p.get("archivos", []):
            en_cola[os.path.normcase(a)] = p
        for rel in p.get("drive") or []:
            en_cola["drive:" + rel] = p
    grupos = {}
    piezas = salas.piezas(forzar)
    for x in piezas:
        ruta = x["archivos"][0] if x["tipo"] == "video" else str(Path(x["archivos"][0]).parent)
        x.update(ruta=ruta, bajado=all(os.path.isfile(a) for a in x["archivos"]),
                 en_cola=_ya(x["archivos"], ["drive:" + r for r in x["drive"]], en_cola))
        nombre = "Sala de diseño" if x["proyecto"] == "DISEÑO" else x["proyecto"]
        grupos.setdefault(nombre, []).append(x)
    prods = []
    for nombre, ps in grupos.items():
        ps.sort(key=lambda x: (x.get("semana") or "", x.get("dia") or 99, x["codigo"]))
        prods.append({"nombre": nombre, "tipo": "diseno" if nombre == "Sala de diseño" else "edicion", "piezas": ps,
                      "reciente": max(x["creado"] for x in ps)})
    prods.sort(key=lambda p: p["reciente"], reverse=True)
    return {"producciones": prods, "semanas": salas.semanas(piezas), "drive": salas.estado(),
            "carpetas": [str(c) for c in carpetas()]}


def _ya(rutas, claves, en_cola):
    p = next((en_cola[k] for k in [*(os.path.normcase(str(r)) for r in rutas), *claves] if k in en_cola), None)
    return {"id": p["id"], "fecha": p.get("fecha"), "aprobado": p.get("aprobado")} if p else None


def pieza(ruta):
    return next((x for prod in listos()["producciones"] for x in prod["piezas"] if x["ruta"] == ruta), None)


def bajar(ruta):
    """Baja de Drive los archivos de una pieza de Listos (para verla antes de pasarla a la cola)."""
    x = pieza(ruta)
    if not x:
        raise ValueError("Esa pieza ya no está en Listos")
    salas.asegurar(x)
    x["bajado"] = True
    return x


def cuerpo_de(p):
    """El cuerpo del brief (C1, C2…) de un video de Listos: el que dejó la Sala o el que dice su nombre."""
    import re
    if re.fullmatch(r"C\d+", p.get("cuerpo") or ""):
        return p["cuerpo"]
    m = re.search(r"(?:^|[-_ ])(C\d+)(?=[-_ ]|$)", p.get("codigo") or "", re.I) if p.get("tipo") == "video" else None
    return m.group(1).upper() if m else None


def nueva_desde_listo(p, codigo=None):
    """Una pieza de Listos → publicación de la cola, con su semana, su cuerpo y de dónde se baja en Drive."""
    pub = nucleo.nueva_publicacion({"codigo": codigo or p["codigo"], "tipo": p["tipo"], "copy_borrador": p["copy"],
                                    "semana": p.get("semana"), "cuerpo": cuerpo_de(p), "nivel": p.get("nivel"),
                                    "publico": p.get("publico")}, Path("/"))
    pub.update(archivos=p["archivos"], portada=p["portada"], produccion=p["produccion"], proyecto=p.get("proyecto"),
               drive=p.get("drive") or [], cuerpo=cuerpo_de(p))
    pub.pop("dia", None)
    pub.pop("_desde", None)
    return pub


def bajar_en_fondo(pub):
    try:
        salas.asegurar(pub)
    except Exception as e:
        nucleo.anotar(f"Drive: no pude bajar {pub.get('codigo')} todavía ({e}); lo intento otra vez al publicar")


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
    import copys   # el copy lo escribe el publicador desde el guion; el .txt de la Sala queda de respaldo
    escritos = {p["ruta"]: copys.generar(p, nivel=p.get("nivel") or nucleo.datos_de_semana(p.get("semana"), cuerpo_de(p)).get("nivel"))
                for p in elegidas if p["tipo"] == "video"}
    nuevas, trabadas = [], []
    with nucleo._candado:
        c = nucleo.cola()
        codigos = {p["codigo"] for p in c["publicaciones"]}
        for p, fecha in zip(elegidas, fechas):
            codigo = p["codigo"] if p["codigo"] not in codigos else f"{p['proyecto'].split()[0]}-{p['codigo']}"
            codigos.add(codigo)
            pub = nueva_desde_listo(p, codigo)
            pub.pop("dia", None)
            pub.pop("_desde", None)
            pub["fecha"] = fecha
            if escritos.get(p["ruta"]):
                copys.aplicar(pub, escritos[p["ruta"]])
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
    import threading
    for pub in nuevas:   # los videos de Drive se van bajando ya, para que estén listos a su hora
        if pub.get("drive"):
            threading.Thread(target=bajar_en_fondo, args=(pub,), daemon=True).start()
    if modo == "ahora" and aprobar:
        for pub in nuevas:
            if pub.get("aprobado"):
                for red in redes:
                    if red in pub["redes"]:
                        threading.Thread(target=nucleo.publicar, args=(pub["id"], red), daemon=True).start()
    return {"nuevas": len(nuevas), "trabadas": trabadas, "fechas": [n["fecha"] for n in nuevas]}
