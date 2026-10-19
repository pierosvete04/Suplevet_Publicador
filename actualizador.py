"""Actualizaciones automáticas desde GitHub Releases (mismo sistema que la sala de edición).

Cada versión publicada (tag vX.Y.Z) trae lo que arma GitHub Actions:
  - app-vX.Y.Z.zip                 solo el código. Es lo que se baja al actualizar.
  - PublicadorSuplevet-vX.Y.Z.zip  la versión completa con el .exe; solo hace falta si cambia el lanzador.
  - PublicadorSuplevet-Instalador-vX.Y.Z.exe

El programa pregunta al abrir y cada hora. Al aceptar, baja app-*.zip, reemplaza la carpeta del código
(los datos están aparte) y se reinicia solo.
"""
import io
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import nucleo

LANZADOR = os.environ.get("PUBLICADOR_LANZADOR")  # versión del .exe; vacío si se corre con py (desarrollo)
CODIGO_REINICIO = 42
_cache = {"t": 0, "datos": None}


def _cfg():
    c = nucleo.config()
    return c.get("actualizaciones", {}).get("repo", ""), nucleo.credenciales().get("GITHUB_TOKEN", "")


def _pedir(url, binario=False):
    _, token = _cfg()
    h = {"Accept": "application/octet-stream" if binario else "application/vnd.github+json",
         "User-Agent": "PublicadorSuplevet"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120 if binario else 15) as r:
        return r.read()


def _num(v):
    return tuple(int(x) for x in v.lstrip("v").split(".")[:3] if x.isdigit())


def revisar(forzar=False):
    repo, _ = _cfg()
    out = {"actual": nucleo.VERSION, "portable": bool(LANZADOR)}
    if not repo:
        return {**out, "error": "Sin repositorio configurado"}
    if not forzar and _cache["datos"] and time.time() - _cache["t"] < 3600:
        return _cache["datos"]
    try:
        rel = json.loads(_pedir(f"https://api.github.com/repos/{repo}/releases/latest"))
        nueva = rel["tag_name"].lstrip("v")
        app = next((a for a in rel["assets"] if a["name"].startswith("app-") and a["name"].endswith(".zip")), None)
        completa = next((a for a in rel["assets"] if "Instalador" in a["name"]), None) \
            or next((a for a in rel["assets"] if a["name"].startswith("PublicadorSuplevet-")), None)
        minimo = next((l.split(":", 1)[1].strip() for l in (rel.get("body") or "").splitlines()
                       if l.lower().startswith("lanzador minimo:")), "0")
        out.update({
            "nueva": nueva if _num(nueva) > _num(nucleo.VERSION) else None,
            "notas": (rel.get("body") or "").strip()[:1500],
            "url_app": app["url"] if app else None,
            "url_completa": completa["browser_download_url"] if completa else rel.get("html_url"),
            "completa": bool(LANZADOR) and _num(minimo) > _num(LANZADOR or "0"),
        })
    except Exception as e:  # sin internet, repo todavía sin releases, etc.
        out["error"] = f"No se pudo revisar: {e}"
    _cache.update(t=time.time(), datos=out)
    return out


def aplicar():
    """Baja el código nuevo y lo pone en lugar del actual. Devuelve la versión instalada."""
    info = revisar(forzar=True)
    if not info.get("nueva"):
        raise RuntimeError(info.get("error") or "Ya tienes la última versión")
    if not info.get("portable"):
        raise RuntimeError("En desarrollo se actualiza con git pull, no desde aquí")
    if info.get("completa"):
        raise RuntimeError("Esta versión necesita bajar el instalador completo: " + (info.get("url_completa") or ""))
    if not info.get("url_app"):
        raise RuntimeError("El release no trae app-*.zip")
    datos = _pedir(info["url_app"], binario=True)
    destino = nucleo.AQUI
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(datos)).extractall(tmp)
        nuevo = Path(tmp)
        if not (nuevo / "servidor.py").exists():
            hijos = [d for d in nuevo.iterdir() if d.is_dir()]
            nuevo = hijos[0] if len(hijos) == 1 else nuevo
        if not (nuevo / "servidor.py").exists() or not (nuevo / "VERSION").exists():
            raise RuntimeError("El paquete descargado no es válido")
        respaldo = destino.with_name(destino.name + "_anterior")
        shutil.rmtree(respaldo, ignore_errors=True)
        shutil.copytree(destino, respaldo, ignore=shutil.ignore_patterns("__pycache__"))
        try:
            shutil.copytree(nuevo, destino, dirs_exist_ok=True)
        except Exception:
            shutil.copytree(respaldo, destino, dirs_exist_ok=True)  # vuelve a la versión anterior
            raise
    nucleo.anotar(f"Actualizado a la versión {info['nueva']}")
    return info["nueva"]


def reiniciar_luego(segundos=1.0):
    """El lanzador vuelve a abrir el servidor cuando el proceso sale con el código 42."""
    def salir():
        time.sleep(segundos)
        os._exit(CODIGO_REINICIO)
    threading.Thread(target=salir, daemon=True).start()
