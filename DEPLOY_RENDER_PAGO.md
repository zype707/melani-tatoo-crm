# Despliegue en producción en Render · plan de pago

Esta guía despliega el CRM para uso real con `render.yaml`: datos persistentes, disco privado para fotos y consentimientos, copias de seguridad y tareas programadas.

Para probar sin método de pago usa [DEPLOY_RENDER_FREE.md](DEPLOY_RENDER_FREE.md).

---

## Qué crea

| Recurso | Plan | Para qué |
|---|---|---|
| `tinta-crm` (web) | `0.5c-512mb` | La aplicación, con un **disco de 5 GB** en `/var/data` (fotos, firmas, PDFs, copias) |
| `tinta-db` (PostgreSQL 17) | `0.1c-256mb` | Base de datos sin acceso desde internet, con recuperación a un momento dado |
| `tinta-bandeja-diaria` (cron) | por uso | Prepara «Mensajes de hoy» cada mañana (10:00 UTC) |
| `tinta-mantenimiento` (cron) | por uso | Copia de seguridad y limpieza de archivos cada noche (8:30 UTC) |
| `tinta-comun` (grupo de variables) | — | Variables compartidas por los tres servicios |

**Coste orientativo** (precios publicados en render.com/pricing en noviembre de 2026, compruébalos antes): web 7 $/mes + base de datos 6 $/mes + almacenamiento de la base de datos (0,30 $/GB) + disco de 5 GB (1,25 $/mes) + cron jobs (céntimos al mes; se cobran por segundo de ejecución). Unos **15 $/mes** en un workspace Hobby (0 $/mes de cuota).

## Por qué este plan y no el gratis

- El disco persistente guarda los archivos privados (consentimientos firmados que la ley obliga a conservar). Los servicios gratis no admiten disco.
- El pre-deploy aplica las migraciones antes de cambiar de versión.
- Las bases de datos de pago no caducan y tienen recuperación a un momento dado (3 días en Hobby, 7 en Pro).
- Los cron jobs preparan la bandeja y hacen las copias aunque nadie entre.
- La Shell permite crear cuentas, restablecer el 2FA o restaurar copias.

---

## Antes de empezar

- El repositorio en GitHub o GitLab (privado recomendado).
- Una cuenta de Render con método de pago.
- Los correos autorizados. El **primero** será la propietaria; los demás, ayudantes.
- Decide el idioma del contenido para clientes (`IDIOMA`, `es` o `en`). Las plantillas de partida se crean una sola vez, en el primer despliegue.
- Opcional: clave de API de OpenAI y un dominio propio.

## Paso a paso

### 1. Revisa `render.yaml`

Valores que quizá quieras cambiar antes de crear nada (algunos no se pueden cambiar después):

| Campo | Valor por defecto | Notas |
|---|---|---|
| `region` | `virginia` | La más cercana a Florida. No se puede cambiar tras crear el recurso. |
| `IDIOMA` (grupo `tinta-comun`) | `es` | `en` para un estudio en inglés. |
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
| `SITE_URL` | en los **tres** servicios | La misma URL en los tres, por ejemplo `https://tinta-crm.onrender.com`, o tu dominio propio. La necesitan los enlaces de los mensajes y los cron. |
| `CORREOS_PERMITIDOS` | web | Correos separados por comas. El primero es la propietaria. |
| `OPENAI_API_KEY` | web | Opcional. Vacío = IA desactivada. |

Se generan solas: `SECRET_KEY` y `TAREAS_SECRETO` (en el grupo, compartidas) y `CODIGO_ALTA` (solo en el web service).

Pulsa **Apply**.

### 4. Primer despliegue

Render crea la base de datos, el disco y los servicios. En **Logs** del web service:

1. **Build** (`build.sh`): instala dependencias con Python 3.13 (`.python-version`) y ejecuta `collectstatic`. Las traducciones ya vienen compiladas en `locale/`.
2. **Pre-deploy:** `migrate`, `createcachetable` e `inicializar_estudio` (plantillas, cuidados, fechas destacadas, tipos de cita y horario en el idioma de `IDIOMA`).
3. **Start:** Gunicorn con 2 workers y 4 hilos.

Comprueba que `https://<tu-servicio>/salud/` responde `ok`. Si la URL final no coincide con la que pusiste, corrige `SITE_URL` en los tres servicios.

### 5. Crea las cuentas

Elige una de las dos formas.

**Desde la web (recomendada):**

1. Copia `CODIGO_ALTA` en **tinta-crm → Environment**.
2. Abre `https://<tu-servicio>/acceso/alta/`, escribe el primer correo de `CORREOS_PERMITIDOS`, tu nombre, el código y una contraseña (12 caracteres o más).
3. Configura la app autenticadora y **guarda los 8 códigos de recuperación**.
4. Cuando todas las cuentas estén creadas, puedes **vaciar `CODIGO_ALTA`** para cerrar el alta.

**Desde la Shell del web service:**

```bash
read -s CLAVE && export CLAVE   # la contraseña no se ve ni queda en el historial
python manage.py crear_cuenta --email tu@correo.example --nombre "Tu Nombre" --password-env CLAVE
unset CLAVE
```

`crear_cuenta` rechaza correos que no estén en `CORREOS_PERMITIDOS`. Con `--rol ayudante` crea una cuenta de ayudante.

### 6. Comprueba los cron jobs

En cada cron: **Trigger Run** y revisa sus **Logs**.

- `tinta-bandeja-diaria` debe terminar con «Bandeja del día preparada».
- `tinta-mantenimiento` llama al web service (`POST /interno/tareas/…` con `TAREAS_SECRETO`) porque los cron no pueden montar el disco. Debe mostrar `copia_seguridad: …` y `limpiar_archivos: …`.

### 7. Dominio propio (opcional)

1. *tinta-crm → Settings → Custom Domains*: añade el dominio.
2. Configura el DNS como indica Render y espera al certificado.
3. Cambia `SITE_URL` al dominio nuevo en los **tres** servicios.

Los enlaces ya enviados con la URL `.onrender.com` siguen funcionando.

### 8. Primeros ajustes en la app

- **Ajustes → Marca y contacto**, **Reservas y textos** y **Consentimiento**: revisa los textos de partida (idealmente con asesoría legal).
- **Solicitudes:** crea el enlace de reservas y ponlo en tu bio de Instagram.
- Idioma: cada persona cambia la interfaz con **ES / EN**. Las clientas ven por defecto el idioma de su navegador.

---

## Operación

### Acceso

- **Añadir o quitar personas:** edita `CORREOS_PERMITIDOS` en *Environment* y guarda. Quitar un correo corta su acceso en la siguiente petición, aunque tenga sesión abierta.
- **Alta de alguien nuevo:** añade su correo y vuelve a poner un valor largo y aleatorio en `CODIGO_ALTA` (16 caracteres o más), o crea su cuenta desde la Shell.
- **Perdió el móvil:** entra con un código de recuperación y reconfigura el 2FA en *Mi cuenta*. Sin códigos: `python manage.py restablecer_2fa --email …` en la Shell.

### Copias de seguridad

- **Archivos y base de datos (app):** copia nocturna en `/var/data/copias` (se guardan 14). Se descargan en *Ajustes → Datos y seguridad* con el código 2FA.
- **Disco:** Render hace un snapshot diario y lo guarda 7 días (*Disk → Snapshots*).
- **Base de datos (Render):** recuperación a un momento dado y exportaciones lógicas desde *Recovery*.
- **Restaurar una copia de la app:** desde la Shell, `python manage.py restaurar_copia /var/data/copias/<archivo>.zip --sobrescribir`.

### Despliegues

Cada push a la rama redespliega. Con disco hay unos segundos sin servicio porque Render para la instancia vieja antes de arrancar la nueva, y el servicio no puede escalar a varias instancias.

### Traducciones

Si cambias textos de la interfaz, regenera y compila el catálogo en local antes de subir (Render no tiene las herramientas de gettext):

```bash
python manage.py makemessages -l en -i "staticfiles/*" -i "*/tests/*" -i "scripts/*" -i "*/management/*"
python manage.py makemessages -d djangojs -l en -i "staticfiles/*" -i "static/vendor/*"
# traduce las entradas nuevas en locale/en/LC_MESSAGES/*.po
python manage.py compilemessages
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
| `DATABASE_URL` | los tres | desde `tinta-db` |
| `SITE_URL` | los tres | URL pública |
| `CORREOS_PERMITIDOS` | web | correos autorizados; el primero es la propietaria |
| `CODIGO_ALTA` | web | código de alta; vacío = alta desactivada |
| `MEDIA_ROOT`, `COPIAS_ROOT` | web | `/var/data/media`, `/var/data/copias` |
| `OPENAI_API_KEY` | web | opcional |

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Nadie puede entrar | `CORREOS_PERMITIDOS` vacía o con erratas (en los logs aparece `cuentas.W001`). |
| `ImproperlyConfigured: SECRET_KEY…` | Falta el grupo `tinta-comun` en el servicio. |
| El pre-deploy (`migrate`) falla con `cuentas.E001` | `CODIGO_ALTA` tiene menos de 16 caracteres. Pon uno más largo o déjalo vacío. |
| Los enlaces de los mensajes apuntan a otro sitio | `SITE_URL` no coincide en los tres servicios. |
| El cron de mantenimiento da 403 o 404 | `TAREAS_SECRETO` distinto entre servicios (debe venir del grupo) o `SITE_URL` mal puesta. |
| `DisallowedHost` | El dominio no coincide con `SITE_URL`; añade otros en `ALLOWED_HOSTS`. |
