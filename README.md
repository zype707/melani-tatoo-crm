# Tinta · CRM para un estudio de tatuaje

CRM completo para una tatuadora que trabaja sola. Cubre agenda, fichas de clientes, consentimientos firmados, mensajería, finanzas, catálogo flash y un asistente de IA.

El centro del producto son los **mensajes**. Cada día prepara el trabajo de mensajería: recordatorios, cuidados, retoques, cumpleaños, aniversarios del tatuaje, campañas y reactivaciones. La tatuadora los revisa, los edita si quiere y los envía con un toque por WhatsApp o SMS desde su móvil. **Nunca se envía nada automáticamente.**

| Escritorio | Móvil |
|---|---|
| ![Hoy](docs/capturas/escritorio-hoy.png) | ![Hoy en móvil](docs/capturas/movil-hoy.png) |
| ![Mensajes de hoy](docs/capturas/escritorio-mensajes.png) | ![Mensajes en móvil](docs/capturas/movil-mensajes.png) |

Más capturas en [`docs/capturas/`](docs/capturas/). Todos los datos que aparecen son ficticios y se generan con `seed_demo`.

---

## Índice

1. [Resumen](#1-resumen)
2. [Mapa de pantallas](#2-mapa-de-pantallas)
3. [Funcionalidades](#3-funcionalidades)
4. [Decisiones de diseño](#4-decisiones-de-diseño)
5. [Arquitectura](#5-arquitectura)
6. [Modelo de datos](#6-modelo-de-datos)
7. [Seguridad](#7-seguridad)
8. [Guía estética](#8-guía-estética)
9. [Instalación local](#9-instalación-local)
10. [Variables de entorno](#10-variables-de-entorno)
11. [Despliegue en Render paso a paso](#11-despliegue-en-render-paso-a-paso)
12. [Primera cuenta y 2FA](#12-primera-cuenta-y-2fa)
13. [Uso diario](#13-uso-diario)
14. [Tareas programadas](#14-tareas-programadas)
15. [Copias de seguridad y restauración](#15-copias-de-seguridad-y-restauración)
16. [Privacidad y protección de datos](#16-privacidad-y-protección-de-datos)
17. [Asistente de IA](#17-asistente-de-ia)
18. [Pruebas y calidad](#18-pruebas-y-calidad)
19. [Limitaciones conocidas](#19-limitaciones-conocidas)
20. [Hoja de ruta](#20-hoja-de-ruta)

---

## 1. Resumen

| | |
|---|---|
| **Para quién** | Una tatuadora autónoma en Orlando, Florida (EE. UU.). Interfaz bilingüe **español / inglés** (selector ES/EN). |
| **Stack** | Django 6.1 · PostgreSQL 17 · plantillas en servidor + HTMX 2 · CSS propio (sin Node ni build) |
| **Servidor** | Gunicorn + WhiteNoise, desplegado en Render con Blueprint (`render.yaml`) |
| **Seguridad** | Solo correos autorizados (`CORREOS_PERMITIDOS`), Argon2, 2FA TOTP obligatorio, códigos de recuperación, bloqueo de accesos, CSP estricta sin scripts inline |
| **Integraciones** | Solo la API de OpenAI, para el asistente (opcional) |
| **Mensajes** | Enlaces `wa.me` y `sms:`, o copiar. Cada envío queda registrado. |
| **Calidad** | 222 pruebas (pytest), ruff sin avisos, contraste WCAG AA verificado por script |

## 2. Mapa de pantallas

```
Acceso ── Verificación 2FA ── (primera vez) Configurar 2FA → Códigos de recuperación
│
├─ Hoy (panel)               resumen del día, avisos, gráficos de ingresos y citas
├─ Agenda                    día · semana · mes · lista
│   ├─ Cita (detalle)        estado, pagos, señal, notas, enlace para la clienta, cierre de sesión
│   ├─ Nueva / editar cita
│   ├─ Lista de espera
│   └─ Horario y tipos       horario laboral, bloqueos y vacaciones, tipos de cita
├─ Mensajes
│   ├─ Hoy (bandeja)         vista previa editable · WhatsApp · SMS · Copiar · Posponer · Descartar · Marcar enviado
│   ├─ Historial
│   ├─ Campañas              segmento → recuento → envío escalonado por días
│   ├─ Fechas destacadas     reglas (fija, n-ésimo día, último, viernes 13, única)
│   ├─ Cuidados              secuencia día 1 · día 3 · semana 2 · retoque (~30 días)
│   └─ Plantillas            variables, vista previa en vivo
├─ Clientes
│   ├─ Ficha                 contacto, salud, promociones, tatuajes, línea de tiempo, notas, consentimientos
│   ├─ Tatuaje               fotos (referencia / resultado / cicatrizado), sesiones, retoque
│   ├─ Consentimiento        modo quiosco: la clienta firma con el dedo → PDF
│   └─ Exportar · Anonimizar · Eliminar
├─ Solicitudes               bandeja de reservas públicas, triaje con IA, aprobar → convertir en cita
├─ Flash                     catálogo de diseños (disponible / reservado / vendido)
├─ Finanzas                  ingresos, gastos, balance mensual, CSV
├─ Asistente IA              búsqueda en lenguaje natural, ideas de retención
└─ Ajustes                   estudio, reservas, textos legales, retención, IA, datos y copias, auditoría

Páginas públicas (sin cuenta, con token):
  /c/<token>/   la clienta confirma, cancela o pide cambiar su cita
  /r/<token>/   formulario de solicitud de reserva con imágenes
  /f/<token>/   catálogo flash público (opcional)
```

En **móvil** hay una barra inferior (Hoy · Agenda · Mensajes · Clientes · Más). En **escritorio** hay una barra lateral.

Atajos de teclado: <kbd>/</kbd> buscar · <kbd>n</kbd> nueva cita · <kbd>c</kbd> nuevo cliente · <kbd>h</kbd> Hoy · <kbd>a</kbd> agenda · <kbd>m</kbd> mensajes · <kbd>?</kbd> ayuda.

## 3. Funcionalidades

### Agenda
- **Vistas:** día, semana, mes y lista. La vista elegida se recuerda.
- **Tipos de cita** configurables, con duración, color y señal sugerida. Hay 4 de serie: Consulta, Sesión, Sesión larga y Retoque.
- **Estados:** solicitada, confirmada, realizada, cancelada y no-show.
- **Solapes imposibles:** los impide una restricción de exclusión de PostgreSQL (`tstzrange`), no solo la validación del formulario. Así se evitan también las carreras entre dos pestañas.
- **Horario laboral** con dos tramos por día, bloqueos (vacaciones, convenciones…) y aviso si una cita cae fuera de horario.
- **Señales y pagos** por cita, con devolución. Los métodos son efectivo, tarjeta, Zelle, Venmo, Cash App, PayPal, transferencia y otro.
- **Lista de espera:** al cancelar una cita, se sugieren las clientes de la lista que encajan con el hueco y se puede ofrecérselo con un mensaje ya preparado.
- **Enlace único por cita**, con caducidad. La clienta confirma, cancela o pide cambiar la fecha sin crear cuenta. Las peticiones de cambio aparecen como aviso en Hoy y en la agenda.
- **Cierre de sesión:** registra el pago, las notas y si el tatuaje queda terminado. Si el tipo de cita lo indica, arranca la secuencia de cuidados.

### Solicitudes de reserva
- Página pública con imágenes de referencia (hasta 5 de 8 MB) y comprobación de edad.
- Protegida con honeypot, sello de tiempo firmado, límite por IP y límite global diario.
- La bandeja «Solicitudes» permite aprobar, convertir en cita, rechazar o marcar como spam. El spam se purga con sus imágenes.
- Al convertir una solicitud se crea o vincula la clienta (detecta duplicados por teléfono o email). El tatuaje se crea con las imágenes de referencia copiadas.
- Opcionalmente, un **triaje con IA** sugiere estilo, tamaño, sesiones, dudas que preguntar y prioridad.

### Clientes
- **Ficha:** datos de contacto con teléfono normalizado a E.164, fecha de nacimiento con edad mínima configurable, canal preferido (WhatsApp o SMS), bloqueo de contacto, notas privadas y etiquetas libres.
- **Consentimiento de marketing** con fecha y origen (presencial, formulario, verbal…), historial de cambios y baja con un clic. Al dar de baja, los mensajes promocionales pendientes se descartan.
- **Datos de salud:** alergias, medicación, anticoagulantes, diabetes, epilepsia, problemas cardíacos, embarazo o lactancia, piel y otros. Generan un aviso destacado en la ficha y en la cita.
- **Consentimiento informado digital:** modo quiosco a pantalla completa. La clienta revisa sus datos, responde el cuestionario de salud y firma con el dedo. Se genera un PDF con el texto exacto de la versión vigente, la firma y su huella SHA-256. Se registra quién firmó, cuándo y desde qué IP.
- **Tatuajes:** zona, estilo, tamaño, sesiones y precio. Las fotos se clasifican como referencia, resultado o cicatrizado. Se registra el retoque y la fecha de aniversario.
- **Línea de tiempo:** citas, pagos, mensajes, notas y consentimientos en un solo hilo.
- **Derechos sobre los datos:**
  - Exportar la ficha completa en un zip con JSON, fotos y PDFs.
  - Anonimizar: conserva las finanzas y los consentimientos retenidos por ley.
  - Eliminar: se bloquea si hay consentimientos que la ley obliga a conservar.
  - Anonimizar y eliminar son solo para la propietaria y piden escribir el nombre completo para confirmar.

### Mensajería
- **Plantillas** con variables (`{nombre}`, `{fecha_cita}`, `{hora_cita}`, `{enlace_cita}`, `{enlace_reserva}`, `{tatuaje}`, `{aniversario}`, `{estudio}`, `{artista}`…). Las variables se validan, hay vista previa en vivo y una plantilla predeterminada por categoría. Vienen 21 plantillas de serie.
- **«Mensajes de hoy»:**
  - Bandeja diaria agrupada y filtrable por categoría, con prioridad.
  - Cada mensaje tiene vista previa editable y los botones WhatsApp, SMS/RCS, Copiar, Posponer, Descartar y Marcar enviado.
  - Al pulsar WhatsApp o SMS se abre la app con el texto ya escrito (el que esté en pantalla, aunque se haya editado). El envío queda registrado.
  - Se puede deshacer.
- **Generadores diarios:**
  - Recordatorios de cita (N días antes, configurable).
  - Cuidados: día 1, día 3 y semana 2.
  - Oferta de retoque a los ~30 días.
  - Cumpleaños y aniversarios del tatuaje.
  - Reactivación de clientes inactivos, con cupo diario.
  - Fechas destacadas y campañas.
- **Fechas destacadas** editables. Hay 9 de serie adaptadas a EE. UU.: Año Nuevo, San Valentín, Día de la Madre (2.º domingo de mayo), Día del Padre (3.er domingo de junio), Día Nacional del Tatuaje (17 de julio), Halloween, Acción de Gracias (4.º jueves de noviembre), Navidad y Viernes 13 (desactivado).
- **Segmentos automáticos:** inactivos, en riesgo, proyectos a medias, VIP, nuevos del mes, cumplen este mes y todos.
- **Campañas escalonadas:** se elige el segmento, se ve el recuento en vivo y se reparte el envío en N mensajes por día hasta la fecha límite.
- **Respeto absoluto del consentimiento y del canal.** La comprobación se hace tres veces:
  - al **generar** el mensaje;
  - al **mostrarlo**: si la clienta retiró el permiso, desaparece de la bandeja;
  - al **enviarlo**: el servidor rechaza marcar como enviado un mensaje no permitido.

  Los promocionales solo van a clientes con consentimiento. Los de servicio (recordatorios, cuidados) no lo necesitan. Las clientes bloqueadas o anonimizadas nunca reciben nada.
- **Idempotencia:** cada mensaje tiene una clave única (`tipo:objeto:fecha`). Ejecutar la tarea diaria dos veces no duplica nada.

### Panel, finanzas y catálogo
- **Hoy:**
  - Próxima cita, citas de hoy y de la semana, mensajes pendientes, solicitudes nuevas e ingresos del mes frente al mismo tramo del mes anterior.
  - Avisos de cambios pedidos.
  - Tasa de no-show y tasa de retorno.
  - Próximos cumpleaños y próxima fecha destacada.
  - Gráficos SVG propios.
- **Finanzas** (solo propietaria):
  - Ingresos (pagos de citas y ventas sueltas), gastos por categoría y balance mensual con gráfico de 12 meses.
  - Exportación CSV protegida contra inyección de fórmulas y auditada.
- **Flash:**
  - Catálogo con imagen, precio, tamaño, zona sugerida y estado (disponible, reservado o vendido). Los diseños pueden ser repetibles.
  - La página pública es opcional y tiene su propio token. Desde un diseño se puede pedir cita, lo que rellena la solicitud.

### Extras
- **Dictado por voz** en las notas y los textos largos (Web Speech API del navegador, `es-US`).
- **PWA instalable:** manifiesto, iconos, service worker y página sin conexión. El service worker **no** guarda en caché páginas con datos personales.
- **Exportación total** (zip con JSON y archivos) y **copias de seguridad** descargables. Ambas piden el código 2FA.
- **Registro de auditoría:** accesos, fallos, bloqueos, 2FA, exportaciones, borrados, anonimizaciones, acceso a documentos, cambios de ajustes, tareas y uso de IA.
- **Ajustes del estudio:** marca y logo, datos de contacto, reservas, edad mínima, textos legales (consentimiento con versionado, privacidad, política de señales, cuidados), retención y parámetros de mensajería y de IA.

## 4. Decisiones de diseño

| Decisión | Por qué |
|---|---|
| **Envío manual por enlaces `wa.me` / `sms:`** | Sin coste por mensaje, sin cuentas de empresa ni riesgo de bloqueo. Los mensajes salen de su número personal, con su voz. El canal está desacoplado en `apps/mensajeria/canales.py`, así que la API oficial de WhatsApp se puede añadir después sin tocar la bandeja. |
| **Plantillas de servidor + HTMX, sin build** | Una persona puede mantenerlo. Sin Node, sin bundler, sin dependencias de frontend salvo HTMX (servido desde el propio dominio). |
| **CSP sin `unsafe-inline` en scripts ni estilos** | Todo el JS vive en archivos estáticos y se activa con atributos `data-*`. Una inyección de HTML no puede ejecutar código. |
| **Una sola instancia con disco persistente** | Las fotos, firmas y PDFs son privados y no pueden ir a un CDN público. Para un estudio con una usuaria, un disco con snapshots diarios es más sencillo y barato que un almacenamiento de objetos. |
| **Tareas de disco vía endpoint interno** | Los cron jobs de Render no pueden montar el disco. Las tareas que tocan archivos (copia, limpieza) las ejecuta el web service al recibir una petición autenticada del cron. |
| **Tokens públicos guardados como hash** | Si alguien leyera la base de datos, no podría reconstruir los enlaces de las clientes. Solo los dos enlaces del estudio (reservas y catálogo) guardan el token visible, para que ella pueda copiarlos. |
| **La IA propone, ella aprueba** | Ningún texto de la IA se envía ni se guarda solo. Siempre acaba en un campo editable. |
| **Interfaz bilingüe, contenido en el idioma del estudio** | Cada persona elige ES/EN (cookie) y las páginas públicas siguen el idioma del navegador de la clienta. Lo que reciben las clientas (mensajes, variables como `{fecha_cita}`, PDF de consentimiento, textos legales) va siempre en el idioma de `IDIOMA`, para que un mensaje no mezcle idiomas aunque quien lo revisa use la interfaz en otro. Los textos en español son los `msgid` y el inglés vive en `locale/en`. |
| **Edad mínima 18 por defecto** | En Florida, los menores de 16 no pueden tatuarse (salvo excepciones médicas) y los de 16–17 necesitan presencia y consentimiento notarial de un progenitor. Para simplificar y reducir riesgos, el valor por defecto es 18, configurable hasta un mínimo de 16. |

## 5. Arquitectura

```
estudio/            configuración (settings base/dev/test/prod, urls, wsgi, formatos)
apps/
  nucleo/           ajustes, auditoría, tokens, límites, imágenes, archivos privados, exportación,
                    copias, limpieza, gráficos SVG, PWA, endpoint de tareas, comandos de sistema
  cuentas/          usuaria, acceso en dos pasos, TOTP, códigos de recuperación, bloqueo
  clientes/         ficha, salud, tatuajes, fotos, notas, consentimiento firmado, exportar/anonimizar
  agenda/           tipos, citas, horario, bloqueos, lista de espera, solicitudes públicas
  mensajeria/       plantillas, variables, canales, segmentos, generadores, bandeja, campañas
  finanzas/         pagos, gastos, resumen, CSV
  catalogo/         diseños flash y página pública
  ia/               proveedor OpenAI, privacidad (minimización), funciones, búsqueda → ORM
  panel/            pantalla «Hoy»
templates/          plantillas (parciales HTMX con {% partialdef %})
static/             css/app.css, js/ (sin build), vendor/htmx, fuentes autoalojadas, iconos SVG
scripts/            contraste.py (WCAG), generar_iconos.py, capturar.py (capturas de desarrollo)
```

- **Capa de canales** (`apps/mensajeria/canales.py`): `Canal` abstracto con `WhatsAppEnlace`, `SMSEnlace` y `Copia`, más un registro por clave (`whatsapp_link | sms_link | copia`). La bandeja pide `acciones_para(cliente, texto)` y pinta lo que reciba.
- **Servicios de dominio:** cada app tiene un `servicios.py` con la lógica. Las vistas son finas y las pruebas atacan los servicios directamente.
- **HTMX:** fragmentos con `{% partialdef %}` de Django 6. Los eventos `HX-Trigger` (`aviso`, `bandeja-cambio`) disparan los avisos y los contadores. Las peticiones HTMX sin sesión reciben `401` + `HX-Redirect`.
- **Formularios:** un renderizador propio (`apps/nucleo/formularios.py`) da un marcado accesible y uniforme: etiquetas, ayudas, errores con `aria-describedby`.
- **Idiomas:** i18n estándar de Django (`{% translate %}`, `gettext`, `ngettext`) con `i18n` como builtin de plantillas; JS con `gettext` del catálogo `/jsi18n/`. Selector en `templates/componentes/idioma.html`, ayuda de contenido en `apps/nucleo/idioma.py`, plantillas de partida en inglés en `apps/mensajeria/predeterminados_en.py` y `apps/nucleo/textos_en.py`.

## 6. Modelo de datos

```
Usuario ─┬─ TOTPDevice / DispositivoRecuperacion ── CodigoRecuperacion (hash Argon2)
         └─ IntentoAcceso · RegistroAuditoria · UsoIA

Cliente ─┬─ DatosSalud (1:1)
         ├─ EventoConsentimiento (historial de marketing)
         ├─ Etiqueta (M:N)
         ├─ NotaCliente ── (opcional) Cita
         ├─ ConsentimientoInformado (texto versionado, firma PNG, PDF, hash, conservar_hasta)
         ├─ Tatuaje ── FotoTatuaje
         ├─ Cita ─┬─ TipoCita
         │        ├─ Tatuaje (opcional)
         │        └─ Pago
         ├─ EntradaListaEspera
         └─ MensajePreparado ─┬─ Plantilla
                              ├─ Cita / Tatuaje / Campana (opcionales)
                              └─ clave única (idempotencia)

SolicitudReserva ── ImagenSolicitud ;  → Cliente, Tatuaje, Cita, DisenoFlash (opcionales)
Campana ── FechaDestacada ;  PasoCuidado ── Plantilla
HorarioLaboral · Bloqueo · Gasto · DisenoFlash
AjustesEstudio (singleton) · EnlacePublico (hash del token, propósito, caducidad, revocación, usos)
```

Restricciones importantes:
- `cita_sin_solapes`: `EXCLUDE USING gist (tstzrange(inicio, fin) WITH &&)` para las citas activas.
- `MensajePreparado.clave` es única.
- `Campana` es única por (fecha destacada, año).
- El email de `Usuario` es único sin distinguir mayúsculas.
- La búsqueda ignora tildes con la extensión `unaccent`.

## 7. Seguridad

**Acceso**
- **Solo entran los correos de `CORREOS_PERMITIDOS`** (lista separada por comas; el primero es la propietaria, el resto ayudantes). El backend `apps/cuentas/backends.py` rechaza cualquier otro correo y quitar uno de la lista corta su sesión en la siguiente petición.
- No hay registro público. Las cuentas se crean en `/acceso/alta/` con el código secreto `CODIGO_ALTA` (solo para correos de la lista; vacío = alta desactivada) o por consola (`crear_cuenta`, que también exige que el correo esté en la lista).
- Contraseñas con **Argon2**, mínimo 12 caracteres y validadores de Django.
- **Acceso en dos pasos:** la sesión solo existe después de verificar el 2FA. Hasta entonces hay un estado «pre-autenticado» que caduca a los 10 minutos.
- **2FA TOTP obligatorio**, con QR en SVG generado en el servidor y la clave legible por si se prefiere teclearla. Los códigos usados no se aceptan dos veces y hay límite de intentos (throttling).
- **8 códigos de recuperación** de un solo uso. Se guardan con hash Argon2 y se muestran una sola vez.
- **Bloqueo de accesos:** 5 fallos por email + IP en 15 minutos, 20 por IP en una hora y 30 por email en una hora. Se registran todos los intentos.
- Cookies `Secure`, `HttpOnly` y `SameSite=Lax`. La sesión dura 72 horas.
- En los formularios de acceso no se revela si un email existe.

**Cabeceras y navegador**
- **CSP estricta:** `default-src 'self'`, sin scripts ni estilos inline (solo atributos `style`), `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'` y `form-action 'self'`.
- HSTS de un año, redirección a HTTPS, `Referrer-Policy: same-origin`, `Permissions-Policy` restrictiva y `Cross-Origin-Resource-Policy`.
- Las páginas con sesión llevan `Cache-Control: private, no-store`.
- CSRF en todos los formularios y en HTMX (cabecera en el `<body>`).

**Páginas públicas**
- Tokens de 256 bits (`secrets.token_urlsafe(32)`), guardados como **hash SHA-256**, con caducidad, revocación y contador de usos. El formato se valida antes de consultar la base de datos.
  - Los enlaces de cita caducan 2 días después de la cita.
  - Los de reservas y catálogo duran un año y se pueden renovar al instante, lo que invalida el anterior.
- Límites por IP: reserva 5/hora (y 150/día en total), página de cita 20/hora, catálogo 120 cada 10 minutos. Las IPs se leen de `X-Forwarded-For` solo a través del número configurado de proxies de confianza.
- **Subidas estrictas:**
  - Tamaño máximo comprobado antes de leer el cuerpo (413).
  - Número máximo de imágenes.
  - Comprobación de *magic bytes* y verificación con Pillow.
  - Límite contra bombas de descompresión.
  - **Recodificación** a JPEG sin EXIF (sin GPS ni metadatos) y nombres aleatorios.

**Archivos privados**
- Fotos, firmas, imágenes de solicitudes y PDFs viven fuera de `static/`, en `MEDIA_ROOT` (el disco persistente).
- Solo se sirven a través de vistas que exigen sesión verificada, con `Content-Disposition` y `X-Content-Type-Options: nosniff`.
- `MEDIA_URL` no está enrutada.
- La descarga de PDFs de consentimiento queda auditada.

**Producción**
- `DEBUG=False` y `SECRET_KEY` obligatoria de al menos 40 caracteres: el arranque falla si falta.
- `ALLOWED_HOSTS` se deriva de `SITE_URL` y del host de Render.
- Las páginas de error no filtran detalles.
- El endpoint interno `/interno/tareas/<nombre>/`:
  - solo acepta POST con `Authorization: Bearer <TAREAS_SECRETO>` (mínimo 32 caracteres, comparación en tiempo constante);
  - solo ejecuta tareas de una lista blanca;
  - tiene límite de peticiones.
- La copia de seguridad se escribe con permisos `600`. Exportar y descargar copias exige el código 2FA.

## 8. Guía estética

**Neobrutalismo de alto contraste.** Superficies planas, bordes gruesos y sombras duras desplazadas (sin difuminar). Sin degradados, sin sombras suaves, sin desenfoque y **sin esquinas redondeadas**.

**Paleta**

| Token | Hex | Uso |
|---|---|---|
| `--tinta` | `#01161b` | fondo más profundo, texto sobre amarillo y hueso |
| `--petroleo-950` | `#031f25` | campos de formulario |
| `--petroleo-900` | `#062f38` | fondo principal |
| `--petroleo-800` | `#0b4250` | tarjetas y bloques |
| `--petroleo-700` | `#12586a` | estados hover y separadores |
| `--hueso` | `#f4f1e8` | texto principal, botones secundarios |
| `--niebla` | `#a8cbd2` | texto secundario |
| `--amarillo` | `#ffe500` | **único acento** |

Los tipos de cita usan seis tonos pastel (hueso, menta, cielo, lila, arena, rosa) con texto en tinta. El color nunca es la única pista: las citas pendientes llevan además borde discontinuo y la etiqueta «POR CONFIRMAR».

**Reglas del amarillo.** Es el único acento y solo se usa para:
1. la acción principal de cada pantalla (Nueva cita, WhatsApp, Guardar…);
2. los datos críticos (mensajes por enviar, alertas de salud, avisos que requieren acción);
3. el elemento activo de la navegación y el foco del teclado.

Nunca se usa para decorar. Si en una pantalla hay más de dos o tres cosas amarillas, sobra alguna.

**Tipografía** (autoalojada, licencia OFL)
- **Archivo** variable, en pesos 800–900 con anchura expandida para los titulares.
- **Atkinson Hyperlegible** para el texto: está diseñada para máxima legibilidad.
- Las cifras usan numerales tabulares.

**Contraste WCAG AA.** Se verifica con `python scripts/contraste.py`, que además se ejecuta como prueba. Resultado actual:

| Texto | Fondo | Ratio | Mínimo |
|---|---|---|---|
| hueso | petróleo 900 | 12.64:1 | 4.5 |
| hueso | petróleo 800 | 9.74:1 | 4.5 |
| hueso | petróleo 700 | 7.07:1 | 4.5 |
| niebla | petróleo 900 | 8.25:1 | 4.5 |
| niebla | petróleo 800 | 6.36:1 | 4.5 |
| tinta | amarillo | 14.54:1 | 4.5 |
| amarillo | petróleo 900 | 11.19:1 | 4.5 |
| amarillo | petróleo 800 | 8.62:1 | 4.5 |
| niebla (borde de campo) | petróleo 950 | 9.90:1 | 3.0 |

**Accesibilidad**
- HTML semántico, enlace «saltar al contenido» y foco visible (contorno amarillo grueso).
- Diálogos nativos `<dialog>`, `aria-live` para los avisos y etiquetas en todos los campos.
- Zonas táctiles de al menos 44 px. Se respeta `prefers-reduced-motion`.
- Los gráficos SVG tienen título, leyenda, tooltips nativos y una tabla equivalente. Las series se distinguen por **relleno sólido frente a trama**, no solo por color.

## 9. Instalación local

Requisitos: Python 3.13 y PostgreSQL 16 o superior (necesita las extensiones `btree_gist` y `unaccent`, incluidas en el paquete *contrib* habitual).

```bash
# 1. Base de datos
createuser estudio --createdb -P          # contraseña: estudio (solo local)
createdb estudio -O estudio

# 2. Entorno
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # revisa los valores; se leen del entorno
export $(grep -v '^#' .env | xargs)        # o usa direnv / tu IDE

# 3. Esquema y contenido inicial
python manage.py migrate
python manage.py createcachetable
python manage.py inicializar_estudio       # plantillas, cuidados, fechas, tipos, horario

# 4. Cuenta (la contraseña se lee de una variable para no dejarla en el historial)
read -s CLAVE && export CLAVE
python manage.py crear_cuenta --email tu@correo.example --nombre "Tu Nombre" --password-env CLAVE

# 5. (Opcional) datos ficticios para probar
python manage.py seed_demo                 # --limpiar para empezar de cero

python manage.py runserver
```

Abre http://localhost:8000, entra y escanea el QR con tu app de autenticación (Google Authenticator, 1Password, Authy…).

`seed_demo` crea «Tinta Brava Studio» con 40 clientes ficticios, todos con teléfonos `555-01XX`, el rango reservado para ficción. Añade 18 meses de historial, citas para las próximas 3 semanas, fotos generadas, pagos, gastos, solicitudes, flash, consentimientos firmados y la bandeja del día ya preparada. Con `DEBUG=False` se niega a ejecutarse salvo con `--forzar`.

## 10. Variables de entorno

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | sí | `estudio.settings.dev` (manage.py) | `estudio.settings.prod` en producción |
| `SECRET_KEY` | en prod | — | ≥ 40 caracteres aleatorios. Render la genera sola. |
| `DATABASE_URL` | sí | `postgres://estudio:estudio@localhost:5432/estudio` | Conexión a PostgreSQL |
| `SITE_URL` | en prod | `RENDER_EXTERNAL_URL` o localhost | URL pública. Se usa en los enlaces de los mensajes y para autorizar el host. |
| `ALLOWED_HOSTS` | no | (se deriva de `SITE_URL`) | Hosts adicionales, separados por comas |
| `CSRF_TRUSTED_ORIGINS` | no | — | Solo si se accede desde otro origen |
| `TIME_ZONE` | no | `America/New_York` | Zona horaria del estudio (Orlando) |
| `REGION_TELEFONO` | no | `US` | Región para interpretar teléfonos sin prefijo |
| `MONEDA` / `SIMBOLO_MONEDA` | no | `USD` / `$` | |
| `MEDIA_ROOT` | en prod | `./media_privado` | Archivos privados. En Render: `/var/data/media`. |
| `COPIAS_ROOT` | no | `./copias` | Copias de seguridad. En Render: `/var/data/copias`. |
| `COPIAS_A_CONSERVAR` | no | `14` | Número de copias nocturnas que se guardan |
| `TAREAS_SECRETO` | en prod | — | ≥ 32 caracteres. Autentica cron → web. Render la genera sola. |
| `PROXIES_DE_CONFIANZA` | no | `0` (dev) / `1` (prod) | Proxies delante de la app, para leer bien la IP |
| `SESION_HORAS` | no | `72` | Duración de la sesión |
| `ACCESO_MAX_FALLOS_EMAIL_IP` / `_IP` / `_EMAIL` | no | `5` / `20` / `30` | Umbrales de bloqueo |
| `ACCESO_VENTANA_MINUTOS` | no | `15` | Ventana del bloqueo por email + IP |
| `SUBIDAS_MAX_MB` / `SUBIDAS_MAX_IMAGENES` | no | `8` / `5` | Límites de las subidas públicas |
| `HSTS_SEGUNDOS` | no | `31536000` | |
| `CORREOS_PERMITIDOS` | sí | vacío (nadie entra) | Correos que pueden iniciar sesión, separados por comas. El primero es la propietaria. |
| `CODIGO_ALTA` | no | vacío (alta desactivada) | Código secreto (≥ 16 caracteres) para crear cuentas en `/acceso/alta/` |
| `IDIOMA` | no | `es` | Idioma del contenido para clientes (mensajes, PDF de consentimiento, textos legales y plantillas de partida): `es` o `en`. La interfaz la elige cada persona. |
| `OPENAI_API_KEY` | no | vacío | Sin clave, el asistente se desactiva y todo lo demás funciona igual |
| `IA_MODELO` | no | `gpt-6-luna` | Modelo de OpenAI. **Verifica el ID vigente** antes de desplegar (ver §17). |
| `IA_LIMITE_MENSUAL` | no | `300` | Peticiones de IA al mes (también ajustable en Ajustes, sin superar este tope) |
| `IA_TIMEOUT_SEGUNDOS` | no | `25` | |

Ningún valor real va en el repositorio. `.env` está en `.gitignore`.

## 11. Despliegue en Render paso a paso

Hay dos Blueprints, cada uno con su guía:

| Archivo | Para qué | Guía |
|---|---|---|
| `render-free.yaml` | Probar sin método de pago (base de datos que caduca a los 30 días, sin disco ni cron) | [DEPLOY_RENDER_FREE.md](DEPLOY_RENDER_FREE.md) |
| `render.yaml` | Producción | [DEPLOY_RENDER_PAGO.md](DEPLOY_RENDER_PAGO.md) |

Resumen del despliegue de producción. El `render.yaml` crea todo:

| Recurso | Plan | Para qué |
|---|---|---|
| `tinta-crm` (web) | `0.5c-512mb` (de pago) | La aplicación, con un **disco de 5 GB** en `/var/data` |
| `tinta-db` (PostgreSQL 17) | `0.1c-256mb` (de pago) | Base de datos sin acceso desde internet, con recuperación a un momento dado |
| `tinta-bandeja-diaria` (cron) | — | Prepara «Mensajes de hoy» cada mañana |
| `tinta-mantenimiento` (cron) | — | Copia de seguridad y limpieza de archivos cada noche |

Los planes gratuitos no sirven aquí: el plan web gratuito no admite disco persistente ni pre-deploy, y la base de datos gratuita no tiene copias de seguridad. Consulta los precios actuales en render.com/pricing.

**Pasos**

1. Sube el proyecto a un repositorio privado de GitHub o GitLab.
2. En Render: **New → Blueprint**, elige el repositorio y la rama. Render lee `render.yaml`.
3. Render pide los valores marcados como `sync: false`:
   - `SITE_URL` en los **tres** servicios, con el mismo valor. Usa `https://tinta-crm.onrender.com` (o el nombre que asigne Render) o tu dominio propio.
   - `CORREOS_PERMITIDOS` en el web service: los correos que podrán entrar.
   - `OPENAI_API_KEY` en el web service. Puedes dejarlo vacío.
4. **Apply.** Render crea la base de datos y despliega el web service:
   - `build.sh` instala las dependencias con Python 3.13 (fijado en `.python-version`) y ejecuta `collectstatic`.
   - El pre-deploy aplica las migraciones, crea la tabla de caché y el contenido inicial.
   - Por último arranca Gunicorn. `SECRET_KEY` y `TAREAS_SECRETO` se generan solas y se comparten por el grupo `tinta-comun`.
5. Si la URL final no coincide con la que pusiste, corrige `SITE_URL` en los tres servicios.
6. Crea la cuenta en `/acceso/alta/` con `CODIGO_ALTA`, o desde la **Shell** (ver §12).
7. Entra en `SITE_URL`, configura el 2FA y guarda los códigos de recuperación.
8. **Dominio propio (opcional):**
   - Añádelo en *Settings → Custom Domains* del web service.
   - Configura el DNS como indica Render.
   - Cambia `SITE_URL` al dominio nuevo en los tres servicios.
   - Los enlaces ya enviados con el dominio antiguo de Render siguen funcionando.
9. Comprueba en *Logs* de cada cron que la primera ejecución termina bien. Puedes lanzarlas a mano con **Trigger Run**.

**Cómo encaja el disco**
- Render hace un snapshot diario del disco y lo conserva 7 días. Se puede restaurar desde la página *Disk*.
- Un servicio con disco **no puede escalar** a varias instancias. En cada despliegue hay unos segundos sin servicio, porque Render para la instancia vieja antes de arrancar la nueva.
- Los cron jobs, el build y el pre-deploy **no** pueden acceder al disco:
  - el pre-deploy solo toca la base de datos;
  - el cron de mantenimiento llama a `python manage.py disparar_tarea <tarea>`, que hace `POST {SITE_URL}/interno/tareas/<tarea>/` con el secreto, y la tarea se ejecuta dentro del web service.
- El disco puede ampliarse después sin cortes, pero no reducirse.

**Base de datos**
- Las bases de datos de pago tienen **recuperación a un momento dado (PITR)**: 3 días en workspaces Hobby y 7 en Pro o superior.
- Desde la página *Recovery* se pueden crear exportaciones lógicas bajo demanda. Se guardan 7 días.
- `ipAllowList: []` impide conectar desde internet. Solo los servicios de Render llegan por la red privada.

**Comprobación de salud.** `/salud/` responde `ok` si la base de datos contesta. Va antes de la validación de host y de la redirección HTTPS para que la comprobación interna de Render funcione.

**Horario de los cron.** Están en UTC: la bandeja a las 10:00 UTC (5:00 en Orlando en invierno, 6:00 en verano) y el mantenimiento a las 8:30 UTC. Ajusta `schedule` en `render.yaml` si quieres otra hora.

## 12. Primera cuenta y 2FA

La forma más sencilla es la web: abre `/acceso/alta/` con el valor de `CODIGO_ALTA` (Render lo genera; está en *Environment*) y un correo de `CORREOS_PERMITIDOS`. Desde la consola:

```bash
# En la Shell del web service de Render (o en local)
read -s CLAVE && export CLAVE          # teclea la contraseña (no se ve ni queda en el historial)
python manage.py crear_cuenta --email tu@correo.example --nombre "Vale Ríos" --password-env CLAVE
unset CLAVE
```

- En el primer acceso, el sistema obliga a configurar el 2FA: escanea el QR, introduce el código y **guarda los 8 códigos de recuperación** (en un gestor de contraseñas o impresos). Solo se muestran una vez.
- **Si pierdes el móvil:** entra con un código de recuperación («¿Sin móvil? Usa un código de recuperación» en la pantalla del 2FA). Después, en *Mi cuenta*, reconfigura el 2FA y genera códigos nuevos.
- **Si pierdes el móvil y los códigos:** desde la Shell de Render, `python manage.py restablecer_2fa --email tu@correo.example`. En el siguiente acceso se pedirá configurar el 2FA de nuevo.
- **Cambiar la contraseña:** en *Mi cuenta*, o con `python manage.py changepassword tu@correo.example` desde la Shell.
- **Cuenta de ayudante (opcional):** `crear_cuenta --rol ayudante` crea una cuenta sin acceso a Finanzas, Ajustes, copias y auditoría, ni a anonimizar o eliminar clientes.

## 13. Uso diario

1. **Por la mañana, abre «Mensajes».** Revisa cada mensaje, ajusta el texto si quieres y pulsa **WhatsApp** o **SMS**. Se abre la app con el texto escrito. Envíalo y vuelve: el mensaje se marca como enviado. Si lo envías por otra vía, usa *Copiar* y después *Marcar enviado*. *Posponer* lo mueve a mañana y *Descartar* lo quita.
2. **«Hoy»** te da la siguiente cita, los avisos (cambios pedidos, citas por confirmar, solicitudes) y las cifras del mes.
3. **Antes de una sesión**, abre la cita:
   - las alertas de salud aparecen arriba;
   - el botón *Preparar resumen* (IA) resume a la clienta;
   - *Firmar consentimiento* abre el modo quiosco para que firme en la tablet o el móvil.
4. **Al terminar**, pulsa *Cerrar sesión*: pago, notas y si el tatuaje está terminado. La secuencia de cuidados arranca sola y los mensajes aparecerán en su día.
5. **Solicitudes nuevas:** revísalas en «Solicitudes» (el triaje IA ayuda). *Aprobar* prepara la respuesta y *Convertir* crea la clienta, el tatuaje y la cita.
6. **Campañas:** en *Mensajes → Campañas*, elige un segmento y una plantilla, revisa el recuento y reparte los envíos en varios días. Solo se incluyen las clientes con consentimiento de marketing.
7. **Comparte tu enlace de reservas:** en *Solicitudes → Enlace*, por ejemplo en la bio de Instagram. Si recibes spam, *Renovar* invalida el anterior.

## 14. Tareas programadas

Todas son **idempotentes**: si se ejecutan dos veces el mismo día, no duplican nada.

| Tarea | Dónde | Qué hace |
|---|---|---|
| `tareas_diarias` | cron → base de datos | Caduca los mensajes vencidos, descarta los que ya no están permitidos y genera recordatorios, cuidados, retoques, cumpleaños, aniversarios, reactivaciones (con cupo), fechas destacadas y tramos de campaña. Cierra las campañas terminadas. Limpia los enlaces caducados, las sesiones expiradas y los intentos de acceso antiguos. |
| `copia_seguridad` | cron → web (disco) | Zip con todos los datos (incluidas la cuenta y el 2FA) y los archivos. Permisos `600`. Conserva las últimas 14. |
| `limpiar_archivos` | cron → web (disco) | Purga las solicitudes rechazadas o de spam con más de 30 días y sus imágenes. Marca los consentimientos cuyo plazo de retención ha vencido. Borra los archivos huérfanos con más de 24 horas. |

En local:

```bash
python manage.py tareas_diarias                  # --fecha AAAA-MM-DD para simular otro día
python manage.py limpiar_archivos
python manage.py copia_seguridad
```

Al final de la bandeja, **«Volver a revisar hoy»** ejecuta los generadores al momento (sin duplicar nada).

## 15. Copias de seguridad y restauración

**Tres capas:**
1. **PITR de Render Postgres** (3–7 días) para errores en la base de datos.
2. **Snapshots diarios del disco** de Render (7 días) para los archivos.
3. **Copia nocturna propia** (datos y archivos en un solo zip, 14 días) en el disco. Descárgala desde *Ajustes → Datos y copias*, que pide el código 2FA.

> Las capas 2 y 3 viven en Render. **Descarga una copia al mes** (o tras cambios importantes) y guárdala cifrada fuera de Render, por ejemplo en un disco externo o en una carpeta cifrada de tu nube. Contiene datos de salud.

**Restaurar una copia** (servidor nuevo o vuelta atrás):

```bash
# 1. Base de datos vacía con el esquema al día (en Render, el pre-deploy ya lo hace)
python manage.py migrate && python manage.py createcachetable

# 2. Sube el zip al servidor (o tenlo en local) y restaura
python manage.py restaurar_copia /ruta/copia-AAAAMMDD-HHMMSS.zip
#    --sobrescribir   si la base de datos ya tiene clientes
#    --si             sin confirmación interactiva
```

`restaurar_copia`:
- comprueba que el zip es válido y no contiene rutas peligrosas;
- vacía la base de datos y carga `datos.json` en una transacción (si falla, no cambia nada);
- copia los archivos a `MEDIA_ROOT`.

Después se entra con la cuenta y el 2FA que había en la copia. Este proceso se ha verificado de principio a fin: la copia del estudio de demostración restaurada en una base de datos nueva conserva el mismo número de clientes, citas, tatuajes, mensajes, consentimientos y archivos.

**Exportación de datos** (*Ajustes → Datos → Exportar todo*, o `python manage.py exportar_datos`). Es un zip legible con `LEEME.txt`, `datos.json` y `archivos/`. Sirve para llevarse sus datos a otro sistema. No incluye credenciales.

## 16. Privacidad y protección de datos

*Esto no es asesoramiento legal. Revisa los textos con un profesional de Florida antes de usarlos con clientes reales.*

- **Retención de registros.** La normativa de Florida sobre establecimientos de tatuaje (Florida Administrative Code, 64E-28) exige conservar los registros de las clientas, incluidos los consentimientos, durante **al menos 2 años**.
  - `retencion_consentimientos_anios` vale 2 por defecto. Cada consentimiento guarda su fecha `conservar_hasta`.
  - Mientras haya consentimientos retenidos, la ficha se puede **anonimizar** pero no eliminar.
  - Cuando vence el plazo, la tarea nocturna lo marca para que pueda borrarse.
- **Edad.** Mínimo 18 por defecto, configurable hasta 16 (ver §4). La comprobación se hace en la reserva pública, en la ficha y en el consentimiento.
- **Consentimiento de marketing:** con fecha y origen, historial completo y baja inmediata. Las felicitaciones de cumpleaños y fechas destacadas cuentan como promocionales.
- **Minimización hacia la IA** (ver §17). Nunca se envían datos de salud, documentos, firmas, imágenes, teléfonos, emails ni apellidos.
- **Texto de privacidad** editable en Ajustes. Se muestra en la reserva pública y en el consentimiento.
- **Derechos de las clientas:** exportar, anonimizar y eliminar desde su ficha. Quedan auditados.
- **Dictado por voz:** usa el reconocimiento de voz del navegador. En Chrome, el audio se procesa en los servidores de Google. No dictes datos de salud si eso te preocupa.
- **Modo quiosco:** la clienta firma en un dispositivo con tu sesión abierta. El quiosco ocupa toda la pantalla y solo muestra el formulario, pero **no** es un entorno aislado. No le dejes el dispositivo sin supervisión.
- **Mensajes:** salen de tu WhatsApp o SMS personal. El CRM solo guarda el texto y la fecha de envío, no el contenido de las conversaciones.

## 17. Asistente de IA

Todo ocurre en el servidor. La clave nunca llega al navegador. **La IA propone y tú decides:** cada resultado aparece en un campo editable o como sugerencia, y nada se envía ni se guarda solo.

| Función | Dónde |
|---|---|
| Redactar un mensaje con tu voz (tono y ejemplos en Ajustes) | Mensaje nuevo, bandeja (*Reescribir*) |
| Triaje de solicitudes (estilo, tamaño, sesiones, preguntas, prioridad) | Detalle de solicitud |
| Resumen antes de la cita | Detalle de cita |
| Sugerencias de retención (a quién escribir y por qué) | Asistente IA |
| Búsqueda en lenguaje natural («clientas VIP que no vienen desde junio») | Asistente IA |
| Respuesta sugerida a una solicitud | Detalle de solicitud |

**Garantías**
- **Búsqueda sin SQL:** la IA devuelve un JSON con esquema estricto (filtros permitidos y valores validados), que se traduce a filtros del ORM. Si la IA no está disponible, un intérprete local entiende las búsquedas sencillas.
- **Privacidad:** se envía un perfil mínimo (nombre de pila, año desde el que es clienta, número de visitas, etiquetas, tatuajes por zona, estilo y año, y fechas de citas). Además, `redactar_pii` borra emails, teléfonos, URLs, @usuarios, números de tarjeta y SSN de cualquier texto libre. Las peticiones usan `store=false`.
- **Límites:** tope mensual de peticiones, tiempo máximo por petición, un reintento y límite de 20 por minuto. Los errores (sin clave, clave inválida, modelo inexistente, límite de OpenAI, red caída o respuesta mal formada) se muestran como mensajes claros y nunca rompen la pantalla.
- **Uso registrado** (función, éxito, duración, tokens) en el modelo `UsoIA` y en la auditoría. *Ajustes → IA* muestra el consumo del mes.
- **Modelo configurable** con `IA_MODELO`. Se usa la API Responses de OpenAI con salidas JSON estructuradas. **Antes de desplegar, confirma en platform.openai.com/docs/models que el ID del modelo es el vigente** y cámbialo si hace falta. No requiere tocar código.

## 18. Pruebas y calidad

```bash
pytest                    # 222 pruebas · ~15 s (usa PostgreSQL: crea una BD de pruebas)
ruff check . && ruff format --check .
python scripts/contraste.py
python manage.py check --deploy --settings=estudio.settings.prod   # con las variables de prod
```

Las pruebas cubren los caminos críticos:
- **Acceso:** 2FA obligatorio, recuperación, bloqueo y sesión preautenticada.
- **Seguridad:** CSP y cabeceras, archivos privados, endpoint interno, tokens (caducidad, revocación, formato) y límites de peticiones.
- **Subidas:** bombas de descompresión, falsos tipos y EXIF.
- **Agenda:** solapes a nivel de base de datos.
- **Reservas públicas:** honeypot y sello de tiempo.
- **Clientes:** consentimiento firmado y PDF, anonimización y eliminación con retención.
- **Mensajería:** consentimiento en las tres comprobaciones, idempotencia de cada generador, campañas escalonadas, canales y variables.
- **Finanzas:** CSV seguro.
- **IA:** con proveedor simulado, incluidas la privacidad y la validación de la búsqueda.
- **Datos:** copia y restauración completa, `seed_demo` y contraste.

`scripts/capturar.py` hace capturas de las pantallas con Playwright y Chrome, solo para desarrollo. Necesita `pip install playwright`.

## 19. Limitaciones conocidas

- **Una sola instancia y unos segundos de corte en cada despliegue**, por el disco persistente. Para un estudio con una usuaria no es un problema. Despliega fuera del horario de trabajo.
- **El envío es manual a propósito.** Si el móvil no tiene WhatsApp, el enlace `wa.me` abre WhatsApp Web. El formato `sms:` con cuerpo funciona en iOS y Android, pero algunas apps de SMS antiguas ignoran el texto: usa *Copiar*.
- **El dictado depende del navegador.** Funciona en Chrome, Edge y Safari, pero no en Firefox. En Chrome usa servidores de Google (ver §16).
- **El modo quiosco** usa tu sesión (ver §16).
- **El modelo de IA** debe verificarse antes de desplegar (ver §17). Sin clave, el asistente simplemente no aparece.
- **Las copias propias viven en el mismo disco** que los archivos: descarga una copia periódicamente.
- **Zona horaria única.** Todo el estudio funciona en `TIME_ZONE`.
- **Textos legales de ejemplo:** los textos de consentimiento y privacidad incluidos son una base razonable, no un documento revisado por un abogado.

## 20. Hoja de ruta

- **API oficial de WhatsApp Business:** añadir un `Canal` nuevo en `canales.py`. La clave `whatsapp_api` ya está reservada en el modelo y la bandeja no cambia.
- **Almacenamiento de objetos privado** (S3 o R2 con URLs firmadas) para quitar el disco y permitir despliegues sin corte y varias instancias.
- **Copia externa automática** (cifrada, a S3 o similar) además de la nocturna en el disco.
- **Varias artistas:** agenda por artista, comisiones y permisos por rol (el modelo `Usuario` ya tiene roles).
- **Recordatorio de señal pendiente** y enlaces de pago (Square o Stripe) como integración opcional.
- **Estadísticas por estilo y zona**, y estimación de duración por tamaño a partir del histórico.

---

**Licencias de terceros:** HTMX (BSD-2-Clause, en `static/vendor/`), Archivo y Atkinson Hyperlegible (SIL OFL 1.1, en `static/fuentes/`). Los iconos son propios.
