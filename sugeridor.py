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
    """S03-C1-H2-CTA1 → «prod · C1». Sin C<n> (nombres a mano como «SUPLEVET H3 1012» o «COMPONENTES (NUEVO)»),
    el cuerpo es el nombre sin el hook ni lo que va entre paréntesis: así las versiones de un mismo video van juntas."""
    codigo = codigo or ""
    m = re.search(r"(?:^|[-_ ])(C\d+)(?=[-_ ]|$)", codigo, re.I)
    if m:
        base = m.group(1).upper()
    else:
        base = re.sub(r"\(.*?\)", " ", codigo)
        base = re.sub(r"(?:^|(?<=[-_ ]))H\d+(?=[-_ ]|$)", " ", base, flags=re.I)
        base = re.sub(r"[-_ ]+", " ", base).strip(" -").upper()
    return f"{prod} · {base}" if prod else base


def hook_de(codigo):
    m = re.search(r"(?:^|[-_ ])(H\d+)(?=[-_ ]|$)", codigo or "", re.I)
    return m.group(1).upper() if m else None


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
    for red in ("tiktok", "youtube"):
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
    return set(nucleo.leer_json(ARCHIVO, {}).get("ya_salieron") or [])


def ya_salio(ruta, si=True):
    """Marca un video como subido por fuera del publicador: no se vuelve a sugerir."""
    with nucleo._candado:
        d = nucleo.leer_json(ARCHIVO, {})
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
        cuerpo = p.get("cuerpo") or (inventario[ruta]["cuerpo"] if ruta in inventario
                                     else cuerpo_de(p.get("codigo"), p.get("produccion", "")))
        for red, r in p["redes"].items():
            if r.get("activa") and r.get("estado") != "error":
                out.append({"clave": _clave(red, r, defectos), "ruta": ruta, "cuerpo": cuerpo, "fecha": p.get("fecha") or ""})
    return out


def _carruseles_usados(dests):
    defectos, out = _defectos(dests), []
    for p in nucleo.cola()["publicaciones"]:
        if p.get("tipo") == "carrusel" and p.get("archivos"):
            for red, r in p["redes"].items():
                if r.get("activa") and r.get("estado") != "error":
                    out.append({"clave": _clave(red, r, defectos), "ruta": _norm(p["archivos"][0]), "fecha": p.get("fecha") or ""})
    return out


# ---------- Horarios ----------

def horas(n):
    """n horarios repartidos parejo entre «desde» y «hasta» (de 5 en 5 minutos)."""
    a = ajustes()
    h0, h1 = [int(x[:2]) * 60 + int(x[3:5]) for x in (a["desde"], a["hasta"])]
    if n <= 1:
        return [a["desde"]]
    paso = (h1 - h0) / (n - 1)
    return [f"{m // 60:02d}:{m % 60:02d}" for m in (int(round((h0 + i * paso) / 5) * 5) for i in range(n))]


# ---------- El plan ----------

def _inventario():
    vids, carrs = {}, {}
    for prod in produccion.listos(forzar=True)["producciones"]:
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


def planear(desde=None, dias=1, excluir=()):
    """Plan de «dias» días desde «desde» (hoy si no se dice). Lo que se sugiere un día cuenta como usado el siguiente."""
    a = ajustes()
    por_dia, aire = max(1, int(a["por_dia"])), max(0, int(a["aire_cuerpo"]))
    hoy = datetime.now().strftime("%Y-%m-%d")
    dia0 = desde or hoy
    todos = destinos()
    dests = [d for d in todos if d["activo"]]
    inv, carrs = _inventario()
    excluir = {_norm(e) for e in excluir}
    manuales = _manuales()
    usos = _usos(inv, todos)
    salidos = {u["ruta"] for u in usos} | manuales
    usos_carr = _carruseles_usados(todos)
    nombres = {d["clave"]: d["nombre"] for d in todos}
    orden = [d["clave"] for d in todos]      # la variante del copy de cada cuenta (la misma que usa aceptar)
    hs = horas(por_dia)
    salida = []
    for n in range(max(1, min(int(dias), 14))):
        dia = (datetime.strptime(dia0, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")
        ahora = datetime.now().strftime("%H:%M") if dia == hoy else "00:00"
        en_algun_lado = {u["ruta"] for u in usos} | manuales
        veces = {}
        for u in usos:
            veces[u["ruta"]] = veces.get(u["ruta"], 0) + 1
        hoy_red = {}       # red → videos de ese día en cualquier cuenta de esa red
        hoy_cuerpo = {}    # cuerpo → cuántas cuentas lo tienen ese día
        plan = {}
        for d in dests:
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
            plan[d["clave"]] = {**d, "ya": [{"fecha": u["fecha"], "codigo": inv.get(u["ruta"], {}).get("codigo") or os.path.basename(u["ruta"])}
                                            for u in sorted(del_dia, key=lambda u: u["fecha"])],
                                "piezas": [], "faltan": 0,
                                "_usadas": {u["ruta"] for u in mios} | manuales | excluir,
                                "_cuerpos": {u["cuerpo"] for u in del_dia}, "_ultimo": ultimo,
                                "_horas": [h for h in hs if h not in ocupadas and h > ahora],
                                "_cupo": max(0, por_dia - len(del_dia))}
            plan[d["clave"]]["_cupo"] = min(plan[d["clave"]]["_cupo"], len(plan[d["clave"]]["_horas"]))
        # por rondas: una pieza por cuenta en cada vuelta, así ninguna se lleva todo lo nuevo
        for _ in range(por_dia):
            for d in dests:
                pl = plan[d["clave"]]
                if len(pl["piezas"]) >= pl["_cupo"]:
                    continue
                cands = [v for r, v in inv.items() if r not in pl["_usadas"] and v["cuerpo"] not in pl["_cuerpos"]]
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
                hace = _dias_entre(dia, pl["_ultimo"][v["cuerpo"]]) if v["cuerpo"] in pl["_ultimo"] else None
                en_cola = sorted({nombres[u["clave"]] for u in usos if u["ruta"] == r and not u.get("plan")})
                en_plan = sorted({nombres[u["clave"]] for u in usos if u["ruta"] == r and u.get("plan")} - set(en_cola))
                if r not in en_algun_lado:
                    motivo = "Nuevo: no salió en ninguna cuenta"
                elif r in manuales:
                    motivo = "Marcado como ya subido a mano"
                else:
                    motivo = "; ".join(x for x in ((f"Ya está en {', '.join(en_cola)}" if en_cola else ""),
                                                    (f"También va en {', '.join(en_plan)}" if en_plan else "")) if x)                         + "; acá todavía no"
                if hace is not None and hace <= aire:
                    motivo += f" · ojo: este cuerpo salió acá hace {hace} día{'s' if hace != 1 else ''}"
                pieza = {"hora": "", "fecha": "", "ruta": v["ruta"], "codigo": v["codigo"],
                         "cuerpo": v["cuerpo"], "hook": v["hook"], "produccion": v["produccion"],
                         "portada": v["portada"], "archivos": v["archivos"], "motivo": motivo,
                         "pronto": hace is not None and hace <= aire,
                         "gancho": (copys.generar(v, orden.index(d["clave"]) + int(dia[8:10]), transcribir=False)
                                    .get("instagram") or "").split("\n")[0],
                         "_uso": {"clave": d["clave"], "ruta": r, "cuerpo": v["cuerpo"], "fecha": f"{dia}T00:00", "plan": True}}
                pl["piezas"].append(pieza)
                pl["_usadas"].add(r)
                pl["_cuerpos"].add(v["cuerpo"])
                en_algun_lado.add(r)
                veces[r] = veces.get(r, 0) + 1
                hoy_red.setdefault(d["red"], set()).add(r)
                hoy_cuerpo[v["cuerpo"]] = hoy_cuerpo.get(v["cuerpo"], 0) + 1
                usos.append(pieza["_uso"])
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
            libres = [c for r, c in carrs.items() if r not in {u["ruta"] for u in mios} and r not in excluir]
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
            lista.append({k: v for k, v in pl.items() if not k.startswith("_")})
        salida.append({"dia": dia, "destinos": lista, "sugeridos": sum(len(x["piezas"]) for x in lista),
                       "faltan": sum(x["faltan"] for x in lista)})
    cuerpos = {v["cuerpo"] for v in inv.values()}
    avisos = []
    if len(cuerpos) < por_dia:
        avisos.append(f"Tienes {len(cuerpos)} cuerpos distintos listos. Para {por_dia} videos diarios por cuenta sin repetir "
                      f"cuerpo en el día hacen falta al menos {por_dia}: pide {por_dia - len(cuerpos)} cuerpos más a producción.")
    if any(x["faltan"] for x in salida[0]["destinos"]):
        avisos.append("Algunas cuentas no llegan a su cupo: ya usaron todos los videos que hay de esos cuerpos.")
    return {"dias": salida, "por_dia": por_dia, "horas": hs, "destinos": todos, "ajustes": a,
            "inventario": {"videos": len(inv), "cuerpos": len(cuerpos), "carruseles": len(carrs),
                           "sin_salir": sum(1 for r in inv if r not in salidos),
                           "ya_salieron_a_mano": len(manuales)},
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
            copies[(it["clave"], _norm(it["ruta"]))] = copys.generar(p, v)
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
            pub = nucleo.nueva_publicacion({"codigo": p["codigo"], "tipo": p["tipo"], "copy_borrador": p["copy"]}, nucleo.AQUI)
            pub.update(archivos=p["archivos"], portada=p["portada"], produccion=p["produccion"], fecha=it["fecha"],
                       sugerido=True, **({"cuerpo": p["cuerpo"]} if p.get("cuerpo") else {}))
            pub.pop("dia", None)
            pub.pop("_desde", None)
            if copies.get((d["clave"], _norm(it["ruta"]))):
                copys.aplicar(pub, copies[(d["clave"], _norm(it["ruta"]))])
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
    nucleo.anotar(f"Sugerencias aceptadas: {len(nuevas)} piezas a la cola" + (f" · {saltadas} ya estaban" if saltadas else "")
                  + (f" · sin aprobar por palabras prohibidas: {trabadas}" if trabadas else ""))
    return {"nuevas": len(nuevas), "saltadas": saltadas, "trabadas": trabadas}
