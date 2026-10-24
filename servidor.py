"""Publicador Suplevet: cola orgánica (IG, FB, TikTok, YouTube), pauta en Meta Ads y métricas.

Abrir:  py servidor.py   →   http://localhost:8766   (o doble clic en abrir_publicador.bat)
Arranca en modo simulación: no sale nada a redes hasta que lo apagues en Conexiones.
"""
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizador  # noqa: E402
import copys  # noqa: E402
import cuenta  # noqa: E402
import nucleo  # noqa: E402
import pauta  # noqa: E402
import produccion  # noqa: E402
import redes  # noqa: E402
import sugeridor  # noqa: E402
from redes import publicadas, tiktok, youtube  # noqa: E402

APP = Path(__file__).resolve().parent / "app.html"


_formatos = {}


def formato_de(p):
    """9:16 para los videos; las fotos de un carrusel se miden (y se recuerda la medida)."""
    if p["tipo"] == "video":
        return "9:16"
    ruta = (p.get("archivos") or [None])[0]
    if ruta not in _formatos:
        _formatos[ruta] = publicadas.formato(publicadas.medida(Path(ruta)) if ruta and os.path.isfile(ruta) else None, False)
    return _formatos[ruta]


def estado():
    cfg = nucleo.config()
    c = nucleo.cola()
    for p in c["publicaciones"]:
        p["avisos"] = nucleo.revisar_copy(p)
        p["formato"] = formato_de(p)
    return {"version": nucleo.VERSION, "datos": str(nucleo.PUBLICACION), "config": cfg, "conexiones": redes.estado_conexiones(), "cola": c, "pauta": pauta.pauta(),
            "registro": nucleo.registro(80), "metricas": nucleo.metricas_guardadas()}


def archivos_permitidos():
    out = set()
    for p in nucleo.cola()["publicaciones"]:
        out.update(p["archivos"])
        if p.get("portada"):
            out.add(p["portada"])
    return out


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # la ventana se cerró o se recargó a mitad de una respuesta: no es un error
        super().handle_error(request, client_address)


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _html(self, texto, codigo=200):
        cuerpo = texto.encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _ir(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _archivo(self, ruta):
        if (ruta not in archivos_permitidos() and ruta not in produccion.archivos_permitidos()) or not os.path.isfile(ruta):
            return self._json({"error": "archivo no está en la cola"}, 404)
        tam = os.path.getsize(ruta)
        tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        rango = self.headers.get("Range")
        ini, fin = 0, tam - 1
        if rango and rango.startswith("bytes="):
            a, _, b = rango[6:].partition("-")
            ini = int(a or 0)
            fin = min(int(b), tam - 1) if b else min(ini + 4 * 1024 * 1024, tam - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.end_headers()
        with open(ruta, "rb") as f:
            f.seek(ini)
            try:
                self.wfile.write(f.read(fin - ini + 1))
            except (ConnectionResetError, BrokenPipeError):
                pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._html(APP.read_text(encoding="utf-8"))
            if u.path == "/api/estado":
                return self._json(estado())
            if u.path == "/cuenta.js":
                b = (Path(__file__).resolve().parent / "cuenta.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return None
            if u.path == "/api/cuenta":  # la página pregunta cada minuto: de paso se anota esta PC (cada 10 min)
                cuenta.latido()
                return self._json(cuenta.estado())
            if u.path == "/api/dispositivos":
                return self._json({"dispositivos": cuenta.dispositivos(), "dias_nuevo": cuenta.DIAS_NUEVO})
            if u.path == "/api/cuenta/carpetas":  # elegir la carpeta del proyecto (cuenta.js): las carpetas de la cuenta
                return self._json({"ok": True, **cuenta.carpetas_para_elegir()})
            if u.path == "/api/actualizacion":
                return self._json(actualizador.revisar(forzar=q.get("forzar") == "1"))
            if u.path == "/api/pendientes":
                ahora = __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M")
                n = sum(1 for p in nucleo.cola()["publicaciones"] if p.get("aprobado") and p.get("fecha", "") > ahora
                        for r in p["redes"].values() if r.get("activa") and r.get("estado") == "pendiente")
                return self._json({"pendientes": n})
            if u.path == "/archivo":
                return self._archivo(q.get("ruta", ""))
            if u.path == "/api/listos":
                return self._json(produccion.listos(q.get("forzar") == "1"))
            if u.path == "/api/sugerencias":
                return self._json(sugeridor.planear(q.get("desde") or None, int(q.get("dias") or 1),
                                                    [x for x in q.get("excluir", "").split("|") if x]))
            if u.path == "/api/publicadas":
                return self._json(publicadas.todas(q.get("forzar") == "1"))
            if u.path == "/img":
                ruta = publicadas.bajar(q.get("u", ""))
                if not ruta:
                    return self._json({"error": "imagen no disponible"}, 404)
                cuerpo = ruta.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                return self.wfile.write(cuerpo)
            if u.path == "/conectar/tiktok":
                return self._ir(tiktok.url_conectar())
            if u.path == "/conectar/youtube":
                return self._ir(youtube.url_conectar())
            if u.path in ("/oauth/tiktok", "/oauth/google"):
                if q.get("error"):
                    return self._html(f"<h2>No se conectó: {q.get('error_description') or q['error']}</h2>")
                c = (tiktok if u.path.endswith("tiktok") else youtube).recibir_codigo(q.get("code", ""), q.get("state", ""))
                nucleo.anotar(f"Conectado {u.path.rsplit('/', 1)[-1]}" + (f" · {c['nombre']}" if isinstance(c, dict) and c.get("nombre") else ""))
                return self._html("<h2>Listo, cuenta conectada. Ya puedes cerrar esta pestaña.</h2>"
                                  "<script>setTimeout(()=>location='/',1500)</script>")
            return self._json({"error": "no existe"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._html(f"<h2>Error</h2><pre>{e}</pre>", 500) if not u.path.startswith("/api") else self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return self._json({"error": "solo desde esta PC"}, 403)
        # Una página de internet abierta en el navegador podría mandar órdenes a la app: el navegador siempre dice
        # de qué página viene el pedido (Origin) y tiene que ser la app misma.
        origen = self.headers.get("Origin")
        if origen and origen != "null" and urlparse(origen).netloc.lower() != (self.headers.get("Host") or "").lower():
            return self._json({"error": "pedido de otra página"}, 403)
        largo = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
        partes = u.path.strip("/").split("/")   # api, pub, <id>, <accion>
        try:
            if u.path == "/api/entrar":  # entrar con Google: sesión común de las tres apps
                return self._json({"ok": True, "cuenta": cuenta.entrar(str(d.get("link", "")))})
            if u.path == "/api/cuenta/primera":  # entrar y elegir (o crear) la carpeta del proyecto (cuenta.js)
                return self._json({"ok": True, **cuenta.primera(d)})
            if u.path == "/api/salir":
                cuenta.cerrar_sesion()
                return self._json({"ok": True})
            if u.path == "/api/cerrar_dispositivo":
                cuenta.cerrar_en(str(d["id"]))
                return self._json({"ok": True})
            if u.path == "/api/cerrar_otros":
                return self._json({"ok": True, "cerrados": cuenta.cerrar_en_todas_menos_esta()})
            if u.path == "/api/adios":
                nucleo.anotar("Publicador apagado")
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return self._json({"ok": True})
            if u.path == "/api/actualizar":
                v = actualizador.aplicar()
                actualizador.reiniciar_luego()
                return self._json({"version": v})
            if u.path == "/api/importar":
                return self._json(nucleo.importar(d["ruta"]))
            if u.path == "/api/config":
                permitidas = {"simular", "tiktok_modo", "tiktok_privacidad", "youtube_privacidad",
                              "horarios_video", "horario_carrusel", "pauta", "carpetas_produccion", "sugeridor"}
                nucleo.guardar_config({k: v for k, v in d.items() if k in permitidas})
                if "simular" in d:
                    nucleo.anotar("Modo simulación " + ("PRENDIDO" if d["simular"] else "APAGADO: ahora sí sale a redes"))
                return self._json(nucleo.config())
            if u.path == "/api/aprobar_dia":
                n, trabadas = 0, []
                for p in nucleo.cola()["publicaciones"]:
                    if (p.get("fecha") or "").startswith(d["dia"]) and not p.get("aprobado"):
                        try:
                            nucleo.cambiar(p["id"], {"aprobado": True})
                            n += 1
                        except ValueError:
                            trabadas.append(p["codigo"])
                nucleo.anotar(f"Aprobadas {n} piezas del {d['dia']}" + (f" · trabadas por palabras: {trabadas}" if trabadas else ""))
                return self._json({"aprobadas": n, "trabadas": trabadas})
            if len(partes) == 3 and partes[0] == "api" and partes[1] in ("tiktok", "youtube") \
                    and partes[2] in ("defecto", "quitar"):   # varias cuentas por red
                red = partes[1]
                if partes[2] == "defecto":
                    nucleo.guardar_config({f"{red}_cuenta": d["id"]})
                else:
                    (tiktok if red == "tiktok" else youtube).quitar_cuenta(d["id"])
                    nucleo.anotar(f"Cuenta de {red} quitada")
                return self._json({"ok": True})
            if u.path == "/api/listos/a_la_cola":
                return self._json(produccion.a_la_cola(d.get("rutas") or [], d.get("redes") or [], d.get("cuentas"),
                                                       d.get("modo") or "repartir", d.get("desde"), d.get("por_dia"), d.get("aprobar") is True))
            if u.path == "/api/sugerencias/aceptar":
                return self._json(sugeridor.aceptar(d.get("items") or [], d.get("aprobar") is True))
            if u.path == "/api/sugerencias/ya_salio":
                return self._json(sugeridor.ya_salio(d["ruta"], d.get("si", True) is not False))
            if u.path == "/api/metricas":
                return self._json(nucleo.recoger_metricas(d.get("semana")))
            if partes[:2] == ["api", "pub"]:
                pid, accion = partes[2], (partes[3] if len(partes) > 3 else "cambiar")
                if accion == "cambiar":
                    return self._json(nucleo.cambiar(pid, d))
                if accion == "copy":   # escribir otro copy desde el guion
                    return self._json(copys.rehacer(pid))
                if accion == "borrar":
                    nucleo.borrar(pid)
                    return self._json({"ok": True})
                if accion == "publicar":
                    reds = [d["red"]] if d.get("red") else [
                        r for r, x in nucleo.buscar(nucleo.cola(), pid)["redes"].items()
                        if x.get("activa") and x.get("estado") in ("pendiente", "error")]
                    for r in reds:
                        nucleo.cambiar(pid, {"redes": {r: {"estado": "pendiente"}}})
                        threading.Thread(target=nucleo.publicar, args=(pid, r), daemon=True).start()
                    return self._json({"publicando": reds})
            if partes[:2] == ["api", "pauta"]:
                if partes[2] == "nueva":
                    return self._json(pauta.nueva(d))
                cid, accion = partes[2], partes[3]
                acciones = {"crear": lambda: pauta.crear_en_meta(cid),
                            "activar": lambda: pauta.activar(cid, d.get("confirmado") is True),
                            "pausar": lambda: pauta.pausar(cid),
                            "resultados": lambda: pauta.resultados(cid),
                            "borrar": lambda: pauta.borrar(cid) or {"ok": True}}
                return self._json(acciones[accion]())
            return self._json({"error": "no existe"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 400)


def main():
    puerto = int(os.environ.get("PUBLICADOR_PUERTO") or nucleo.config()["puerto"])
    inicio = time.time()
    srv = Servidor(("127.0.0.1", puerto), Manejador)
    nucleo.arrancar_reloj()
    cuenta.iniciar("Publicador", nucleo.VERSION)
    cuenta.latido(forzar=True)
    url = f"http://localhost:{puerto}"
    nucleo.anotar(f"Publicador abierto en {url} · simulación {'sí' if nucleo.config()['simular'] else 'NO'}")
    print(f"Lista para usar en {time.time() - inicio:.1f} s", flush=True)
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
