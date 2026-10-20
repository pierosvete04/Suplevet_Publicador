"""Publicador Suplevet: cola orgánica (IG, FB, TikTok, YouTube), pauta en Meta Ads y métricas.

Abrir:  py servidor.py   →   http://localhost:8766   (o doble clic en abrir_publicador.bat)
Arranca en modo simulación: no sale nada a redes hasta que lo apagues en Conexiones.
"""
import json
import mimetypes
import os
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizador  # noqa: E402
import nucleo  # noqa: E402
import pauta  # noqa: E402
import redes  # noqa: E402
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
        if ruta not in archivos_permitidos() or not os.path.isfile(ruta):
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
            if u.path == "/api/actualizacion":
                return self._json(actualizador.revisar())
            if u.path == "/api/pendientes":
                ahora = __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M")
                n = sum(1 for p in nucleo.cola()["publicaciones"] if p.get("aprobado") and p.get("fecha", "") > ahora
                        for r in p["redes"].values() if r.get("activa") and r.get("estado") == "pendiente")
                return self._json({"pendientes": n})
            if u.path == "/archivo":
                return self._archivo(q.get("ruta", ""))
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
        largo = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
        partes = u.path.strip("/").split("/")   # api, pub, <id>, <accion>
        try:
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
                              "horarios_video", "horario_carrusel", "pauta"}
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
            if u.path == "/api/metricas":
                return self._json(nucleo.recoger_metricas(d.get("semana")))
            if partes[:2] == ["api", "pub"]:
                pid, accion = partes[2], (partes[3] if len(partes) > 3 else "cambiar")
                if accion == "cambiar":
                    return self._json(nucleo.cambiar(pid, d))
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
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    nucleo.arrancar_reloj()
    url = f"http://localhost:{puerto}"
    nucleo.anotar(f"Publicador abierto en {url} · simulación {'sí' if nucleo.config()['simular'] else 'NO'}")
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
