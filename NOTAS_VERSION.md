## 1.10.0 · Qué publicar con fichas grandes y menos sorpresas

- **Hoy (Qué publicar) con fichas como en el celular**: cada cuenta es una franja a todo el ancho y cada video es una ficha vertical con la imagen grande y la hora encima. Al pasar el mouse el video se mueve sin sonido. Con un clic se ve en grande.
- **El día entero de cada cuenta**: lo que ya está en la cola sale también como ficha (con «En la cola», «Simulada» o «Con error»), ordenado por hora junto a lo sugerido. Un clic lo abre para editarlo.
- La casilla de cada ficha está arriba a la derecha. Lo que no va se ve en gris con «No va», y marcar o desmarcar ya no salta la página. Cada ficha tiene «Cambiar» y un menú «⋯» con «Ver en grande» y «Ya lo publiqué a mano aquí».
- **«Nuevo» dice la verdad**: solo sale cuando el video no está en la cola de ninguna cuenta ni va a otra ese mismo día. Las cuentas se nombran con su red («TikTok · Suplevet»), porque hay nombres repetidos.
- **Nunca el mismo cuerpo el mismo día**, también con lo que pasó por Subir contenido (antes se escapaba: un C1 en la cola y otro C1 sugerido a los 5 minutos). Lo sugerido queda al menos a 30 minutos de lo que ya está en la cola.
- Lo que falló al publicar ya no se vuelve a sugerir en esa cuenta: al reintentarlo podía salir dos veces.
- La página de Facebook puesta en Preparación muestra su nombre real (antes decía «Página de credenciales.env»).
- «Cambiar» en un carrusel lo cambia solo en esa cuenta. «Armar de nuevo» vuelve a leer Drive; cambiar la fecha o «Cambiar» ya no esperan a Drive.
- Ajustes ya no dice «Hay cambios sin guardar» si no cambiaste nada.
- Los horarios de Conexiones se guardan siempre como 08:00 (con «8:00» la cola se ordenaba mal) y avisa si una hora no vale.
- Una pieza aprobada no se puede quedar sin día ni hora (nunca habría salido).
- Los botones ya no fallan con nombres que llevan apóstrofo («Mascotas D'Lux»). El código ya no sale como «P04-P04-…».
- El visor: las flechas ya no reinician el video, el foco entra en «Cerrar» y vuelve al botón que lo abrió, y Tab no se escapa de la ventana.
- Las preguntas de confirmación que apagan o borran algo dejan el foco en «Cancelar». «Apagar simulación» va en rojo.
- Palabras parejas: «Qué publicar», «Armar de nuevo», «videos terminados», «Ya está publicado», «Hora del primer video»… Los avisos ya no dicen «1 cuerpos».
- Los avisos flotantes ya no tapan la barra de abajo; las casillas miden lo mismo que los botones.

## 1.9.0 · Varias cuentas de verdad y copies que calzan con el video

- **Conectar otra cuenta** ahora abre tu navegador (antes se abría dentro del Publicador y siempre volvía a entrar la misma cuenta). Ahí cambias de cuenta o cierras sesión, pulsas «Agregar cuenta» y la nueva aparece sola en Conexiones.
- **Subir contenido con varias cuentas**: en cada red eliges una o varias cuentas (por ejemplo las tres de TikTok). El mismo video sale en cada una con su propio copy, un día después en la siguiente cuenta. Un video que ya está en la cola se puede volver a marcar para mandarlo a otra cuenta.
- **Hoy reparte mejor entre cuentas**: el mismo video espera al menos un día antes de salir en otra cuenta de la misma red (se cambia en Ajustes › «Días entre cuentas»), y cada cuenta sale unos minutos corrida de las demás: ya no salen todas al mismo minuto.
- **La Cola dice a qué cuenta va** cada pieza cuando una red tiene varias. Se puede buscar por cuenta.
- **Copies desde el guion, mejor armados**: los videos «P2H1», «P6 H1»… se leen como cuerpo 2, cuerpo 6 (antes se les ponía el copy del cuerpo 1). Usa el texto del cuerpo y del CTA que el guionista dejó escritos en el guion, y los beneficios salen en frases enteras (antes salían cortados: «…cuidan su piel y»).
- **Nunca el mismo cuerpo el mismo día en una cuenta**, también con los videos «P2H1» y «P2H2» (antes se contaban como cuerpos distintos).
- **Publicadas**: si una cuenta falla (por ejemplo, venció su permiso), las otras de la misma red igual se ven, y dice cuál hay que reconectar.
- Hoy ya no muestra videos rotos: los que siguen en Drive llevan su miniatura o una carpeta, y «Ver» los baja primero.
- La pantalla se refresca mucho más rápido con la cola llena (de 1,6 s a 0,04 s con 130 piezas).
- TikTok en modo Directo: no deja aprobar sin elegir quién puede ver el video, y si TikTok no aprobó la app explica qué hacer.
- «Recoger ahora» en Métricas guarda los números de cada cuenta aunque todavía no haya nada publicado. Y si el instalado y el portable deben usar los mismos datos, basta un `usar_datos_de.txt` en datos/ con la carpeta que tiene las llaves.

## 1.8.2 · Las tres apps se ven igual

- Las tres apps se ven y se sienten igual: el mismo bloque de estilo en la Sala de edición, la Sala de diseño y el Publicador.
- Botones del mismo alto en las tres (36 px; los chicos, 30 px), con el texto centrado.
- Avisos flotantes iguales: abajo al centro, con una franja del color del estado (verde listo, ámbar cuidado, rojo error, azul información).
- Etiquetas (✓ Listo, Por rearmar…) del mismo tamaño y letra; los rótulos de sección en mayúsculas; los títulos con las mismas medidas.
- La rueda de «cargando» es la misma en todas.

## 1.8.1 · Bordes iguales en las tres apps

- Bordes iguales en las tres apps: las casillas para escribir o elegir y los botones con esquinas de 9 px, las tarjetas de 14 px y las ventanas de 16 px. La muestra del selector de color también se ve redondeada.

## 1.8.0 · Subir contenido más claro, Procesos arriba y logos de verdad

- La pestaña **Listos** ahora se llama **Subir contenido**. Muestra solo lo terminado: los **videos finales** de la Sala de edición (carpeta V.FINALES; nada de partes sueltas ni clips) y los **posts y carruseles** de la Sala de diseño (carpeta FINAL).
- Cada pieza dice de qué sala viene (**E** Sala de edición, **D** Sala de diseño) y en qué carpeta está. Los videos sin portada muestran su imagen de Drive.
- **Qué post va con qué video**: el post dice «Va con: P04-C1-H1-CTA1» y el video dice «Tiene post». Sale de los posts hechos con «Crear con IA» a partir de un video en la Sala de diseño (desde su versión 0.10.2).
- **Filtros más claros**: la semana (lunes a domingo, la misma en las tres apps: S03 = 19 – 25 oct) y de dónde viene (las dos salas, solo videos o solo posts, y el proyecto).
- El **Registro** pasó al botón **☰ Procesos** de arriba, al lado de Simulación, como en la Sala de edición: lo que se está subiendo, los avisos del día, los errores y todo el historial, con buscador.
- **Logos oficiales** de Instagram, Facebook, TikTok y YouTube.
- La pestaña **Pauta** quedó oculta por ahora.

## 1.7.0 · Lee Drive como las salas, y más seguro al publicar

- **Listos lee Drive directo**, con la misma cuenta de Google de las salas: los videos de la Sala de edición (V.FINALES, también dentro de cada día o sesión) y, por primera vez, los **posts y carruseles de la Sala de diseño** (DISEÑO/…/FINAL).
- Arriba eliges la **semana** (abre sola en la de hoy) y el **proyecto**. Los videos se bajan recién al verlos o al publicarlos; si ya están en la PC, usa esos.
- El brief de la semana y los guiones salen de Drive: ahora sí revisa las palabras que el brief pide evitar.
- **Nunca sube dos veces lo mismo**: lo que ya salió o se está subiendo no se vuelve a subir, ni con «Publicar ahora».
- Si se cierra el programa a mitad de una subida, esa pieza queda en **Revisar** (no se sube sola otra vez). Si la PC estuvo apagada, lo que tiene más de 90 minutos de atraso queda **Atrasado** y no sale todo de golpe.
- No se pueden abrir **dos Publicadores** con los mismos datos, y la cola o las llaves nunca se borran si un archivo no se puede leer.
- Las llaves de TikTok y YouTube ya no se pisan entre cuentas; si un permiso vence, dice «reconecta la cuenta».
- **Conectar con Facebook**: varias páginas y sus cuentas de Instagram. Instagram acepta posts de una sola imagen.
- Nueva pestaña **Preparación**: cada uno pega las llaves de sus apps de Meta, TikTok y Google, con los pasos de cada red. TikTok directo con la pantalla que pide su revisión.
- **Cabecera y menú de la cuenta iguales a las salas**; Configuración se abre desde la cuenta. Muchos arreglos en Hoy, Listos, Cola, Pauta, Publicadas y Conexiones.

## 1.6.0 · Entrar y elegir la carpeta, actualizar más seguro

- **Entrar y elegir la carpeta, paso a paso** (igual en las tres apps): entras con Google sin pegar ningún link, eliges la carpeta del equipo (una tuya, una compartida contigo, una nueva o con su link) y te dice cómo invitar al equipo como Editor. En **Configuración → Cuenta** está la carpeta, con «Cambiar de carpeta…».
- **Actualizar más seguro**: si GitHub se corta, vuelve a intentar y, si hace falta, baja la versión por otro camino. Mientras se instala, el botón dice «⟳ Actualizando…» y una cortina tapa el programa hasta que la versión nueva arranca.
- **Más seguridad**: el Publicador solo acepta órdenes de su propia ventana (una página de internet ya no puede mandarle nada).

## 1.5.0 · Configuración como en las salas

- La **Configuración** tiene el mismo diseño en las tres apps (menú a la izquierda, secciones a la derecha), con **Cuenta y dispositivos** y **Buscar actualizaciones**.
- Nueva pestaña **Configuración**: tu cuenta, dispositivos y seguridad, un atajo a las redes conectadas y **Buscar actualizaciones**.

## 1.4.0 · Entrar con Google y dispositivos

- **Entrar con Google**: al abrir, si no hay sesión, aparece la pantalla «Entrar con Google» (con el link de la carpeta del proyecto). La sesión queda abierta hasta que alguien toque «Cerrar sesión», y es una sola para las tres apps de la PC: si entras en una, ya entraste en todas.
- Arriba a la derecha está tu cuenta (foto y nombre). Ahí: **Dispositivos y seguridad**: las PCs donde se abrió tu cuenta, con qué apps, la primera y la última vez, las nuevas marcadas, y «Cerrar sesión ahí» o «Cerrar sesión en todos los demás» (esa PC la cierra sola en máximo 10 minutos).
- El candado de verdad sigue siendo Drive: solo entra quien tenga compartida la carpeta del proyecto.

## 1.3.3 · Abre más rápido

- El Publicador abre más rápido: la ventana aparece al instante con «Abriendo…» y la app carga apenas está lista (antes no se veía nada hasta que todo arrancaba). Para tenerlo hay que pasar una vez el instalador completo de esta versión; con «Actualizar ahora» todo sigue funcionando igual que antes.

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
