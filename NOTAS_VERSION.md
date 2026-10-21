## 1.3.2 · Nombre e ícono nuevos

- Se llama **Publicador** (sin Suplevet) y tiene ícono nuevo: una **P** verde, de la misma familia que la Sala de edición (E) y la Sala de diseño (D). Para ver el ícono y el nombre nuevos en el escritorio hay que pasar una vez el instalador completo; borra solo el acceso directo viejo.

## 1.3.1 · Arreglo: la 1.3.0 no traía la pestaña Hoy ni los copies

- La versión 1.3.0 se armó sin los archivos nuevos (sugerencias y copies), y el programa no arrancaba al actualizarse. Esta los trae.
- El armado ahora copia todo el código y revisa que no falte nada antes de publicar.
- Portable: descomprime `PublicadorSuplevet-vX.Y.Z.zip` donde quieras y abre `PublicadorSuplevet.exe`, sin instalar nada. Si la carpeta queda dentro de `2_PUBLICACION`, usa los datos de ahí.

## 1.3.0 · Qué subir hoy y copies desde el guion

- Pestaña nueva **Hoy**: mira lo que está listo en producción y lo que ya salió, y arma la mezcla de cada cuenta (Instagram, Facebook, cada cuenta de TikTok y cada canal de YouTube). Por defecto 10 videos por cuenta al día, repartidos de 8:00 a 22:00.
- Nunca pone dos videos del mismo cuerpo en una cuenta el mismo día, ni el mismo video dos veces en una cuenta. Primero va el cuerpo que esa cuenta tiene más olvidado y lo que no salió en ningún lado, y trata de no repetir el mismo video el mismo día en dos cuentas de la misma red.
- Si no alcanzan los videos, no repite: dice cuántos cuerpos faltan para llegar a 10 diarios.
- Cada sugerencia dice por qué se eligió. Se puede desmarcar, cambiar por otra o marcar como «ya lo subí a mano». Se planea 1, 3 o 7 días y se pasa todo a la cola con un botón.
- Ajustes: videos por cuenta al día, primera y última hora, días antes de repetir un cuerpo y qué cuentas reciben.
- **Copies automáticos**: el publicador escribe el copy de cada video desde su guion (`produccion.json`). Arriba va el hook directo con un emoji según el tipo, después 2 o 3 beneficios del cuerpo y el cierre con hashtags, con el largo de cada red y el título de YouTube. Cada cuenta recibe una variante distinta.
- En el editor, «Escribir otro copy» saca otra variante. Los videos sin guion usan lo que se escucha en el audio (solo si está faster-whisper) y avisan para que los revises.

## 1.2.0 · Conectado con producción

- Pestaña nueva **Listos**: muestra sola los videos que la Sala dejó en V.FINALES de cada producción (Drive «EDICIÓN DE VIDEOS» y la copia de la Sala). Ya no hace falta importar a mano.
- Marca varios (o «Marcar los nuevos» de una producción), elige a qué redes van y cuándo: repartidos en la semana desde un día, de 1 a 5 por día, o publicar ahora.
- Elige la cuenta de TikTok o el canal de YouTube para todo el grupo, y si quieres, apruébalos de una vez.
- Cada video dice si ya está en la cola y a qué hora sale. Los carruseles (una carpeta con fotos dentro de V.FINALES) también entran.
- En Conexiones puedes poner otras carpetas de producción si no se encuentran solas.

## 1.1.1 · Textos más prolijos

- Las etiquetas salen con mayúscula inicial: «Dueños», «Picazón», «Reproducciones».
- Los títulos de filtros y tablas ya no van todo en mayúsculas.
- Fechas más cortas y claras: «Mié 21 · 09:00».

## 1.1.0 · Antena: nueva cara, Publicadas y varias cuentas

- Nueva marca «Antena», con el mismo estilo que la Sala de edición: oscuro por defecto y botón para pasar a claro.
- Pestaña **Publicadas**: lo que ya salió en Instagram, Facebook, TikTok y YouTube, cada pieza con su medida real (9:16, 4:5, 1:1). Los carruseles se pasan con flechas, con me gusta, vistas, alcance y guardados. Arriba se ven las próximas piezas para ver cómo queda el feed.
- **Cola** con tres vistas: Lista con vista previa fija, Tablero (por revisar, aprobadas, publicadas, con error) y Calendario semanal.
- Filtros en todo: por red, por tipo (videos o posts y carruseles) y por formato.
- Editor lateral con vista de celular, contador de caracteres por red, cuenta o canal por pieza y aviso si cierras sin guardar.
- Varias cuentas de TikTok y varios canales de YouTube: una fila por cuenta en Conexiones y la cuenta se elige en cada pieza.
- Métricas con los seguidores de cada cuenta.
- Arreglo: conexión de TikTok para apps de escritorio (PKCE).
- Se adapta a pantallas chicas.

## 1.0.0 · primera versión

- Cola orgánica: importa V.FINALES o paquete.json, arma el calendario (5 videos y 1 carrusel por día) y publica sola a su hora lo que apruebes.
- Redes: Instagram (Reels y carruseles), Facebook (Reels y carruseles), TikTok (a la bandeja o directo) y YouTube Shorts.
- Revisa el copy antes de aprobar: palabras que el brief pide evitar, largo por red y TOFU sin Suplevet en la primera línea.
- Pauta en Meta Ads: campañas de reproducciones, alcance, tráfico o mensajes. Todo se crea en pausa y solo gasta al apretar «Activar».
- Métricas: las guarda en metricas/<semana>.json para el estratega, y las de pauta en metricas/<semana>_pauta.json.
- Modo simulación prendido al instalar.
