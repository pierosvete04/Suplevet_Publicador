"""Sugeridor: qué subir cada día a cada cuenta, mirando lo que está listo en producción y lo que ya salió.

Cada cuenta es un destino (Instagram, Facebook, cada cuenta de TikTok y cada canal de YouTube) y recibe hasta
«por_dia» videos. Reglas:
- En una cuenta, nunca el mismo video dos veces.
- En una cuenta y un mismo día, nunca dos videos del mismo cuerpo (el mismo cuerpo con otro hook no cuenta como otro).
- Mezcla: primero el cuerpo que esa cuenta tiene más olvidado, después lo que no salió en ninguna parte, y trata de no
  poner el mismo video el mismo día en dos cuentas de la misma red.
Si no alcanzan los videos, no repite: dice cuántos faltan.
"""
import os
import threading
import re
from datetime import datetime, timedelta

import copys
import nucleo
import produccion
import redes

ARCHIVO = nucleo.PUBLICACION / "sugeridor.json"   # videos que ya salieron por fuera del publicador
NOMBRES = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube"}


def ajustes():
    return nucleo.config()["sugeridor"]


def _norm(ruta):
    return os.path.normcase(str(ruta))


# ---------- Cuerpo y hook de cada video ----------

def cuerpo_de(codigo, prod=""):
    """S03-C1-H2-CTA1 o P2H1 → «prod · C1». Sin cuerpo en el nombre («SUPLEVET H3 1012» o «COMPONENTES (NUEVO)»),
    el cuerpo es el nombre sin el hook ni lo que va entre paréntesis: así las versiones de un mismo video van juntas."""
    codigo = codigo or ""
    base = nucleo.partes_codigo(codigo)[0]
    if not base:
        base = re.sub(r"\(.*?\)", " ", codigo)
        base = re.sub(r"(?:^|(?<=[-_ ]))H\d+(?=[-_ ]|$)", " ", base, flags=re.I)
        base = re.sub(r"[-_ ]+", " ", base).strip(" -").upper()
    return f"{prod} · {base}" if prod else base


def hook_de(codigo):
    return nucleo.partes_codigo(codigo)[1]


# ---------- Destinos (una fila por cuenta) ----------

def destinos():
    con = redes.estado_conexiones()
    apagados = set(ajustes().get("apagados") or [])
    out = []
    for red in nucleo.REDES_VIDEO:
        cs = con[red].get("cuentas") or []
        filas = [(f"{red}:{c['id']}", c["id"], c["nombre"]) for c in cs] or [(red, None, NOMBRES[red])]
        for clave, cuenta, nombre in filas:
            out.append({"clave": clave, "red": red, "cuenta": cuenta, "nombre": nombre, "listo": con[red]["listo"],
                        "activo": clave not in apagados})
    return out


def _defectos(dests):
    """La cuenta que usa una pieza sin cuenta elegida: la de por defecto (o la primera)."""
    cfg, out = nucleo.config(), {}
    for red in nucleo.REDES_VIDEO:
        ids = [d["cuenta"] for d in dests if d["red"] == red and d["cuenta"]]
        out[red] = cfg.get(f"{red}_cuenta") if cfg.get(f"{red}_cuenta") in ids else (ids[0] if ids else None)
    return out


def _clave(red, r, defectos):
    if red not in defectos:
        return red
    cuenta = r.get("cuenta") or defectos[red]
    return f"{red}:{cuenta}" if cuenta else red


# ---------- Lo que ya salió o ya está en la cola ----------

def _manuales():
    """Videos marcados como subidos a mano en todas las cuentas (lo viejo, sin cuenta)."""
    return set(nucleo.leer_json(ARCHIVO, {}).get("ya_salieron") or [])


def _manuales_por_cuenta():
    """{clave de la cuenta: {rutas}} de los videos marcados como subidos a mano solo en esa cuenta."""
    return {k: set(v or []) for k, v in (nucleo.leer_json(ARCHIVO, {}).get("por_cuenta") or {}).items()}


def ya_salio(ruta, si=True, clave=None):
    """Marca un video como subido por fuera del publicador: no se vuelve a sugerir en esa cuenta (o en ninguna, sin cuenta)."""
    with nucleo._candado:
        d = nucleo.leer_json(ARCHIVO, {})
        if clave:
            pc = d.setdefault("por_cuenta", {})
            ya = set(pc.get(clave) or [])
            (ya.add if si else ya.discard)(_norm(ruta))
            pc[clave] = sorted(ya)
        else:
            ya = set(d.get("ya_salieron") or [])
            (ya.add if si else ya.discard)(_norm(ruta))
            d["ya_salieron"] = sorted(ya)
        nucleo.escribir_json(ARCHIVO, d)
    return {"ok": True}


def _usos(inventario, dests):
    """[{clave, ruta, cuerpo, fecha}] de cada video que ya está en la cola (salido o por salir), por cuenta."""
    defectos, out = _defectos(dests), []
    for p in nucleo.cola()["publicaciones"]:
        if p.get("tipo") != "video" or not p.get("archivos"):
            continue
        ruta = _norm(p["archivos"][0])
        cuerpo = (inventario[ruta]["cuerpo"] if ruta in inventario
                  else cuerpo_de(p.get("codigo"), p.get("produccion", "")))
        for red, r in p["redes"].items():
            if r.get("activa"):
                out.append({"clave": _clave(red, r, defectos), "ruta": ruta, "cuerpo": cuerpo, "fecha": p.get("fecha") or "",
                            "id": p.get("id"), "codigo": p.get("codigo"), "estado": r.get("estado") or "pendiente"})
    return out


def _en_cola(u, inv):
    """Lo que ya está en la cola ese día en esa cuenta, con su imagen: la ficha se ve igual que las sugeridas."""
    v = inv.get(u["ruta"]) or {}
    return {"fecha": u["fecha"], "hora": u["fecha"][11:16], "id": u.get("id"), "estado": u.get("estado"),
            "codigo": v.get("codigo") or u.get("codigo") or os.path.basename(u["ruta"]),
            "portada": v.get("portada"), "mini": v.get("mini"), "bajado": v.get("bajado"), "archivos": v.get("archivos") or []}


def _carruseles_usados(dests):
    defectos, out = _defectos(dests), []
    for p in nucleo.cola()["publicaciones"]:
        if p.get("tipo") == "carrusel" and p.get("archivos"):
            for red, r in p["redes"].items():
                if r.get("activa"):
                    out.append({"clave": _clave(red, r, defectos), "ruta": _norm(p["archivos"][0]), "fecha": p.get("fecha") or ""})
    return out


# ---------- Horarios ----------

def _minutos(hhmm):
    """«08:30» → 510. Si no es una hora, ValueError."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(hhmm or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError
    return int(m.group(1)) * 60 + int(m.group(2))


def hora_valida(h, nombre):
    """«8:0», «08:00» → «08:00»; si no es una hora, ValueError en palabras simples."""
    try:
        m = _minutos(h)
    except ValueError:
        raise ValueError(f"«{h}» no es una hora válida en «{nombre}»: escríbela como 08:30") from None
    return f"{m // 60:02d}:{m % 60:02d}"


def validar_ajustes(a):
    """Revisa los ajustes de Hoy antes de guardarlos. Devuelve los ajustes limpios o ValueError en palabras simples."""
    a = dict(a or {})
    for k, nombre in (("desde", "Hora del primer video"), ("hasta", "Hora del último video")):
        if k in a:
            try:
                m = _minutos(a[k])
            except ValueError:
                raise ValueError(f"Falta la hora de «{nombre}» (o no es una hora válida)") from None
            a[k] = f"{m // 60:02d}:{m % 60:02d}"
    actual = ajustes()
    if _minutos(a.get("desde", actual["desde"])) >= _minutos(a.get("hasta", actual["hasta"])):
        raise ValueError("La hora del primer video tiene que ser antes que la del último")
    for k, nombre, lo, hi in (("por_dia", "Videos por cuenta al día", 1, 30), ("aire_cuerpo", "Días antes de repetir un cuerpo", 0, 30),
                              ("entre_cuentas", "Días entre cuentas para el mismo video", 0, 14)):
        if k in a:
            try:
                a[k] = int(a[k])
            except (TypeError, ValueError):
                raise ValueError(f"«{nombre}» tiene que ser un número") from None
            if not lo <= a[k] <= hi:
                raise ValueError(f"«{nombre}» va de {lo} a {hi}")
    return a


def _rango():
    a = ajustes()
    try:
        h0, h1 = _minutos(a["desde"]), _minutos(a["hasta"])
    except (KeyError, ValueError):
        h0, h1 = 8 * 60, 22 * 60          # ajustes rotos: el horario de siempre
    if h1 <= h0:                          # al revés: se usan dándoles la vuelta
        h0, h1 = h1, h0
    if h1 == h0:
        h1 = min(h0 + 60, 23 * 60 + 55)
    return h0, h1


def horas(n, cuenta=0, cuentas=1):
    """n horarios repartidos parejo entre «desde» y «hasta» (de 5 en 5 minutos). Con varias cuentas, cada una corre
    un poco sus horas (la 2.ª unos minutos después de la 1.ª…): así no salen todas al mismo minuto ni se suben juntas."""
    h0, h1 = _rango()
    k = max(1, cuentas)
    # el paso entre videos de una cuenta y el corrimiento entre cuentas, para que la última termine justo en «hasta»
    # y ninguna cuenta caiga en la hora de otra: (n-1) pasos + (k-1)/k de paso = todo el rango
    paso = (h1 - h0) / ((n - 1) + (k - 1) / k) if n > 1 or k > 1 else 60
    off = min(cuenta, k - 1) * paso / k
    return [f"{m // 60:02d}:{m % 60:02d}" for m in (int(round((h0 + off + i * paso) / 5) * 5) for i in range(n))]


# ---------- El plan ----------

def _inventario(forzar=False):
    vids, carrs = {}, {}
    for prod in produccion.listos(forzar=forzar)["producciones"]:
        for p in prod["piezas"]:
            x = {**p, "cuerpo": cuerpo_de(p["codigo"], p["produccion"]), "hook": hook_de(p["codigo"])}
            (vids if p["tipo"] == "video" else carrs)[_norm(p["ruta"] if p["tipo"] == "carrusel" else p["archivos"][0])] = x
    return vids, carrs


def _reciente(x):
    """Para ordenar de lo más nuevo a lo más viejo."""
    try:
        return -datetime.fromisoformat(x["creado"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return 0


def _dias_entre(a, b):
    return (datetime.strptime(a[:10], "%Y-%m-%d") - datetime.strptime(b[:10], "%Y-%m-%d")).days


def planear(desde=None, dias=1, excluir=(), forzar=False):
    """Plan de «dias» días desde «desde» (hoy si no se dice). Lo que se sugiere un día cuenta como usado el siguiente."""
    a = ajustes()
    por_dia, aire = max(1, int(a["por_dia"])), max(0, int(a["aire_cuerpo"]))
    entre = max(0, int(a.get("entre_cuentas", 1) or 0))
    hoy = datetime.now().strftime("%Y-%m-%d")
    dia0 = desde or hoy
    try:
        datetime.strptime(dia0, "%Y-%m-%d")
    except ValueError:
        raise ValueError("La fecha «Desde» no es válida") from None
    if dia0 < hoy:
        raise ValueError("«Desde» no puede ser un día que ya pasó: elige hoy o un día que viene")
    todos = destinos()
    dests = [d for d in todos if d["activo"]]
    inv, carrs = _inventario(forzar)
    # «cuenta>ruta» quita un video o carrusel solo de esa cuenta («Cambiar»); una ruta sola, de todas
    excl_cuenta = {}
    for e in excluir:
        if ">" in e:
            c, r = e.split(">", 1)
            excl_cuenta.setdefault(c, set()).add(_norm(r))
    excluir = {_norm(e) for e in excluir if ">" not in e}
    manuales = _manuales()
    por_cuenta = _manuales_por_cuenta()
    a_mano = manuales.union(*por_cuenta.values())        # subidos a mano en alguna cuenta
    usos = _usos(inv, todos)
    salidos = {u["ruta"] for u in usos} | a_mano
    usos_carr = _carruseles_usados(todos)
    nombres = {d["clave"]: f"{NOMBRES[d['red']]} · {d['nombre']}" for d in todos}
    orden = [d["clave"] for d in todos]      # la variante del copy de cada cuenta (la misma que usa aceptar)
    hs = horas(por_dia)
    salida = []
    for n in range(max(1, min(int(dias), 14))):
        dia = (datetime.strptime(dia0, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")
        ahora = datetime.now().strftime("%H:%M") if dia == hoy else "00:00"
        en_algun_lado = {u["ruta"] for u in usos} | a_mano
        antes = set(en_algun_lado)                  # lo que ya pasó por Antena antes de armar este día
        veces = {}
        for u in usos:
            veces[u["ruta"]] = veces.get(u["ruta"], 0) + 1
        hoy_red = {}       # red → videos de ese día en cualquier cuenta de esa red
        hoy_cuerpo = {}    # cuerpo → cuántas cuentas lo tienen ese día
        en_red = {}        # (red, video) → [(cuenta, fecha)] para esperar «entre» días entre cuentas de la misma red
        for u in usos:
            en_red.setdefault((u["clave"].split(":")[0], u["ruta"]), []).append((u["clave"], u["fecha"]))

        def espera(r, d, dia=dia, en_red=en_red):
            """El video ya sale en otra cuenta de esta red a menos de «entre» días de este (antes o después)."""
            return bool(entre) and any(c != d["clave"] and f and abs(_dias_entre(dia, f)) < entre
                                       for c, f in en_red.get((d["red"], r), ()))
        plan = {}
        for i, d in enumerate(dests):
            mios = [u for u in usos if u["clave"] == d["clave"]]
            del_dia = [u for u in mios if u["fecha"][:10] == dia]
            for u in del_dia:
                hoy_red.setdefault(d["red"], set()).add(u["ruta"])
                hoy_cuerpo[u["cuerpo"]] = hoy_cuerpo.get(u["cuerpo"], 0) + 1
            ultimo = {}
            for u in mios:
                if u["fecha"][:10] < dia:
                    ultimo[u["cuerpo"]] = max(ultimo.get(u["cuerpo"], ""), u["fecha"])
            ocupadas = {u["fecha"][11:16] for u in del_dia}
            plan[d["clave"]] = {**d, "ya": [_en_cola(u, inv) for u in sorted(del_dia, key=lambda u: u["fecha"])],
                                "piezas": [], "faltan": 0,
                                "_usadas": ({u["ruta"] for u in mios} | manuales | por_cuenta.get(d["clave"], set()) | excluir
                                           | excl_cuenta.get(d["clave"], set())),
                                "_cuerpos": {u["cuerpo"] for u in del_dia}, "_ultimo": ultimo,
                                "_horas": [h for h in horas(por_dia, i, len(dests))
                                           if h > ahora and all(abs(_minutos(h) - _minutos(o)) >= 30 for o in ocupadas if o)],
                                "_cupo": max(0, por_dia - len(del_dia))}
            pl = plan[d["clave"]]
            # hoy ya pasaron algunas horas: el cupo de hoy es lo que cabe en los horarios que quedan
            pl["por_hora"] = len(pl["_horas"]) < pl["_cupo"]
            pl["_cupo"] = min(pl["_cupo"], len(pl["_horas"]))
            pl["cupo"] = len(del_dia) + pl["_cupo"]          # videos que puede tener esta cuenta ese día
            pl["horas_libres"] = len(pl["_horas"])
        def armar(v, d, pl, dia=dia, antes=antes):
            """La ficha de un video para una cuenta: código, por qué se sugiere y la primera línea del copy."""
            r = _norm(v["archivos"][0])
            hace = _dias_entre(dia, pl["_ultimo"][v["cuerpo"]]) if v["cuerpo"] in pl["_ultimo"] else None
            otras = [u for u in usos if u["ruta"] == r and u["clave"] != d["clave"]]
            en_cola = sorted({nombres[u["clave"]] for u in otras if not u.get("plan")})
            en_plan = sorted({nombres[u["clave"]] for u in otras if u.get("plan")} - set(en_cola))
            nuevo = r not in antes and not en_plan
            if nuevo:
                motivo = "Nuevo en Antena: no está en la cola de ninguna cuenta"
            elif r in a_mano and not en_cola and not en_plan:
                motivo = "Publicado a mano en otra cuenta, aquí todavía no"
            else:
                motivo = " · ".join(x for x in ((f"En la cola de {', '.join(en_cola)}" if en_cola else ""),
                                                 (f"También va a {', '.join(en_plan)}" if en_plan else ""),
                                                 ("publicado a mano en otra cuenta" if r in a_mano else "")) if x) + " · aquí todavía no"
            if hace is not None and hace <= aire:
                motivo += f" · Ojo: este cuerpo se publicó aquí hace {hace} día{'s' if hace != 1 else ''}"
            return {"hora": "", "fecha": "", "ruta": v["ruta"], "codigo": v["codigo"],
                    "cuerpo": v["cuerpo"], "hook": v["hook"], "produccion": v["produccion"],
                    "portada": v["portada"], "mini": v.get("mini"), "bajado": v.get("bajado"),
                    "archivos": v["archivos"], "motivo": motivo,
                    "pronto": hace is not None and hace <= aire, "nuevo": nuevo,
                    "gancho": (copys.generar(v, orden.index(d["clave"]) + int(dia[8:10]), transcribir=False)
                               .get("instagram") or "").split("\n")[0]}

        # por rondas: una pieza por cuenta en cada vuelta, así ninguna se lleva todo lo nuevo
        for _ in range(por_dia):
            for d in dests:
                pl = plan[d["clave"]]
                if len(pl["piezas"]) >= pl["_cupo"]:
                    continue
                cands = [v for r, v in inv.items() if r not in pl["_usadas"] and v["cuerpo"] not in pl["_cuerpos"]
                         and not espera(r, d)]
                if not cands:
                    continue

                def puntaje(v, pl=pl, d=d):
                    r = _norm(v["archivos"][0])
                    hace = _dias_entre(dia, pl["_ultimo"][v["cuerpo"]]) if v["cuerpo"] in pl["_ultimo"] else 999
                    return (max(0, aire - hace + 1) if hace <= aire else 0,       # su cuerpo salió hace poco en esta cuenta
                            0 if r not in en_algun_lado else 1,                    # nuevo de verdad
                            1 if r in hoy_red.get(d["red"], ()) else 0,            # ya va hoy en otra cuenta de esta red
                            hoy_cuerpo.get(v["cuerpo"], 0),                        # su cuerpo ya va hoy en otras cuentas
                            veces.get(r, 0), -hace, _reciente(v))                 # lo más nuevo primero
                v = min(cands, key=puntaje)
                r = _norm(v["archivos"][0])
                pieza = {"_v": v, "_uso": {"clave": d["clave"], "ruta": r, "cuerpo": v["cuerpo"], "fecha": f"{dia}T00:00", "plan": True}}
                pl["piezas"].append(pieza)
                pl["_usadas"].add(r)
                pl["_cuerpos"].add(v["cuerpo"])
                en_algun_lado.add(r)
                veces[r] = veces.get(r, 0) + 1
                hoy_red.setdefault(d["red"], set()).add(r)
                hoy_cuerpo[v["cuerpo"]] = hoy_cuerpo.get(v["cuerpo"], 0) + 1
                en_red.setdefault((d["red"], r), []).append((d["clave"], f"{dia}T00:00"))
                usos.append(pieza["_uso"])
        for d in dests:
            pl = plan[d["clave"]]
            pl["piezas"] = [{**armar(x["_v"], d, pl), "_uso": x["_uso"]} for x in pl["piezas"]]
        # horas: repartidas parejo en el día aunque haya pocos videos (no todos en la mañana)
        for d in dests:
            pl = plan[d["clave"]]
            k, libres = len(pl["piezas"]), pl["_horas"]
            idx = [0] if k == 1 else [round(i * (len(libres) - 1) / (k - 1)) for i in range(k)]
            for pieza, i in zip(pl["piezas"], idx):
                pieza["hora"] = libres[i]
                pieza["fecha"] = pieza["_uso"]["fecha"] = f"{dia}T{libres[i]}"
                del pieza["_uso"]
        # un carrusel al día en Instagram y Facebook, si hay
        hc = nucleo.config()["horario_carrusel"]
        for d in dests:
            pl = plan[d["clave"]]
            pl["carrusel"] = None
            if d["red"] not in nucleo.REDES_CARRUSEL or (dia == hoy and hc <= ahora):
                continue
            mios = [u for u in usos_carr if u["clave"] == d["clave"]]
            if any(u["fecha"][:10] == dia for u in mios):
                continue
            libres = [c for r, c in carrs.items() if r not in {u["ruta"] for u in mios} and r not in excluir
                      and r not in excl_cuenta.get(d["clave"], ())]
            if libres:
                fuera = {u["ruta"] for u in usos_carr}
                c = min(libres, key=lambda c: (_norm(c["ruta"]) in fuera, _reciente(c)))
                pl["carrusel"] = {"hora": hc, "fecha": f"{dia}T{hc}", "ruta": c["ruta"], "codigo": c["codigo"], "portada": c["portada"],
                                  "archivos": c["archivos"], "tipo": "carrusel"}
                usos_carr.append({"clave": d["clave"], "ruta": _norm(c["ruta"]), "fecha": f"{dia}T{hc}"})
        lista = []
        for d in dests:
            pl = plan[d["clave"]]
            pl["faltan"] = max(0, pl["_cupo"] - len(pl["piezas"]))
            sin_usar = [v for r, v in inv.items() if r not in pl["_usadas"]]
            otro_cuerpo = [v for v in sin_usar if v["cuerpo"] not in pl["_cuerpos"]]
            # por qué faltan: no quedan videos sin subir a esta cuenta, los que quedan son de cuerpos que ya van ese día,
            # o esos videos salen hace poco en otra cuenta de esta red
            pl["por_que_faltan"] = ("" if not pl["faltan"] else "videos" if not sin_usar else "cuerpos" if not otro_cuerpo
                                    else "cuentas")
            pl["entre_cuentas"] = entre
            # otros videos que pueden ir en esta cuenta ese día, para «Cambiar por otro» sin tocar las demás cuentas
            libres = sorted((v for v in otro_cuerpo if not espera(_norm(v["archivos"][0]), d)),
                            key=lambda v: (_norm(v["archivos"][0]) in en_algun_lado, _reciente(v)))
            pl["reserva"] = [armar(v, d, pl) for v in libres[:6]]
            lista.append({k: v for k, v in pl.items() if not k.startswith("_")})
        salida.append({"dia": dia, "destinos": lista, "sugeridos": sum(len(x["piezas"]) for x in lista),
                       "faltan": sum(x["faltan"] for x in lista)})
    cuerpos = {v["cuerpo"] for v in inv.values()}
    avisos = []
    if len(cuerpos) < por_dia:
        faltan = por_dia - len(cuerpos)
        avisos.append(f"Hay {len(cuerpos)} cuerpo{'s' if len(cuerpos) != 1 else ''} y pides {por_dia} videos al día por cuenta: "
                      f"pide {faltan} cuerpo{'s' if faltan != 1 else ''} más a producción para no repetir cuerpo en el día.")
    if any(x["faltan"] for x in salida[0]["destinos"]):
        avisos.append("Algunas cuentas no llegan a su cupo: el motivo sale al pie de cada una.")
    if any(x.get("por_hora") for x in salida[0]["destinos"]) and salida[0]["dia"] == hoy:
        avisos.append("Hoy ya pasaron algunos horarios: van menos videos que otros días.")
    return {"dias": salida, "por_dia": por_dia, "horas": hs, "destinos": todos, "ajustes": a,
            "inventario": {"videos": len(inv), "cuerpos": len(cuerpos), "carruseles": len(carrs),
                           "sin_salir": sum(1 for r in inv if r not in salidos),
                           "ya_salieron_a_mano": len(a_mano)},
            "avisos": avisos}


def aceptar(items, aprobar=False):
    """Pasa a la cola lo sugerido: items [{ruta, clave, fecha}]. Una publicación por video y cuenta."""
    if not items:
        raise ValueError("No hay nada elegido")
    dests = {d["clave"]: d for d in destinos()}
    inv, carrs = _inventario()
    por_ruta = {**{_norm(v["archivos"][0]): v for v in inv.values()}, **{_norm(c["ruta"]): c for c in carrs.values()},
                **{_norm(v["ruta"]): v for v in inv.values()}}
    # el copy se escribe antes de tomar la cola (transcribir un video sin guion tarda): una variante por cuenta
    orden = list(dests)
    copies = {}
    for it in items:
        p = por_ruta.get(_norm(it.get("ruta")))
        if p and it.get("clave") in dests and p["tipo"] == "video":
            v = orden.index(it["clave"]) + int((it.get("fecha") or "0000-00-00")[8:10])
            nivel = p.get("nivel") or nucleo.datos_de_semana(p.get("semana"), produccion.cuerpo_de(p)).get("nivel")
            copies[(it["clave"], _norm(it["ruta"]))] = {**copys.generar(p, v, nivel=nivel), "variante": v}
    nuevas, trabadas, saltadas = [], [], 0
    with nucleo._candado:
        c = nucleo.cola()
        ya = {(u["clave"], u["ruta"]) for u in _usos(inv, list(dests.values())) + _carruseles_usados(list(dests.values()))}
        for it in items:
            p, d = por_ruta.get(_norm(it.get("ruta"))), dests.get(it.get("clave"))
            if not p or not d or not it.get("fecha"):
                saltadas += 1
                continue
            llave = _norm(p["ruta"] if p["tipo"] == "carrusel" else p["archivos"][0])
            if (d["clave"], llave) in ya:
                saltadas += 1
                continue
            ya.add((d["clave"], llave))
            pub = produccion.nueva_desde_listo(p)   # con su semana (brief) y de dónde se baja en Drive
            pub.update(fecha=it["fecha"], sugerido=True, **({"cuerpo": p["cuerpo"]} if p.get("cuerpo") else {}))
            cp = copies.get((d["clave"], _norm(it["ruta"])))
            if cp and cp.get("fuente"):
                copys.aplicar(pub, cp)
                pub["copy_variante"] = cp["variante"]   # «Escribir otro copy» sigue desde aquí, no repite el de otra cuenta
            for red, r in pub["redes"].items():
                r["activa"] = red == d["red"]
                if red == d["red"] and d["cuenta"]:
                    r["cuenta"] = d["cuenta"]
            if aprobar:
                pub["aprobado"] = not [x for x in nucleo.revisar_copy(pub) if "pide evitar" in x]
                if not pub["aprobado"]:
                    trabadas.append(p["codigo"])
            c["publicaciones"].append(pub)
            nuevas.append(pub)
        nucleo.guardar_cola(c)
    produccion._memo["datos"] = None
    for pub in nuevas:   # los videos de Drive se van bajando ya, para que estén listos a su hora
        if pub.get("drive"):
            threading.Thread(target=produccion.bajar_en_fondo, args=(pub,), daemon=True).start()
    nucleo.anotar(f"Sugerencias aceptadas: {len(nuevas)} piezas a la cola" + (f" · {saltadas} ya estaban" if saltadas else "")
                  + (f" · sin aprobar por palabras prohibidas: {trabadas}" if trabadas else ""))
    return {"nuevas": len(nuevas), "saltadas": saltadas, "trabadas": trabadas}
