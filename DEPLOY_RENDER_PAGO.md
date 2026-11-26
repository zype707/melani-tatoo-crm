# Despliegue en producción en Render · ink_mels

Esta guía despliega el CRM de ink_mels con `render.yaml` en un plan de pago: datos persistentes, disco privado para fotos y consentimientos, copias de seguridad y tareas programadas.

---

## Qué crea

| Recurso | Plan | Para qué |
|---|---|---|
| `ink-mels` (web) | `0.5c-512mb` | La aplicación, con un **disco de 5 GB** en `/var/data` (fotos, firmas, PDFs, copias) |
| `ink-mels-db` (PostgreSQL 17) | `0.1c-256mb` | Base de datos sin acceso desde internet, con recuperación a un momento dado |
| `ink-mels-bandeja-diaria` (cron) | por uso | Prepara «Mensajes de hoy» cada mañana (10:00 UTC) |
| `ink-mels-mantenimiento` (cron) | por uso | Copia de seguridad y limpieza de archivos cada noche (8:30 UTC) |
| `ink-mels-comun` (grupo de variables) | — | Variables compartidas por los tres servicios |

**Coste orientativo** (precios publicados en render.com/pricing en noviembre de 2026, compruébalos antes): web 7 $/mes + base de datos 6 $/mes + almacenamiento de la base de datos (0,30 $/GB) + disco de 5 GB (1,25 $/mes) + cron jobs (céntimos al mes; se cobran por segundo de ejecución). Unos **15 $/mes** en un workspace Hobby (0 $/mes de cuota).

## Qué aporta el plan de pago

- El disco persistente guarda los archivos privados (consentimientos firmados que la ley obliga a conservar).
- El pre-deploy aplica las migraciones y crea la cuenta de la propietaria antes de cambiar de versión.
- Las bases de datos de pago no caducan y tienen recuperación a un momento dado (3 días en Hobby, 7 en Pro).
- Los cron jobs preparan la bandeja y hacen las copias aunque nadie entre.
- La Shell permite crear cuentas, cambiar contraseñas o restaurar copias.

---

## Antes de empezar

- El repositorio en GitHub o GitLab (privado recomendado).
- Una cuenta de Render con método de pago.
- El **usuario** y la **contraseña** con los que entrará la propietaria (contraseña de 12 caracteres o más).
- Decide el idioma del contenido para clientes (`IDIOMA`, `es` o `en`). Las plantillas de partida se crean una sola vez, en el primer despliegue.
- Opcional: clave de API de OpenAI y un dominio propio.

## Paso a paso

### 1. Revisa `render.yaml`

Valores que quizá quieras cambiar antes de crear nada (algunos no se pueden cambiar después):

| Campo | Valor por defecto | Notas |
|---|---|---|
| `region` | `virginia` | La más cercana a Florida. No se puede cambiar tras crear el recurso. |
| `IDIOMA` (grupo `ink-mels-comun`) | `es` | `en` para un estudio en inglés. |
| `TIME_ZONE` | `America/New_York` | Zona horaria del estudio. |
| `schedule` de los cron | `0 10 * * *` y `30 8 * * *` | En UTC. |
| `disk.sizeGB` | `5` | Se puede ampliar después, nunca reducir. |
| `IA_MODELO` | `gpt-6-luna` | Comprueba el ID vigente en la documentación de OpenAI. |

### 2. Crea el Blueprint

1. En Render: **New → Blueprint**.
2. Elige el repositorio y la rama.
3. Deja **Blueprint Path** vacío (o escribe `render.yaml`).

### 3. Rellena las variables que pide Render

| Variable | Dónde | Qué poner |
|---|---|---|
| `SITE_URL` | en los **tres** servicios | La misma URL en los tres, por ejemplo `https://ink-mels.onrender.com`, o tu dominio propio. La necesitan los enlaces de los mensajes y los cron. |
| `PROPIETARIA_USUARIO` | web | El usuario con el que entrarás, por ejemplo `ink_mels`. Sin espacios; no distingue mayúsculas. |
| `PROPIETARIA_PASSWORD` | web | Su contraseña (12 caracteres o más, que no se parezca al usuario). |
| `OPENAI_API_KEY` | web | Opcional. Vacío = IA desactivada. |

Se generan solas: `SECRET_KEY` y `TAREAS_SECRETO` (en el grupo, compartidas).

Pulsa **Apply**.

### 4. Primer despliegue

Render crea la base de datos, el disco y los servicios. En **Logs** del web service:

1. **Build** (`build.sh`): instala dependencias con Python 3.13 (`.python-version`) y ejecuta `collectstatic`. Las traducciones ya vienen compiladas en `locale/`.
2. **Pre-deploy:** `migrate`, `createcachetable`, `inicializar_estudio` (plantillas, cuidados, fechas destacadas, tipos de cita y horario en el idioma de `IDIOMA`) y `crear_cuenta --desde-entorno`, que crea la cuenta de la propietaria y muestra «Cuenta de la propietaria creada: …».
3. **Start:** Gunicorn con 2 workers y 4 hilos.

Comprueba que `https://<tu-servicio>/salud/` responde `ok`. Si la URL final no coincide con la que pusiste, corrige `SITE_URL` en los tres servicios.

### 5. Entra

Abre `https://<tu-servicio>/acceso/`, escribe el usuario y la contraseña y acepta cuando el navegador ofrezca **guardar la contraseña**. A partir de ahí se rellena sola, y la sesión dura 30 días en ese dispositivo aunque cierres el navegador (`SESION_HORAS`).

No hay registro ni alta: la cuenta ya existe desde el pre-deploy. `PROPIETARIA_PASSWORD` solo se usa para crearla; si cambias la contraseña en *Mi cuenta*, la variable deja de importar (puedes borrarla de *Environment*: el pre-deploy no la vuelve a pedir mientras la cuenta exista).

**Cuentas para ayudantes** (opcional), desde la Shell del web service:

```bash
read -s CLAVE && export CLAVE   # la contraseña no se ve ni queda en el historial
python manage.py crear_cuenta --usuario ayudante --nombre "Su Nombre" --rol ayudante --password-env CLAVE
unset CLAVE
```

Las ayudantes no ven finanzas, ajustes ni exportaciones.

### 6. Comprueba los cron jobs

En cada cron: **Trigger Run** y revisa sus **Logs**.

- `ink-mels-bandeja-diaria` debe terminar con «Bandeja del día preparada».
- `ink-mels-mantenimiento` llama al web service (`POST /interno/tareas/…` con `TAREAS_SECRETO`) porque los cron no pueden montar el disco. Debe mostrar `copia_seguridad: …` y `limpiar_archivos: …`.

### 7. Dominio propio (opcional)

1. *ink-mels → Settings → Custom Domains*: añade el dominio.
2. Configura el DNS como indica Render y espera al certificado.
3. Cambia `SITE_URL` al dominio nuevo en los **tres** servicios.

Los enlaces ya enviados con la URL `.onrender.com` siguen funcionando.

### 8. Primeros ajustes en la app

- **Ajustes → Marca y contacto**: el estudio ya se llama **ink_mels**; añade el logotipo, el teléfono y el Instagram.
- **Reservas y textos** y **Consentimiento**: revisa los textos de partida (idealmente con asesoría legal).
- **Solicitudes:** crea el enlace de reservas y ponlo en tu bio de Instagram.
- Idioma: cada persona cambia la interfaz con **ES / EN**. Las clientas ven por defecto el idioma de su navegador.

---

## Operación

### Acceso

- **Olvidaste la contraseña:** desde la Shell, `python manage.py changepassword <usuario>`.
- **Añadir a alguien:** `crear_cuenta` desde la Shell (paso 5).
- **Quitar a alguien:** desde la Shell, `python manage.py shell -c "from apps.cuentas.models import Usuario; Usuario.objects.filter(usuario='ayudante').update(is_active=False)"`. Una cuenta desactivada no puede entrar y su sesión deja de valer.
- **Demasiados intentos fallidos:** el acceso se bloquea unos minutos por usuario e IP (`ACCESO_MAX_FALLOS_*`). Basta con esperar.

### Copias de seguridad

- **Archivos y base de datos (app):** copia nocturna en `/var/data/copias` (se guardan 14). Se descargan en *Ajustes → Datos y seguridad* confirmando con tu contraseña.
- **Disco:** Render hace un snapshot diario y lo guarda 7 días (*Disk → Snapshots*).
- **Base de datos (Render):** recuperación a un momento dado y exportaciones lógicas desde *Recovery*.
- **Restaurar una copia de la app:** desde la Shell, `python manage.py restaurar_copia /var/data/copias/<archivo>.zip --sobrescribir`. Las copias anteriores al acceso por usuario también se restauran (cada cuenta recibe como usuario lo que había antes de la @ de su email).

### Despliegues

Cada push a la rama redespliega. Con disco hay unos segundos sin servicio porque Render para la instancia vieja antes de arrancar la nueva, y el servicio no puede escalar a varias instancias.

### Si ya tenías el CRM desplegado con la versión anterior

- **Nombres del Blueprint:** antes los recursos se llamaban `tinta-*`. Render identifica cada recurso por su nombre, así que si sincronizas el Blueprint con los nombres nuevos (`ink-mels-*`) los trataría como recursos nuevos, con una base de datos vacía. En un despliegue que ya tiene datos, deja en `render.yaml` los nombres antiguos (la marca que ven las clientas sale de *Ajustes*, no del nombre del servicio).
- **Cuentas:** la migración convierte cada cuenta al acceso por usuario: el usuario es lo que había antes de la @ del email (`vale@…` → `vale`) y la contraseña no cambia. El 2FA y los códigos de recuperación desaparecen.
- **Variables:** borra `CORREOS_PERMITIDOS` y `CODIGO_ALTA` de *Environment*; ya no se usan.
- **Nombre del estudio:** si seguía con el nombre de partida («Mi estudio»), pasa a **ink_mels**. Si lo habías cambiado, cámbialo en *Ajustes → Marca y contacto*.

### Traducciones

Si cambias textos de la interfaz, regenera y compila el catálogo en local antes de subir (Render no tiene las herramientas de gettext):

```bash
python scripts/i18n.py extraer          # makemessages + lista lo que falta traducir
python scripts/i18n.py aplicar f.tsv    # "msgid<TAB>English" y compila los .mo
```

---

## Variables de entorno de producción

| Variable | Dónde | Valor |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | grupo | `estudio.settings.prod` |
| `SECRET_KEY` | grupo | generada |
| `TAREAS_SECRETO` | grupo | generada (cron → web) |
| `IDIOMA` | grupo | `es` o `en`: idioma del contenido para clientes |
| `TIME_ZONE`, `REGION_TELEFONO`, `MONEDA`, `SIMBOLO_MONEDA` | grupo | `America/New_York`, `US`, `USD`, `$` |
| `IA_MODELO`, `IA_LIMITE_MENSUAL` | grupo | modelo de OpenAI y tope mensual |
| `PROXIES_DE_CONFIANZA` | grupo | `1` |
| `DATABASE_URL` | los tres | desde `ink-mels-db` |
| `SITE_URL` | los tres | URL pública |
| `PROPIETARIA_USUARIO`, `PROPIETARIA_PASSWORD` | web | cuenta de la propietaria que crea el pre-deploy si no existe |
| `PROPIETARIA_NOMBRE` | web | opcional: nombre que muestra la app (si no, el usuario) |
| `SESION_HORAS` | web | opcional: duración de la sesión, `720` (30 días) por defecto |
| `MEDIA_ROOT`, `COPIAS_ROOT` | web | `/var/data/media`, `/var/data/copias` |
| `OPENAI_API_KEY` | web | opcional |

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Nadie puede entrar | No hay ninguna cuenta: en los logs del pre-deploy aparece «No hay ninguna cuenta…». Define `PROPIETARIA_USUARIO` y `PROPIETARIA_PASSWORD` y redespliega, o usa `crear_cuenta` en la Shell. |
| El pre-deploy falla en `crear_cuenta` | `PROPIETARIA_PASSWORD` vacía, demasiado corta, demasiado común o parecida al usuario, o el usuario tiene espacios. El log dice cuál. |
| «Usuario o contraseña incorrectos» con la contraseña buena | Si la cambiaste en *Mi cuenta*, vale la nueva, no la de `PROPIETARIA_PASSWORD`. Si no la recuerdas: `changepassword` en la Shell. |
| `ImproperlyConfigured: SECRET_KEY…` | Falta el grupo `ink-mels-comun` en el servicio. |
| Los enlaces de los mensajes apuntan a otro sitio | `SITE_URL` no coincide en los tres servicios. |
| El cron de mantenimiento da 403 o 404 | `TAREAS_SECRETO` distinto entre servicios (debe venir del grupo) o `SITE_URL` mal puesta. |
| `DisallowedHost` | El dominio no coincide con `SITE_URL`; añade otros en `ALLOWED_HOSTS`. |
