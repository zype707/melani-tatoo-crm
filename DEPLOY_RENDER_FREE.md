# Despliegue de prueba en Render · plan gratis

Esta guía despliega el CRM **sin tarjeta ni método de pago**, con `render-free.yaml`. Sirve para probar la app, enseñarla y decidir. **No es para datos reales de clientes**: lee las limitaciones antes de empezar.

Para producción usa [DEPLOY_RENDER_PAGO.md](DEPLOY_RENDER_PAGO.md).

---

## Qué crea

| Recurso | Plan | Notas |
|---|---|---|
| `tinta-crm-free` (web) | `free` | Django + Gunicorn, 512 MB de RAM |
| `tinta-free-db` (PostgreSQL 17) | `free` | 1 GB, sin acceso desde internet |

No crea cron jobs ni disco: el plan gratis no los ofrece.

## Limitaciones del plan gratis

| Limitación | Qué significa para el CRM |
|---|---|
| **La base de datos caduca a los 30 días** | Al día 30 deja de funcionar. Tienes 14 días más para pasarla a un plan de pago; después Render la borra con todos los datos. Solo puede haber una base de datos gratis por workspace. |
| **Sin disco persistente** | Fotos de tatuajes, firmas, PDFs de consentimiento, imágenes de solicitudes y copias se guardan en `/tmp` y **se pierden** cuando el servicio se duerme, se reinicia o se redespliega. Los datos de la base de datos sí se conservan. |
| **Se duerme tras 15 min sin visitas** | La primera visita después tarda alrededor de un minuto en cargar. |
| **Sin cron jobs** | La bandeja «Mensajes de hoy» se prepara cada vez que el servicio arranca y con el botón **Volver a revisar hoy**. Opcional: un cron externo gratuito (paso 8). Sin copias de seguridad nocturnas. |
| **Sin Shell ni pre-deploy** | Las migraciones se ejecutan al arrancar. La primera cuenta se crea desde la web con el código de alta. No se puede ejecutar `seed_demo`, `restablecer_2fa` ni otros comandos. |
| **Sin copias de seguridad de la base de datos** | Si la base de datos se borra, no hay vuelta atrás. |
| **750 horas gratis al mes por workspace** | Suficiente para un servicio. Si se agotan, los servicios gratis se suspenden hasta el mes siguiente. |

---

## Antes de empezar

- Una cuenta de **GitHub** con este repositorio (puede ser privado).
- Una cuenta de **Render** (render.com). No pide tarjeta para el plan gratis.
- Los correos que podrán entrar. El **primero** de la lista será la propietaria; los demás, ayudantes (sin acceso a Finanzas, Ajustes, copias, auditoría ni a anonimizar o eliminar clientes).
- Opcional: una clave de API de OpenAI para el asistente de IA.

## Paso a paso

### 1. Sube el código a GitHub

Si aún no está, sube el repositorio a tu cuenta (privado recomendado). Comprueba que `render-free.yaml` está en la raíz.

### 2. Crea el Blueprint

1. En el panel de Render: **New → Blueprint**.
2. Conecta GitHub y elige el repositorio y la rama (`main`).
3. En **Blueprint Path** escribe `render-free.yaml`.
   Si lo dejas vacío, Render usa `render.yaml`, que crea servicios de pago y pedirá tarjeta.
4. Ponle un nombre al Blueprint, por ejemplo `tinta-prueba`.

### 3. Rellena las variables que pide Render

| Variable | Qué poner |
|---|---|
| `CORREOS_PERMITIDOS` | Correos separados por comas, sin espacios raros. Ej.: `vale@tuestudio.com,ayudante@tuestudio.com`. El primero es la propietaria. |
| `OPENAI_API_KEY` | Tu clave de OpenAI, o vacío para desactivar la IA. |

Las demás se configuran solas:

- `SECRET_KEY`, `TAREAS_SECRETO` y `CODIGO_ALTA` se generan aleatoriamente.
- `IDIOMA=es` fija el idioma del **contenido para clientes**: plantillas de mensajes de partida, textos legales y PDF de consentimiento. Cámbialo a `en` **antes del primer despliegue** si el estudio trabaja en inglés: las plantillas de partida solo se crean una vez. La interfaz se puede cambiar cuando quieras con el selector **ES / EN**.
- La URL pública se toma de Render automáticamente (`https://tinta-crm-free.onrender.com` o la que te asigne).

Pulsa **Apply**.

### 4. Espera al primer despliegue

Render crea la base de datos y luego el web service. Tarda unos 3–6 minutos. En **Logs** verás:

1. `build.sh`: instala las dependencias y recopila los estáticos.
2. Al arrancar: `migrate`, `createcachetable`, `inicializar_estudio` («Contenido inicial creado») y `tareas_diarias` («Bandeja del día preparada»).
3. `Listening at: http://0.0.0.0:10000`. El servicio pasa a **Live**.

Comprueba que `https://<tu-servicio>.onrender.com/salud/` responde `ok`.

### 5. Copia el código de alta

En el panel: **tinta-crm-free → Environment → `CODIGO_ALTA`**, pulsa el ojo para verlo y cópialo. Compártelo solo con las personas de `CORREOS_PERMITIDOS`.

### 6. Crea la cuenta de la propietaria

1. Abre `https://<tu-servicio>.onrender.com/acceso/alta/` (o «¿Primer acceso? Crea tu cuenta» en la pantalla de acceso).
2. Escribe el **primer** correo de `CORREOS_PERMITIDOS`, tu nombre, el código de alta y una contraseña de al menos 12 caracteres.
3. Configura la app autenticadora (Google Authenticator, 1Password, Authy…): escanea el QR y escribe el código.
4. **Guarda los 8 códigos de recuperación.** En el plan gratis no hay Shell: si pierdes el móvil y los códigos, no podrás recuperar la cuenta.

Las ayudantes repiten el paso 6 con su correo.

### 7. Primeros ajustes

- **Ajustes → Marca y contacto:** nombre del estudio, teléfono, Instagram, logo.
- **Ajustes → Reservas y textos:** revisa los textos de partida.
- **Solicitudes:** crea tu enlace de reservas para probar la página pública.
- Cambia el idioma de la interfaz con **ES / EN** (barra lateral en escritorio, menú «Más» en móvil, cabecera en las páginas públicas). Cada persona elige el suyo; las clientas ven por defecto el idioma de su navegador.

### 8. (Opcional) Bandeja diaria con un cron externo gratuito

Sin cron jobs, la bandeja se prepara al arrancar el servicio. Si quieres que se prepare cada mañana aunque nadie entre, usa un servicio de cron gratuito (por ejemplo cron-job.org) con:

- **URL:** `https://<tu-servicio>.onrender.com/interno/tareas/tareas_diarias/`
- **Método:** `POST`
- **Cabecera:** `Authorization: Bearer <TAREAS_SECRETO>` (cópialo de *Environment*).
- **Horario:** una vez al día, por ejemplo 10:00 UTC (5:00/6:00 en Orlando).

La tarea es idempotente: ejecutarla varias veces no duplica mensajes. El endpoint tiene límite de 10 peticiones por hora y rechaza cualquier otra tarea.

---

## Operación

### Cambiar quién puede entrar

**Environment → `CORREOS_PERMITIDOS` → Save changes.** Render redespliega solo.

- Quitar un correo corta su acceso en la siguiente petición, aunque tenga la sesión abierta.
- Añadir un correo le permite crear su cuenta en `/acceso/alta/` con el código de alta.
- Si ya nadie va a darse de alta, puedes vaciar `CODIGO_ALTA`: la página de alta deja de existir.

### Qué hacer antes del día 30

En el panel verás la fecha de caducidad de la base de datos. Antes de esa fecha:

- **Llevarte los datos:** *Ajustes → Datos y seguridad → Exportar todos tus datos* descarga un .zip con todos los registros en JSON. Las fotos y PDFs de `/tmp` pueden haberse perdido ya.
- **Ganar tiempo:** puedes subir `tinta-free-db` a un plan de pago desde su página (*Instance type*). Ojo: el Blueprint gratis sigue declarando `plan: free`, así que para producción es mejor el paso siguiente.
- **Empezar de cero:** deja que caduque, bórrala y vuelve a crear el Blueprint gratis.

### Pasar a producción

El plan gratis y el de pago son Blueprints distintos y no comparten recursos. Crea uno nuevo con `render.yaml` siguiendo [DEPLOY_RENDER_PAGO.md](DEPLOY_RENDER_PAGO.md) y empieza con datos reales allí. Cuando el de pago funcione, borra el Blueprint gratis y sus dos recursos para que no queden servicios huérfanos. Trata los datos de la prueba como desechables.

---

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| «Email o contraseña incorrectos» con la contraseña buena | El correo no está en `CORREOS_PERMITIDOS` (o tiene un espacio o una errata). Revísalo en *Environment*. |
| «No se pudo crear la cuenta» en el alta | Código de alta incorrecto, correo fuera de la lista o la cuenta ya existe. El mensaje es el mismo a propósito. |
| La página de alta da 404 | `CODIGO_ALTA` está vacío. |
| «Demasiados intentos» | Bloqueo de seguridad tras varios fallos. Espera 15 minutos. |
| La primera carga tarda un minuto | El servicio estaba dormido. Es normal en el plan gratis. |
| Desaparecieron fotos o PDFs | Se perdieron al dormirse o redesplegar: el plan gratis no tiene disco. |
| Aviso `cuentas.W001` en los logs | `CORREOS_PERMITIDOS` está vacía: nadie puede entrar. |
| El despliegue falla en `migrate` | La base de datos aún no estaba lista o caducó. Revisa su estado y pulsa *Manual Deploy*. |
