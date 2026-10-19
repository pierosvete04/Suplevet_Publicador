"""PublicadorSuplevet.exe: abre el publicador en su propia ventana (como un programa) y lo reinicia al actualizarse.

Carpeta portable (lo que se instala):
  PublicadorSuplevet/
    PublicadorSuplevet.exe   este lanzador + Python + librerías (PyInstaller)
    app/                     el código; es lo único que cambia al actualizar
    datos/                   lo de esta PC: credenciales.env, cola, pauta, tokens, métricas (nunca se toca)

Si la carpeta del programa está dentro de 2_PUBLICACION (o al lado de un credenciales.env), los datos se leen
de ahí y no de datos/: así el estratega sigue encontrando las métricas donde siempre.

Al cerrar la ventana, si quedan piezas aprobadas por salir, pregunta si sigue publicando en segundo plano.
Por dentro es un servidor solo de esta PC (127.0.0.1); nadie de afuera puede entrar.

Si cambias este archivo o las librerías, sube LANZADOR_VERSION y el archivo LANZADOR_MINIMO.
"""
LANZADOR_VERSION = "1.0.0"

# Imports explícitos para que PyInstaller empaquete lo que usa el código de app/ (que no analiza).
import ctypes, http.server, io, json, mimetypes, re, runpy, secrets, shutil, socket, socketserver  # noqa: E401,F401
import subprocess, sys, tempfile, threading, time, traceback, uuid, webbrowser, zipfile  # noqa: E401,F401
import urllib.error, urllib.parse, urllib.request  # noqa: E401,F401
import os
from datetime import datetime, timedelta  # noqa: F401
from pathlib import Path

try:
    import webview  # ventana propia; si falta, se usa Edge
except Exception:  # noqa: BLE001
    webview = None

PUERTO = int(os.environ.get("PUBLICADOR_PUERTO") or 8766)
URL = f"http://127.0.0.1:{PUERTO}"
TITULO = "Publicador Suplevet"


def base():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def preparar_entorno():
    b = base()
    app = b / "app" if (b / "app" / "servidor.py").exists() else b
    if (b.parent / "credenciales.env").exists():        # instalado dentro de 2_PUBLICACION
        datos = b.parent
    elif app != b:
        datos = b / "datos"
    else:                                               # desarrollo: 2_PUBLICACION/publicador
        datos = b.parent
    datos.mkdir(exist_ok=True)
    os.environ["PUBLICADOR_DATOS"] = str(datos)
    os.environ["PUBLICADOR_PUERTO"] = str(PUERTO)
    if getattr(sys, "frozen", False):
        os.environ["PUBLICADOR_LANZADOR"] = LANZADOR_VERSION
    return app, datos


def en_uso():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PUERTO)) == 0


def salida_a_log(datos):
    if sys.stdout is None or sys.stderr is None:
        log = open(datos / "publicador.log", "a", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def correr_servidor():
    app, datos = preparar_entorno()
    salida_a_log(datos)
    sys.path.insert(0, str(app))
    os.chdir(app)
    sys.argv.append("--sin-navegador")
    runpy.run_path(str(app / "servidor.py"), run_name="__main__")


def mensaje(texto, pregunta=False):
    """MessageBox de Windows. Con pregunta=True devuelve True si dicen Sí."""
    if os.name != "nt":
        print(texto)
        return False
    r = ctypes.windll.user32.MessageBoxW(0, texto, TITULO, (0x04 | 0x20) if pregunta else 0x10)
    return r == 6


def pedir(ruta, metodo="GET"):
    req = urllib.request.Request(URL + ruta, data=b"" if metodo == "POST" else None, method=metodo)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")


def navegador_app():
    pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
        for raiz in pf:
            ruta = os.path.join(raiz, rel)
            if raiz and os.path.isfile(ruta):
                return ruta
    return None


def ventana_propia(datos, log):
    if webview is None:
        return False
    try:
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Conectar TikTok/YouTube y «ver» abren el navegador
        webview.create_window(TITULO, URL, width=1380, height=900, min_size=(900, 600), text_select=True)
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(datos / "ventana_app"))
        return True
    except Exception:  # noqa: BLE001
        log.write("No se pudo abrir la ventana propia; se usa Edge.\n" + traceback.format_exc())
        log.flush()
        return False


def abrir_ventana(datos):
    exe = navegador_app()
    if not exe:
        webbrowser.open(URL)
        return
    subprocess.Popen([exe, f"--app={URL}", f"--user-data-dir={datos / 'ventana'}", "--no-first-run",
                      "--no-default-browser-check", "--window-size=1380,900"])


def al_cerrar():
    """Si quedan piezas aprobadas por salir, ofrece seguir en segundo plano; si no, apaga el servidor."""
    try:
        n = pedir("/api/pendientes").get("pendientes", 0)
    except Exception:  # noqa: BLE001
        return
    if n and mensaje(f"Quedan {n} publicaciones aprobadas por salir.\n\n"
                     "¿Sigo publicando en segundo plano? (vuelve a abrir el programa para ver la cola)", pregunta=True):
        return
    try:
        pedir("/api/adios", "POST")
    except Exception:  # noqa: BLE001
        pass


def main():
    if "--servidor" in sys.argv:
        return correr_servidor()
    _, datos = preparar_entorno()
    salida_a_log(datos)
    if en_uso():  # ya estaba corriendo (quizá en segundo plano): solo otra ventana
        if not ventana_propia(datos, sys.stderr):
            abrir_ventana(datos)
        return
    log = open(datos / "publicador.log", "a", encoding="utf-8", errors="replace")
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} · lanzador {LANZADOR_VERSION} =====\n")
    log.flush()
    cmd = [sys.executable, "--servidor"] if getattr(sys, "frozen", False) else [sys.executable, __file__, "--servidor"]
    sin_consola = 0x08000000 if os.name == "nt" else 0
    estado = {"proc": subprocess.Popen(cmd, stdout=log, stderr=log, creationflags=sin_consola), "codigo": None}
    for _ in range(120):
        if en_uso() or estado["proc"].poll() is not None:
            break
        time.sleep(0.25)
    if estado["proc"].poll() is not None:
        mensaje(f"El publicador no pudo arrancar. Mándale a Claude el archivo:\n{datos / 'publicador.log'}")
        return

    def servidor():  # se reinicia solo cuando se instala una actualización (código 42)
        while True:
            codigo = estado["proc"].wait()
            if codigo != 42:
                estado["codigo"] = codigo
                return
            estado["proc"] = subprocess.Popen(cmd, stdout=log, stderr=log, creationflags=sin_consola)
    hilo = threading.Thread(target=servidor, daemon=True)
    hilo.start()
    if ventana_propia(datos, log):   # espera aquí hasta que se cierre la ventana
        al_cerrar()
    else:
        abrir_ventana(datos)         # con Edge no se puede esperar: se apaga con el botón «Apagar» del programa
    hilo.join()
    if estado["codigo"] not in (0, None):
        mensaje(f"El publicador se detuvo (código {estado['codigo']}). Mándale a Claude el archivo:\n"
                f"{datos / 'publicador.log'}")


if __name__ == "__main__":
    main()
