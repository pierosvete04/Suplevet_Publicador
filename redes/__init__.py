"""Conectores por red. Cada uno tiene publicar(pub, red) → {id_remoto, url} y metricas(red) → {vistas, me_gusta, …}."""
import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ErrorRed(Exception):
    pass


class Dudoso(ErrorRed):
    """Falló el último paso (el que publica) sin respuesta clara: puede que haya salido. No se reintenta solo."""


def final(metodo, url, **kw):
    """El pedido que publica de verdad. Si se corta (sin respuesta, tiempo agotado, error 5xx de la red), no se sabe
    si salió: Dudoso, para que la pieza quede en «revisar» y «Reintentar» no la suba dos veces."""
    try:
        return pedir(metodo, url, **kw)
    except ErrorRed as e:
        if str(e)[:1] == "5":
            raise Dudoso(f"La red respondió con un error al publicar ({str(e)[:120]})") from None
        raise
    except (OSError, ValueError) as e:      # sin conexión, tiempo agotado, conexión cortada
        raise Dudoso(f"Se cortó la conexión al publicar ({e})") from None


def pedir(metodo, url, params=None, datos=None, json_=None, cabeceras=None, cuerpo=None, tiempo=300):
    """HTTP sin dependencias. datos = formulario, json_ = JSON, cuerpo = bytes ya armados."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    cab = dict(cabeceras or {})
    if json_ is not None:
        cuerpo = json.dumps(json_).encode()
        cab.setdefault("Content-Type", "application/json; charset=UTF-8")
    elif datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode()
        cab.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=tiempo) as r:
            texto = r.read().decode("utf-8", "replace")
            cabeceras_resp = dict(r.headers)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        raise ErrorRed(f"{e.code} en {url.split('?')[0]}: {texto[:600]}") from None
    try:
        out = json.loads(texto) if texto else {}
    except ValueError:
        out = {"_texto": texto}
    if isinstance(out, dict):
        out["_cabeceras"] = cabeceras_resp
    return out


def multipart(campos, archivos):
    """campos {k: v}, archivos {k: ruta} → (bytes, content-type)."""
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, ruta in archivos.items():
        tipo = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        with open(ruta, "rb") as f:
            datos = f.read()
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"; filename="{ruta.name}"\r\n'
                      f'Content-Type: {tipo}\r\n\r\n'.encode() + datos + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


from . import meta, tiktok, youtube  # noqa: E402

CONECTORES = {"instagram": meta.Instagram(), "facebook": meta.Facebook(),
              "tiktok": tiktok.TikTok(), "youtube": youtube.YouTube()}


def estado_conexiones():
    return {red: c.estado() for red, c in CONECTORES.items()}
