# CLAUDE.md · ink_mels CRM

CRM Django de **ink_mels**, estudio de tatuaje en Orlando (FL). Interfaz bilingüe es/en; código, comentarios y commits en **español**.

## Stack
Django 6.1 · PostgreSQL 17 (obligatorio: `btree_gist`, `unaccent`, restricciones de exclusión) · plantillas + HTMX 2 · CSS propio sin build · Gunicorn + WhiteNoise · Render.

## Comandos
```bash
python -m pytest -q                      # ~20 s, necesita Postgres local (estudio/estudio@localhost/estudio)
python -m pytest -q apps/cuentas -k login # una app / un test
ruff check . && ruff format .            # lint + formato (line-length 120)
python manage.py runserver               # settings dev por defecto
python scripts/i18n.py extraer           # makemessages + lista lo que falta traducir
python scripts/i18n.py aplicar f.tsv     # "msgid<TAB>English" (plural "uno||varios") y compila .mo
python scripts/i18n.py buscar "texto"    # ver una traducción sin abrir el .po
```
Settings: `estudio.settings.{dev,test,prod}`; pytest usa `test`. Todo lo variable viene de env (`estudio/settings/base.py`).

## Mapa
```
estudio/settings/   base.py (env, i18n, CSP, auth), prod.py, test.py
apps/<app>/         models · forms · views (finas) · servicios.py (lógica, lo que testean) · urls · tests/
  cuentas/          usuario + contraseña (ModelBackend), bloqueo por intentos, crear_cuenta [--desde-entorno]
  nucleo/           ajustes, auditoría, tokens, imágenes, archivos privados, idioma.py, templatetags/ui.py,
                    ayuda.py (tutorial /ayuda/, ayuda de cada pantalla, primeros pasos), views_ayuda.py
  mensajeria/       plantillas, variables.py, generadores (bandeja diaria), canales, predeterminados(_en).py
  agenda/ clientes/ finanzas/ catalogo/ ia/ panel/   (clientes/importacion.py: importación CSV)
templates/          parciales HTMX con {% partialdef %}; componentes/ (campo, vacio, idioma…)
static/js/          sin build, enganchado por data-*; textos con gettext()
locale/en/          django.po (msgid = español) + .mo compilados (se commitean: Render no tiene gettext)
render.yaml         producción en Render, plan de pago (disco + cron + pre-deploy)
```

## Reglas que rompen cosas si se olvidan
- **i18n**: todo texto visible va traducido. Plantillas: `{% translate %}` / `{% blocktranslate %}` (i18n es builtin, no hace falta `{% load %}`). Plurales con `{% blocktranslate count n=… %}…{% plural %}…` o `ngettext`, nunca `|pluralize` dentro de una frase. Fechas: `date:"SHORT_DATE_FORMAT"` o `date:_("j M")`.
- Python: `gettext as _` dentro de funciones; **`gettext_lazy` a nivel de módulo/clase** (choices, labels, dicts constantes). No uses `_` como variable desechable (usa `_x`). Nada de f-strings dentro de `_()`: `_("Hola %(nombre)s") % {...}`. `str()` antes de `", ".join()` de lazies. No pongas lazy en `default=` de modelos.
- **Contenido para clientas** (mensajes, variables, PDF de consentimiento, plantillas de partida) va en el idioma del estudio (`IDIOMA` → `LANGUAGE_CODE`), no en el de la interfaz: envuelve con `apps.nucleo.idioma.contenido()`.
- Tras cambiar textos: `python scripts/i18n.py extraer`, traduce lo pendiente, `aplicar`, y commitea `.po` y `.mo`.
- **CSP estricta**: cero JS/CSS inline (solo atributos `style`). Comportamiento nuevo → `static/js/app.js` con `data-*`.
- **Acceso**: todo es privado salvo vistas con `@vista_publica`. Usuario + contraseña, sin registro público ni 2FA: las cuentas se crean con `crear_cuenta` (o `PROPIETARIA_USUARIO`/`PROPIETARIA_PASSWORD` en el pre-deploy). Sesión de 30 días (`SESION_HORAS`). Acciones sensibles: `@solo_propietaria`; exportar/descargar copias pide la contraseña.
- Archivos privados en `MEDIA_ROOT`, servidos solo por vistas autenticadas; nunca bajo `static/`.
- Mensajes: nunca se envía nada solo; la idempotencia depende de `MensajePreparado.clave`.
- Migraciones: `python manage.py makemigrations --check` debe decir "No changes".
- **Ayuda**: toda pantalla o botón nuevo se documenta en `apps/nucleo/ayuda.py` (pantalla por nombre de vista, `BOTONES`, capítulos) y los botones no evidentes llevan `data-ayuda="{% translate "…" %}"` (tooltip + descripción accesible). En los textos de ayuda, `[[clave]]` dibuja el botón de `BOTONES` y `**texto**` va en negrita. `test_ayuda.py` exige que esté todo traducido.
- La ayuda (pistas, panel, tutorial) no usa el amarillo salvo en las muestras de botones principales: el acento es solo para acciones clave y datos críticos.

## Ahorro de contexto
- No leas `locale/**/*.po` (≈6000 líneas): usa `scripts/i18n.py`.
- `README.md` es largo (20 secciones): busca el encabezado con grep y lee solo esa sección.
- Ignora `static/vendor/`, `static/fuentes/`, `static/img/*.png`, `docs/capturas/`, `*/migrations/`, `staticfiles/`.
- Para entender una app empieza por su `servicios.py` y sus tests; las vistas son finas.
- Despliegue: `DEPLOY_RENDER_PAGO.md` (todo se despliega en un plan de pago de Render).
