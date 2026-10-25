"""Preparación: dejar el Publicador listo para conectar las redes, sin tocar archivos a mano.

Cada persona usa sus propias llaves (su app de Meta for Developers, de TikTok for Developers y de Google Cloud): se
escriben en la pestaña Preparación y quedan solo en esta PC (credenciales.env y google_client_secret.json en la carpeta
de datos; nunca en Drive ni en GitHub). A la pantalla nunca vuelve una clave secreta: solo si está y sus últimas letras.

estado() dice, red por red, qué falta: las llaves, la dirección de vuelta que hay que copiar en la consola de la red,
las cuentas conectadas, en qué punto va la revisión de la red y qué pide esa revisión.
"""
import json
import os
import re

import nucleo
from redes import meta, tiktok, youtube

# clave en credenciales.env → (texto en pantalla, es secreta)
LLAVES = {
    "meta": [("META_APP_ID", "ID de la app", False), ("META_APP_SECRET", "Clave secreta de la app", True)],
    "tiktok": [("TIKTOK_CLIENT_KEY", "Client key", False), ("TIKTOK_CLIENT_SECRET", "Client secret", True)],
    "youtube": [("GOOGLE_CLIENT_ID", "ID de cliente", False), ("GOOGLE_CLIENT_SECRET", "Secreto del cliente", True)],
}
# opcionales: solo para la pauta (anuncios de Meta), que sigue usando el token de un usuario del sistema
ANUNCIOS = [("META_TOKEN_USUARIO_SISTEMA", "Token del usuario del sistema", True), ("META_AD_ACCOUNT_ID", "Cuenta publicitaria (act_…)", False),
            ("META_PAGE_ID", "ID de la página de los anuncios", False), ("META_IG_USER_ID", "ID del Instagram de los anuncios", False)]
EXTRA = [("META_REDIRECT_URI", "Dirección de vuelta de Meta (si no es la de esta PC)", False),
         ("TIKTOK_REDIRECT_URI", "Dirección de vuelta de TikTok (si no es la de esta PC)", False)]
REVISION = ("prueba", "enviada", "aprobada")

RED = {
    "meta": {"nombre": "Instagram y Facebook", "consola": "https://developers.facebook.com/apps",
             "crear": "Crea una app de tipo «Empresa» en Meta for Developers y agrégale el producto «Inicio de sesión con Facebook».",
             "donde_vuelta": "Inicio de sesión con Facebook → Configuración → «URI de redireccionamiento de OAuth válidos».",
             "prueba": "Mientras la app no esté aprobada, solo pueden conectarse las personas que agregues como evaluadoras "
                       "(Roles de la app → Evaluadores) y la app queda en modo desarrollo.",
             "revision": ["Verificar tu negocio en el Administrador comercial de Meta.",
                          "Una página web con la política de privacidad y otra con cómo pedir que se borren los datos.",
                          "Un video demo por cada permiso: conectar con Facebook, elegir la página, publicar un Reel y un carrusel y ver las métricas.",
                          "Permisos que se piden: pages_show_list, pages_read_engagement, pages_manage_posts, read_insights, "
                          "instagram_basic, instagram_content_publish, instagram_manage_insights y business_management.",
                          "Después de aprobada, pasar la app a modo «Activo» (Live)."]},
    "tiktok": {"nombre": "TikTok", "consola": "https://developers.tiktok.com/apps",
               "crear": "Crea una app en TikTok for Developers (plataforma Desktop) con «Login Kit» y «Content Posting API».",
               "donde_vuelta": "Login Kit → Redirect URI (tipo Desktop).",
               "prueba": "En Sandbox solo entran las cuentas que agregues como Target users, y lo que se publica directo queda privado.",
               "revision": ["Una página web con la política de privacidad y otra con los términos de uso.",
                            "Un video demo del flujo completo: conectar la cuenta, elegir el video, la pantalla de publicar "
                            "(cuenta, privacidad, comentarios, dúos, stitch, contenido comercial y el aviso de música) y el resultado.",
                            "Para publicar directo (sin pasar por la bandeja del celular), TikTok revisa que esa pantalla esté completa: "
                            "el Publicador ya la trae."]},
    "youtube": {"nombre": "YouTube", "consola": "https://console.cloud.google.com/apis/credentials",
                "crear": "En Google Cloud: activa «YouTube Data API v3», configura la pantalla de consentimiento y crea un ID de cliente "
                         "OAuth de tipo «App de escritorio».",
                "donde_vuelta": "No hace falta copiarla: las apps de escritorio aceptan la dirección de esta PC solas.",
                "prueba": "En modo «Prueba» solo entran los correos que agregues como usuarios de prueba (hasta 100), la conexión vence "
                          "a los 7 días y los videos que se suben quedan privados.",
                "revision": ["Publicar la pantalla de consentimiento (pasar de «Prueba» a «En producción»).",
                             "Un dominio verificado con la página de inicio y la política de privacidad.",
                             "Un video demo que muestre cómo se usa el permiso de subir videos (youtube.upload).",
                             "Para que los videos salgan públicos: la auditoría de la API de YouTube (formulario de Google)."]},
}


# ---------- credenciales.env ----------

def _escribir_env(cambios):
    """Cambia o agrega claves en credenciales.env sin tocar las demás líneas (ni los comentarios). "" = borrar."""
    try:
        lineas = nucleo.CREDENCIALES.read_text(encoding="utf-8").splitlines()
    except OSError:
        lineas = ["# Llaves del Publicador. Quedan solo en esta PC: nunca a Drive ni a GitHub."]
    hechos = set()
    for i, linea in enumerate(lineas):
        m = re.match(r"\s*([A-Z_]+)\s*=", linea)
        if m and m.group(1) in cambios:
            lineas[i] = f"{m.group(1)}={cambios[m.group(1)]}"
            hechos.add(m.group(1))
    lineas += [f"{k}={v}" for k, v in cambios.items() if k not in hechos and v]
    nucleo.CREDENCIALES.parent.mkdir(parents=True, exist_ok=True)
    tmp = nucleo.CREDENCIALES.with_suffix(".env.part")
    tmp.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.replace(tmp, nucleo.CREDENCIALES)


def _google():
    d = nucleo.leer_json(nucleo.GOOGLE_SECRET, {})
    return d.get("installed") or d.get("web") or {}


def _escribir_google(cid=None, secreto=None, json_entero=None):
    if json_entero:
        try:
            d = json.loads(json_entero)
        except ValueError:
            raise ValueError("Eso no es el archivo JSON que se baja de Google Cloud")
        c = d.get("installed") or d.get("web") or {}
        if not c.get("client_id"):
            raise ValueError("El JSON no trae client_id: bájalo de Google Cloud → Credenciales → tu ID de cliente → Descargar JSON")
        cid, secreto = c["client_id"], c.get("client_secret", "")
    actual = _google()
    cid = actual.get("client_id", "") if cid is None else cid
    secreto = actual.get("client_secret", "") if secreto is None else secreto
    if not cid and not secreto:
        nucleo.GOOGLE_SECRET.unlink(missing_ok=True)
        return
    nucleo.escribir_json(nucleo.GOOGLE_SECRET, {"installed": {
        "client_id": cid, "client_secret": secreto, "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}})


def guardar_llaves(cambios):
    """cambios = {CLAVE: valor}: solo las claves conocidas; "" borra. Devuelve el estado nuevo."""
    validas = {k for lista in (*LLAVES.values(), ANUNCIOS, EXTRA) for k, _, _ in lista}
    env, google, google_json = {}, {}, False
    for k, v in (cambios or {}).items():
        if k == "GOOGLE_JSON":
            if str(v or "").strip():
                _escribir_google(json_entero=str(v))
                google_json = True
            continue
        if k not in validas:
            raise ValueError(f"Clave desconocida: {k}")
        v = str(v if v is not None else "").strip().strip('"')
        if re.search(r"[\r\n]", v) or len(v) > 600:
            raise ValueError(f"El valor de {k} no es válido")
        if k == "META_AD_ACCOUNT_ID" and v and not v.startswith("act_"):
            v = "act_" + v
        (google if k.startswith("GOOGLE_") else env)[k] = v
    if env:
        _escribir_env(env)
    if google:
        _escribir_google(google.get("GOOGLE_CLIENT_ID"), google.get("GOOGLE_CLIENT_SECRET"))
    nombres = sorted({**env, **google}) + (["google_client_secret.json"] if google_json else [])
    nucleo.anotar(f"Preparación: llaves guardadas ({', '.join(nombres)})")
    return estado()


def guardar_revision(red, valor):
    if red not in RED or valor not in REVISION:
        raise ValueError("Valor no válido")
    rev = {**(nucleo.config().get("revision") or {}), red: valor}
    nucleo.guardar_config({"revision": rev})
    return estado()


# ---------- Estado ----------

def _muestra(valor, secreto):
    if not valor:
        return ""
    return ("•••• " + valor[-4:]) if secreto else valor


def _valores():
    c = nucleo.credenciales()
    g = _google()
    return {**c, "GOOGLE_CLIENT_ID": g.get("client_id", ""), "GOOGLE_CLIENT_SECRET": g.get("client_secret", "")}


def estado():
    v = _valores()
    rev = nucleo.config().get("revision") or {}
    con = {"meta": len(meta.cuentas_red("facebook")) + len(meta.cuentas_red("instagram")),
           "tiktok": len(tiktok.cuentas()), "youtube": len(youtube.cuentas())}
    vuelta = {"meta": meta.redireccion(), "tiktok": tiktok.redireccion(), "youtube": youtube.redireccion()}
    out = []
    for red, info in RED.items():
        llaves = [{"clave": k, "nombre": n, "secreto": s, "tiene": bool(v.get(k)), "muestra": _muestra(v.get(k, ""), s)}
                  for k, n, s in LLAVES[red]]
        tiene = all(x["tiene"] for x in llaves)
        pasos = [{"texto": info["crear"], "ok": tiene, "como": "Pega abajo las llaves de tu app."},
                 {"texto": "Copia la dirección de vuelta en la consola de la red.", "ok": None, "como": info["donde_vuelta"]},
                 {"texto": "Conecta tus cuentas (pestaña Conexiones).", "ok": con[red] > 0,
                  "como": f"{con[red]} conectada(s)." if con[red] else "Cuando quieras: no hace falta para dejar todo preparado."}]
        out.append({"red": red, **{k: info[k] for k in ("nombre", "consola", "prueba", "revision")}, "llaves": llaves,
                    "listo_para_conectar": tiene, "vuelta": vuelta[red], "pasos": pasos, "cuentas": con[red],
                    "revision_estado": rev.get(red) if rev.get(red) in REVISION else "prueba"})
    anuncios = [{"clave": k, "nombre": n, "secreto": s, "tiene": bool(v.get(k)), "muestra": _muestra(v.get(k, ""), s)} for k, n, s in ANUNCIOS]
    extra = [{"clave": k, "nombre": n, "secreto": s, "tiene": bool(v.get(k)), "muestra": _muestra(v.get(k, ""), s)} for k, n, s in EXTRA]
    return {"redes": out, "anuncios": anuncios, "extra": extra, "carpeta": str(nucleo.PUBLICACION),
            "listas": sum(1 for r in out if r["listo_para_conectar"])}
