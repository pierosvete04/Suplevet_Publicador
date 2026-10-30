"""TikTok por la Content Posting API.

Modo «borrador» (por defecto): el video llega a la bandeja de TikTok del celular y ahí le pones sonido y publicas.
Funciona sin que TikTok audite la app. Modo «directo»: publica solo, pero sin auditoría queda en privado (SELF_ONLY).

En modo directo se siguen las reglas de TikTok para apps que publican (las revisa en la auditoría): antes de publicar
se pregunta a TikTok qué deja esa cuenta (info_creador), la persona elige en cada pieza quién puede verla (sin opción
marcada de antemano), si permite comentarios, dúos y stitch, y si es contenido comercial (red["ajustes_tiktok"]).
"""
import hashlib
import os
import secrets
import time
import urllib.parse

import nucleo

from . import ErrorRed, pedir

API = "https://open.tiktokapis.com/v2"
ALCANCES = "user.info.basic,user.info.stats,video.upload,video.publish,video.list"


def _cred():
    c = nucleo.credenciales()
    return c.get("TIKTOK_CLIENT_KEY", ""), c.get("TIKTOK_CLIENT_SECRET", "")


def redireccion():
    return nucleo.credenciales().get("TIKTOK_REDIRECT_URI") or f"http://localhost:{nucleo.puerto()}/oauth/tiktok"


_estados = {}  # state -> code_verifier


def url_conectar():
    clave, _ = _cred()
    if not clave:
        raise ErrorRed("Falta TIKTOK_CLIENT_KEY en credenciales.env")
    st = secrets.token_urlsafe(12)
    # PKCE: TikTok lo exige en apps de escritorio. Ojo: el challenge va en hex, no en base64.
    verificador = secrets.token_urlsafe(48)
    _estados[st] = verificador
    return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": clave, "scope": ALCANCES, "response_type": "code",
        "redirect_uri": redireccion(), "state": st,
        "code_challenge": hashlib.sha256(verificador.encode()).hexdigest(), "code_challenge_method": "S256"})


def recibir_codigo(codigo, estado):
    if estado not in _estados:
        raise ErrorRed("La respuesta de TikTok no coincide con la conexión que se pidió")
    verificador = _estados.pop(estado)
    clave, secreto = _cred()
    r = pedir("POST", f"{API}/oauth/token/", datos={
        "client_key": clave, "client_secret": secreto, "code": codigo,
        "grant_type": "authorization_code", "redirect_uri": redireccion(), "code_verifier": verificador})
    t = _guardar(r)
    try:
        u = _revisar(pedir("GET", f"{API}/user/info/?fields=open_id,display_name",
                           cabeceras={"Authorization": f"Bearer {t['access_token']}"})).get("user", {})
        t["nombre"] = u.get("display_name") or t["nombre"]
    except ErrorRed as e:
        nucleo.anotar(f"TikTok: no se pudo leer el nombre de la cuenta: {e}")
    _escribir_cuenta(t)
    if not nucleo.config().get("tiktok_cuenta"):
        nucleo.guardar_config({"tiktok_cuenta": t["open_id"]})
    return t


# ---------- Varias cuentas: tokens.json → "tiktok_cuentas": {open_id: {...}} ----------

def cuentas():
    t = nucleo.tokens()
    cs = {k: v for k, v in (t.get("tiktok_cuentas") or {}).items() if isinstance(v, dict)}  # guardar_token mete "guardado"
    viejo = t.get("tiktok")   # versiones anteriores guardaban una sola cuenta
    if viejo and viejo.get("open_id") and viejo["open_id"] not in cs:
        cs[viejo["open_id"]] = {**viejo, "nombre": viejo.get("nombre") or "Cuenta TikTok"}
    return cs


def _escribir_cuenta(c):
    with nucleo._candado_tokens:   # leer y guardar juntos: si no, dos cuentas que se renuevan a la vez se pisan
        nucleo.guardar_token("tiktok_cuentas", {**cuentas(), c["open_id"]: c})


def quitar_cuenta(open_id):
    with nucleo._candado_tokens:
        cs = cuentas()
        cs.pop(open_id, None)
        nucleo.guardar_token("tiktok_cuentas", cs)
        if nucleo.tokens().get("tiktok", {}).get("open_id") == open_id:
            nucleo.guardar_token("tiktok", {})
    if nucleo.config().get("tiktok_cuenta") == open_id:
        nucleo.guardar_config({"tiktok_cuenta": next(iter(cs), None)})


def cuenta_de(red=None):
    """La cuenta de una pieza (red["cuenta"]) o la que está por defecto."""
    cs = cuentas()
    if not cs:
        raise ErrorRed("TikTok no está conectado (pestaña Conexiones)")
    oid = (red or {}).get("cuenta") or nucleo.config().get("tiktok_cuenta")
    if oid not in cs:
        if (red or {}).get("cuenta"):
            raise ErrorRed("La cuenta de TikTok elegida para esta pieza ya no está conectada")
        oid = next(iter(cs))
    return cs[oid]


def _guardar(r, anterior=None):
    if not r.get("access_token"):
        raise ErrorRed(f"TikTok no dio token: {r}")
    oid = r.get("open_id") or (anterior or {}).get("open_id")
    return {**(anterior or {"nombre": "Cuenta TikTok"}), "access_token": r["access_token"],
            "refresh_token": r.get("refresh_token"), "vence": int(time.time()) + int(r.get("expires_in", 0)),
            "open_id": oid, "guardado": int(time.time())}


def token(red=None):
    t = cuenta_de(red)
    if t["vence"] - time.time() < 300:
        # TikTok cambia el refresh_token en cada renovación: dos hilos renovando la misma cuenta la desconectarían
        with nucleo._candado_tokens:
            t = cuenta_de(red)   # quizá otro hilo ya la renovó mientras esperaba
            if t["vence"] - time.time() < 300:
                clave, secreto = _cred()
                try:
                    t = _guardar(pedir("POST", f"{API}/oauth/token/", datos={
                        "client_key": clave, "client_secret": secreto, "grant_type": "refresh_token",
                        "refresh_token": t["refresh_token"]}), t)
                except ErrorRed as e:
                    if "invalid_grant" in str(e) or "refresh_token" in str(e):
                        _escribir_cuenta({**t, "vencida": True})   # Conexiones lo muestra hasta que se reconecte
                        raise ErrorRed(f"Se venció el permiso de la cuenta de TikTok «{t.get('nombre')}»: "
                                       "reconéctala en Conexiones") from None
                    raise
                _escribir_cuenta(t)
    return t["access_token"]


def _cab(red=None):
    return {"Authorization": f"Bearer {token(red)}"}


def _trozos(tam):
    """TikTok pide trozos de 5 a 64 MB; el último se lleva lo que sobra."""
    if tam <= 64 * 1024 * 1024:
        return tam, 1
    trozo = 10 * 1024 * 1024
    return trozo, tam // trozo


# ---------- Modo directo: lo que pide TikTok antes de publicar ----------
PRIVACIDADES = {"PUBLIC_TO_EVERYONE": "Todos", "MUTUAL_FOLLOW_FRIENDS": "Amigos", "FOLLOWER_OF_CREATOR": "Seguidores",
                "SELF_ONLY": "Solo yo"}


def info_creador(cuenta=None):
    """Lo que TikTok deja hacer hoy a esa cuenta: nombre, privacidades posibles, si tiene apagados los comentarios,
    dúos o stitch y cuántos segundos puede durar el video."""
    d = _revisar(pedir("POST", f"{API}/post/publish/creator_info/query/", cabeceras=_cab({"cuenta": cuenta} if cuenta else None),
                       json_={}))
    return {"nombre": d.get("creator_nickname"), "usuario": d.get("creator_username"), "foto": d.get("creator_avatar_url"),
            "privacidades": [{"id": p, "nombre": PRIVACIDADES.get(p, p)} for p in d.get("privacy_level_options") or []],
            "sin_comentarios": bool(d.get("comment_disabled")), "sin_duo": bool(d.get("duet_disabled")),
            "sin_stitch": bool(d.get("stitch_disabled")), "max_segundos": d.get("max_video_post_duration_sec")}


def _post_info(red):
    """post_info del modo directo con lo que la persona eligió en la pieza (TikTok no deja poner valores por defecto)."""
    aj = red.get("ajustes_tiktok") or {}
    creador = info_creador(red.get("cuenta"))
    validas = [p["id"] for p in creador["privacidades"]]
    if not aj.get("privacidad"):
        raise ErrorRed("Falta elegir quién puede ver el video en TikTok (se elige en cada pieza)")
    if aj["privacidad"] not in validas:
        raise ErrorRed(f"Esa cuenta de TikTok no deja publicar con privacidad «{PRIVACIDADES.get(aj['privacidad'], aj['privacidad'])}»")
    if aj.get("comercial") and not (aj.get("marca_propia") or aj.get("contenido_marca")):
        raise ErrorRed("Marcaste contenido comercial: elige «Tu marca», «Contenido de marca» o las dos")
    if aj.get("comercial") and aj.get("contenido_marca") and aj["privacidad"] == "SELF_ONLY":
        raise ErrorRed("El contenido de marca no puede ser privado («Solo yo»)")
    return {"title": red["copy"][:2200], "privacy_level": aj["privacidad"],
            "disable_comment": creador["sin_comentarios"] or not aj.get("comentarios"),
            "disable_duet": creador["sin_duo"] or not aj.get("duo"),
            "disable_stitch": creador["sin_stitch"] or not aj.get("stitch"),
            "brand_organic_toggle": bool(aj.get("comercial") and aj.get("marca_propia")),
            "brand_content_toggle": bool(aj.get("comercial") and aj.get("contenido_marca"))}


def _revisar(r):
    err = r.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise ErrorRed(f"TikTok: {err.get('code')} · {err.get('message')}")
    return r.get("data", {})


class TikTok:
    cuenta_de = staticmethod(cuenta_de)

    def estado(self):
        clave, secreto = _cred()
        cs = cuentas()
        conectable = bool(clave and secreto)
        falta = [] if conectable else ["Faltan las llaves de TikTok: ponlas en Preparación"]
        if not cs and conectable:
            falta.append("Conectar la cuenta")
        defecto = nucleo.config().get("tiktok_cuenta")
        lista = [{"id": k, "nombre": c.get("nombre"), "defecto": k == defecto or (defecto not in cs and i == 0),
                  "vencida": bool(c.get("vencida"))}
                 for i, (k, c) in enumerate(cs.items())]
        return {"listo": not falta, "falta": falta, "modo": nucleo.config()["tiktok_modo"], "cuentas": lista,
                "conectable": conectable}

    def publicar(self, pub, red):
        if pub["tipo"] != "video":
            raise ErrorRed("Carruseles en TikTok todavía no: piden URL pública de un dominio verificado")
        ruta = pub["archivos"][0]
        tam = os.path.getsize(ruta)
        trozo, n = _trozos(tam)
        fuente = {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": trozo, "total_chunk_count": n}
        cfg = nucleo.config()
        cuenta = cuenta_de(red)
        red["cuenta"], red["cuenta_nombre"] = cuenta["open_id"], cuenta.get("nombre")
        if cfg["tiktok_modo"] == "directo":
            try:
                d = _revisar(pedir("POST", f"{API}/post/publish/video/init/", cabeceras=_cab(red), json_={
                    "post_info": _post_info(red), "source_info": fuente}))
            except ErrorRed as e:
                if "unaudited_client_can_only_post_to_private_accounts" in str(e):
                    raise ErrorRed("TikTok todavía no aprobó la app: en modo Directo solo deja publicar en cuentas privadas. "
                                   "Usa el modo Borrador (Conexiones › Cómo sube a TikTok) o pon la cuenta en privado "
                                   "mientras tanto.") from None
                raise
        else:
            d = _revisar(pedir("POST", f"{API}/post/publish/inbox/video/init/", cabeceras=_cab(red),
                               json_={"source_info": fuente}))
        with open(ruta, "rb") as f:
            for i in range(n):
                ini = i * trozo
                fin = tam - 1 if i == n - 1 else ini + trozo - 1
                f.seek(ini)
                pedir("PUT", d["upload_url"], cuerpo=f.read(fin - ini + 1), tiempo=900, cabeceras={
                    "Content-Type": "video/mp4", "Content-Range": f"bytes {ini}-{fin}/{tam}"})
        out = {"id_remoto": d["publish_id"], "url": None, "cuenta": red["cuenta"], "cuenta_nombre": red["cuenta_nombre"]}
        if cfg["tiktok_modo"] != "directo":
            out["nota"] = "En la bandeja de TikTok: entra al celular, ponle sonido y publica con este copy"
        else:
            out["nota"] = "TikTok está procesando el video: puede tardar unos minutos en aparecer en el perfil"
        return out

    def estado_publicacion(self, publish_id, red=None):
        return _revisar(pedir("POST", f"{API}/post/publish/status/fetch/", cabeceras=_cab(red),
                              json_={"publish_id": publish_id}))

    def metricas(self, red):
        vid = red.get("video_id")
        if not vid:
            ids = self.estado_publicacion(red["id_remoto"], red).get("publicaly_available_post_id") or []
            if not ids:
                return {}
            vid = str(ids[0])
            red["video_id"] = vid
        d = _revisar(pedir("POST", f"{API}/video/query/?fields=id,view_count,like_count,comment_count,share_count",
                           cabeceras=_cab(red), json_={"filters": {"video_ids": [vid]}}))
        v = (d.get("videos") or [{}])[0]
        return {"vistas": v.get("view_count"), "me_gusta": v.get("like_count"),
                "comentarios": v.get("comment_count"), "compartidos": v.get("share_count")}

    def cuentas(self):
        """Foto de cada cuenta conectada (permiso user.info.stats) → {nombre: {...}}."""
        out = {}
        for oid, c in cuentas().items():
            try:
                d = _revisar(pedir("GET", f"{API}/user/info/?fields=follower_count,following_count,likes_count,video_count",
                                   cabeceras=_cab({"cuenta": oid})))
            except ErrorRed as e:   # una cuenta caída no frena a las demás
                nucleo.anotar(f"Cuenta TikTok {c.get('nombre')}: {e}")
                continue
            u = d.get("user", {})
            out[c.get("nombre") or oid] = {"seguidores": u.get("follower_count"), "siguiendo": u.get("following_count"),
                                           "me_gusta_total": u.get("likes_count"), "videos": u.get("video_count")}
        return out
