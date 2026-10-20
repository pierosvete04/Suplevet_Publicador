"""Núcleo del publicador: rutas, credenciales, cola de publicaciones, importar paquetes y el reloj que publica a la hora.

El código y los datos van separados. Los datos (credenciales, cola, pauta, tokens, métricas) viven en la carpeta
que dice PUBLICADOR_DATOS (la pone el .exe); si no, en 2_PUBLICACION. Nada de los datos va a GitHub.
"""
import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PUBLICACION = Path(os.environ.get("PUBLICADOR_DATOS") or AQUI.parent)   # 2_PUBLICACION o datos/ del portable
PUBLICACION.mkdir(parents=True, exist_ok=True)
VERSION = (AQUI / "VERSION").read_text(encoding="utf-8").strip() if (AQUI / "VERSION").exists() else "0.0.0"
CREDENCIALES = PUBLICACION / "credenciales.env"
GOOGLE_SECRET = PUBLICACION / "google_client_secret.json"
TOKENS = PUBLICACION / "tokens.json"           # tokens de TikTok y YouTube que se ganan al conectar
COLA = PUBLICACION / "cola.json"
PAUTA = PUBLICACION / "pauta.json"
METRICAS = PUBLICACION / "metricas"
COPIES = PUBLICACION / "copies"
REGISTRO = PUBLICACION / "registro.log"
CONFIG_PATH = PUBLICACION / "config_publicador.json"   # lo que cambias en la pantalla; el código no lo pisa

REDES_VIDEO = ["instagram", "facebook", "tiktok", "youtube"]
REDES_CARRUSEL = ["instagram", "facebook"]     # TikTok fotos pide URL pública de dominio verificado: más adelante
LIMITES = {"instagram": 2200, "facebook": 63000, "tiktok": 2200, "youtube": 5000, "youtube_titulo": 100}

_candado = threading.RLock()


# ---------- Utilidades ----------

def leer_json(ruta, defecto):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def anotar(texto):
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texto}"
    print(linea)
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def registro(n=200):
    try:
        return REGISTRO.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []


CONFIG_DEFECTO = {
    "simular": True,                 # True: no sale nada a redes, solo se anota lo que se haría
    "puerto": 8766,
    "carpeta_estrategia": "",        # vacío: busca 0_ESTRATEGIA al lado de 2_PUBLICACION
    "actualizaciones": {"repo": "pierosvete04/Suplevet_Publicador"},
    "graph_version": "v23.0",
    "horarios_video": ["09:00", "12:00", "15:00", "18:00", "21:00"],
    "horario_carrusel": "13:00",
    "youtube_cuenta": None,         # id del canal de YouTube por defecto
    "tiktok_cuenta": None,          # open_id de la cuenta de TikTok por defecto (hay varias en tokens.json)
    "tiktok_modo": "borrador",       # borrador: llega a la bandeja de TikTok y tú publicas desde el celular · directo
    "tiktok_privacidad": "SELF_ONLY",  # mientras TikTok no apruebe la app, solo deja SELF_ONLY en modo directo
    "youtube_privacidad": "public",
    "youtube_categoria": "15",       # 15 = Mascotas y animales
    "pauta": {
        "pais": ["PE"],
        "edad_min": 25,
        "edad_max": 55,
        "enlace": "https://wa.me/51999999999",
        "boton": "LEARN_MORE",
        "moneda": "PEN",
    },
}


def config():
    c = json.loads(json.dumps(CONFIG_DEFECTO))
    guardada = leer_json(CONFIG_PATH, {})
    for k, v in guardada.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k].update(v)
        else:
            c[k] = v
    return c


def guardar_config(cambios):
    c = leer_json(CONFIG_PATH, {})
    for k, v in cambios.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k].update(v)
        else:
            c[k] = v
    escribir_json(CONFIG_PATH, c)


def credenciales():
    out = {}
    try:
        for linea in CREDENCIALES.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def tokens():
    return leer_json(TOKENS, {})


def guardar_token(red, datos):
    with _candado:
        t = tokens()
        t[red] = {**datos, "guardado": int(time.time())}
        escribir_json(TOKENS, t)


# ---------- Estrategia: brief y reglas ----------

def estrategia():
    """Carpeta 0_ESTRATEGIA: la de la configuración o la que está al lado de los datos."""
    c = config().get("carpeta_estrategia")
    if c:
        return Path(c)
    for cand in (PUBLICACION.parent / "0_ESTRATEGIA", AQUI.parent.parent / "0_ESTRATEGIA",
                 PUBLICACION.parent.parent / "0_ESTRATEGIA"):
        if cand.is_dir():
            return cand
    return PUBLICACION / "0_ESTRATEGIA"


def brief_de(semana):
    for b in sorted(estrategia().glob("semanas/*/brief.json")):
        d = leer_json(b, {})
        if d.get("semana") == semana:
            return d
    return {}


def palabras_prohibidas(semana):
    """Palabras del brief (campo «evitar») que no pueden ir en el copy."""
    out = []
    for e in brief_de(semana).get("evitar", []):
        p = re.split(r"[\s(]", e.strip(), maxsplit=1)[0].strip("«»\"'").lower()
        if len(p) > 2:
            out.append(p)
    return out


def revisar_copy(pub):
    """Avisos del copy de una publicación: palabras prohibidas, largo, TOFU que nombra a Suplevet arriba."""
    avisos = []
    malas = palabras_prohibidas(pub.get("semana", ""))
    for red, r in pub["redes"].items():
        if not r.get("activa"):
            continue
        texto = (r.get("copy") or "")
        bajo = texto.lower()
        for m in malas:
            if re.search(rf"\b{re.escape(m)}", bajo):
                avisos.append(f"{red}: dice «{m}», que el brief pide evitar")
        if len(texto) > LIMITES.get(red, 99999):
            avisos.append(f"{red}: el copy pasa de {LIMITES[red]} letras")
        if not texto.strip():
            avisos.append(f"{red}: no tiene copy")
        if red == "youtube" and len(r.get("titulo") or "") > LIMITES["youtube_titulo"]:
            avisos.append("youtube: el título pasa de 100 letras")
    if pub.get("nivel") == "TOFU":
        primera = next((r.get("copy", "") for r in pub["redes"].values() if r.get("activa")), "").split("\n")[0]
        if "suplevet" in primera.lower():
            avisos.append("TOFU: la primera línea nombra a Suplevet")
    return avisos


# ---------- Cola ----------

def cola():
    return leer_json(COLA, {"publicaciones": []})


def guardar_cola(c):
    escribir_json(COLA, c)


def buscar(c, pid):
    return next((p for p in c["publicaciones"] if p["id"] == pid), None)


def _datos_del_codigo(codigo):
    """S03-C1-H2-CTAO → semana S03, cuerpo C1 y lo que el brief dice de ese cuerpo."""
    m = re.match(r"(S\d+)-(C\d+)", codigo or "")
    if not m:
        return {}
    semana, cuerpo = m.groups()
    b = brief_de(semana)
    cu = next((x for x in b.get("cuerpos", []) if x.get("id") == cuerpo), {})
    return {"semana": semana, "cuerpo": cuerpo, "dolor": b.get("dolor"),
            "nivel": cu.get("nivel"), "publico": cu.get("publico"), "desde": b.get("desde")}


def _fecha_para(dia, n_en_el_dia, tipo, desde):
    cfg = config()
    try:
        base = datetime.strptime(desde, "%Y-%m-%d")
    except (TypeError, ValueError):
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    if tipo == "carrusel":
        hora = cfg["horario_carrusel"]
    else:
        hs = cfg["horarios_video"]
        hora = hs[n_en_el_dia % len(hs)]
    return (base + timedelta(days=max(int(dia or 1), 1) - 1)).strftime("%Y-%m-%d") + "T" + hora


def nueva_publicacion(pieza, carpeta):
    """Pieza con la forma de paquete.json → publicación de la cola."""
    tipo = pieza.get("tipo", "video")
    archivos = pieza.get("archivos") or [pieza.get("archivo")]
    archivos = [str((carpeta / a).resolve()) for a in archivos if a]
    datos = _datos_del_codigo(pieza.get("codigo"))
    cb = pieza.get("copy_borrador", {})
    redes = {}
    for red in (REDES_VIDEO if tipo == "video" else REDES_CARRUSEL):
        copy = cb.get(red) or cb.get("instagram") or ""
        redes[red] = {"activa": True, "copy": copy, "estado": "pendiente"}
    if "youtube" in redes:
        redes["youtube"]["titulo"] = cb.get("youtube_titulo") or (cb.get("instagram") or "").split("\n")[0][:95]
    return {
        "id": uuid.uuid4().hex[:10],
        "codigo": pieza.get("codigo"),
        "tipo": tipo,
        "archivos": archivos,
        "portada": str((carpeta / pieza["portada"]).resolve()) if pieza.get("portada") else None,
        "semana": datos.get("semana"), "dolor": pieza.get("dolor") or datos.get("dolor"),
        "nivel": pieza.get("nivel") or datos.get("nivel"), "publico": pieza.get("publico") or datos.get("publico"),
        "dia": pieza.get("dia_sugerido"), "_desde": datos.get("desde"),
        "aprobado": False,
        "redes": redes,
        "creado": datetime.now().isoformat(timespec="seconds"),
    }


def _leer_txt_copy(txt):
    """Lee el .txt que deja la sala en V.FINALES (INSTAGRAM / TIKTOK / YOUTUBE · título / YOUTUBE · descripción)."""
    claves = {"INSTAGRAM": "instagram", "TIKTOK": "tiktok", "YOUTUBE · título": "youtube_titulo",
              "YOUTUBE · descripción": "youtube"}
    out, actual, buf = {}, None, []
    for linea in txt.read_text(encoding="utf-8").splitlines():
        if linea.strip() in claves:
            if actual:
                out[actual] = "\n".join(buf).strip()
            actual, buf = claves[linea.strip()], []
        else:
            buf.append(linea)
    if actual:
        out[actual] = "\n".join(buf).strip()
    return out


def piezas_de_carpeta(carpeta):
    """Sin paquete.json: arma las piezas mirando los .mp4 de V.FINALES (y sus .jpg/.txt). DIA_X da el día."""
    carpeta = Path(carpeta)
    piezas = []
    for v in sorted(carpeta.rglob("*.mp4")):
        m = re.match(r"DIA_(\d+)", v.parent.name)
        txt, jpg = v.with_suffix(".txt"), v.with_suffix(".jpg")
        piezas.append({
            "codigo": v.stem, "tipo": "video", "archivo": str(v.relative_to(carpeta)),
            "dia_sugerido": int(m.group(1)) if m else None,
            "copy_borrador": _leer_txt_copy(txt) if txt.exists() else {},
            "portada": str(jpg.relative_to(carpeta)) if jpg.exists() else None,
        })
    return piezas


def importar(ruta):
    """Acepta un paquete.json o una carpeta (V.FINALES o la que tenga paquete.json). Devuelve cuántas entraron."""
    ruta = Path(ruta.strip().strip('"'))
    if ruta.is_dir() and (ruta / "paquete.json").exists():
        ruta = ruta / "paquete.json"
    if ruta.is_file():
        carpeta = ruta.parent
        piezas = leer_json(ruta, {}).get("piezas", [])
    elif ruta.is_dir():
        carpeta = ruta
        piezas = piezas_de_carpeta(ruta)
    else:
        raise ValueError(f"No encuentro {ruta}")
    with _candado:
        c = cola()
        ya = {p["codigo"] for p in c["publicaciones"]}
        nuevas = [nueva_publicacion(p, carpeta) for p in piezas if p.get("codigo") not in ya]
        # fechas: por día, en el orden en que vienen
        por_dia = {}
        for p in nuevas:
            dia = p.pop("dia") or 1
            n = por_dia.get((dia, p["tipo"]), 0)
            por_dia[(dia, p["tipo"])] = n + 1
            p["fecha"] = _fecha_para(dia, n, p["tipo"], p.pop("_desde"))
        c["publicaciones"].extend(nuevas)
        guardar_cola(c)
    anotar(f"Importadas {len(nuevas)} piezas desde {ruta} ({len(piezas) - len(nuevas)} ya estaban)")
    return {"nuevas": len(nuevas), "repetidas": len(piezas) - len(nuevas)}


def cambiar(pid, cambios):
    with _candado:
        c = cola()
        p = buscar(c, pid)
        if not p:
            raise ValueError("No existe esa publicación")
        for k in ("fecha", "aprobado"):
            if k in cambios:
                p[k] = cambios[k]
        for red, r in (cambios.get("redes") or {}).items():
            if red in p["redes"]:
                for k in ("activa", "copy", "titulo", "cuenta"):
                    if k in r:
                        p["redes"][red][k] = r[k]
                if "estado" in r and r["estado"] == "pendiente":   # reintentar
                    p["redes"][red].update(estado="pendiente", error=None)
        if cambios.get("aprobado"):
            p["avisos"] = revisar_copy(p)
            prohibidas = [a for a in p["avisos"] if "pide evitar" in a]
            if prohibidas:
                raise ValueError("No se puede aprobar: " + "; ".join(prohibidas))
        guardar_cola(c)
        return p


def borrar(pid):
    with _candado:
        c = cola()
        c["publicaciones"] = [p for p in c["publicaciones"] if p["id"] != pid]
        guardar_cola(c)


def guardar_copy_final(p):
    """Deja el copy final que salió a cada red en 2_PUBLICACION/copies/<semana>/<codigo>.json."""
    if p.get("semana"):
        escribir_json(COPIES / p["semana"] / f"{p['codigo']}.json",
                      {red: {k: r.get(k) for k in ("copy", "titulo", "id_remoto", "url", "publicado")}
                       for red, r in p["redes"].items() if r.get("activa")})


# ---------- Publicar ----------

def publicar(pid, red):
    """Sube una publicación a una red. Marca estado y guarda el id que devuelve la red."""
    import redes  # tarde para no cruzar imports
    with _candado:
        c = cola()
        p = buscar(c, pid)
        r = p["redes"][red]
        if r.get("estado") in ("publicando", "publicado", "simulado"):
            return r
        r["estado"] = "publicando"
        guardar_cola(c)
    try:
        if config()["simular"]:
            time.sleep(0.3)
            res = {"id_remoto": f"sim-{red}-{uuid.uuid4().hex[:6]}", "url": None, "simulado": True}
            if hasattr(redes.CONECTORES[red], "cuenta_de"):
                try:
                    cu = redes.CONECTORES[red].cuenta_de(r)
                    res.update(cuenta=cu.get("open_id") or cu.get("id"), cuenta_nombre=cu.get("nombre"))
                except Exception:
                    pass
            anotar(f"[SIMULACIÓN] {red} · {p['codigo']} · {len(p['archivos'])} archivo(s) · {r.get('copy', '')[:60]!r}")
        else:
            res = redes.CONECTORES[red].publicar(p, r)
            anotar(f"Publicado {red} · {p['codigo']} → {res.get('id_remoto')}")
        nuevo = {"estado": "simulado" if res.get("simulado") else "publicado", "error": None,
                 "publicado": datetime.now().isoformat(timespec="minutes"), **res}
    except Exception as e:
        anotar(f"ERROR {red} · {p['codigo']}: {e}\n{traceback.format_exc()}")
        nuevo = {"estado": "error", "error": str(e)[:500]}
    with _candado:
        c = cola()
        p = buscar(c, pid)
        p["redes"][red].update(nuevo)
        guardar_cola(c)
        guardar_copy_final(p)
        return p["redes"][red]


def tocan_ahora():
    ahora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    for p in cola()["publicaciones"]:
        if p.get("aprobado") and p.get("fecha") and p["fecha"] <= ahora:
            for red, r in p["redes"].items():
                if r.get("activa") and r.get("estado") == "pendiente":
                    yield p["id"], red


def reloj(cada=30):
    """Hilo que revisa la cola y publica lo aprobado cuya hora ya llegó. La PC tiene que estar prendida."""
    while True:
        try:
            for pid, red in list(tocan_ahora()):
                publicar(pid, red)
        except Exception as e:
            anotar(f"ERROR en el reloj: {e}")
        time.sleep(cada)


def arrancar_reloj():
    threading.Thread(target=reloj, daemon=True).start()


# ---------- Métricas (forma del contrato metricas.json) ----------

def recoger_metricas(semana=None):
    import redes
    c = cola()
    por_semana = {}
    for p in c["publicaciones"]:
        if semana and p.get("semana") != semana:
            continue
        for red, r in p["redes"].items():
            if r.get("estado") != "publicado" or not r.get("id_remoto"):
                continue
            try:
                m = redes.CONECTORES[red].metricas(r)
            except Exception as e:
                anotar(f"Métricas {red} · {p['codigo']}: {e}")
                m = {}
            fila = {"codigo": p["codigo"], "red": red, "publicado": r.get("publicado"),
                    "vistas": 0, "retencion_3s": 0, "vista_completa": 0, "me_gusta": 0, "comentarios": 0,
                    "guardados": 0, "compartidos": 0, "seguidores": 0, "mensajes": 0,
                    "dolor": p.get("dolor"), "nivel": p.get("nivel"), "publico": p.get("publico")}
            if r.get("cuenta_nombre"):
                fila["cuenta"] = r["cuenta_nombre"]
            fila.update({k: v for k, v in m.items() if v is not None})
            por_semana.setdefault(p.get("semana") or "SIN_SEMANA", []).append(fila)
    cuentas = {}
    for red, con in redes.CONECTORES.items():
        if hasattr(con, "cuentas") and con.estado().get("cuentas"):
            try:
                cuentas[red] = con.cuentas()
            except Exception as e:
                anotar(f"Cuenta {red}: {e}")
    for sem, filas in por_semana.items():
        escribir_json(METRICAS / f"{sem}.json", {"semana": sem, "recogido": datetime.now().isoformat(timespec="minutes"),
                                                "cuentas": cuentas, "piezas": filas})
    anotar(f"Métricas recogidas: {sum(len(f) for f in por_semana.values())} filas en {list(por_semana)}")
    return {s: len(f) for s, f in por_semana.items()}


def metricas_guardadas():
    return {f.stem: leer_json(f, {}) for f in sorted(METRICAS.glob("*.json"))}
