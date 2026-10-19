# Publicador Suplevet

Programa de Windows que sube el contenido de Suplevet a las redes, tanto orgánico como pauta.

| | Qué hace |
|---|---|
| **Cola orgánica** | Trae los videos de V.FINALES (o un `paquete.json`), arma el calendario de la semana con el brief y publica sola a su hora lo que apruebas: Instagram, Facebook, TikTok y YouTube Shorts |
| **Pauta** | Crea campañas en Meta Ads (Instagram + Facebook). Todo nace **en pausa**; solo gasta cuando aprietas «Activar» y confirmas el monto |
| **Métricas** | Recoge vistas, me gusta, guardados, etc. y los deja en `metricas/<semana>.json` para el estratega |

Arranca en **modo simulación**: anota lo que haría, pero no sube nada ni gasta. Se apaga en la pestaña Conexiones.

## Instalar

1. Baja `PublicadorSuplevet-Instalador-vX.Y.Z.exe` de la página de Releases del repo y ábrelo.
2. Abre el programa desde el escritorio. Se actualiza solo: cuando hay versión nueva aparece una franja naranja con «Actualizar ahora».
3. Pega tus claves en `datos\credenciales.env` (la ruta exacta sale en Conexiones → Carpeta de datos).

Si instalas el programa **dentro de `2_PUBLICACION`**, usa directamente `2_PUBLICACION\credenciales.env` y deja las métricas donde el estratega las busca.

## Conectar cada red

| Red | Qué necesita | Dónde |
|---|---|---|
| Instagram y Facebook | `META_TOKEN_USUARIO_SISTEMA`, `META_PAGE_ID`, `META_IG_USER_ID` | Business Manager → Usuarios del sistema → Generar token con `instagram_content_publish`, `pages_manage_posts`, `pages_read_engagement`, `instagram_manage_insights` |
| Pauta Meta | lo mismo + `META_AD_ACCOUNT_ID` y el permiso `ads_management` | El mismo usuario del sistema, con la cuenta publicitaria asignada |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, luego botón «Conectar» | developers.tiktok.com → app con *Content Posting API* y *Login Kit*. La URL de retorno tiene que ser igual a `TIKTOK_REDIRECT_URI` |
| YouTube | `google_client_secret.json` en la carpeta de datos, luego botón «Conectar» | Google Cloud → API de YouTube Data v3 → ID de cliente OAuth tipo *App de escritorio* |

**TikTok sin auditar:** mientras TikTok no apruebe la app, el modo «directo» solo publica en privado. Por eso viene en modo **«borrador»**: el video llega a la bandeja de TikTok del celular, le pones el sonido de moda y publicas. Es lo que conviene igual, porque los sonidos de tendencia solo se ponen desde la app.

## Reglas que cuida solo

- No deja aprobar una pieza si su copy tiene palabras del campo `evitar` del brief (tumor, cura, prurito…).
- Avisa si un TOFU nombra a Suplevet en la primera línea o si un copy pasa el largo de la red.
- Para gastar pide confirmación con el monto. Al cerrar la ventana, si quedan piezas por salir, pregunta si sigue en segundo plano.
- Las piezas programadas solo salen si el programa está prendido. El instalador ofrece abrirlo al prender la PC.

## Para programar (desarrollo)

- Correr sin .exe: `abrir_publicador.bat` (usa `py lanzador.py`; los datos van a la carpeta de arriba, `2_PUBLICACION`).
- Sacar una versión: subir `VERSION`, escribir `NOTAS_VERSION.md`, commit, `git tag vX.Y.Z`, `git push origin main --tags`. GitHub Actions arma el instalador, el zip portable y el `app-*.zip` que baja la actualización.
- Si cambia `lanzador.py` o `requirements-build.txt`, subir `LANZADOR_VERSION` y `LANZADOR_MINIMO`: el programa pedirá reinstalar en vez de actualizar solo el código.

| Archivo | Qué es |
|---|---|
| `lanzador.py` | El .exe: abre la ventana y reinicia al actualizar |
| `servidor.py` | La API local (solo 127.0.0.1) |
| `nucleo.py` | Cola, calendario, reglas del copy, reloj que publica y métricas |
| `redes/` | Un conector por red: `meta.py` (IG + FB), `tiktok.py`, `youtube.py` |
| `pauta.py` | Meta Ads: campaña → conjunto → anuncios, en pausa |
| `actualizador.py` | Revisa GitHub Releases y cambia el código |
| `app.html` | La pantalla |

## Lo que falta

- Pauta en TikTok Ads (pide una app aparte en TikTok for Business).
- Carruseles en TikTok (piden una URL pública de un dominio verificado).
- Que la sala exporte `paquete.json` con nivel, público y día; hoy se leen de la carpeta V.FINALES y del brief.
