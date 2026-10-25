"""Pauta en Meta Ads (Instagram + Facebook).

Regla de oro: todo se crea en PAUSA. Solo se gasta cuando tú aprietas «Activar» en la pestaña Pauta.
Si la pieza ya salió orgánica en Instagram o Facebook, se impulsa esa misma publicación (suma sus me gusta).
Si no, se sube el video a la cuenta publicitaria y se arma el anuncio con el copy.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

import nucleo
from redes import ErrorRed, meta, multipart, pedir

# objetivo → (objetivo de campaña, optimización del conjunto, destino)
OBJETIVOS = {
    "alcance": ("OUTCOME_AWARENESS", "REACH", None),
    "reproducciones": ("OUTCOME_ENGAGEMENT", "THRUPLAY", "ON_VIDEO"),
    "trafico": ("OUTCOME_TRAFFIC", "LINK_CLICKS", "WEBSITE"),
    "mensajes": ("OUTCOME_ENGAGEMENT", "CONVERSATIONS", "WHATSAPP"),
}


def pauta():
    return nucleo.leer_json(nucleo.PAUTA, {"campanas": []})


def guardar(p):
    nucleo.escribir_json(nucleo.PAUTA, p)


def buscar(p, cid):
    c = next((x for x in p["campanas"] if x["id"] == cid), None)
    if not c:
        raise ErrorRed("No existe esa campaña")
    return c


def _numero(v, nombre, entero=False):
    try:
        return int(v) if entero else float(v)
    except (TypeError, ValueError):
        raise ErrorRed(f"«{nombre}» tiene que ser un número") from None


def _fecha(v, nombre):
    try:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        raise ErrorRed(f"«{nombre}» no es una fecha y hora válida") from None


def nueva(datos):
    cfg = nucleo.config()["pauta"]
    pres = datos.get("presupuesto_diario")
    pres = 20.0 if pres in (None, "") else _numero(pres, "Presupuesto por día")
    if pres < 1:
        raise ErrorRed("El presupuesto por día tiene que ser mayor que cero (Meta pide al menos unos soles al día)")
    emin = _numero(datos["edad_min"], "Edad desde", True) if datos.get("edad_min") not in (None, "") else int(cfg["edad_min"])
    emax = _numero(datos["edad_max"], "Edad hasta", True) if datos.get("edad_max") not in (None, "") else int(cfg["edad_max"])
    if not 18 <= emin <= 65 or not 18 <= emax <= 65:
        raise ErrorRed("Las edades van de 18 a 65")
    if emin > emax:
        raise ErrorRed("«Edad desde» no puede ser mayor que «hasta»")
    inicio = _fecha(datos["inicio"], "Desde") if datos.get("inicio") else datetime.now().strftime("%Y-%m-%dT%H:%M")
    fin = _fecha(datos["fin"], "Hasta") if datos.get("fin") else None
    if fin and fin <= inicio:
        raise ErrorRed("«Hasta» tiene que ser después de «Desde»")
    plataformas = datos.get("plataformas")
    plataformas = ["instagram", "facebook"] if plataformas is None else [x for x in plataformas if x in ("instagram", "facebook")]
    if not plataformas:
        raise ErrorRed("Prende al menos Instagram o Facebook")
    c = {
        "id": uuid.uuid4().hex[:8],
        "nombre": datos.get("nombre") or f"Suplevet {datetime.now():%Y-%m-%d}",
        "objetivo": datos.get("objetivo", "reproducciones"),
        "presupuesto_diario": pres,
        "inicio": inicio,
        "fin": fin,
        "paises": datos.get("paises") or cfg["pais"],
        "edad_min": emin,
        "edad_max": emax,
        "plataformas": plataformas,
        "piezas": datos.get("piezas") or [],
        "estado": "borrador",
        "meta": {},
        "creado": datetime.now().isoformat(timespec="minutes"),
    }
    if c["objetivo"] not in OBJETIVOS:
        raise ErrorRed(f"Objetivo desconocido: {c['objetivo']}")
    if not c["piezas"]:
        raise ErrorRed("Elige al menos una pieza para la campaña")
    p = pauta()
    p["campanas"].append(c)
    guardar(p)
    nucleo.anotar(f"Campaña borrador «{c['nombre']}» con {len(c['piezas'])} piezas, S/ {c['presupuesto_diario']}/día")
    return c


def borrar(cid):
    p = pauta()
    c = buscar(p, cid)
    if c["estado"] == "activa":
        raise ErrorRed("Primero pausa la campaña")
    p["campanas"] = [x for x in p["campanas"] if x["id"] != cid]
    guardar(p)


def _hora(t):
    return datetime.strptime(t, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M:00-0500")   # hora de Lima


def _cuenta():
    a = meta.cred()["META_AD_ACCOUNT_ID"]
    if not a:
        raise ErrorRed("Falta META_AD_ACCOUNT_ID en credenciales.env")
    return a if a.startswith("act_") else f"act_{a}"


def _creativo(pub, c, tok):
    cr, cfg = meta.cred(), nucleo.config()["pauta"]
    acc, base = _cuenta(), meta.base()
    ig, fb = pub["redes"].get("instagram", {}), pub["redes"].get("facebook", {})
    boton = {"type": cfg["boton"], "value": {"link": cfg["enlace"]}}
    if c["objetivo"] == "mensajes":
        boton = {"type": "WHATSAPP_MESSAGE", "value": {"app_destination": "WHATSAPP"}}
    datos = {"name": f"{pub['codigo']} · {c['nombre']}", "access_token": tok}
    if ig.get("estado") == "publicado" and ig.get("id_remoto"):
        datos.update(object_id=cr["META_PAGE_ID"], instagram_user_id=cr["META_IG_USER_ID"],
                     source_instagram_media_id=ig["id_remoto"])
        if c["objetivo"] in ("trafico", "mensajes"):
            datos["call_to_action"] = json.dumps(boton)
    elif fb.get("estado") == "publicado" and fb.get("post_id"):
        pid = fb["post_id"] if "_" in fb["post_id"] else f"{cr['META_PAGE_ID']}_{fb['post_id']}"
        datos["object_story_id"] = pid
    else:
        if pub["tipo"] != "video":
            raise ErrorRed(f"{pub['codigo']}: para pautar un carrusel primero publícalo orgánico en Instagram")
        cuerpo, tipo = multipart({"access_token": tok}, {"source": Path(pub["archivos"][0])})
        vid = pedir("POST", f"{base}/{acc}/advideos", cuerpo=cuerpo, cabeceras={"Content-Type": tipo}, tiempo=900)["id"]
        video = {"video_id": vid, "message": (ig or fb).get("copy", ""), "call_to_action": boton}
        if pub.get("portada") and Path(pub["portada"]).exists():
            cuerpo, tipo = multipart({"access_token": tok}, {"filename": Path(pub["portada"])})
            imgs = pedir("POST", f"{base}/{acc}/adimages", cuerpo=cuerpo, cabeceras={"Content-Type": tipo})["images"]
            video["image_hash"] = next(iter(imgs.values()))["hash"]
        spec = {"page_id": cr["META_PAGE_ID"], "video_data": video}
        if cr["META_IG_USER_ID"]:
            spec["instagram_user_id"] = cr["META_IG_USER_ID"]
        datos["object_story_spec"] = json.dumps(spec)
    return pedir("POST", f"{base}/{acc}/adcreatives", datos=datos)["id"]


def crear_en_meta(cid):
    """Crea campaña + conjunto + un anuncio por pieza, todo en PAUSA."""
    p = pauta()
    c = buscar(p, cid)
    if c["estado"] not in ("borrador", "error"):
        raise ErrorRed("Esta campaña ya se creó en Meta")
    cola = nucleo.cola()
    pubs = [nucleo.buscar(cola, x) for x in c["piezas"]]
    if any(x is None for x in pubs):
        raise ErrorRed("Una de las piezas ya no está en la cola")
    objetivo, optimizacion, destino = OBJETIVOS[c["objetivo"]]
    if nucleo.config()["simular"]:
        c["meta"] = {"campaign_id": "sim-camp", "adset_id": "sim-set",
                     "ads": [{"pieza": x["id"], "codigo": x["codigo"], "ad_id": f"sim-ad-{n}"} for n, x in enumerate(pubs)]}
        c["estado"] = "creada"
        guardar(p)
        nucleo.anotar(f"[SIMULACIÓN] Meta Ads «{c['nombre']}» {objetivo}/{optimizacion} creada en pausa")
        return c
    tok, acc, base = meta.token(), _cuenta(), meta.base()
    try:
        camp = pedir("POST", f"{base}/{acc}/campaigns", datos={
            "name": c["nombre"], "objective": objetivo, "status": "PAUSED", "special_ad_categories": "[]",
            "is_adset_budget_sharing_enabled": "false", "access_token": tok})["id"]
        c["meta"] = {"campaign_id": camp, "ads": []}
        guardar(p)
        targeting = {"geo_locations": {"countries": c["paises"]}, "age_min": c["edad_min"], "age_max": c["edad_max"],
                     "publisher_platforms": c["plataformas"],
                     "targeting_automation": {"advantage_audience": 0}}
        conjunto = {"name": f"{c['nombre']} · conjunto", "campaign_id": camp, "status": "PAUSED",
                    "daily_budget": str(int(round(c["presupuesto_diario"] * 100))),
                    "billing_event": "IMPRESSIONS", "optimization_goal": optimizacion,
                    "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "start_time": _hora(c["inicio"]),
                    "targeting": json.dumps(targeting), "access_token": tok}
        if destino:
            conjunto["destination_type"] = destino
        if c.get("fin"):
            conjunto["end_time"] = _hora(c["fin"])
        if c["objetivo"] in ("trafico", "mensajes"):
            conjunto["promoted_object"] = json.dumps({"page_id": meta.cred()["META_PAGE_ID"]})
        c["meta"]["adset_id"] = pedir("POST", f"{base}/{acc}/adsets", datos=conjunto)["id"]
        guardar(p)
        for pub in pubs:
            creativo = _creativo(pub, c, tok)
            ad = pedir("POST", f"{base}/{acc}/ads", datos={
                "name": pub["codigo"], "adset_id": c["meta"]["adset_id"], "status": "PAUSED",
                "creative": json.dumps({"creative_id": creativo}), "access_token": tok})["id"]
            c["meta"]["ads"].append({"pieza": pub["id"], "codigo": pub["codigo"], "creative_id": creativo, "ad_id": ad})
            guardar(p)
        c["estado"], c["error"] = "creada", None
        nucleo.anotar(f"Meta Ads «{c['nombre']}» creada en pausa: {camp}")
    except Exception as e:
        c["estado"], c["error"] = "error", str(e)[:500]
        nucleo.anotar(f"ERROR Meta Ads «{c['nombre']}»: {e}")
    guardar(p)
    return c


def _cambiar_estado(c, estado):
    ids = [c["meta"].get("campaign_id"), c["meta"].get("adset_id")] + [a["ad_id"] for a in c["meta"].get("ads", [])]
    if nucleo.config()["simular"]:
        nucleo.anotar(f"[SIMULACIÓN] Meta Ads «{c['nombre']}» → {estado}")
        return
    tok = meta.token()
    for i in filter(None, ids):
        pedir("POST", f"{meta.base()}/{i}", datos={"status": estado, "access_token": tok})


def activar(cid, confirmado):
    """Empieza a gastar. Pide confirmado=True (la página muestra el monto antes)."""
    if not confirmado:
        raise ErrorRed("Falta confirmar el gasto")
    p = pauta()
    c = buscar(p, cid)
    if c["estado"] not in ("creada", "pausada"):
        raise ErrorRed("Primero crea la campaña en Meta")
    _cambiar_estado(c, "ACTIVE")
    c["estado"] = "activa"
    guardar(p)
    nucleo.anotar(f"ACTIVADA «{c['nombre']}» · S/ {c['presupuesto_diario']}/día")
    return c


def pausar(cid):
    p = pauta()
    c = buscar(p, cid)
    _cambiar_estado(c, "PAUSED")
    c["estado"] = "pausada"
    guardar(p)
    nucleo.anotar(f"Pausada «{c['nombre']}»")
    return c


def resultados(cid):
    """Gasto y resultados por anuncio (para ver qué hook gana con plata encima)."""
    p = pauta()
    c = buscar(p, cid)
    if nucleo.config()["simular"] or not c["meta"].get("campaign_id"):
        return c
    r = pedir("GET", f"{meta.base()}/{c['meta']['campaign_id']}/insights", {
        "level": "ad", "date_preset": "maximum", "access_token": meta.token(),
        "fields": "ad_id,ad_name,spend,impressions,reach,clicks,ctr,cpc,cpm,actions,video_thruplay_watched_actions"})
    filas = []
    for f in r.get("data", []):
        acc = {a["action_type"]: float(a["value"]) for a in f.get("actions", [])}
        filas.append({"codigo": f.get("ad_name"), "gasto": float(f.get("spend", 0)), "impresiones": int(f.get("impressions", 0)),
                      "alcance": int(f.get("reach", 0)), "clics": int(f.get("clicks", 0)), "ctr": float(f.get("ctr", 0)),
                      "thruplays": sum(float(a["value"]) for a in f.get("video_thruplay_watched_actions", [])),
                      "mensajes": acc.get("onsite_conversion.messaging_conversation_started_7d", 0)})
    c["resultados"] = {"actualizado": datetime.now().isoformat(timespec="minutes"), "anuncios": filas}
    guardar(p)
    semanas = {nucleo._datos_del_codigo(f["codigo"]).get("semana") for f in filas} - {None}
    for s in semanas:
        ruta = nucleo.METRICAS / f"{s}_pauta.json"
        d = nucleo.leer_json(ruta, {"semana": s, "campanas": {}})
        d["campanas"][c["id"]] = {"nombre": c["nombre"], "objetivo": c["objetivo"],
                                  "anuncios": [f for f in filas if f["codigo"].startswith(s)]}
        nucleo.escribir_json(ruta, d)
    return c
