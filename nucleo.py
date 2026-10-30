"""Núcleo del publicador: rutas, credenciales, cola de publicaciones, importar paquetes y el reloj que publica a la hora.

El código y los datos van separados. Los datos (credenciales, cola, pauta, tokens, métricas) viven en la carpeta
que dice PUBLICADOR_DATOS (la pone el .exe); si no, en 2_PUBLICACION. Nada de los datos va a GitHub.
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
def _carpeta_datos():
    """2_PUBLICACION o datos/ del instalado. Si en datos/ hay un usar_datos_de.txt con otra carpeta que tiene las
    llaves (credenciales.env), se usa esa: así el instalado y el portable comparten llaves, tokens y cola."""
    base = Path(os.environ.get("PUBLICADOR_DATOS") or AQUI.parent)
    try:
        otra = Path((base / "usar_datos_de.txt").read_text(encoding="utf-8").strip().strip('"'))
        if (otra / "credenciales.env").is_file():
            return otra
    except OSError:
        pass
    return base


PUBLICACION = _carpeta_datos()
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

# La consola de Windows usa «charmap» y revienta con emojis (un copy con 🐶): que los print nunca fallen.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------- Utilidades ----------

class DatosIlegibles(Exception):
    """Un archivo de datos existe pero no se pudo leer: mejor parar que seguir con uno vacío y pisarlo."""


def leer_json(ruta, defecto, estricto=False):
    """estricto=True (cola y tokens): si el archivo existe y no se puede leer, avisa en vez de devolver el vacío.
    Windows bloquea un archivo un instante mientras otro lo reemplaza: se reintenta un poco antes de rendirse."""
    ruta = Path(ruta)
    for intento in range(8):
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return defecto
        except PermissionError as e:
            error = e
            time.sleep(0.1 * (intento + 1))
        except (OSError, ValueError) as e:
            error = e
            break
    if estricto:
        raise DatosIlegibles(f"No pude leer {ruta.name} ({error}). No toqué nada para no perder datos.")
    return defecto


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(f"{ruta.name}.{os.getpid()}.{threading.get_ident()}.tmp")   # un .tmp propio por hilo
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    for intento in range(8):
        try:
            tmp.replace(ruta)
            return
        except PermissionError:   # alguien lo está leyendo justo ahora
            time.sleep(0.1 * (intento + 1))
    tmp.replace(ruta)


# ---------- Una sola copia abierta por carpeta de datos ----------

_cerrojo = None


def tomar_cerrojo():
    """Deja tomado publicador.lock mientras la app está abierta. False si otra copia ya lo tiene:
    dos publicadores con la misma cola tendrían dos relojes y subirían todo dos veces."""
    global _cerrojo
    f = open(PUBLICACION / "publicador.lock", "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _cerrojo = f
    return True


def anotar(texto):
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texto}"
    try:
        print(linea)
    except Exception:   # sin consola o con una que no entiende el texto: igual queda en el registro
        pass
    try:
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


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
    # sugerencias diarias: videos por cuenta al día, entre qué horas, cuentas que no reciben, días de aire por cuerpo
    # y días que espera un video antes de salir en otra cuenta de la misma red
    "sugeridor": {"por_dia": 10, "desde": "08:00", "hasta": "22:00", "apagados": [], "aire_cuerpo": 2, "entre_cuentas": 1},
    "youtube_cuenta": None,         # id del canal de YouTube por defecto
    "facebook_cuenta": None,        # id de la página de Facebook por defecto (hay varias en tokens.json → meta_paginas)
    "instagram_cuenta": None,       # id de la cuenta de Instagram por defecto
    "tiktok_cuenta": None,          # open_id de la cuenta de TikTok por defecto (hay varias en tokens.json)
    "tiktok_modo": "borrador",       # borrador: llega a la bandeja de TikTok y tú publicas desde el celular · directo
    "tiktok_privacidad": "SELF_ONLY",  # ya no se usa: en modo directo la privacidad se elige en cada pieza (regla de TikTok)
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


def puerto():
    """El puerto en que corre la app de verdad (el lanzador lo pasa en PUBLICADOR_PUERTO); si no, el de la configuración."""
    try:
        return int(os.environ.get("PUBLICADOR_PUERTO") or config()["puerto"])
    except (TypeError, ValueError):
        return 8766


def guardar_config(cambios):
    with _candado:
        c = leer_json(CONFIG_PATH, {}, estricto=True)
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
    return leer_json(TOKENS, {}, estricto=True)


_candado_tokens = threading.RLock()   # leer, cambiar y guardar tokens.json va siempre junto, bajo este candado


def guardar_token(red, datos):
    with _candado_tokens:
        t = tokens()
        t[red] = {**datos, "guardado": int(time.time())}
        escribir_json(TOKENS, t)


def cambiar_token(red, cambio):
    """Lee lo que hay en tokens.json[red], le aplica cambio(dict) → dict y lo guarda, sin que otro hilo se meta en medio.
    Así dos cuentas que se renuevan a la vez no se pisan."""
    with _candado_tokens:
        t = tokens()
        actual = {k: v for k, v in (t.get(red) or {}).items() if k != "guardado"}
        t[red] = {**cambio(actual), "guardado": int(time.time())}
        escribir_json(TOKENS, t)
        return t[red]


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


_briefs = {"cuando": 0, "por_semana": {}}


def brief_de(semana):
    """El brief de la semana: el de _SEMANAS en Drive (lo que ven las salas) o el de 0_ESTRATEGIA en esta PC.
    Se leen todos juntos cada 30 s (antes se leían una vez por cada pieza de la cola)."""
    if not semana:
        return {}
    if time.time() - _briefs["cuando"] > 30:
        import salas
        por_semana = {}
        for b in [*salas.briefs(), *sorted(estrategia().glob("semanas/*/brief.json"))]:
            d = leer_json(b, {})
            if d.get("semana"):
                por_semana.setdefault(d["semana"], d)   # el de Drive gana
        _briefs.update(cuando=time.time(), por_semana=por_semana)
    return _briefs["por_semana"].get(semana) or {}


def datos_de_semana(semana, cuerpo=None):
    """Lo que el brief de esa semana dice del cuerpo: dolor, nivel y público."""
    b = brief_de(semana)
    cu = next((x for x in b.get("cuerpos", []) if x.get("id") == cuerpo), {}) if cuerpo else {}
    return {"semana": semana, "cuerpo": cuerpo, "dolor": b.get("dolor"), "nivel": cu.get("nivel"),
            "publico": cu.get("publico"), "desde": b.get("desde")}


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
    return leer_json(COLA, {"publicaciones": []}, estricto=True)


def guardar_cola(c):
    escribir_json(COLA, c)


def buscar(c, pid):
    return next((p for p in c["publicaciones"] if p["id"] == pid), None)


def partes_codigo(codigo):
    """Cuerpo, hook y CTA que dice el nombre de un video: «S03-C1-H2-CTA1» → ("C1", "H2", "CTA1").
    Los de la sesión 13/10 se llaman «P2H1» o «P6 H1»: la parte 2 es el cuerpo C2 (el «P04» de una producción no cuenta)."""
    codigo = (codigo or "").strip()
    c = re.search(r"(?:^|[-_ ])C(\d+)(?=[-_ ]|$)", codigo, re.I)
    h = re.search(r"(?:^|[-_ ])H(\d+)(?=[-_ ]|$)", codigo, re.I)
    t = re.search(r"(?:^|[-_ ])(CTA\w*?)(?=[-_ ]|$)", codigo, re.I)
    cuerpo, hook = (f"C{int(c.group(1))}" if c else None), (f"H{int(h.group(1))}" if h else None)
    if not c:
        p = re.search(r"(?:^|[-_ ])P([1-9]\d?)[-_ ]?H(\d+)(?=[-_ ]|$)", codigo, re.I)
        if p:
            cuerpo, hook = f"C{int(p.group(1))}", f"H{int(p.group(2))}"
    return cuerpo, hook, (t.group(1).upper() if t else None)


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
    datos = datos_de_semana(pieza["semana"], pieza.get("cuerpo")) if pieza.get("semana") else _datos_del_codigo(pieza.get("codigo"))
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
                if red == "tiktok" and isinstance(r.get("ajustes_tiktok"), dict):   # lo que se elige para publicar directo
                    a = r["ajustes_tiktok"]
                    p["redes"][red]["ajustes_tiktok"] = {
                        "privacidad": a.get("privacidad") if a.get("privacidad") in ("PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS",
                                                                                     "FOLLOWER_OF_CREATOR", "SELF_ONLY") else None,
                        **{k: bool(a.get(k)) for k in ("comentarios", "duo", "stitch", "comercial", "marca_propia", "contenido_marca")}}
                # reintentar: solo lo que falló o quedó en duda; lo que ya salió o está subiendo no se toca
                if r.get("estado") == "pendiente" and p["redes"][red].get("estado") in REINTENTABLES:
                    p["redes"][red].update(estado="pendiente", error=None)
        if cambios.get("aprobado"):
            if not any(r.get("activa") for r in p["redes"].values()):
                raise ValueError("No se puede aprobar: prende al menos una red para esta pieza")
            if not re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", p.get("fecha") or ""):
                raise ValueError("No se puede aprobar: ponle día y hora de salida")
            tt = p["redes"].get("tiktok") or {}
            if tt.get("activa") and config()["tiktok_modo"] == "directo" and not (tt.get("ajustes_tiktok") or {}).get("privacidad"):
                raise ValueError("No se puede aprobar: elige en TikTok quién puede ver el video")
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
    """Deja el copy final que salió a cada red en 2_PUBLICACION/copies/<semana>/<codigo>.json, uno por red y cuenta
    («tiktok:<cuenta>»): el mismo video en tres cuentas de TikTok deja los tres copies, no solo el último."""
    if p.get("semana"):
        ruta = COPIES / p["semana"] / f"{p['codigo']}.json"
        datos = leer_json(ruta, {})
        for red, r in p["redes"].items():
            if r.get("activa"):
                datos[f"{red}:{r['cuenta']}" if r.get("cuenta") else red] = {
                    k: r.get(k) for k in ("copy", "titulo", "id_remoto", "url", "publicado", "cuenta_nombre")}
        escribir_json(ruta, datos)


# ---------- Publicar ----------

def publicar(pid, red):
    """Sube una publicación a una red. Marca estado y guarda el id que devuelve la red."""
    import redes  # tarde para no cruzar imports
    with _candado:
        c = cola()
        p = buscar(c, pid)
        if not p or red not in p["redes"]:
            return None   # la borraron mientras esperaba
        r = p["redes"][red]
        if r.get("estado") != "pendiente" or not r.get("activa"):   # ya está subiendo, ya salió, hay que revisarla o no va
            return r
        r.update(estado="publicando", inicio=datetime.now().isoformat(timespec="seconds"))
        guardar_cola(c)
    try:
        import salas   # los videos de Drive se bajan recién cuando se van a subir
        salas.asegurar(p)
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
        p2 = buscar(c, pid)
        if not p2 or red not in p2["redes"]:
            anotar(f"{red} · {p['codigo']}: la borraron de la cola mientras subía ({nuevo['estado']})")
            return nuevo
        p2["redes"][red].update(nuevo)
        p2["redes"][red].pop("inicio", None)
        guardar_cola(c)
        guardar_copy_final(p2)
        return p2["redes"][red]


REINTENTABLES = ("error", "revisar", "atrasado")   # estados en que «Reintentar» vuelve a poner la red en pendiente


def recuperar_trabadas():
    """Al abrir: lo que quedó «publicando» es porque la app se cerró a mitad de una subida. No se sabe si salió,
    así que pasa a «revisar» (y no se vuelve a subir solo)."""
    with _candado:
        c = cola()
        n = 0
        for p in c["publicaciones"]:
            for red, r in p["redes"].items():
                if r.get("estado") == "publicando":
                    r.update(estado="revisar", error="El Publicador se cerró mientras subía. Mira en la red si salió "
                                                     "antes de reintentar.")
                    r.pop("inicio", None)
                    n += 1
                    anotar(f"Revisar {red} · {p['codigo']}: quedó a medio subir")
        if n:
            guardar_cola(c)
    return n


def tocan_ahora():
    """Lo aprobado cuya hora ya llegó. Lo que lleva más de «atraso_max_min» de retraso (la PC estuvo apagada)
    no sale solo: pasa a «atrasado» para que no salga todo junto de golpe."""
    ahora = datetime.now()
    limite = (ahora - timedelta(minutes=int(config().get("atraso_max_min") or 90))).strftime("%Y-%m-%dT%H:%M")
    ahora = ahora.strftime("%Y-%m-%dT%H:%M")
    atrasadas, toca = [], []
    for p in cola()["publicaciones"]:
        if p.get("aprobado") and p.get("fecha") and p["fecha"] <= ahora:
            for red, r in p["redes"].items():
                if r.get("activa") and r.get("estado") == "pendiente":
                    (atrasadas if p["fecha"] < limite else toca).append((p["id"], red))
    if atrasadas:
        with _candado:
            c = cola()
            for pid, red in atrasadas:
                p = buscar(c, pid)
                if p and p["redes"].get(red, {}).get("estado") == "pendiente":
                    p["redes"][red].update(estado="atrasado", error=f"No salió a su hora ({p['fecha'].replace('T', ' ')}): "
                                                                    "el Publicador estaba cerrado. Reintenta o cambia la hora.")
                    anotar(f"Atrasado {red} · {p['codigo']}: no salió a las {p['fecha']}")
            guardar_cola(c)
    return toca


def reloj(cada=30):
    """Hilo que revisa la cola y publica lo aprobado cuya hora ya llegó. La PC tiene que estar prendida."""
    while True:
        try:
            for pid, red in tocan_ahora():
                publicar(pid, red)
        except Exception as e:
            anotar(f"ERROR en el reloj: {e}")
        time.sleep(cada)


def arrancar_reloj():
    try:
        recuperar_trabadas()
    except Exception as e:
        anotar(f"ERROR revisando lo que quedó a medio subir: {e}")
    threading.Thread(target=reloj, daemon=True, name="reloj").start()


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
    if not por_semana and cuentas:   # aún no hay piezas publicadas: igual quedan los números de cada cuenta
        import salas
        por_semana[salas.semana_de(datetime.now().date())] = []
    for sem, filas in por_semana.items():
        escribir_json(METRICAS / f"{sem}.json", {"semana": sem, "recogido": datetime.now().isoformat(timespec="minutes"),
                                                "cuentas": cuentas, "piezas": filas})
    n = sum(len(f) for f in por_semana.values())
    anotar(f"Métricas recogidas: {n} fila{'s' if n != 1 else ''}" + (f" ({', '.join(por_semana)})" if por_semana else " (no hay nada publicado para medir)"))
    return {s: len(f) for s, f in por_semana.items()}


def metricas_guardadas():
    return {f.stem: leer_json(f, {}) for f in sorted(METRICAS.glob("*.json"))}
