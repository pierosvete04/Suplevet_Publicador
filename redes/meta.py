"""Instagram y Facebook (páginas) por la Graph API de Meta.

Cuentas: «Conectar con Facebook» (inicio de sesión de Meta) trae todas las páginas que la persona administra y la
cuenta de Instagram de cada una; se pueden conectar varias personas y varias páginas (tokens.json → "meta_paginas").
El token de usuario del sistema de credenciales.env sigue sirviendo: su página aparece como una cuenta más, y la
pauta (anuncios) lo sigue usando.
Videos: Reels con subida directa del archivo (no hace falta URL pública).
Carruseles: las fotos se suben primero a la página como no publicadas; Instagram las toma de ahí.
"""
import os
import secrets
import time
import urllib.parse
from pathlib import Path

import nucleo

from . import ErrorRed, multipart, pedir

_token_pagina = {}


def base():
    return f"https://graph.facebook.com/{nucleo.config()['graph_version']}"


def cred():
    c = nucleo.credenciales()
    return {k: c.get(k, "") for k in ("META_TOKEN_USUARIO_SISTEMA", "META_PAGE_ID", "META_IG_USER_ID", "META_AD_ACCOUNT_ID")}


def token():
    t = cred()["META_TOKEN_USUARIO_SISTEMA"]
    if not t:
        raise ErrorRed("Falta META_TOKEN_USUARIO_SISTEMA en credenciales.env")
    return t


def token_pagina():
    pagina = cred()["META_PAGE_ID"]
    if not pagina:
        raise ErrorRed("Falta META_PAGE_ID en credenciales.env")
    if pagina not in _token_pagina:
        r = pedir("GET", f"{base()}/{pagina}", {"fields": "access_token", "access_token": token()})
        if not r.get("access_token"):
            raise ErrorRed("El token no tiene permiso sobre la página (pages_manage_posts)")
        _token_pagina[pagina] = r["access_token"]
    return _token_pagina[pagina]


# ---------- Conectar con Facebook: varias personas, páginas y cuentas de Instagram ----------
ALCANCES = ("pages_show_list,pages_read_engagement,pages_manage_posts,read_insights,"
            "instagram_basic,instagram_content_publish,instagram_manage_insights,business_management")
_estados = set()


def _app():
    c = nucleo.credenciales()
    return c.get("META_APP_ID", ""), c.get("META_APP_SECRET", "")


def redireccion():
    return nucleo.credenciales().get("META_REDIRECT_URI") or f"http://localhost:{nucleo.puerto()}/oauth/meta"


def url_conectar():
    app_id, secreto = _app()
    if not (app_id and secreto):
        raise ErrorRed("Faltan META_APP_ID y META_APP_SECRET en credenciales.env (la app de Meta for Developers)")
    st = secrets.token_urlsafe(12)
    _estados.add(st)
    return f"https://www.facebook.com/{nucleo.config()['graph_version']}/dialog/oauth?" + urllib.parse.urlencode({
        "client_id": app_id, "redirect_uri": redireccion(), "state": st, "scope": ALCANCES, "response_type": "code"})


def _todas(url, params):
    """Todas las páginas de una lista de la Graph API (sigue «next»)."""
    out = []
    r = pedir("GET", url, params)
    while True:
        out += r.get("data") or []
        sig = (r.get("paging") or {}).get("next")
        if not sig or len(out) > 500:
            return out
        r = pedir("GET", sig)


def recibir_codigo(codigo, estado):
    """Vuelve de Facebook: cambia el código por un token largo y guarda cada página con su Instagram."""
    if estado not in _estados:
        raise ErrorRed("La respuesta de Facebook no coincide con la conexión que se pidió")
    _estados.discard(estado)
    app_id, secreto = _app()
    corto = pedir("GET", f"{base()}/oauth/access_token", {"client_id": app_id, "client_secret": secreto,
                                                          "redirect_uri": redireccion(), "code": codigo})
    if not corto.get("access_token"):
        raise ErrorRed(f"Facebook no dio token: {corto}")
    largo = pedir("GET", f"{base()}/oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": app_id,
                                                          "client_secret": secreto, "fb_exchange_token": corto["access_token"]})
    tok = largo.get("access_token") or corto["access_token"]  # con el token largo, los de página no vencen
    persona = pedir("GET", f"{base()}/me", {"fields": "id,name", "access_token": tok})
    paginas_fb = _todas(f"{base()}/me/accounts", {"fields": "id,name,access_token,instagram_business_account{id,username}",
                                                   "limit": 100, "access_token": tok})
    if not paginas_fb:
        raise ErrorRed("Esa cuenta de Facebook no administra ninguna página, o no marcaste ninguna al dar permiso")
    cs = {k: v for k, v in paginas().items() if not v.get("sistema")}
    for pg in paginas_fb:
        ig = pg.get("instagram_business_account") or {}
        cs[pg["id"]] = {"id": pg["id"], "nombre": pg.get("name") or pg["id"], "token": pg.get("access_token"),
                        "ig_id": ig.get("id"), "ig_usuario": ig.get("username"),
                        "persona": persona.get("name"), "persona_id": persona.get("id"), "guardado": int(time.time())}
    nucleo.guardar_token("meta_paginas", cs)
    cfg = nucleo.config()
    if not cfg.get("facebook_cuenta"):
        nucleo.guardar_config({"facebook_cuenta": paginas_fb[0]["id"]})
    con_ig = [pg for pg in paginas_fb if (pg.get("instagram_business_account") or {}).get("id")]
    if not cfg.get("instagram_cuenta") and con_ig:
        nucleo.guardar_config({"instagram_cuenta": con_ig[0]["instagram_business_account"]["id"]})
    return {"nombre": ", ".join(pg.get("name") or pg["id"] for pg in paginas_fb)}


def paginas():
    """{id de página: {id, nombre, token, ig_id, ig_usuario, persona}}; la de credenciales.env lleva sistema=True."""
    cs = {k: v for k, v in (nucleo.tokens().get("meta_paginas") or {}).items() if isinstance(v, dict)}
    c = cred()
    if c["META_TOKEN_USUARIO_SISTEMA"] and c["META_PAGE_ID"] and c["META_PAGE_ID"] not in cs:
        cs[c["META_PAGE_ID"]] = {"id": c["META_PAGE_ID"], "nombre": "Página de credenciales.env", "token": None,
                                 "ig_id": c["META_IG_USER_ID"] or None, "ig_usuario": None, "sistema": True}
    return cs


def cuentas_red(red):
    """{id: {id, nombre, pagina}} de las cuentas de esa red (facebook = páginas, instagram = sus cuentas de IG)."""
    out = {}
    for pid, pg in paginas().items():
        if red == "facebook":
            out[pid] = {"id": pid, "nombre": pg.get("nombre") or pid, "pagina": pid}
        elif pg.get("ig_id"):
            out[pg["ig_id"]] = {"id": pg["ig_id"], "nombre": "@" + pg["ig_usuario"] if pg.get("ig_usuario") else f"Instagram de {pg.get('nombre')}",
                                "pagina": pid}
    return out


def cuenta_de(red, pieza=None):
    """La cuenta de una pieza (pieza["cuenta"]) o la que está por defecto."""
    cs = cuentas_red(red)
    nombre = "Instagram" if red == "instagram" else "Facebook"
    if not cs:
        raise ErrorRed(f"{nombre} no está conectado (Conexiones → Conectar con Facebook)")
    cid = (pieza or {}).get("cuenta") or nucleo.config().get(f"{red}_cuenta")
    if cid not in cs:
        if (pieza or {}).get("cuenta"):
            raise ErrorRed(f"La cuenta de {nombre} elegida para esta pieza ya no está conectada")
        cid = next(iter(cs))
    return cs[cid]


def token_de_pagina(pid):
    pg = paginas().get(pid)
    if not pg:
        raise ErrorRed("Esa página ya no está conectada")
    return pg["token"] or token_pagina()  # la de credenciales.env saca su token del usuario del sistema


def token_de(red, cuenta):
    """Token para la API: el de la página (también sirve para su Instagram); el del sistema para la de credenciales.env."""
    pg = paginas()[cuenta["pagina"]]
    if pg.get("sistema"):
        return token() if red == "instagram" else token_pagina()
    return pg["token"]


def quitar_cuenta(red, cid):
    cs = {k: v for k, v in (nucleo.tokens().get("meta_paginas") or {}).items() if isinstance(v, dict)}
    if red == "facebook":
        if cid not in cs:
            raise ErrorRed("Esta página viene de credenciales.env: para quitarla, borra META_PAGE_ID de ese archivo")
        cs.pop(cid)
    else:
        pg = next((v for v in cs.values() if v.get("ig_id") == cid), None)
        if not pg:
            raise ErrorRed("Esta cuenta viene de credenciales.env: para quitarla, borra META_IG_USER_ID de ese archivo")
        pg["ig_id"] = pg["ig_usuario"] = None
    nucleo.guardar_token("meta_paginas", cs)
    for r in ("facebook", "instagram"):
        if nucleo.config().get(f"{r}_cuenta") not in cuentas_red(r):
            nucleo.guardar_config({f"{r}_cuenta": next(iter(cuentas_red(r)), None)})


def _estado(red):
    cs = cuentas_red(red)
    app_id, secreto = _app()
    falta = [] if cs else (["Faltan las llaves de Meta: ponlas en Preparación"] if not (app_id and secreto)
                           else ["Conectar con Facebook"])
    defecto = nucleo.config().get(f"{red}_cuenta")
    lista = [{"id": k, "nombre": c["nombre"], "defecto": k == defecto or (defecto not in cs and i == 0)}
             for i, (k, c) in enumerate(cs.items())]
    return {"listo": bool(cs), "falta": falta, "cuentas": lista, "conectable": bool(app_id and secreto)}


def subir_bytes(url, ruta, tok):
    """Subida en un solo envío a rupload.facebook.com (Reels de IG y de FB)."""
    tam = os.path.getsize(ruta)
    with open(ruta, "rb") as f:
        return pedir("POST", url, cuerpo=f.read(), tiempo=900,
                     cabeceras={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(tam)})


def esperar_contenedor(cid, tok, maximo=600):
    """Instagram procesa el video antes de dejar publicarlo."""
    fin = time.time() + maximo
    while time.time() < fin:
        r = pedir("GET", f"{base()}/{cid}", {"fields": "status_code,status", "access_token": tok})
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") in ("ERROR", "EXPIRED"):
            raise ErrorRed(f"Instagram rechazó el archivo: {r.get('status')}")
        time.sleep(5)
    raise ErrorRed("Instagram tardó más de 10 minutos en procesar el video")


def fotos_en_pagina(archivos, pagina, tp):
    """Sube fotos a la página sin publicarlas. Devuelve [(id_foto, url_cdn)]."""
    out = []
    for a in archivos:
        cuerpo, tipo = multipart({"published": "false", "access_token": tp}, {"source": Path(a)})
        r = pedir("POST", f"{base()}/{pagina}/photos", cuerpo=cuerpo, cabeceras={"Content-Type": tipo})
        info = pedir("GET", f"{base()}/{r['id']}", {"fields": "images", "access_token": tp})
        out.append((r["id"], info["images"][0]["source"]))
    return out


def _valor(item):
    if "total_value" in item:
        return item["total_value"].get("value")
    v = (item.get("values") or [{}])[0].get("value")
    return sum(v.values()) if isinstance(v, dict) else v


def _foto_de_cuenta(nombre_red):
    """Seguidores y publicaciones de cada cuenta conectada → {nombre: {...}} (para las métricas)."""
    out = {}
    for cid, c in cuentas_red(nombre_red).items():
        try:
            tok = token_de(nombre_red, c)
            if nombre_red == "instagram":
                r = pedir("GET", f"{base()}/{cid}", {"fields": "followers_count,media_count", "access_token": tok})
                out[c["nombre"]] = {"seguidores": r.get("followers_count"), "videos": r.get("media_count")}
            else:
                r = pedir("GET", f"{base()}/{cid}", {"fields": "followers_count,fan_count", "access_token": tok})
                out[c["nombre"]] = {"seguidores": r.get("followers_count") or r.get("fan_count")}
        except ErrorRed as e:  # una cuenta caída no frena a las demás
            nucleo.anotar(f"Cuenta {nombre_red} {c['nombre']}: {e}")
    return out


class Instagram:
    def estado(self):
        return _estado("instagram")

    def cuentas(self):
        return _foto_de_cuenta("instagram")

    def publicar(self, pub, red):
        cuenta = cuenta_de("instagram", red)
        ig, tok = cuenta["id"], token_de("instagram", cuenta)
        red["cuenta"], red["cuenta_nombre"] = ig, cuenta["nombre"]
        if pub["tipo"] == "video":
            r = pedir("POST", f"{base()}/{ig}/media", datos={
                "media_type": "REELS", "upload_type": "resumable", "caption": red["copy"],
                "share_to_feed": "true", "access_token": tok})
            subir_bytes(r["uri"], pub["archivos"][0], tok)
            cid = r["id"]
        elif len(pub["archivos"]) == 1:   # post de una sola imagen (Sala de diseño): un carrusel pide de 2 a 10
            _, url = next(iter(fotos_en_pagina(pub["archivos"][:1], cuenta["pagina"], token_de("facebook", cuenta))))
            cid = pedir("POST", f"{base()}/{ig}/media", datos={"image_url": url, "caption": red["copy"], "access_token": tok})["id"]
        else:
            hijos = []
            for _, url in fotos_en_pagina(pub["archivos"][:10], cuenta["pagina"], token_de("facebook", cuenta)):
                h = pedir("POST", f"{base()}/{ig}/media", datos={
                    "image_url": url, "is_carousel_item": "true", "access_token": tok})
                hijos.append(h["id"])
            cid = pedir("POST", f"{base()}/{ig}/media", datos={
                "media_type": "CAROUSEL", "children": ",".join(hijos), "caption": red["copy"],
                "access_token": tok})["id"]
        esperar_contenedor(cid, tok)
        mid = pedir("POST", f"{base()}/{ig}/media_publish", datos={"creation_id": cid, "access_token": tok})["id"]
        link = pedir("GET", f"{base()}/{mid}", {"fields": "permalink", "access_token": tok}).get("permalink")
        return {"id_remoto": mid, "url": link, "cuenta": ig, "cuenta_nombre": cuenta["nombre"]}

    def metricas(self, red):
        r = pedir("GET", f"{base()}/{red['id_remoto']}/insights", {
            "metric": "views,reach,likes,comments,saved,shares,follows", "access_token": token_de("instagram", cuenta_de("instagram", red))})
        v = {i["name"]: _valor(i) for i in r.get("data", [])}
        return {"vistas": v.get("views"), "alcance": v.get("reach"), "me_gusta": v.get("likes"),
                "comentarios": v.get("comments"), "guardados": v.get("saved"), "compartidos": v.get("shares"),
                "seguidores": v.get("follows")}


class Facebook:
    def estado(self):
        return _estado("facebook")

    def cuentas(self):
        return _foto_de_cuenta("facebook")

    def publicar(self, pub, red):
        cuenta = cuenta_de("facebook", red)
        pagina, tp = cuenta["id"], token_de("facebook", cuenta)
        red["cuenta"], red["cuenta_nombre"] = pagina, cuenta["nombre"]
        if pub["tipo"] == "video":
            ini = pedir("POST", f"{base()}/{pagina}/video_reels", datos={"upload_phase": "start", "access_token": tp})
            subir_bytes(ini["upload_url"], pub["archivos"][0], tp)
            pedir("POST", f"{base()}/{pagina}/video_reels", datos={
                "upload_phase": "finish", "video_id": ini["video_id"], "video_state": "PUBLISHED",
                "description": red["copy"], "access_token": tp})
            info = pedir("GET", f"{base()}/{ini['video_id']}", {"fields": "permalink_url,post_id", "access_token": tp})
            url = info.get("permalink_url")
            return {"id_remoto": ini["video_id"], "post_id": info.get("post_id"), "cuenta": pagina, "cuenta_nombre": cuenta["nombre"],
                    "url": ("https://www.facebook.com" + url) if url and url.startswith("/") else url}
        fotos = fotos_en_pagina(pub["archivos"], pagina, tp)
        datos = {"message": red["copy"], "access_token": tp}
        for n, (fid, _) in enumerate(fotos):
            datos[f"attached_media[{n}]"] = f'{{"media_fbid":"{fid}"}}'
        r = pedir("POST", f"{base()}/{pagina}/feed", datos=datos)
        return {"id_remoto": r["id"], "post_id": r["id"], "url": f"https://www.facebook.com/{r['id']}",
                "cuenta": pagina, "cuenta_nombre": cuenta["nombre"]}

    def metricas(self, red):
        tp = token_de("facebook", cuenta_de("facebook", red))
        if red.get("post_id") and red["post_id"] != red["id_remoto"]:   # reel
            r = pedir("GET", f"{base()}/{red['id_remoto']}/video_insights", {
                "metric": "blue_reels_play_count,post_video_social_actions", "access_token": tp})
            v = {i["name"]: (i.get("values") or [{}])[0].get("value") for i in r.get("data", [])}
            acc = v.get("post_video_social_actions") or {}
            return {"vistas": v.get("blue_reels_play_count"), "me_gusta": acc.get("REACTION") or acc.get("LIKE"),
                    "comentarios": acc.get("COMMENT"), "compartidos": acc.get("SHARE")}
        r = pedir("GET", f"{base()}/{red['id_remoto']}", {
            "fields": "reactions.summary(true).limit(0),comments.summary(true).limit(0),shares", "access_token": tp})
        return {"me_gusta": r.get("reactions", {}).get("summary", {}).get("total_count"),
                "comentarios": r.get("comments", {}).get("summary", {}).get("total_count"),
                "compartidos": r.get("shares", {}).get("count")}
