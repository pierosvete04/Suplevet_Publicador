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
        "scope": ALCANCES, "access_type": "offline", "prompt": "consent", "state": st})


def recibir_codigo(codigo, estado):
    if estado not in _estados:
        raise ErrorRed("La respuesta de Google no coincide con la conexión que se pidió")
    _estados.discard(estado)
    c = _cliente()
    r = pedir("POST", "https://oauth2.googleapis.com/token", datos={
        "code": codigo, "client_id": c["client_id"], "client_secret": c["client_secret"],
        "redirect_uri": redireccion(), "grant_type": "authorization_code"})
    nucleo.guardar_token("youtube", {"access_token": r["access_token"], "refresh_token": r.get("refresh_token"),
                                     "vence": int(time.time()) + int(r.get("expires_in", 0))})


def token():
    t = nucleo.tokens().get("youtube")
    if not t:
        raise ErrorRed("YouTube no está conectado (pestaña Conexiones)")
    if t["vence"] - time.time() < 300:
        c = _cliente()
        r = pedir("POST", "https://oauth2.googleapis.com/token", datos={
            "client_id": c["client_id"], "client_secret": c["client_secret"],
            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        t = {**t, "access_token": r["access_token"], "vence": int(time.time()) + int(r.get("expires_in", 0))}
        nucleo.guardar_token("youtube", t)
    return t["access_token"]


class YouTube:
    def estado(self):
        falta = []
        if not nucleo.GOOGLE_SECRET.exists():
            falta.append("google_client_secret.json")
        if not nucleo.tokens().get("youtube"):
            falta.append("conectar la cuenta")
        return {"listo": not falta, "falta": falta}

    def publicar(self, pub, red):
        if pub["tipo"] != "video":
            raise ErrorRed("YouTube solo recibe videos")
        cfg = nucleo.config()
        ruta = pub["archivos"][0]
        texto = red["copy"]
        tags = [w.lstrip("#") for w in texto.split() if w.startswith("#")][:15]
        meta = {"snippet": {"title": (red.get("titulo") or texto.split("\n")[0])[:100], "description": texto[:5000],
                            "tags": tags, "categoryId": cfg["youtube_categoria"], "defaultLanguage": "es"},
                "status": {"privacyStatus": cfg["youtube_privacidad"], "selfDeclaredMadeForKids": False}}
        tam = os.path.getsize(ruta)
        ini = pedir("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                    cuerpo=json.dumps(meta).encode(), cabeceras={
                        "Authorization": f"Bearer {token()}", "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tam)})
        destino = ini["_cabeceras"].get("Location") or ini["_cabeceras"].get("location")
        with open(ruta, "rb") as f:
            r = pedir("PUT", destino, cuerpo=f.read(), tiempo=1800,
                      cabeceras={"Authorization": f"Bearer {token()}", "Content-Type": "video/mp4"})
        return {"id_remoto": r["id"], "url": f"https://youtube.com/shorts/{r['id']}"}

    def metricas(self, red):
        r = pedir("GET", "https://www.googleapis.com/youtube/v3/videos",
                  {"part": "statistics", "id": red["id_remoto"]}, cabeceras={"Authorization": f"Bearer {token()}"})
        s = (r.get("items") or [{}])[0].get("statistics", {})
        n = lambda k: int(s[k]) if k in s else None  # noqa: E731
        return {"vistas": n("viewCount"), "me_gusta": n("likeCount"), "comentarios": n("commentCount")}
