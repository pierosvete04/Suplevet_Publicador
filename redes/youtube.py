"""YouTube Shorts por la Data API v3 (subida reanudable) con OAuth de app de escritorio.

Necesita 2_PUBLICACION/google_client_secret.json (Google Cloud → Credenciales → ID de cliente OAuth → App de escritorio).
"""
import json
import os
import secrets
import time
import urllib.parse

import nucleo

from . import ErrorRed, pedir

ALCANCES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
_estados = set()


def _cliente():
    d = nucleo.leer_json(nucleo.GOOGLE_SECRET, {})
    d = d.get("installed") or d.get("web") or {}
    if not d.get("client_id"):
        raise ErrorRed("Falta google_client_secret.json en 2_PUBLICACION")
    return d


def redireccion():
    return f"http://127.0.0.1:{nucleo.config()['puerto']}/oauth/google"


def url_conectar():
    c = _cliente()
    st = secrets.token_urlsafe(12)
    _estados.add(st)
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redireccion(), "response_type": "code",
        "scope": ALCANCES, "access_type": "offline", "prompt": "select_account consent", "state": st})


def recibir_codigo(codigo, estado):
    if estado not in _estados:
        raise ErrorRed("La respuesta de Google no coincide con la conexión que se pidió")
    _estados.discard(estado)
    c = _cliente()
    r = pedir("POST", "https://oauth2.googleapis.com/token", datos={
        "code": codigo, "client_id": c["client_id"], "client_secret": c["client_secret"],
        "redirect_uri": redireccion(), "grant_type": "authorization_code"})
    t = {"access_token": r["access_token"], "refresh_token": r.get("refresh_token"),
         "vence": int(time.time()) + int(r.get("expires_in", 0)), "guardado": int(time.time())}
    canal = (pedir("GET", "https://www.googleapis.com/youtube/v3/channels", {"part": "snippet", "mine": "true"},
                   cabeceras={"Authorization": f"Bearer {t['access_token']}"}).get("items") or [{}])[0]
    if not canal.get("id"):
        raise ErrorRed("Esa cuenta de Google no tiene canal de YouTube")
    t.update(id=canal["id"], nombre=canal.get("snippet", {}).get("title") or canal["id"])
    if not t["refresh_token"] and canal["id"] in cuentas():   # Google a veces no repite el refresh_token
        t["refresh_token"] = cuentas()[canal["id"]].get("refresh_token")
    _escribir_cuenta(t)
    if not nucleo.config().get("youtube_cuenta"):
        nucleo.guardar_config({"youtube_cuenta": t["id"]})
    return t


# ---------- Varios canales: tokens.json → "youtube_cuentas": {channel_id: {...}} ----------

def cuentas():
    t = nucleo.tokens()
    cs = {k: v for k, v in (t.get("youtube_cuentas") or {}).items() if isinstance(v, dict)}  # guardar_token mete "guardado"
    viejo = t.get("youtube")   # versiones anteriores guardaban un solo canal, sin id
    if viejo and viejo.get("access_token") and not cs:
        cs["_anterior"] = {**viejo, "id": "_anterior", "nombre": "Canal de YouTube"}
    return cs


def _escribir_cuenta(c):
    cs = {k: v for k, v in cuentas().items() if k != "_anterior"}
    nucleo.guardar_token("youtube_cuentas", {**cs, c["id"]: c})
    nucleo.guardar_token("youtube", {})   # el formato viejo ya no hace falta


def quitar_cuenta(cid):
    cs = cuentas()
    cs.pop(cid, None)
    nucleo.guardar_token("youtube_cuentas", {k: v for k, v in cs.items() if k != "_anterior"})
    if cid == "_anterior":
        nucleo.guardar_token("youtube", {})
    if nucleo.config().get("youtube_cuenta") == cid:
        nucleo.guardar_config({"youtube_cuenta": next(iter(cs), None)})


def cuenta_de(red=None):
    """El canal de una pieza (red["cuenta"]) o el que está por defecto."""
    cs = cuentas()
    if not cs:
        raise ErrorRed("YouTube no está conectado (pestaña Conexiones)")
    cid = (red or {}).get("cuenta") or nucleo.config().get("youtube_cuenta")
    if cid not in cs:
        if (red or {}).get("cuenta"):
            raise ErrorRed("El canal de YouTube elegido para esta pieza ya no está conectado")
        cid = next(iter(cs))
    return cs[cid]


def token(red=None):
    t = cuenta_de(red)
    if t["vence"] - time.time() < 300:
        c = _cliente()
        r = pedir("POST", "https://oauth2.googleapis.com/token", datos={
            "client_id": c["client_id"], "client_secret": c["client_secret"],
            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        t = {**t, "access_token": r["access_token"], "vence": int(time.time()) + int(r.get("expires_in", 0))}
        if t["id"] == "_anterior":
            nucleo.guardar_token("youtube", {k: v for k, v in t.items() if k not in ("id", "nombre")})
        else:
            _escribir_cuenta(t)
    return t["access_token"]


def _cab(red=None):
    return {"Authorization": f"Bearer {token(red)}"}


class YouTube:
    cuenta_de = staticmethod(cuenta_de)

    def estado(self):
        falta = []
        if not nucleo.GOOGLE_SECRET.exists():
            falta.append("google_client_secret.json")
        cs = cuentas()
        if not cs:
            falta.append("conectar la cuenta")
        defecto = nucleo.config().get("youtube_cuenta")
        lista = [{"id": k, "nombre": c.get("nombre"), "defecto": k == defecto or (defecto not in cs and i == 0)}
                 for i, (k, c) in enumerate(cs.items())]
        return {"listo": not falta, "falta": falta, "cuentas": lista}

    def publicar(self, pub, red):
        if pub["tipo"] != "video":
            raise ErrorRed("YouTube solo recibe videos")
        cfg = nucleo.config()
        canal = cuenta_de(red)
        red["cuenta"], red["cuenta_nombre"] = canal["id"], canal.get("nombre")
        ruta = pub["archivos"][0]
        texto = red["copy"]
        tags = [w.lstrip("#") for w in texto.split() if w.startswith("#")][:15]
        meta = {"snippet": {"title": (red.get("titulo") or texto.split("\n")[0])[:100], "description": texto[:5000],
                            "tags": tags, "categoryId": cfg["youtube_categoria"], "defaultLanguage": "es"},
                "status": {"privacyStatus": cfg["youtube_privacidad"], "selfDeclaredMadeForKids": False}}
        tam = os.path.getsize(ruta)
        ini = pedir("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                    cuerpo=json.dumps(meta).encode(), cabeceras={
                        "Authorization": f"Bearer {token(red)}", "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tam)})
        destino = ini["_cabeceras"].get("Location") or ini["_cabeceras"].get("location")
        with open(ruta, "rb") as f:
            r = pedir("PUT", destino, cuerpo=f.read(), tiempo=1800,
                      cabeceras={"Authorization": f"Bearer {token(red)}", "Content-Type": "video/mp4"})
        return {"id_remoto": r["id"], "url": f"https://youtube.com/shorts/{r['id']}",
                "cuenta": red["cuenta"], "cuenta_nombre": red["cuenta_nombre"]}

    def metricas(self, red):
        r = pedir("GET", "https://www.googleapis.com/youtube/v3/videos",
                  {"part": "statistics", "id": red["id_remoto"]}, cabeceras=_cab(red))
        s = (r.get("items") or [{}])[0].get("statistics", {})
        n = lambda k: int(s[k]) if k in s else None  # noqa: E731
        return {"vistas": n("viewCount"), "me_gusta": n("likeCount"), "comentarios": n("commentCount")}

    def cuentas(self):
        """Foto de cada canal conectado → {nombre: {seguidores, vistas_total, videos}}."""
        out = {}
        for cid, c in cuentas().items():
            try:
                r = pedir("GET", "https://www.googleapis.com/youtube/v3/channels", {"part": "statistics", "mine": "true"},
                          cabeceras=_cab({"cuenta": cid}))
            except ErrorRed as e:   # un canal caído no frena a los demás
                nucleo.anotar(f"Canal YouTube {c.get('nombre')}: {e}")
                continue
            s = (r.get("items") or [{}])[0].get("statistics", {})
            n = lambda k: int(s[k]) if k in s else None  # noqa: E731
            out[c.get("nombre") or cid] = {"seguidores": n("subscriberCount"), "vistas_total": n("viewCount"),
                                           "videos": n("videoCount")}
        return out
