"""Lo que ya salió en cada red, para la pestaña Publicadas.

Todas las redes se devuelven con la misma forma:
{red, cuenta, id, clase: video|post, tipo, img, fotos[], texto, link, fecha, met{}, formato: 9:16|4:5|1:1|16:9}
Las portadas pasan por /img (se guardan en cache_img/) porque las URL de las redes vencen a las pocas horas.
"""
import hashlib
import struct
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import nucleo

from . import ErrorRed, meta, pedir, tiktok, youtube

CACHE = nucleo.PUBLICACION / "cache_img"
HOSTS = ("fbcdn.net", "cdninstagram.com", "tiktokcdn.com", "tiktokcdn-us.com", "ibyteimg.com", "ytimg.com", "ggpht.com", "googleusercontent.com")
_memo = {"cuando": 0, "datos": None}
_candado = threading.Lock()


# ---------- Portadas ----------

def permitido(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return url.startswith("https://") and any(host == h or host.endswith("." + h) for h in HOSTS)


def bajar(url):
    """Guarda la portada en cache_img/ y devuelve la ruta (o None si no es una imagen)."""
    if not permitido(url):
        return None
    CACHE.mkdir(exist_ok=True)
    ruta = CACHE / (hashlib.md5(url.split("?")[0].encode()).hexdigest()[:20] + ".img")
    if not ruta.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                datos = r.read(15 * 1024 * 1024)
        except Exception:
            return None
        if b"ftyp" in datos[:16]:   # es el video, no una imagen
            return None
        ruta.write_bytes(datos)
    return ruta


def medida(ruta):
    """Ancho y alto leyendo solo la cabecera (JPEG, PNG o WebP)."""
    try:
        d = ruta.read_bytes()[:256 * 1024]
        if d[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", d[16:24])
        if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
            if d[12:16] == b"VP8X":
                return int.from_bytes(d[24:27], "little") + 1, int.from_bytes(d[27:30], "little") + 1
            if d[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", d[26:30])
                return w & 0x3FFF, h & 0x3FFF
        i = 2
        while i + 9 < len(d):
            if d[i] != 0xFF:
                i += 1
                continue
            if d[i + 1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", d[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    except (OSError, struct.error):
        pass
    return None


def formato(wh, es_video):
    if es_video or not wh:
        return "9:16" if es_video else "1:1"
    r = wh[0] / wh[1]
    return "9:16" if r < .62 else "4:5" if r < .9 else "1:1" if r < 1.1 else "16:9"


def _iso(t):
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t, timezone.utc).isoformat()
    return t


# ---------- Cada red ----------

def _instagram():
    out = []
    for ig, cu in meta.cuentas_red("instagram").items():
        out += _instagram_de(ig, meta.token_de("instagram", cu))
    return out


def _instagram_de(ig, tok):
    r = pedir("GET", f"{meta.base()}/{ig}/media", {
        "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count,"
                  "children{media_type,media_url,thumbnail_url},insights.metric(reach,saved,shares)",
        "limit": 36, "access_token": tok})
    if "error" in r and "insights" in str(r.get("error")):   # algunas cuentas no dan insights por publicación
        r = pedir("GET", f"{meta.base()}/{ig}/media", {
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count,children{media_type,media_url,thumbnail_url}",
            "limit": 36, "access_token": tok})
    yo = pedir("GET", f"{meta.base()}/{ig}", {"fields": "username", "access_token": tok})
    cuenta = "@" + (yo.get("username") or "instagram")
    out = []
    for m in r.get("data", []):
        vid = m.get("media_type") == "VIDEO"
        img = m.get("thumbnail_url") or m.get("media_url")
        hijos = [h.get("thumbnail_url") or h.get("media_url") for h in (m.get("children") or {}).get("data", [])]
        ins = {x["name"]: (x.get("values") or [{}])[0].get("value") for x in (m.get("insights") or {}).get("data", [])}
        out.append({"red": "instagram", "cuenta": cuenta, "id": m["id"],
                    "clase": "video" if vid else "post",
                    "tipo": "Carrusel" if m.get("media_type") == "CAROUSEL_ALBUM" else "Reel" if vid else "Foto",
                    "img": img, "fotos": hijos or [img], "texto": m.get("caption") or "", "link": m.get("permalink"),
                    "fecha": m.get("timestamp"), "es_video": vid,
                    "met": {"Me gusta": m.get("like_count"), "Comentarios": m.get("comments_count"),
                            "Alcance": ins.get("reach"), "Guardados": ins.get("saved"), "Compartidos": ins.get("shares")}})
    return out


def _facebook():
    out = []
    for pid, cu in meta.cuentas_red("facebook").items():
        out += _facebook_de(pid, cu["nombre"], meta.token_de("facebook", cu))
    return out


def _facebook_de(pid, nombre, tok):
    r = pedir("GET", f"{meta.base()}/{pid}/posts", {
        "fields": "id,message,created_time,full_picture,permalink_url,attachments{media_type,subattachments.limit(10){media{image{src}}}}",
        "limit": 24, "access_token": tok})
    out = []
    for m in r.get("data", []):
        at = ((m.get("attachments") or {}).get("data") or [{}])[0]
        sub = [s.get("media", {}).get("image", {}).get("src") for s in (at.get("subattachments") or {}).get("data", [])]
        sub = [s for s in sub if s]
        img = m.get("full_picture") or (sub[0] if sub else None)
        if not img:
            continue
        vid = "video" in (at.get("media_type") or "")
        out.append({"red": "facebook", "cuenta": nombre, "id": m["id"], "clase": "video" if vid else "post",
                    "tipo": "Álbum" if len(sub) > 1 else "Video" if vid else "Foto", "img": img, "fotos": sub or [img],
                    "texto": m.get("message") or "", "link": m.get("permalink_url"), "fecha": m.get("created_time"),
                    "es_video": vid, "met": {}})
    return out


def _tiktok():
    out = []
    for oid, cu in tiktok.cuentas().items():
        r = pedir("POST", f"{tiktok.API}/video/list/?fields=id,title,cover_image_url,share_url,create_time,view_count,like_count,comment_count,share_count",
                  cabeceras=tiktok._cab({"cuenta": oid}), json_={"max_count": 20})
        for v in (r.get("data") or {}).get("videos", []):
            out.append({"red": "tiktok", "cuenta": cu.get("nombre"), "id": v["id"], "clase": "video", "tipo": "Video",
                        "img": v.get("cover_image_url"), "fotos": [v.get("cover_image_url")], "texto": v.get("title") or "",
                        "link": v.get("share_url"), "fecha": _iso(v.get("create_time")), "es_video": True,
                        "met": {"Vistas": v.get("view_count"), "Me gusta": v.get("like_count"),
                                "Comentarios": v.get("comment_count"), "Compartidos": v.get("share_count")}})
    return out


def _youtube():
    out = []
    for cid, cu in youtube.cuentas().items():
        cab = youtube._cab({"cuenta": cid})
        ch = pedir("GET", "https://www.googleapis.com/youtube/v3/channels", {"part": "contentDetails", "mine": "true"}, cabeceras=cab)
        sube = (ch.get("items") or [{}])[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not sube:
            continue
        pl = pedir("GET", "https://www.googleapis.com/youtube/v3/playlistItems",
                   {"part": "contentDetails", "playlistId": sube, "maxResults": 24}, cabeceras=cab)
        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if not ids:
            continue
        vs = pedir("GET", "https://www.googleapis.com/youtube/v3/videos", {"part": "snippet,statistics", "id": ",".join(ids)}, cabeceras=cab)
        for v in vs.get("items", []):
            sn, st = v.get("snippet", {}), v.get("statistics", {})
            th = sn.get("thumbnails", {})
            n = lambda k: int(st[k]) if k in st else None  # noqa: E731
            img = (th.get("maxres") or th.get("high") or th.get("medium") or {}).get("url")
            out.append({"red": "youtube", "cuenta": cu.get("nombre"), "id": v["id"], "clase": "video", "tipo": "Short",
                        "img": img, "fotos": [img], "texto": sn.get("title") or "", "link": f"https://youtube.com/shorts/{v['id']}",
                        "fecha": sn.get("publishedAt"), "es_video": True,
                        "met": {"Vistas": n("viewCount"), "Me gusta": n("likeCount"), "Comentarios": n("commentCount")}})
    return out


FUENTES = {"instagram": _instagram, "facebook": _facebook, "tiktok": _tiktok, "youtube": _youtube}


def todas(forzar=False):
    """Junta las 4 redes. Guarda el resultado 10 minutos para no gastar llamadas a las APIs."""
    with _candado:
        if not forzar and _memo["datos"] and time.time() - _memo["cuando"] < 600:
            return _memo["datos"]
        piezas, errores = [], {}
        for red, f in FUENTES.items():
            try:
                piezas += f()
            except ErrorRed as e:
                errores[red] = str(e)[:300]
            except Exception as e:  # una red caída no frena a las demás
                errores[red] = f"{type(e).__name__}: {e}"[:300]
        # Las fotos necesitan su medida real; los videos de estas redes son verticales
        with ThreadPoolExecutor(8) as ex:
            rutas = dict(zip([p["img"] for p in piezas], ex.map(lambda u: bajar(u) if u else None, [p["img"] for p in piezas])))
        for p in piezas:
            ruta = rutas.get(p["img"])
            p["formato"] = formato(medida(ruta) if ruta else None, p.pop("es_video"))
            p["met"] = {k: v for k, v in p["met"].items() if v is not None}
            p["img"] = local(p["img"])
            p["fotos"] = [local(u) for u in p["fotos"] if u]
        piezas.sort(key=lambda p: p.get("fecha") or "", reverse=True)
        _memo.update(cuando=time.time(), datos={"piezas": piezas, "errores": errores,
                                                 "traido": datetime.now().isoformat(timespec="minutes")})
        return _memo["datos"]


def local(url):
    return "/img?u=" + urllib.parse.quote(url, safe="") if url and permitido(url) else url
