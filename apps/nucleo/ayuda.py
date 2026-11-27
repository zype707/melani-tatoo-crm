"""Ayuda integrada: qué hace cada botón de cada pantalla, el tutorial «Cómo usar» y los primeros pasos.

Es la única fuente de la documentación de uso. La misma información aparece en tres sitios:

* el panel «Ayuda» de cada pantalla (botón ? / tecla ?), elegido por el nombre de la vista;
* la página /ayuda/ (tutorial por capítulos + referencia de todas las pantallas);
* la lista de «Primeros pasos» (en /ayuda/ y en Hoy mientras no esté completa).

Al añadir una pantalla o un botón nuevo, documéntalo aquí: `apps/nucleo/tests/test_ayuda.py`
comprueba que las vistas principales tienen ayuda y que los botones citados existen.

En los textos, «[[clave]]» se dibuja como el botón real de `BOTONES` (mismo icono y misma etiqueta,
ya traducida) y «**texto**» va en negrita.
"""

import re
from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

# --- Botones reconocibles ------------------------------------------------------------------------
# clave → (icono, etiqueta tal y como aparece en pantalla, estilo de la muestra)
# Estilos: primario (amarillo) · normal · peligro (borde discontinuo) · fantasma (sin borde) ·
#          pestana · icono (solo icono) · tarjeta (zona que se toca, no un botón)

BOTONES = {
    # Generales
    "nueva_cita": ("plus", _("Nueva cita"), "primario"),
    "ayuda": ("ayuda", _("Ayuda"), "normal"),
    "como_usar": ("libro", _("Cómo usar"), "fantasma"),
    "mas": ("mas", _("Más"), "normal"),
    "mi_cuenta": ("usuario", _("Mi cuenta"), "fantasma"),
    "salir": ("salir", _("Salir"), "fantasma"),
    "idioma": ("", "ES · EN", "normal"),
    "guardar": ("check", _("Guardar"), "primario"),
    "cancelar": ("", _("Cancelar"), "fantasma"),
    "eliminar": ("basura", _("Eliminar"), "peligro"),
    "borrar": ("basura", pgettext_lazy("botón con icono de papelera", "Borrar"), "icono"),
    "editar": ("editar", _("Editar"), "normal"),
    "copiar": ("copiar", _("Copiar"), "normal"),
    "ver": ("externo", _("Ver"), "fantasma"),
    "volver": ("", _("Volver"), "fantasma"),
    "nuevo": ("plus", _("Nuevo"), "fantasma"),
    "anadir": ("plus", _("Añadir"), "primario"),
    "dictar": ("mic", _("Dictar"), "fantasma"),
    "pista_entendido": ("x", _("Entendido"), "fantasma"),
    # Hoy
    "tarjeta_cifra": ("panel", _("Tarjetas de cifras"), "tarjeta"),
    "aviso_amarillo": ("alerta", _("Avisos"), "primario"),
    "hueco_libre": ("reloj", _("Huecos libres · 7 días"), "tarjeta"),
    "ver_agenda": ("flecha-der", _("Ver agenda"), "fantasma"),
    "campana_reactivacion": ("enviar", _("Campaña de reactivación"), "normal"),
    "siguiente_cita": ("", _("Siguiente"), "normal"),
    "primeros_pasos": ("check", _("Primeros pasos"), "tarjeta"),
    # Agenda
    "vistas_agenda": (
        "semana",
        format_lazy("{} · {} · {} · {}", _("Día"), _("Semana"), _("Mes"), _("Lista")),
        "pestana",
    ),
    "anterior_siguiente": ("flecha-der", _("Anterior / Siguiente"), "icono"),
    "hoy_agenda": ("", _("Hoy"), "normal"),
    "ir_a_fecha": ("agenda", _("Ir a una fecha"), "normal"),
    "lista_espera": ("lista", _("Lista de espera"), "normal"),
    "horario_tipos": ("ajustes", _("Horario y tipos"), "normal"),
    "hueco_calendario": ("plus", _("Hueco vacío"), "tarjeta"),
    "cita_calendario": ("agenda", _("Cita en el calendario"), "tarjeta"),
    # Detalle de cita
    "confirmar": ("check", _("Confirmar"), "primario"),
    "marcar_realizada": ("check", _("Marcar realizada"), "normal"),
    "no_vino": ("x", _("No vino"), "normal"),
    "cancelar_cita": ("", _("Cancelar cita"), "peligro"),
    "editar_mover": ("editar", _("Editar / mover"), "fantasma"),
    "reactivar": ("refrescar", _("Reactivar"), "normal"),
    "registrar_pago": ("plus", _("Registrar seña o pago"), "fantasma"),
    "pago_devuelto": ("", _("Devuelto"), "fantasma"),
    "generar_enlace": ("enlace", _("Generar enlace"), "normal"),
    "firmar_consentimiento": ("firma", _("Firmar consentimiento"), "normal"),
    "ver_pdf": ("documento", _("Ver PDF"), "normal"),
    "ofrecer": ("mensajes", _("Ofrecer"), "normal"),
    "marcar_atendido": ("", _("Marcar como atendido"), "normal"),
    "preparar_resumen": ("ia", _("Preparar resumen"), "normal"),
    # Formularios de agenda
    "buscar_cliente": ("buscar", _("Cliente"), "normal"),
    "cliente_nuevo": ("plus", _("Cliente nuevo"), "fantasma"),
    "guardar_cita": ("check", _("Guardar cita"), "primario"),
    "marcar_como_realizada": ("check", _("Marcar como realizada"), "primario"),
    "dictar_notas": ("mic", _("Dictar notas"), "fantasma"),
    "quitar_lista": ("", _("Quitar de la lista"), "peligro"),
    "guardar_horario": ("check", _("Guardar horario"), "primario"),
    "bloquear": ("candado", _("Bloquear"), "primario"),
    # Mensajes
    "escribir_mensaje": ("editar", _("Escribir mensaje"), "normal"),
    "pestanas_mensajes": (
        "mensajes",
        format_lazy("{} · {} · {} · {}", _("Hoy"), _("Historial"), _("Campañas"), _("Plantillas")),
        "pestana",
    ),
    "filtro_tipo": ("", _("Filtrar por tipo"), "normal"),
    "whatsapp": ("whatsapp", "WhatsApp", "primario"),
    "sms": ("sms", _("SMS / RCS"), "normal"),
    "si_enviado": ("check", _("Sí, enviado"), "primario"),
    "marcar_enviado": ("check", _("Marcar enviado"), "fantasma"),
    "posponer": ("posponer", _("Posponer"), "fantasma"),
    "reescribir": ("ia", _("Reescribir"), "fantasma"),
    "descartar": ("x", _("Descartar"), "fantasma"),
    "deshacer": ("", _("Deshacer"), "fantasma"),
    "volver_a_revisar": ("refrescar", _("Volver a revisar hoy"), "fantasma"),
    "preparar_envio": ("flecha-der", _("Preparar envío"), "primario"),
    "filtrar": ("", _("Filtrar"), "normal"),
    "nueva_campana": ("plus", _("Nueva campaña"), "primario"),
    "segmento": ("clientes", _("Segmentos automáticos"), "tarjeta"),
    "lanzar_campana": ("enviar", _("Lanzar campaña"), "primario"),
    "ampliar_campana": ("plus", _("Añadir clientes nuevos del segmento"), "normal"),
    "cancelar_campana": ("", _("Cancelar campaña"), "peligro"),
    "nueva_fecha": ("plus", _("Nueva fecha"), "primario"),
    "nueva_plantilla": ("plus", _("Nueva plantilla"), "primario"),
    "insertar_variable": ("", "{nombre}", "normal"),
    # Clientes
    "nuevo_cliente": ("plus", _("Nuevo cliente"), "primario"),
    "etiquetas": ("etiqueta", _("Etiquetas"), "normal"),
    "importar_csv": ("subir", _("Importar CSV"), "normal"),
    "buscador_clientes": ("buscar", _("Buscar clientes"), "normal"),
    "filtro_rapido": ("", _("Filtro rápido"), "normal"),
    "ordenar": ("", _("Ordenar"), "normal"),
    "anadir_tatuaje": ("plus", _("Añadir tatuaje"), "normal"),
    "guardar_nota": ("plus", _("Guardar nota"), "normal"),
    "registrar_consentimiento": ("", _("Registrar consentimiento"), "normal"),
    "registrar_baja": ("", _("Registrar baja"), "peligro"),
    "anadir_lista": ("plus", _("Añadir a la lista"), "normal"),
    "exportar_datos": ("descargar", _("Exportar sus datos"), "normal"),
    "anonimizar": ("", _("Anonimizar"), "peligro"),
    "eliminar_definitivamente": ("", _("Eliminar definitivamente"), "peligro"),
    "pedir_ideas": ("ia", _("Pedir ideas"), "normal"),
    "nueva_sesion": ("plus", _("Nueva sesión"), "primario"),
    "subir_fotos": ("subir", _("Subir fotos"), "normal"),
    "crear_etiqueta": ("plus", _("Crear"), "normal"),
    # Importación
    "descargar_plantilla": ("descargar", _("Descargar plantilla"), "normal"),
    "revisar_archivo": ("ojo", _("Revisar archivo"), "primario"),
    "descargar_errores": ("descargar", _("Descargar filas con error"), "normal"),
    "importar": ("check", _("Importar"), "primario"),
    # Solicitudes y flash
    "crear_enlace": ("enlace", _("Crear enlace"), "primario"),
    "renovar_enlace": ("refrescar", _("Renovar enlace"), "normal"),
    "cerrar_agenda": ("candado", _("Cerrar agenda"), "fantasma"),
    "abrir_agenda": ("", _("Abrir agenda"), "primario"),
    "dar_cita": ("agenda", _("Dar cita"), "primario"),
    "aceptar_sin_fecha": ("check", _("Aceptar sin fecha"), "normal"),
    "rechazar": ("", _("Rechazar"), "peligro"),
    "responder_rapido": ("mensajes", _("Responder rápido"), "fantasma"),
    "analizar_ia": ("ia", _("Analizar con IA"), "normal"),
    "nuevo_diseno": ("plus", _("Nuevo diseño"), "primario"),
    "estado_flash": (
        "",
        format_lazy("{} · {} · {}", _("Disponible"), _("Reservado"), _("Vendido")),
        "pestana",
    ),
    "publicar_catalogo": ("externo", _("Publicar catálogo"), "normal"),
    "ocultar_catalogo": ("", _("Ocultar catálogo"), "fantasma"),
    # Finanzas
    "mes_anterior_siguiente": ("flecha-izq", _("Mes anterior / siguiente"), "icono"),
    "ingreso": ("plus", _("Ingreso"), "normal"),
    "gasto": ("plus", _("Gasto"), "primario"),
    "exportar_csv": ("descargar", _("Exportar CSV"), "normal"),
    # Asistente IA
    "buscar_ia": ("buscar", _("Buscar"), "normal"),
    "proponer_respuesta": ("ia", _("Proponer respuesta"), "primario"),
    # Ajustes y cuenta
    "secciones_ajustes": ("ajustes", _("Secciones de ajustes"), "pestana"),
    "actualizar_logo": ("subir", _("Actualizar logotipo"), "normal"),
    "descargar_exportacion": ("descargar", _("Descargar exportación"), "primario"),
    "crear_copia": ("plus", _("Crear copia ahora"), "normal"),
    "descargar_copia": ("descargar", _("Descargar copia"), "icono"),
    "registro_actividad": ("escudo", _("Registro de actividad"), "fantasma"),
    "cambiar_contrasena": ("", _("Cambiar contraseña"), "normal"),
    "mostrar_ayudas": ("bombilla", _("Mostrar ayudas en pantalla"), "normal"),
}


def muestra(clave: str) -> str:
    """HTML de la muestra de un botón: se parece al botón real para reconocerlo en pantalla."""
    from .templatetags.ui import icono

    if clave not in BOTONES:
        return escape(f"[[{clave}]]")
    nombre_icono, etiqueta, estilo = BOTONES[clave]
    svg = icono(nombre_icono) if nombre_icono else ""
    if estilo == "icono":
        return format_html(
            '<span class="muestra-con-nombre"><span class="muestra muestra-icono" aria-hidden="true">{}</span>'
            "<strong>{}</strong></span>",
            svg,
            etiqueta,
        )
    return format_html('<span class="muestra muestra-{}">{}{}</span>', estilo, svg, etiqueta)


_TOKEN = re.compile(r"\[\[([a-z_]+)\]\]")
_NEGRITA = re.compile(r"\*\*(.+?)\*\*")


def marcado(texto) -> str:
    """Escapa el texto y convierte [[boton]] en su muestra y **texto** en negrita."""
    html = escape(str(texto))
    html = _TOKEN.sub(lambda m: muestra(m.group(1)), html)
    html = _NEGRITA.sub(r"<strong>\1</strong>", html)
    return mark_safe(html)  # noqa: S308 - el texto se escapa antes de añadir etiquetas propias


# --- Pantallas ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Boton:
    clave: str
    texto: str
    propietaria: bool = False  # solo lo ve la propietaria

    @property
    def muestra(self) -> str:
        return muestra(self.clave)

    @property
    def nombre(self) -> str:
        return str(BOTONES[self.clave][1])


@dataclass(frozen=True)
class Pantalla:
    clave: str
    titulo: str
    resumen: str
    botones: tuple = ()
    consejos: tuple = ()
    vistas: tuple = ()
    capitulo: str = ""
    propietaria: bool = False

    def botones_para(self, usuario) -> list:
        es_propietaria = getattr(usuario, "es_propietaria", False)
        return [b for b in self.botones if es_propietaria or not b.propietaria]

    @property
    def texto_busqueda(self) -> str:
        partes = [self.titulo, self.resumen, *self.consejos]
        for b in self.botones:
            partes += [b.nombre, b.texto]
        return " ".join(str(p) for p in partes).lower()


PANTALLAS = [
    Pantalla(
        "panel",
        _("Hoy"),
        _(
            "Tu resumen del día: citas de hoy, mensajes por enviar, solicitudes nuevas y avisos que necesitan "
            "tu atención. Es la pantalla de inicio."
        ),
        (
            Boton("nueva_cita", _("Apunta una cita nueva. Está siempre a mano (atajo: tecla n).")),
            Boton(
                "tarjeta_cifra",
                _(
                    "Cada número es un acceso directo: «Mensajes por enviar» abre la bandeja, «Solicitudes nuevas» "
                    "las reservas pendientes, etc. En amarillo = hay algo que hacer."
                ),
            ),
            Boton(
                "aviso_amarillo",
                _("Una clienta canceló (hay hueco que ofrecer) o pide otra fecha. Tócalo para abrir la cita."),
            ),
            Boton("siguiente_cita", _("La próxima cita de hoy. Tócala para ver su ficha y su seña.")),
            Boton("hueco_libre", _("Huecos sin citas en los próximos 7 días. Toca uno para crear la cita a esa hora.")),
            Boton(
                "campana_reactivacion",
                _("Prepara mensajes para quien lleva meses sin volver (solo si acepta promociones)."),
            ),
            Boton(
                "primeros_pasos",
                _("Mientras configuras la app, una lista te dice qué falta. Desaparece al completarla o al cerrarla."),
            ),
        ),
        (
            _("Empieza el día aquí: si «Mensajes por enviar» está en amarillo, ve primero a la bandeja."),
            _(
                "«Salud del estudio» compara no-shows y clientes que repiten: sirve para ver tendencias, no hay que tocar nada."
            ),
        ),
        ("panel:inicio",),
        "rutina",
    ),
    Pantalla(
        "agenda",
        _("Agenda"),
        _(
            "Tus citas por día, semana, mes o lista. Cada color es un tipo de cita; las zonas rayadas son días "
            "libres o bloqueos; el borde discontinuo significa «por confirmar»."
        ),
        (
            Boton("vistas_agenda", _("Cambia la forma de ver la agenda. Recuerda la última que usaste.")),
            Boton("anterior_siguiente", _("Retrocede o avanza un día, una semana o un mes.")),
            Boton("hoy_agenda", _("Vuelve a la fecha de hoy.")),
            Boton("ir_a_fecha", _("Salta a cualquier fecha con el calendario.")),
            Boton("hueco_calendario", _("Toca una franja vacía (vista día o semana) para crear una cita a esa hora.")),
            Boton("cita_calendario", _("Toca una cita para ver su detalle, cobrar o cambiar su estado.")),
            Boton("lista_espera", _("Personas que quieren cita si se libera un hueco.")),
            Boton("horario_tipos", _("Tu horario de trabajo, días libres y vacaciones, y los tipos de cita.")),
            Boton("nueva_cita", _("Apunta una cita nueva.")),
        ),
        (
            _("Dos citas no pueden solaparse: si eliges una hora ocupada, la app no te dejará guardarla."),
            _("La línea amarilla marca la hora actual."),
        ),
        ("agenda:calendario",),
        "agenda",
    ),
    Pantalla(
        "cita",
        _("Detalle de la cita"),
        _("Todo sobre una cita: su estado, señas y pagos, el consentimiento firmado y el enlace para la clienta."),
        (
            Boton("confirmar", _("Pasa la cita de «por confirmar» a «confirmada».")),
            Boton(
                "marcar_realizada",
                _(
                    "Cierra la sesión al terminar: apuntas el cobro y las notas, y se programan solos los mensajes "
                    "de cuidados."
                ),
            ),
            Boton("no_vino", _("Marca que no se presentó. Queda en su historial de no-shows.")),
            Boton(
                "cancelar_cita",
                _(
                    "Cancela indicando quién y por qué. Después te sugiere a quién de la lista de espera ofrecer el hueco."
                ),
            ),
            Boton("editar_mover", _("Cambia fecha, hora, duración, tipo o descripción.")),
            Boton("reactivar", _("Devuelve una cita cancelada o «no vino» a confirmada, si el hueco sigue libre.")),
            Boton(
                "registrar_pago", _("Apunta una seña o un pago con su método (efectivo, Zelle…). Aparece en Finanzas.")
            ),
            Boton("pago_devuelto", _("Marca un pago como devuelto (o deshace la devolución).")),
            Boton("borrar", _("Borra un pago que apuntaste por error.")),
            Boton(
                "generar_enlace",
                _("Crea un enlace privado para que la clienta confirme, cancele o pida otra fecha sin crear cuenta."),
            ),
            Boton(
                "firmar_consentimiento",
                _("Abre el modo tablet: la clienta lee, responde su salud y firma con el dedo."),
            ),
            Boton("ver_pdf", _("Abre el consentimiento ya firmado.")),
            Boton("ofrecer", _("Prepara un mensaje para ofrecer el hueco libre a esa persona de la lista de espera.")),
            Boton("marcar_atendido", _("Quita el aviso de «pide cambiar la fecha» cuando ya lo hayas resuelto.")),
            Boton("preparar_resumen", _("La IA resume quién viene y qué recordar. Nunca ve datos de salud.")),
        ),
        (_("Si la clienta tiene alergias o es menor de edad, verás un aviso amarillo arriba antes de empezar."),),
        ("agenda:detalle",),
        "agenda",
    ),
    Pantalla(
        "cita_form",
        _("Nueva cita / Editar cita"),
        _("Apunta o cambia una cita: quién, cuándo, de qué tipo y, si quieres, a qué tatuaje pertenece."),
        (
            Boton(
                "buscar_cliente",
                _("Escribe dos letras del nombre, el teléfono o el @ de Instagram y elige a la persona."),
            ),
            Boton("cliente_nuevo", _("Si aún no tiene ficha, escribe aquí su nombre y teléfono y se crea al guardar.")),
            Boton("guardar_cita", _("Guarda la cita. Si choca con otra o con un bloqueo, te lo dirá.")),
            Boton("cancelar", _("Vuelve sin guardar nada.")),
        ),
        (
            _("Al elegir el tipo de cita, la duración se rellena sola."),
            _("Si pones el tatuaje, la cita queda en su historial de sesiones."),
        ),
        ("agenda:nueva", "agenda:editar"),
        "agenda",
    ),
    Pantalla(
        "cerrar_sesion",
        _("¿Cómo fue la sesión?"),
        _("Se rellena al terminar una cita: cobro final, notas de la sesión y si el tatuaje queda terminado."),
        (
            Boton(
                "dictar_notas", _("Dicta las notas con la voz en lugar de escribirlas (si tu navegador lo permite).")
            ),
            Boton(
                "marcar_como_realizada",
                _("Guarda y marca la cita como hecha. Arranca la secuencia de cuidados si el tipo de cita la usa."),
            ),
            Boton("volver", _("Vuelve a la cita sin cambiar nada.")),
        ),
        (),
        ("agenda:cerrar_sesion",),
        "agenda",
    ),
    Pantalla(
        "espera",
        _("Lista de espera"),
        _("Quien quiere cita antes de lo que tienes libre. Si se cancela una cita, la app te sugiere a quién avisar."),
        (
            Boton("anadir", _("Apunta a alguien: qué tipo de cita quiere, qué días y en qué franja le va bien.")),
            Boton("quitar_lista", _("La saca de la lista (por ejemplo, cuando ya tiene cita).")),
            Boton("guardar", _("Guarda los cambios.")),
        ),
        (_("Marca «Prioritaria» a quien deba ir primero cuando haya un hueco."),),
        ("agenda:lista_espera", "agenda:espera_nueva", "agenda:espera_editar"),
        "agenda",
    ),
    Pantalla(
        "configuracion_agenda",
        _("Horario y tipos de cita"),
        _(
            "Define cuándo trabajas, tus días libres o vacaciones y los tipos de cita (duración, color y seña sugerida)."
        ),
        (
            Boton("guardar_horario", _("Guarda tu horario semanal. Hasta dos tramos por día; vacío = no trabajas.")),
            Boton("nuevo", _("Crea un tipo de cita nuevo o un bloqueo (vacaciones, convención…).")),
            Boton("bloquear", _("Guarda el bloqueo: esos días no se podrán reservar.")),
            Boton("borrar", _("Elimina un bloqueo.")),
        ),
        (
            _("Los tipos que vienen de serie (Consulta, Sesión, Sesión larga y Retoque) se pueden editar."),
            _("Los mensajes de cuidados se envían tras las citas de categoría «Sesión de tatuaje» o «Retoque»."),
        ),
        (
            "agenda:configuracion",
            "agenda:tipo_nuevo",
            "agenda:tipo_editar",
            "agenda:bloqueo_nuevo",
        ),
        "ajustes",
    ),
    Pantalla(
        "bandeja",
        _("Mensajes de hoy"),
        _(
            "Cada mañana la app prepara los mensajes del día: recordatorios, cuidados, cumpleaños, campañas… "
            "Tú los revisas y los envías desde tu móvil. Nada se envía solo."
        ),
        (
            Boton(
                "whatsapp",
                _("Abre WhatsApp con el texto ya escrito. Envíalo allí y vuelve: la app te preguntará si lo enviaste."),
            ),
            Boton("sms", _("Igual, pero con la app de mensajes del móvil.")),
            Boton("copiar", _("Copia el texto para pegarlo donde quieras (Instagram, email…).")),
            Boton("si_enviado", _("Confirma que lo enviaste: el mensaje sale de la bandeja y queda en el historial.")),
            Boton(
                "marcar_enviado", _("Márcalo como enviado sin abrir nada (por ejemplo, si se lo dijiste en persona).")
            ),
            Boton("posponer", _("Lo aparta hasta mañana, dentro de 3 días o de una semana.")),
            Boton("reescribir", _("La IA propone otra versión del texto con tu tono.")),
            Boton("descartar", _("No se enviará. Desaparece de la bandeja y no vuelve a aparecer.")),
            Boton("deshacer", _("Si marcaste uno por error, lo devuelve a pendiente.")),
            Boton("filtro_tipo", _("Muestra solo un tipo de mensaje: recordatorios, cuidados, cumpleaños…")),
            Boton("escribir_mensaje", _("Escribe a cualquier clienta, desde cero o a partir de una plantilla.")),
            Boton("volver_a_revisar", _("Comprueba si falta algún mensaje de hoy. Nunca duplica los que ya hay.")),
        ),
        (
            _("Puedes cambiar el texto antes de enviarlo: se guarda solo mientras escribes."),
            _("Los mensajes promocionales (marca «Promo») solo se preparan para quien aceptó promociones."),
        ),
        ("mensajeria:bandeja", "mensajeria:enviar"),
        "mensajes",
    ),
    Pantalla(
        "mensaje_nuevo",
        _("Escribir mensaje"),
        _("Prepara un mensaje suelto para una clienta, desde cero o con una de tus plantillas."),
        (
            Boton("buscar_cliente", _("Elige a quién escribes.")),
            Boton("preparar_envio", _("Prepara el mensaje con los botones de WhatsApp, SMS y Copiar.")),
            Boton("cancelar", _("Vuelve a la bandeja.")),
        ),
        (),
        ("mensajeria:nuevo",),
        "mensajes",
    ),
    Pantalla(
        "historial",
        _("Historial de mensajes"),
        _("Todo lo que has enviado (y descartado), con fecha y canal. Sirve para saber qué le dijiste a quién."),
        (
            Boton("buscador_clientes", _("Busca por nombre de la clienta o por una palabra del mensaje.")),
            Boton("filtrar", _("Aplica los filtros de tipo y canal.")),
        ),
        (),
        ("mensajeria:historial",),
        "mensajes",
    ),
    Pantalla(
        "campanas",
        _("Campañas"),
        _(
            "Envíos a un grupo (segmento): VIP, inactivos, cumpleaños del mes… Los mensajes se reparten por días "
            "en tu bandeja para no enviar todo de golpe."
        ),
        (
            Boton("nueva_campana", _("Elige segmento, plantilla y cuántos mensajes por día.")),
            Boton(
                "segmento", _("Cada tarjeta muestra cuántas personas hay en ese grupo. Tócala para crear su campaña.")
            ),
            Boton(
                "lanzar_campana", _("Prepara los mensajes en tu bandeja, repartidos por días. Tú sigues enviándolos.")
            ),
            Boton("ampliar_campana", _("Añade a quien entró en el segmento después de lanzarla.")),
            Boton("cancelar_campana", _("Descarta los mensajes de la campaña que aún no enviaste.")),
        ),
        (_("Solo entran clientes que aceptaron promociones y no pidieron «no contactar»."),),
        ("mensajeria:campanas", "mensajeria:campana_nueva", "mensajeria:campana"),
        "fidelizacion",
    ),
    Pantalla(
        "fechas",
        _("Fechas destacadas"),
        _("Días especiales (San Valentín, Halloween, viernes 13…). Unos días antes se prepara una campaña sola."),
        (
            Boton("nueva_fecha", _("Añade una fecha: fija, «el último viernes de…», viernes 13 o un día concreto.")),
            Boton("guardar", _("Guarda la fecha.")),
            Boton("eliminar", _("Borra la fecha.")),
        ),
        (_("Ponla en «Solo recordatorio» si prefieres que te avise sin preparar mensajes."),),
        ("mensajeria:fechas", "mensajeria:fecha_nueva", "mensajeria:fecha_editar"),
        "fidelizacion",
    ),
    Pantalla(
        "cuidados",
        _("Cuidados posteriores"),
        _(
            "La secuencia de mensajes tras cada sesión: día 1, día 3, semana 2 y retoque. Cada paso aparece en tu "
            "bandeja el día que toca."
        ),
        (
            Boton("guardar", _("Guarda el paso (día, plantilla y si está activo).")),
            Boton("eliminar", _("Borra el paso de la secuencia.")),
            Boton("cancelar", _("Deja de editar el paso.")),
        ),
        (_("El paso de retoque no se envía si ya hubo retoque o si quedan sesiones de ese tatuaje."),),
        ("mensajeria:cuidados", "mensajeria:cuidado_editar"),
        "fidelizacion",
    ),
    Pantalla(
        "plantillas",
        _("Plantillas"),
        _("Los textos de partida de cada tipo de mensaje. Las variables entre llaves se rellenan solas."),
        (
            Boton("nueva_plantilla", _("Crea otra plantilla (por ejemplo, para una campaña concreta).")),
            Boton("insertar_variable", _("Inserta un dato que se rellena solo: {nombre}, {fecha_cita}, {estudio}…")),
            Boton("guardar", _("Guarda la plantilla.")),
            Boton("eliminar", _("Borra la plantilla.")),
        ),
        (_("La vista previa de la derecha usa datos de ejemplo: así ves cómo quedará."),),
        ("mensajeria:plantillas", "mensajeria:plantilla_nueva", "mensajeria:plantilla_editar"),
        "fidelizacion",
    ),
    Pantalla(
        "clientes",
        _("Clientes"),
        _("Todas tus fichas. Busca, filtra y abre cualquier ficha para ver su historia completa."),
        (
            Boton(
                "buscador_clientes", _("Busca por nombre, un trozo del teléfono, email o @instagram. Atajo: tecla /.")
            ),
            Boton("filtro_rapido", _("Todos, con cita, VIP, nuevos del mes o quienes aceptan promociones.")),
            Boton("ordenar", _("Ordena por nombre, más recientes, última visita o mayor gasto.")),
            Boton("nuevo_cliente", _("Crea una ficha nueva. Atajo: tecla c.")),
            Boton(
                "importar_csv",
                _("Trae de golpe tu lista de clientes desde Excel, Google Sheets u otro programa."),
                propietaria=True,
            ),
            Boton("etiquetas", _("Crea o borra etiquetas para agrupar fichas (VIP, proyecto grande…).")),
        ),
        (_("La fecha amarilla junto a un nombre es su próxima cita; si no tiene, verás cuándo vino por última vez."),),
        ("clientes:lista",),
        "clientes",
    ),
    Pantalla(
        "cliente_form",
        _("Nuevo cliente / Editar ficha"),
        _("Datos de contacto, cumpleaños, canal preferido, consentimiento de promociones, etiquetas y notas privadas."),
        (
            Boton("guardar", _("Guarda la ficha. Si el teléfono o el email ya existen en otra ficha, te avisará.")),
            Boton("cancelar", _("Vuelve sin guardar.")),
        ),
        (
            _("Basta con el nombre y un dato de contacto (teléfono, email o Instagram)."),
            _("Si marcas que acepta promociones, indica cómo lo aceptó: queda registrado."),
        ),
        ("clientes:nuevo", "clientes:editar"),
        "clientes",
    ),
    Pantalla(
        "ficha",
        _("Ficha de cliente"),
        _(
            "Toda la historia de una persona: próximas citas, tatuajes con fotos, notas, pagos, mensajes, "
            "consentimientos, salud y promociones."
        ),
        (
            Boton("nueva_cita", _("Apunta una cita para esta persona.")),
            Boton("escribir_mensaje", _("Escríbele un mensaje suelto.")),
            Boton("editar", _("Cambia sus datos de contacto, etiquetas o notas.")),
            Boton("anadir_tatuaje", _("Registra un tatuaje para guardar fotos, sesiones y su aniversario.")),
            Boton("guardar_nota", _("Añade una nota a su historial (también puedes dictarla).")),
            Boton("registrar_consentimiento", _("Apunta que acepta promociones y cómo lo dijo.")),
            Boton(
                "registrar_baja", _("Deja de enviarle promociones. Sus mensajes promocionales pendientes se descartan.")
            ),
            Boton("firmar_consentimiento", _("Abre el modo tablet para firmar el consentimiento informado.")),
            Boton("anadir_lista", _("La apunta en la lista de espera.")),
            Boton("pedir_ideas", _("La IA sugiere cómo retomar el contacto con quien no tiene citas.")),
            Boton("exportar_datos", _("Descarga un .zip con todos sus datos, fotos y PDFs (derecho de acceso).")),
            Boton("anonimizar", _("Borra sus datos personales y conserva importes y consentimientos el plazo legal.")),
            Boton(
                "eliminar_definitivamente", _("Borra la ficha entera. Solo si no hay consentimientos que conservar.")
            ),
        ),
        (_("Los datos de salud nunca se envían a la IA."),),
        ("clientes:ficha",),
        "clientes",
    ),
    Pantalla(
        "salud",
        _("Datos de salud"),
        _("Alergias, medicación y condiciones importantes. Generan un aviso en la ficha y en sus citas."),
        (Boton("guardar", _("Guarda los datos de salud.")), Boton("cancelar", _("Vuelve a la ficha."))),
        (),
        ("clientes:salud",),
        "clientes",
    ),
    Pantalla(
        "tatuaje",
        _("Tatuaje"),
        _(
            "Un proyecto concreto: zona, estilo, tamaño, precio, sesiones y fotos (referencia, recién hecho y cicatrizado)."
        ),
        (
            Boton("nueva_sesion", _("Apunta otra cita para este mismo tatuaje.")),
            Boton("editar", _("Cambia los datos o márcalo como terminado.")),
            Boton("subir_fotos", _("Sube varias fotos a la vez. Se les quita la ubicación GPS.")),
            Boton("borrar", _("Borra una foto.")),
        ),
        (_("La fecha de fin se usa para felicitar el aniversario del tatuaje."),),
        ("clientes:tatuaje", "clientes:tatuaje_nuevo", "clientes:tatuaje_editar"),
        "clientes",
    ),
    Pantalla(
        "etiquetas",
        _("Etiquetas"),
        _("Palabras para agrupar fichas. La etiqueta «VIP» alimenta el segmento VIP de las campañas."),
        (
            Boton("crear_etiqueta", _("Crea una etiqueta nueva.")),
            Boton("borrar", _("Borra la etiqueta y la quita de todas las fichas.")),
        ),
        (),
        ("clientes:etiquetas",),
        "clientes",
    ),
    Pantalla(
        "importar",
        _("Importar clientes"),
        _(
            "Trae tu lista de clientes de una vez desde un archivo CSV. Primero ves una vista previa; nada se guarda sin confirmar."
        ),
        (
            Boton("descargar_plantilla", _("Un CSV de ejemplo con todas las columnas. Rellénalo o úsalo de guía.")),
            Boton("revisar_archivo", _("Lee el archivo y te enseña qué entra, qué ya existe y qué tiene errores.")),
            Boton(
                "descargar_errores",
                _("Solo las filas que fallan, con el motivo, para corregirlas y volver a subirlas."),
            ),
            Boton("importar", _("Crea las fichas nuevas de una vez. Si algo falla a mitad, no se guarda nada.")),
            Boton("cancelar", _("Descarta el archivo sin guardar nada.")),
        ),
        (
            _(
                "Quien ya está (mismo teléfono o email) nunca se duplica: eliges dejar su ficha o completar lo que falte."
            ),
            _("Añade la columna «cliente_desde» para conservar su antigüedad."),
        ),
        ("clientes:importar", "clientes:importar_revisar", "clientes:importar_listo"),
        "clientes",
        propietaria=True,
    ),
    Pantalla(
        "solicitudes",
        _("Solicitudes"),
        _(
            "Las peticiones que llegan desde tu página pública de reservas (con fotos de referencia). "
            "Comparte el enlace en tu bio de Instagram."
        ),
        (
            Boton("copiar", _("Copia tu enlace de reservas para pegarlo en Instagram, WhatsApp o tu web.")),
            Boton("ver", _("Abre tu página de reservas tal y como la ven tus clientas.")),
            Boton("crear_enlace", _("Crea tu enlace público de reservas.")),
            Boton("renovar_enlace", _("Crea un enlace nuevo y anula el anterior (tendrás que cambiarlo en tu bio).")),
            Boton("cerrar_agenda", _("Deja de aceptar solicitudes; la página lo indica. Ábrela cuando quieras.")),
            Boton("abrir_agenda", _("Vuelve a aceptar solicitudes.")),
        ),
        (_("Las pestañas separan las nuevas, las aceptadas sin fecha, las que ya tienen cita y las rechazadas."),),
        ("solicitudes:lista",),
        "solicitudes",
    ),
    Pantalla(
        "solicitud",
        _("Solicitud"),
        _("Una petición de reserva: la idea, las referencias y el contacto. Decide qué hacer con ella."),
        (
            Boton("dar_cita", _("Crea su ficha (o usa la que ya existe) y abre una cita nueva con sus datos.")),
            Boton("aceptar_sin_fecha", _("Crea su ficha y su proyecto, sin fecha todavía.")),
            Boton(
                "rechazar",
                _("La rechaza (sus datos se borran solos en 30 días) o la marca como spam (se borra al momento)."),
            ),
            Boton("responder_rapido", _("Abre una respuesta preparada lista para WhatsApp, SMS o copiar.")),
            Boton("analizar_ia", _("La IA estima estilo, tamaño y sesiones y te dice qué falta preguntar.")),
        ),
        (),
        ("solicitudes:detalle",),
        "solicitudes",
    ),
    Pantalla(
        "flash",
        _("Flash"),
        _("Tu catálogo de diseños flash: disponibles, reservados o vendidos. Puedes publicarlo en una página pública."),
        (
            Boton("nuevo_diseno", _("Sube un diseño con su precio y tamaño.")),
            Boton("estado_flash", _("Cambia el estado de un diseño con un toque.")),
            Boton("publicar_catalogo", _("Crea la página pública del catálogo para compartirla.")),
            Boton("ocultar_catalogo", _("La página deja de verse (no se borra nada).")),
            Boton("renovar_enlace", _("Crea un enlace nuevo y anula el anterior.")),
        ),
        (_("Marca un diseño como «repetible» si lo tatúas más de una vez."),),
        ("catalogo:lista", "catalogo:nuevo", "catalogo:editar"),
        "flash",
    ),
    Pantalla(
        "finanzas",
        _("Finanzas"),
        _("Ingresos, gastos y balance de cada mes. Los cobros de las citas aparecen solos; los gastos los apuntas tú."),
        (
            Boton("mes_anterior_siguiente", _("Cambia de mes.")),
            Boton("ingreso", _("Apunta un ingreso que no viene de una cita (venta de flash, merch…).")),
            Boton("gasto", _("Apunta un gasto (tintas, alquiler, agujas…) con su categoría.")),
            Boton("exportar_csv", _("Descarga los movimientos de un periodo para tu contable.")),
        ),
        (_("Toca cualquier movimiento de la tabla para corregirlo."),),
        (
            "finanzas:resumen",
            "finanzas:gasto_nuevo",
            "finanzas:gasto_editar",
            "finanzas:pago_nuevo",
            "finanzas:pago_editar",
        ),
        "finanzas",
        propietaria=True,
    ),
    Pantalla(
        "asistente",
        _("Asistente IA"),
        _("Pregunta a tu CRM con tus palabras y pide propuestas de respuesta. La IA propone; tú decides y envías."),
        (
            Boton("buscar_ia", _("Busca clientes con una frase: «VIP que cumplen en diciembre».")),
            Boton(
                "proponer_respuesta", _("Pega un mensaje que te han enviado y la IA redacta una respuesta con tu tono.")
            ),
        ),
        (_("Sin clave de OpenAI configurada, la búsqueda sigue funcionando con un intérprete básico."),),
        ("ia:asistente",),
        "asistente",
    ),
    Pantalla(
        "ajustes",
        _("Ajustes"),
        _(
            "Datos del estudio, textos legales, reservas, fidelización, IA, copias de seguridad y registro de actividad."
        ),
        (
            Boton("secciones_ajustes", _("Cada pestaña es un grupo de ajustes: marca, reservas, consentimiento…")),
            Boton("guardar", _("Guarda la sección que estás viendo.")),
            Boton("actualizar_logo", _("Sube tu logotipo (PNG cuadrado). Sale en la app y en tus páginas públicas.")),
            Boton("descargar_exportacion", _("Descarga un .zip con todos tus datos. Pide tu contraseña.")),
            Boton("crear_copia", _("Hace una copia de seguridad ahora mismo (además de la automática de cada noche).")),
            Boton("descargar_copia", _("Descarga una copia guardada. Pide tu contraseña.")),
            Boton("registro_actividad", _("Quién entró, qué se exportó o borró y cuándo.")),
        ),
        (_("Al cambiar el texto del consentimiento se crea una versión nueva; lo ya firmado no cambia."),),
        ("nucleo:ajustes", "nucleo:auditoria"),
        "datos",
        propietaria=True,
    ),
    Pantalla(
        "cuenta",
        _("Mi cuenta"),
        _("Tu nombre, tu contraseña y tus preferencias de ayuda."),
        (
            Boton("guardar", _("Guarda tu nombre.")),
            Boton("cambiar_contrasena", _("Cambia la contraseña (mínimo 12 caracteres).")),
            Boton("mostrar_ayudas", _("Enciende o apaga las pistas que salen arriba de cada pantalla.")),
        ),
        (),
        ("cuentas:cuenta",),
        "empezar",
    ),
    Pantalla(
        "tutorial",
        _("Cómo usar"),
        _("Este tutorial: empieza por «Primeros pasos» y consulta cualquier capítulo cuando lo necesites."),
        (
            Boton("ayuda", _("En cualquier pantalla abre la ayuda de esa pantalla: qué hace cada botón. Tecla ?.")),
            Boton("mostrar_ayudas", _("Vuelve a mostrar las pistas de cada pantalla si las cerraste.")),
        ),
        (),
        ("ayuda:inicio",),
        "empezar",
    ),
]

_POR_VISTA = {vista: p for p in PANTALLAS for vista in p.vistas}
_POR_CLAVE = {p.clave: p for p in PANTALLAS}


def pantalla_para(nombre_vista: str | None) -> Pantalla | None:
    return _POR_VISTA.get(nombre_vista or "")


def pantalla(clave: str) -> Pantalla | None:
    return _POR_CLAVE.get(clave)


# --- Tutorial ---------------------------------------------------------------------------------------------


def texto_plano(texto) -> str:
    """El texto con [[boton]] sustituido por la etiqueta del botón y sin asteriscos (para buscar)."""
    plano = _TOKEN.sub(lambda m: str(BOTONES[m.group(1)][1]) if m.group(1) in BOTONES else "", str(texto))
    return plano.replace("**", "")


@dataclass(frozen=True)
class Solo:
    """Paso del tutorial que solo ve la propietaria (habla de pantallas a las que una ayudante no entra)."""

    texto: str

    def __str__(self) -> str:
        return str(self.texto)


@dataclass(frozen=True)
class Capitulo:
    clave: str
    icono: str
    titulo: str
    resumen: str
    intro: str
    pasos: tuple
    consejo: str = ""
    pantallas: tuple = field(default_factory=tuple)
    propietaria: bool = False

    def pasos_para(self, usuario) -> list:
        es_propietaria = getattr(usuario, "es_propietaria", False)
        return [p for p in self.pasos if es_propietaria or not isinstance(p, Solo)]

    @property
    def texto_busqueda(self) -> str:
        partes = [self.titulo, self.resumen, self.intro, *self.pasos, self.consejo]
        return " ".join(texto_plano(p) for p in partes).lower()


CAPITULOS = [
    Capitulo(
        "empezar",
        "libro",
        _("Lo básico"),
        _("Cómo moverte por la app y dónde está la ayuda."),
        _(
            "La app funciona igual en el móvil, la tablet y el ordenador. No tienes que aprender nada de memoria: "
            "cada pantalla tiene su propia ayuda."
        ),
        (
            _(
                "**Para moverte:** en el ordenador usa la barra de la izquierda; en el móvil, la barra de abajo "
                "(Hoy · Agenda · Mensajes · Clientes) y [[mas]] para el resto de secciones."
            ),
            _(
                "**El amarillo significa «esto es lo importante»:** el botón principal de cada pantalla y los avisos "
                "que necesitan tu atención. Lo demás es secundario."
            ),
            _(
                "**¿Dudas en una pantalla?** Pulsa [[ayuda]] (arriba en el móvil, abajo a la izquierda en el "
                "ordenador, o la tecla ?). Verás qué hace cada botón de esa pantalla."
            ),
            _("En el ordenador, deja el ratón quieto sobre un botón un momento y verás una pequeña explicación."),
            _(
                "Las **pistas** con una bombilla que salen arriba de cada pantalla se cierran con [[pista_entendido]]. "
                "Puedes apagarlas todas en [[mi_cuenta]]."
            ),
            _(
                "Cambia el idioma de la interfaz con [[idioma]]. Los mensajes a clientes van siempre en el idioma del estudio."
            ),
            _(
                "**Instálala como una app:** en el móvil, abre el menú del navegador y elige «Añadir a pantalla de "
                "inicio». Se abrirá a pantalla completa, como cualquier otra app."
            ),
        ),
        _("La sesión dura 30 días: no tendrás que escribir la contraseña cada vez."),
        ("cuenta", "tutorial"),
    ),
    Capitulo(
        "rutina",
        "reloj",
        _("Tu día a día en 5 minutos"),
        _("La rutina recomendada para cada jornada."),
        _(
            "Si solo vas a leer una parte, que sea esta. Con esta rutina no se te escapa ningún mensaje ni ninguna cita."
        ),
        (
            _(
                "**Por la mañana, abre Hoy.** Mira las citas del día y los avisos amarillos (cancelaciones o cambios de fecha)."
            ),
            _(
                "**Vacía «Mensajes de hoy».** Para cada mensaje pulsa [[whatsapp]], envíalo en WhatsApp, vuelve y "
                "pulsa [[si_enviado]]. Lo que no quieras enviar: [[posponer]] o [[descartar]]."
            ),
            _("**Revisa Solicitudes** si tienen número amarillo: [[dar_cita]], [[aceptar_sin_fecha]] o [[rechazar]]."),
            _(
                "**Antes de cada sesión,** abre la cita: revisa los avisos de salud y pulsa [[firmar_consentimiento]] "
                "si aún no ha firmado."
            ),
            _(
                "**Al terminar cada sesión,** pulsa [[marcar_realizada]]: apuntas el cobro y las notas, y los mensajes "
                "de cuidados se preparan solos para los días siguientes."
            ),
            _(
                "**Si alguien cancela,** ábrela desde el aviso y pulsa [[ofrecer]] junto a quien encaje de la lista de espera."
            ),
        ),
        _(
            "La bandeja se rellena sola cada mañana (hacia las 5-6 h en Orlando). No hace falta que hagas nada para que aparezcan los mensajes."
        ),
        ("panel",),
    ),
    Capitulo(
        "ajustes",
        "ajustes",
        _("Prepara tu estudio"),
        _("Datos, horario, tipos de cita y textos legales."),
        _("Hazlo una vez al principio. Todo se puede cambiar después."),
        (
            Solo(
                _(
                    "Ve a **Ajustes › Marca y contacto**: nombre del estudio, tu nombre artístico, teléfono, Instagram y "
                    "dirección. Sube tu logotipo con [[actualizar_logo]]."
                )
            ),
            _(
                "En **Agenda › [[horario_tipos]]** pon tu horario (hasta dos tramos por día) y pulsa [[guardar_horario]]. "
                "Añade vacaciones o convenciones con [[nuevo]] en «Días libres y bloqueos»."
            ),
            _(
                "Revisa los **tipos de cita** (Consulta, Sesión, Sesión larga, Retoque): duración, color y seña sugerida. "
                "Crea los tuyos si hace falta."
            ),
            Solo(
                _(
                    "En **Ajustes › Reservas y textos** escribe tu política de señas, los cuidados y el texto de bienvenida "
                    "de tu página de reservas."
                )
            ),
            Solo(
                _(
                    "En **Ajustes › Consentimiento** revisa el texto legal con tu asesoría. Es una plantilla de partida: "
                    "cada cambio crea una versión nueva."
                )
            ),
            Solo(
                _(
                    "En **Ajustes › Fidelización** decide con cuántos días se recuerda una cita y cuándo alguien cuenta como inactivo."
                )
            ),
        ),
        _(
            "Los textos que ven tus clientas (mensajes, consentimiento) van en el idioma del estudio, que se elige en el servidor."
        ),
        ("ajustes", "configuracion_agenda"),
    ),
    Capitulo(
        "clientes",
        "clientes",
        _("Clientes e importación"),
        _("Trae tu lista desde un CSV y conoce la ficha."),
        _(
            "Si ya tienes tus clientes en Excel, Google Sheets, el móvil u otro programa, impórtalos todos de una vez "
            "antes de empezar. Si no, se irán creando solas con las citas y las solicitudes."
        ),
        (
            Solo(
                _(
                    "Ve a **Clientes** y pulsa [[importar_csv]]. Si quieres una guía, pulsa [[descargar_plantilla]] y rellénala."
                )
            ),
            Solo(
                _(
                    "Guarda tu hoja como **CSV** (en Excel: Archivo › Guardar como › CSV UTF-8; en Google Sheets: "
                    "Archivo › Descargar › CSV). La primera fila debe tener los títulos: nombre, telefono, email…"
                )
            ),
            Solo(
                _(
                    "Elige el archivo, indica cómo están escritas las fechas y pulsa [[revisar_archivo]]. Todavía no se "
                    "guarda nada: verás qué filas entran, cuáles ya existen y cuáles tienen errores."
                )
            ),
            Solo(
                _(
                    "Si alguna fila falla, pulsa [[descargar_errores]], corrígela en tu hoja y súbela después. "
                    "Pulsa [[importar]] para crear el resto."
                )
            ),
            _(
                "Para dar de alta a alguien a mano, pulsa [[nuevo_cliente]]. Basta con el nombre y un dato de contacto. "
                "Si acepta promociones, indica cómo lo aceptó: queda registrado."
            ),
            _(
                "En la **ficha** tienes su historia completa. Desde ahí: [[nueva_cita]], [[escribir_mensaje]], "
                "[[anadir_tatuaje]] (con fotos) o [[guardar_nota]]."
            ),
            _("Usa [[etiquetas]] para agrupar fichas. La etiqueta «VIP» se usa en las campañas."),
        ),
        _(
            "Sin consentimiento de promociones solo recibirá mensajes de servicio (recordatorios y cuidados), nunca "
            "felicitaciones ni campañas."
        ),
        ("clientes", "importar", "ficha", "tatuaje"),
    ),
    Capitulo(
        "agenda",
        "agenda",
        _("La agenda y las citas"),
        _("Crear, confirmar, cobrar y cerrar citas."),
        _("Cada cita pasa por estados: por confirmar → confirmada → realizada (o cancelada / no vino)."),
        (
            _(
                "Pulsa [[nueva_cita]] (o toca un hueco vacío del calendario). Busca a la clienta, elige el tipo y la "
                "hora y pulsa [[guardar_cita]]."
            ),
            _("Si cobras una seña, ábrela y usa [[registrar_pago]]. Aparece sola en Finanzas."),
            _(
                "Para que la clienta confirme sin llamarte, pulsa [[generar_enlace]] y envíaselo. Podrá confirmar, "
                "cancelar o pedir otra fecha."
            ),
            _("Si la cita está «por confirmar», pulsa [[confirmar]] cuando la cierres con ella."),
            _(
                "Al terminar, pulsa [[marcar_realizada]]: cobro final, notas y si el tatuaje queda terminado. "
                "Los mensajes de cuidados se programan solos."
            ),
            _(
                "Si alguien cancela, pulsa [[cancelar_cita]]. La app te propone quién de la [[lista_espera]] encaja "
                "y prepara el mensaje con [[ofrecer]]."
            ),
            _("Si no se presenta, pulsa [[no_vino]]: queda en su historial."),
        ),
        _("Dos citas nunca pueden solaparse, aunque las crees a la vez desde dos dispositivos."),
        ("agenda", "cita", "cita_form", "espera"),
    ),
    Capitulo(
        "mensajes",
        "mensajes",
        _("Mensajes de hoy"),
        _("El corazón de la app: revisar y enviar en un minuto."),
        _(
            "Cada mañana la app prepara los mensajes que tocan: recordatorios de cita, cuidados, retoques, "
            "cumpleaños, aniversarios del tatuaje, campañas y reactivaciones. **Nunca se envía nada solo.**"
        ),
        (
            _("Abre **Mensajes**. El número amarillo es lo que queda por enviar hoy."),
            _("Lee el texto. Si quieres, cámbialo ahí mismo: se guarda solo."),
            _("Pulsa [[whatsapp]] (o [[sms]], o [[copiar]]). Se abre tu app con el texto escrito: envíalo."),
            _("Vuelve a la app y pulsa [[si_enviado]]. El mensaje sale de la bandeja y queda en el historial."),
            _("¿No es buen momento? [[posponer]]. ¿No tiene sentido enviarlo? [[descartar]]."),
            _("Para escribir a alguien fuera de la bandeja, usa [[escribir_mensaje]]."),
        ),
        _("Si marcaste uno por error, pulsa [[deshacer]]."),
        ("bandeja", "historial"),
    ),
    Capitulo(
        "fidelizacion",
        "corazon",
        _("Campañas, fechas, cuidados y plantillas"),
        _("Que vuelvan: mensajes automáticos que tú revisas."),
        _("Todo esto acaba en tu bandeja, repartido por días. Tú sigues decidiendo qué se envía."),
        (
            _(
                "**Plantillas:** revisa los textos de partida. Las palabras entre llaves, como {nombre}, se rellenan "
                "solas. La vista previa te enseña el resultado."
            ),
            _("**Cuidados:** ajusta la secuencia tras cada sesión (día 1, día 3, semana 2 y retoque)."),
            _(
                "**Fechas destacadas:** San Valentín, Halloween, viernes 13… Unos días antes se prepara una campaña. "
                "Añade las tuyas con [[nueva_fecha]]."
            ),
            _(
                "**Campañas:** pulsa [[nueva_campana]], elige el grupo (VIP, inactivos, cumpleaños del mes…), "
                "la plantilla y cuántos por día, y pulsa [[lanzar_campana]]."
            ),
        ),
        _(
            "Solo reciben promociones quienes aceptaron promociones y no pidieron «no contactar». Si alguien se da de baja, su mensaje desaparece."
        ),
        ("plantillas", "cuidados", "fechas", "campanas"),
    ),
    Capitulo(
        "solicitudes",
        "bandeja",
        _("Reservas online y solicitudes"),
        _("Tu página pública para pedir cita, con fotos."),
        _("Tus clientas rellenan un formulario con su idea y sus referencias; tú decides desde Solicitudes."),
        (
            _("Ve a **Solicitudes** y pulsa [[crear_enlace]]. Luego [[copiar]] y pégalo en tu bio de Instagram."),
            _("Cuando llegue una solicitud, el menú lo marcará con un número amarillo. Ábrela."),
            _("Revisa la idea y las fotos. Si quieres, pulsa [[analizar_ia]] para estimar sesiones."),
            _(
                "Decide: [[dar_cita]] crea la ficha y abre la cita; [[aceptar_sin_fecha]] guarda la ficha y el proyecto; "
                "[[rechazar]] la descarta."
            ),
            _("Usa [[responder_rapido]] para contestarle con un mensaje preparado."),
            _("¿Agenda llena? Pulsa [[cerrar_agenda]] y la página dejará de aceptar solicitudes hasta que la abras."),
        ),
        _("La página tiene protecciones contra spam y comprueba la edad mínima."),
        ("solicitudes", "solicitud"),
    ),
    Capitulo(
        "consentimiento",
        "firma",
        _("Consentimiento con firma"),
        _("La clienta firma con el dedo en tu tablet o móvil."),
        _(
            "Se genera un PDF con el texto exacto que firmó, sus respuestas de salud y la firma, y se guarda en su ficha."
        ),
        (
            _("Abre la cita (o la ficha) y pulsa [[firmar_consentimiento]]."),
            _("Pasa la tablet a la clienta: lee el texto, revisa sus datos, responde las preguntas de salud y firma."),
            _("Al terminar verás la confirmación. Puedes abrirlo cuando quieras con [[ver_pdf]]."),
        ),
        _("Los consentimientos se conservan el plazo legal (2 años en Florida) aunque anonimices la ficha."),
        (),
    ),
    Capitulo(
        "flash",
        "flash",
        _("Catálogo flash"),
        _("Tus diseños disponibles, con página pública opcional."),
        _("Sube tus diseños y marca su estado. Si lo publicas, tus clientas pueden verlos y pedirlos."),
        (
            _("Pulsa [[nuevo_diseno]], sube la imagen y pon precio y tamaño."),
            _("Cambia el estado con un toque: [[estado_flash]]."),
            _(
                "Pulsa [[publicar_catalogo]] para tener una página pública que compartir. [[ocultar_catalogo]] la esconde."
            ),
        ),
        "",
        ("flash",),
    ),
    Capitulo(
        "finanzas",
        "dinero",
        _("Finanzas"),
        _("Ingresos, gastos y balance del mes."),
        _(
            "Las señas y los cobros que apuntas en las citas aparecen solos. Tú solo añades los gastos y otros ingresos."
        ),
        (
            _("Pulsa [[gasto]] para apuntar un gasto con su categoría."),
            _("Pulsa [[ingreso]] para un ingreso que no viene de una cita."),
            _("Muévete entre meses con las flechas y descarga los movimientos con [[exportar_csv]] para tu contable."),
        ),
        "",
        ("finanzas",),
        propietaria=True,
    ),
    Capitulo(
        "asistente",
        "ia",
        _("Asistente IA"),
        _("Busca con tus palabras y redacta respuestas."),
        _(
            "Opcional: funciona si el estudio tiene una clave de OpenAI. Solo ve lo mínimo (nombre de pila, tatuajes, "
            "visitas). Nunca ve salud, teléfono, email, notas ni firmas."
        ),
        (
            _(
                "En **Asistente IA**, escribe a quién buscas («no vienen desde hace 8 meses y aceptan promociones») y pulsa [[buscar_ia]]."
            ),
            _("Pega un mensaje que te han enviado y pulsa [[proponer_respuesta]]. Revísalo y envíalo tú."),
            _("En la bandeja, [[reescribir]] propone otra versión de un mensaje con tu tono."),
        ),
        _("En Ajustes › Asistente IA puedes pegar ejemplos de mensajes tuyos para que imite tu estilo."),
        ("asistente",),
    ),
    Capitulo(
        "datos",
        "escudo",
        _("Copias de seguridad y privacidad"),
        _("Tus datos están a salvo y bajo tu control."),
        _("Cada noche se hace una copia de seguridad automática. Además, puedes descargar todo cuando quieras."),
        (
            _(
                "En **Ajustes › Datos y seguridad**, pulsa [[descargar_exportacion]] para bajar un .zip con todo (pide tu contraseña)."
            ),
            _("Pulsa [[crear_copia]] antes de un cambio grande, como una importación masiva."),
            _(
                "Si una clienta pide sus datos, abre su ficha y pulsa [[exportar_datos]]. Si pide que la borres, usa "
                "[[anonimizar]] (o [[eliminar_definitivamente]] si no tiene consentimientos que conservar)."
            ),
            _("Consulta el [[registro_actividad]] para ver accesos, exportaciones y borrados."),
        ),
        _("La exportación contiene datos de salud: guárdala en un lugar seguro."),
        ("ajustes",),
        propietaria=True,
    ),
]

PREGUNTAS = [
    (
        _("¿La app envía mensajes sola?"),
        _(
            "No. Prepara los mensajes cada mañana, pero siempre los envías tú desde tu WhatsApp o tu app de mensajes. "
            "Así nada sale sin que lo veas."
        ),
    ),
    (
        _("¿Por qué no aparece el mensaje de cumpleaños de una clienta?"),
        _(
            "Las felicitaciones y promociones solo se preparan para quien aceptó promociones, tiene la fecha de "
            "nacimiento en su ficha y no pidió «no contactar»."
        ),
    ),
    (
        _("Importé clientes y aparecen como «nuevos del mes». ¿Es normal?"),
        _(
            "Sí, si el archivo no traía la columna «cliente_desde». Para conservar su antigüedad, añade esa columna "
            "con la fecha de su primera visita antes de importar."
        ),
    ),
    (
        _("Importé un archivo equivocado. ¿Cómo lo deshago?"),
        _(
            "Si pusiste una etiqueta al lote, filtra la lista de clientes por ella para revisarlas juntas y "
            "eliminarlas una a una desde su ficha. Si fue un error grande, restaura la copia de seguridad de antes de "
            "importar (ver «Copias de seguridad»)."
        ),
    ),
    (
        _("Una clienta pidió cambiar su cita desde el enlace. ¿Dónde lo veo?"),
        _(
            "Sale un aviso amarillo en Hoy y en la agenda. Ábrelo, mueve la cita con «Editar / mover» y pulsa "
            "«Marcar como atendido»."
        ),
    ),
    (
        _("¿Puedo usarla desde varios dispositivos a la vez?"),
        _("Sí: móvil, tablet y ordenador a la vez. Las citas nunca se solapan aunque las crees al mismo tiempo."),
    ),
    (
        _("Olvidé mi contraseña."),
        _(
            "Por seguridad no hay recuperación por email. Quien administra el servidor puede ponerte una nueva desde "
            "la Shell de Render con «python manage.py changepassword tu_usuario». Mientras tengas la sesión abierta, "
            "cámbiala en «Mi cuenta»."
        ),
    ),
    (
        _("¿Cómo cambio el idioma?"),
        _(
            "Con los botones ES · EN del menú. Cambia la interfaz; los mensajes para clientas van en el idioma del "
            "estudio."
        ),
    ),
    (
        _("He cerrado las pistas y quiero volver a verlas."),
        _("Ve a «Mi cuenta» (o a este tutorial) y activa «Mostrar ayudas en pantalla»."),
    ),
]

GLOSARIO = [
    (_("Seña"), _("Pago por adelantado para reservar la fecha. Se descuenta del precio final.")),
    (_("No-show"), _("Cuando alguien no se presenta a su cita sin avisar. En la app: «No vino».")),
    (_("Bandeja"), _("«Mensajes de hoy»: los mensajes preparados para que los revises y envíes.")),
    (_("Plantilla"), _("Texto de partida de un tipo de mensaje, con variables que se rellenan solas.")),
    (_("Variable"), _("Palabra entre llaves, como {nombre}, que se sustituye por el dato de cada clienta.")),
    (_("Segmento"), _("Grupo automático de clientes (VIP, inactivos, cumpleaños del mes…) para una campaña.")),
    (_("Campaña"), _("Envío a un segmento repartido en varios días en tu bandeja.")),
    (_("Fecha destacada"), _("Día especial que prepara una campaña sola unos días antes.")),
    (_("Cuidados"), _("Mensajes tras una sesión para que el tatuaje cicatrice bien (día 1, día 3, semana 2…).")),
    (_("Retoque"), _("Sesión corta para repasar un tatuaje ya cicatrizado, normalmente al mes.")),
    (_("Bloqueo"), _("Días u horas en los que no se puede reservar (vacaciones, convenciones…).")),
    (_("Lista de espera"), _("Personas que quieren cita si se libera un hueco antes.")),
    (
        _("Consentimiento informado"),
        _("Documento legal que la clienta firma antes de tatuarse. Se guarda en PDF."),
    ),
    (
        _("Consentimiento de promociones"),
        _("Permiso para enviarle felicitaciones y promociones. Se registra cuándo y cómo lo dio."),
    ),
    (_("Anonimizar"), _("Borrar los datos personales de una ficha conservando importes y documentos legales.")),
    (_("CSV"), _("Archivo de texto con una tabla (columnas separadas por comas). Lo exportan Excel y Google Sheets.")),
    (_("VIP"), _("Etiqueta para tus mejores clientes. Se puede asignar a mano o por gasto acumulado.")),
]

ATAJOS = [
    ("/", _("Buscar")),
    (_("n"), _("Nueva cita")),
    (_("c"), _("Nuevo cliente")),
    (_("h"), _("Ir a Hoy")),
    (_("a"), _("Ir a la agenda")),
    (_("m"), _("Mensajes de hoy")),
    ("?", _("Ayuda de la pantalla")),
]


# --- Primeros pasos ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Paso:
    clave: str
    titulo: str
    texto: str
    url: str
    accion: str
    hecho: bool
    manual: bool  # se marca a mano (no se puede detectar)


def _url(nombre: str, sufijo: str = "") -> str:
    try:
        return reverse(nombre) + sufijo
    except NoReverseMatch:
        return ""


def primeros_pasos(usuario) -> list[Paso]:
    """Lista de configuración inicial. Se detecta lo que se puede; el resto se marca a mano."""
    from apps.agenda.models import Cita
    from apps.clientes.models import Cliente
    from apps.mensajeria.models import MensajePreparado

    from .models import AjustesEstudio, EnlacePublico

    ajustes = AjustesEstudio.obtener()
    marcados = set(getattr(usuario, "ayudas_cerradas", None) or [])
    propietaria = getattr(usuario, "es_propietaria", False)

    def manual(clave: str) -> bool:
        return f"paso:{clave}" in marcados

    pasos = []
    if propietaria:
        pasos.append(
            Paso(
                "marca",
                str(_("Pon los datos de tu estudio")),
                str(_("Nombre, teléfono, Instagram y logotipo. Salen en tus páginas públicas y en los mensajes.")),
                _url("nucleo:ajustes", "?seccion=marca"),
                str(_("Abrir ajustes")),
                bool(ajustes.telefono or ajustes.instagram or ajustes.logo) or manual("marca"),
                False,
            )
        )
        pasos.append(
            Paso(
                "horario",
                str(_("Ajusta tu horario y tus tipos de cita")),
                str(_("Vienen de serie de 11:00 a 19:00, de martes a sábado. Cámbialos a tu medida.")),
                _url("agenda:configuracion"),
                str(_("Abrir horario")),
                manual("horario"),
                True,
            )
        )
    pasos.append(
        Paso(
            "clientes",
            str(_("Trae a tus clientes")),
            str(
                _("Importa tu lista desde un CSV (Excel, Google Sheets…) o añade las primeras fichas a mano.")
                if propietaria
                else _("Añade las primeras fichas de clientes.")
            ),
            _url("clientes:importar") if propietaria else _url("clientes:nuevo"),
            str(_("Importar CSV") if propietaria else _("Nuevo cliente")),
            Cliente.objects.activos().exists(),
            False,
        )
    )
    pasos.append(
        Paso(
            "cita",
            str(_("Apunta tu primera cita")),
            str(_("Elige clienta, tipo y hora. Luego podrás cobrar la seña y enviarle el enlace para confirmar.")),
            _url("agenda:nueva"),
            str(_("Nueva cita")),
            Cita.objects.exists(),
            False,
        )
    )
    pasos.append(
        Paso(
            "reservas",
            str(_("Comparte tu enlace de reservas")),
            str(_("Crea tu página pública y pega el enlace en tu bio de Instagram.")),
            _url("solicitudes:lista"),
            str(_("Ir a Solicitudes")),
            EnlacePublico.objects.filter(proposito=EnlacePublico.Proposito.RESERVA).exists() or manual("reservas"),
            False,
        )
    )
    pasos.append(
        Paso(
            "plantillas",
            str(_("Repasa tus plantillas de mensajes")),
            str(_("Ajusta los textos a tu forma de hablar. Las palabras entre llaves se rellenan solas.")),
            _url("mensajeria:plantillas"),
            str(_("Ver plantillas")),
            manual("plantillas"),
            True,
        )
    )
    if propietaria:
        pasos.append(
            Paso(
                "consentimiento",
                str(_("Revisa el texto del consentimiento")),
                str(_("Es una plantilla de partida: revísala con tu asesoría antes de la primera firma.")),
                _url("nucleo:ajustes", "?seccion=legal"),
                str(_("Revisar texto")),
                ajustes.version_consentimiento > 1 or manual("consentimiento"),
                True,
            )
        )
    pasos.append(
        Paso(
            "mensaje",
            str(_("Envía tu primer mensaje")),
            str(_("Abre «Mensajes de hoy», pulsa WhatsApp, envíalo y vuelve para confirmarlo.")),
            _url("mensajeria:bandeja"),
            str(_("Abrir mensajes")),
            MensajePreparado.objects.filter(estado=MensajePreparado.Estado.ENVIADO).exists() or manual("mensaje"),
            False,
        )
    )
    return pasos


PISTA_PRIMEROS_PASOS = "primeros_pasos"
CLAVES_PASOS = {"marca", "horario", "clientes", "cita", "reservas", "plantillas", "consentimiento", "mensaje"}


def contexto(request) -> dict:
    """Ayuda de la pantalla actual para base.html (panel «Ayuda» y pista de arriba)."""
    usuario = request.user
    match = getattr(request, "resolver_match", None)
    p = pantalla_para(match.view_name if match else "")
    if p and p.propietaria and not getattr(usuario, "es_propietaria", False):
        p = None
    visibles = getattr(usuario, "ayudas_visibles", True)
    return {
        "pantalla": p,
        "botones": p.botones_para(usuario) if p else [],
        "pista": bool(p and p.clave != "tutorial" and visibles and not usuario.ayuda_cerrada(p.clave)),
        "visibles": visibles,
        "atajos": ATAJOS,
    }
