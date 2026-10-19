"""Instagram y Facebook (página) por la Graph API de Meta, con el token de usuario del sistema.

Videos: Reels con subida directa del archivo (no hace falta URL pública).
Carruseles: las fotos se suben primero a la página como no publicadas; Instagram las toma de ahí.
"""
import os
import time
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


def fotos_en_pagina(archivos):
    """Sube fotos a la página sin publicarlas. Devuelve [(id_foto, url_cdn)]."""
    tp, pagina = token_pagina(), cred()["META_PAGE_ID"]
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


class Instagram:
    def estado(self):
        c = cred()
        return {"listo": bool(c["META_TOKEN_USUARIO_SISTEMA"] and c["META_IG_USER_ID"]),
                "falta": [k for k in ("META_TOKEN_USUARIO_SISTEMA", "META_IG_USER_ID") if not c[k]]}

    def publicar(self, pub, red):
        ig, tok = cred()["META_IG_USER_ID"], token()
        if not ig:
            raise ErrorRed("Falta META_IG_USER_ID en credenciales.env")
        if pub["tipo"] == "video":
            r = pedir("POST", f"{base()}/{ig}/media", datos={
                "media_type": "REELS", "upload_type": "resumable", "caption": red["copy"],
                "share_to_feed": "true", "access_token": tok})
            subir_bytes(r["uri"], pub["archivos"][0], tok)
            cid = r["id"]
        else:
            hijos = []
            for _, url in fotos_en_pagina(pub["archivos"][:10]):
                h = pedir("POST", f"{base()}/{ig}/media", datos={
                    "image_url": url, "is_carousel_item": "true", "access_token": tok})
                hijos.append(h["id"])
            cid = pedir("POST", f"{base()}/{ig}/media", datos={
                "media_type": "CAROUSEL", "children": ",".join(hijos), "caption": red["copy"],
                "access_token": tok})["id"]
        esperar_contenedor(cid, tok)
        mid = pedir("POST", f"{base()}/{ig}/media_publish", datos={"creation_id": cid, "access_token": tok})["id"]
        link = pedir("GET", f"{base()}/{mid}", {"fields": "permalink", "access_token": tok}).get("permalink")
        return {"id_remoto": mid, "url": link}

    def metricas(self, red):
        r = pedir("GET", f"{base()}/{red['id_remoto']}/insights", {
            "metric": "views,reach,likes,comments,saved,shares,follows", "access_token": token()})
        v = {i["name"]: _valor(i) for i in r.get("data", [])}
        return {"vistas": v.get("views"), "alcance": v.get("reach"), "me_gusta": v.get("likes"),
                "comentarios": v.get("comments"), "guardados": v.get("saved"), "compartidos": v.get("shares"),
                "seguidores": v.get("follows")}


class Facebook:
    def estado(self):
        c = cred()
        return {"listo": bool(c["META_TOKEN_USUARIO_SISTEMA"] and c["META_PAGE_ID"]),
                "falta": [k for k in ("META_TOKEN_USUARIO_SISTEMA", "META_PAGE_ID") if not c[k]]}

    def publicar(self, pub, red):
        pagina, tp = cred()["META_PAGE_ID"], token_pagina()
        if pub["tipo"] == "video":
            ini = pedir("POST", f"{base()}/{pagina}/video_reels", datos={"upload_phase": "start", "access_token": tp})
            subir_bytes(ini["upload_url"], pub["archivos"][0], tp)
            pedir("POST", f"{base()}/{pagina}/video_reels", datos={
                "upload_phase": "finish", "video_id": ini["video_id"], "video_state": "PUBLISHED",
                "description": red["copy"], "access_token": tp})
            info = pedir("GET", f"{base()}/{ini['video_id']}", {"fields": "permalink_url,post_id", "access_token": tp})
            url = info.get("permalink_url")
            return {"id_remoto": ini["video_id"], "post_id": info.get("post_id"),
                    "url": ("https://www.facebook.com" + url) if url and url.startswith("/") else url}
        fotos = fotos_en_pagina(pub["archivos"])
        datos = {"message": red["copy"], "access_token": tp}
        for n, (fid, _) in enumerate(fotos):
            datos[f"attached_media[{n}]"] = f'{{"media_fbid":"{fid}"}}'
        r = pedir("POST", f"{base()}/{pagina}/feed", datos=datos)
        return {"id_remoto": r["id"], "post_id": r["id"], "url": f"https://www.facebook.com/{r['id']}"}

    def metricas(self, red):
        tp = token_pagina()
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
