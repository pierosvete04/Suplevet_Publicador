"""TikTok por la Content Posting API.

Modo «borrador» (por defecto): el video llega a la bandeja de TikTok del celular y ahí le pones sonido y publicas.
Funciona sin que TikTok audite la app. Modo «directo»: publica solo, pero sin auditoría queda en privado (SELF_ONLY).
"""
import os
import secrets
import time
import urllib.parse

import nucleo

from . import ErrorRed, pedir

API = "https://open.tiktokapis.com/v2"
ALCANCES = "user.info.basic,video.upload,video.publish,video.list"


def _cred():
    c = nucleo.credenciales()
    return c.get("TIKTOK_CLIENT_KEY", ""), c.get("TIKTOK_CLIENT_SECRET", "")


def redireccion():
    return nucleo.credenciales().get("TIKTOK_REDIRECT_URI") or f"http://localhost:{nucleo.config()['puerto']}/oauth/tiktok"


_estados = set()


def url_conectar():
    clave, _ = _cred()
    if not clave:
        raise ErrorRed("Falta TIKTOK_CLIENT_KEY en credenciales.env")
    st = secrets.token_urlsafe(12)
    _estados.add(st)
    return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": clave, "scope": ALCANCES, "response_type": "code",
        "redirect_uri": redireccion(), "state": st})


def recibir_codigo(codigo, estado):
    if estado not in _estados:
        raise ErrorRed("La respuesta de TikTok no coincide con la conexión que se pidió")
    _estados.discard(estado)
    clave, secreto = _cred()
    r = pedir("POST", f"{API}/oauth/token/", datos={
        "client_key": clave, "client_secret": secreto, "code": codigo,
        "grant_type": "authorization_code", "redirect_uri": redireccion()})
    _guardar(r)


def _guardar(r):
    if not r.get("access_token"):
        raise ErrorRed(f"TikTok no dio token: {r}")
    nucleo.guardar_token("tiktok", {"access_token": r["access_token"], "refresh_token": r.get("refresh_token"),
                                    "vence": int(time.time()) + int(r.get("expires_in", 0)), "open_id": r.get("open_id")})


def token():
    t = nucleo.tokens().get("tiktok")
    if not t:
        raise ErrorRed("TikTok no está conectado (pestaña Conexiones)")
    if t["vence"] - time.time() < 300:
        clave, secreto = _cred()
        _guardar(pedir("POST", f"{API}/oauth/token/", datos={
            "client_key": clave, "client_secret": secreto, "grant_type": "refresh_token",
            "refresh_token": t["refresh_token"]}))
        t = nucleo.tokens()["tiktok"]
    return t["access_token"]


def _cab():
    return {"Authorization": f"Bearer {token()}"}


def _trozos(tam):
    """TikTok pide trozos de 5 a 64 MB; el último se lleva lo que sobra."""
    if tam <= 64 * 1024 * 1024:
        return tam, 1
    trozo = 10 * 1024 * 1024
    return trozo, tam // trozo


def _revisar(r):
    err = r.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise ErrorRed(f"TikTok: {err.get('code')} · {err.get('message')}")
    return r.get("data", {})


class TikTok:
    def estado(self):
        clave, secreto = _cred()
        t = nucleo.tokens().get("tiktok")
        falta = [k for k, v in (("TIKTOK_CLIENT_KEY", clave), ("TIKTOK_CLIENT_SECRET", secreto)) if not v]
        if not t:
            falta.append("conectar la cuenta")
        return {"listo": not falta, "falta": falta, "modo": nucleo.config()["tiktok_modo"]}

    def publicar(self, pub, red):
        if pub["tipo"] != "video":
            raise ErrorRed("Carruseles en TikTok todavía no: piden URL pública de un dominio verificado")
        ruta = pub["archivos"][0]
        tam = os.path.getsize(ruta)
        trozo, n = _trozos(tam)
        fuente = {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": trozo, "total_chunk_count": n}
        cfg = nucleo.config()
        if cfg["tiktok_modo"] == "directo":
            d = _revisar(pedir("POST", f"{API}/post/publish/video/init/", cabeceras=_cab(), json_={
                "post_info": {"title": red["copy"][:2200], "privacy_level": cfg["tiktok_privacidad"],
                              "disable_comment": False, "disable_duet": False, "disable_stitch": False},
                "source_info": fuente}))
        else:
            d = _revisar(pedir("POST", f"{API}/post/publish/inbox/video/init/", cabeceras=_cab(),
                               json_={"source_info": fuente}))
        with open(ruta, "rb") as f:
            for i in range(n):
                ini = i * trozo
                fin = tam - 1 if i == n - 1 else ini + trozo - 1
                f.seek(ini)
                pedir("PUT", d["upload_url"], cuerpo=f.read(fin - ini + 1), tiempo=900, cabeceras={
                    "Content-Type": "video/mp4", "Content-Range": f"bytes {ini}-{fin}/{tam}"})
        out = {"id_remoto": d["publish_id"], "url": None}
        if cfg["tiktok_modo"] != "directo":
            out["nota"] = "En la bandeja de TikTok: entra al celular, ponle sonido y publica con este copy"
        return out

    def estado_publicacion(self, publish_id):
        return _revisar(pedir("POST", f"{API}/post/publish/status/fetch/", cabeceras=_cab(),
                              json_={"publish_id": publish_id}))

    def metricas(self, red):
        vid = red.get("video_id")
        if not vid:
            ids = self.estado_publicacion(red["id_remoto"]).get("publicaly_available_post_id") or []
            if not ids:
                return {}
            vid = str(ids[0])
            red["video_id"] = vid
        d = _revisar(pedir("POST", f"{API}/video/query/?fields=id,view_count,like_count,comment_count,share_count",
                           cabeceras=_cab(), json_={"filters": {"video_ids": [vid]}}))
        v = (d.get("videos") or [{}])[0]
        return {"vistas": v.get("view_count"), "me_gusta": v.get("like_count"),
                "comentarios": v.get("comment_count"), "compartidos": v.get("share_count")}
