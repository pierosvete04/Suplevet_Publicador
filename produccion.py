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
    juntar(piezas)
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


def juntar(piezas):
    """Qué post va con qué video. Seguro: el post se hizo a partir de ese video en la Sala de diseño («video» en
    pieza.json). Si no, el post dice qué cuerpos acompaña («acompaña»: C1…) y van los videos de ese cuerpo en su semana."""
    videos = [x for x in piezas if x["tipo"] == "video"]
    por_rel = {v["rel"]: v for v in videos}
    for v in videos:
        v["posts"] = []
    for x in piezas:
        if x["tipo"] == "video":
            continue
        con, como = [], ""
        if x.get("video") in por_rel:
            con, como = [por_rel[x["video"]]], "hecho con este video"
        elif x.get("acompana"):
            cuerpos = {str(c).upper() for c in x["acompana"]}
            con = [v for v in videos if v.get("semana") == x.get("semana") and cuerpo_de(v) in cuerpos]
            como = "mismo cuerpo y semana"
        x["va_con"] = [{"codigo": v["codigo"], "rel": v["rel"], "proyecto": v["proyecto"]} for v in con]
        x["va_con_como"] = como if con else ""
        for v in con:
            v["posts"].append({"codigo": x["codigo"], "titulo": x.get("titulo"), "rel": x["rel"], "como": como})


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
    """El cuerpo del brief (C1, C2…) de un video de Listos: el que dejó la Sala o el que dice su nombre (C1 o P2H1)."""
    import re
    if re.fullmatch(r"C\d+", p.get("cuerpo") or ""):
        return p["cuerpo"]
    return nucleo.partes_codigo(p.get("codigo"))[0] if p.get("tipo") == "video" else None


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
    """Los próximos horarios libres, día por día, saltando los que ya tienen una pieza y los que ya pasaron."""
    ahora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    while True:
        for h in horas:
            f = dia.strftime("%Y-%m-%d") + "T" + h
            if f not in ocupadas and f > ahora:
                ocupadas.add(f)
                yield f
        dia += timedelta(days=1)


def _fechas(n, modo, desde, por_dia, tipos):
    """Fechas para las piezas. repartir: llena los horarios de cada día desde «desde». ahora: todas ya."""
    cfg = nucleo.config()
    if modo == "ahora":
        return [datetime.now().strftime("%Y-%m-%dT%H:%M")] * n
    horas = cfg["horarios_video"][:max(1, int(por_dia or len(cfg["horarios_video"])))]
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        dia = datetime.strptime(desde, "%Y-%m-%d")
    except (TypeError, ValueError):
        dia = hoy + timedelta(days=1)
    if dia < hoy:
        raise ValueError("«Desde» es un día que ya pasó: elige hoy o un día que viene")
    ocupadas = {p.get("fecha") for p in nucleo.cola()["publicaciones"]}
    videos, carruseles = _huecos(dia, horas, ocupadas), _huecos(dia, [cfg["horario_carrusel"]], ocupadas)
    return [next(carruseles if t == "carrusel" else videos) for t in tipos]


def _principales(redes_):
    """{red: id} de la cuenta principal de cada red (o la primera conectada), para dejarla fija en la pieza."""
    import redes as conectores
    cfg, con, out = nucleo.config(), conectores.estado_conexiones(), {}
    for red in redes_:
        ids = [c["id"] for c in (con.get(red) or {}).get("cuentas") or []]
        out[red] = cfg.get(f"{red}_cuenta") if cfg.get(f"{red}_cuenta") in ids else (ids[0] if ids else None)
    return out


def _en_cola_por_cuenta():
    """{(red, cuenta, video)} de lo que ya está en la cola (sin cuenta elegida = la cuenta por defecto de esa red)."""
    cfg, out = nucleo.config(), set()
    for p in nucleo.cola()["publicaciones"]:
        for red, r in p["redes"].items():
            if r.get("activa") and r.get("estado") != "error":
                for a in [*p.get("archivos", [])[:1], *(f"drive:{x}" for x in (p.get("drive") or [])[:1])]:
                    out.add((red, r.get("cuenta") or cfg.get(f"{red}_cuenta"), os.path.normcase(a)))
    return out


def a_la_cola(rutas, redes, cuentas=None, modo="repartir", desde=None, por_dia=None, aprobar=False):
    """Pasa a la cola las piezas elegidas, con las redes y cuentas que marcaste. Devuelve lo que entró.
    cuentas: {red: id} o {red: [id, id…]}. Con varias cuentas en una red, el mismo video va a cada una en su propia
    publicación, corrida «entre_cuentas» días (lo mismo que en Hoy) y unos minutos, y con otra variante del copy."""
    if not rutas:
        raise ValueError("Elige al menos un video")
    if not redes:
        raise ValueError("Elige al menos una red")
    cfg = nucleo.config()
    por_red = {red: [x for x in ((cuentas or {}).get(red) if isinstance((cuentas or {}).get(red), list)
                                 else [(cuentas or {}).get(red)]) if x] or [None] for red in redes}
    rondas = max(len(v) for v in por_red.values())
    entre = max(0, int(cfg["sugeridor"].get("entre_cuentas", 1) or 0))
    todas = {p["ruta"]: p for prod in listos(forzar=True)["producciones"] for p in prod["piezas"]}
    elegidas = [todas[r] for r in rutas if r in todas]
    if not elegidas:
        raise ValueError("Esos videos ya no están en Subir contenido")
    fechas = _fechas(len(elegidas), modo, desde, por_dia, [p["tipo"] for p in elegidas])
    principal = _principales(redes)
    import copys   # el copy lo escribe el publicador desde el guion; el .txt de la Sala queda de respaldo
    escritos = {(p["ruta"], j): copys.generar(p, j, nivel=p.get("nivel") or nucleo.datos_de_semana(p.get("semana"), cuerpo_de(p)).get("nivel"))
                for p in elegidas if p["tipo"] == "video" for j in range(rondas)}
    nuevas, trabadas, repetidas = [], [], 0
    with nucleo._candado:
        c = nucleo.cola()
        ya = _en_cola_por_cuenta()
        # el mismo nombre en dos producciones distintas («C1 H1» de P03 y de P05) lleva delante el proyecto;
        # el mismo video en otra cuenta conserva su nombre
        codigos = {x["codigo"]: os.path.normcase((x.get("archivos") or [""])[0]) for x in c["publicaciones"]}
        for (p, fecha), j in ((x, j) for x in zip(elegidas, fechas) for j in range(rondas)):
            # la vuelta j lleva la cuenta j de cada red (las redes con una sola cuenta van solo en la primera);
            # una cuenta que ya tiene este video en la cola no lo vuelve a recibir
            posibles = nucleo.REDES_VIDEO if p["tipo"] == "video" else nucleo.REDES_CARRUSEL
            llevar = {red: cs[j] for red, cs in por_red.items() if j < len(cs) and red in posibles
                      and (red, cs[j] or cfg.get(f"{red}_cuenta"), os.path.normcase(p["archivos"][0])) not in ya}
            repetidas += sum(1 for red, cs in por_red.items() if j < len(cs) and red in posibles and red not in llevar)
            if not llevar:
                continue
            codigo = p["codigo"]
            pre = p["proyecto"].split()[0] if p.get("proyecto") else ""
            if pre and not codigo.startswith(pre + "-") and codigos.get(codigo, os.path.normcase(p["archivos"][0])) != os.path.normcase(p["archivos"][0]):
                codigo = f"{pre}-{codigo}"
            codigos[codigo] = os.path.normcase(p["archivos"][0])
            pub = nueva_desde_listo(p, codigo)
            pub["fecha"] = fecha
            if j and modo != "ahora":   # la otra cuenta: «entre_cuentas» días después y unos minutos corrida
                f = datetime.strptime(fecha, "%Y-%m-%dT%H:%M") + timedelta(days=entre * j, minutes=10 * j)
                pub["fecha"] = f.strftime("%Y-%m-%dT%H:%M")
            if escritos.get((p["ruta"], j)):
                copys.aplicar(pub, escritos[(p["ruta"], j)])
                pub["copy_variante"] = j
            for red, r in pub["redes"].items():
                r["activa"] = red in llevar
                if red in llevar:
                    r["cuenta"] = llevar[red] or principal.get(red)
            if aprobar:   # la misma revisión que al aprobar en la Cola; lo que no pasa queda por revisar
                pub["aprobado"] = not nucleo.faltas(pub)
                if not pub["aprobado"]:
                    trabadas.append(codigo)
            c["publicaciones"].append(pub)
            nuevas.append(pub)
        if not nuevas:
            raise ValueError("Esos videos ya están en la cola para esas cuentas")
        nucleo.guardar_cola(c)
    _memo["datos"] = None
    nucleo.anotar(f"Desde producción: {len(nuevas)} piezas a la cola para {', '.join(redes)} · {modo}"
                  + (f" · {repetidas} ya estaban en esa cuenta" if repetidas else "")
                  + (f" · sin aprobar por palabras prohibidas: {trabadas}" if trabadas else ""))
    import threading
    for pub in nuevas:   # los videos de Drive se van bajando ya, para que estén listos a su hora
        if pub.get("drive"):
            threading.Thread(target=bajar_en_fondo, args=(pub,), daemon=True).start()
    if modo == "ahora" and aprobar:
        for pub in nuevas:
            if pub.get("aprobado"):
                for red, r in pub["redes"].items():
                    if r.get("activa"):
                        threading.Thread(target=nucleo.publicar, args=(pub["id"], red), daemon=True).start()
    return {"nuevas": len(nuevas), "trabadas": trabadas, "repetidas": repetidas, "fechas": [n["fecha"] for n in nuevas]}
