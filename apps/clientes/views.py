from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.agenda.models import Cita, EstadoCita
from apps.nucleo.archivos import borrar_archivo, servir
from apps.nucleo.auditoria import Accion, registrar
from apps.nucleo.red import es_htmx

from . import servicios
from .forms import (
    ClienteForm,
    DatosSaludForm,
    EtiquetaForm,
    FotosForm,
    MarketingForm,
    NotaForm,
    TatuajeForm,
)
from .models import Cliente, DatosSalud, Etiqueta, FotoTatuaje, NotaCliente, Tatuaje

FILTROS = {
    "todos": gettext_lazy("Todos"),
    "proximas": gettext_lazy("Con cita"),
    "vip": gettext_lazy("VIP"),
    "nuevos": gettext_lazy("Nuevos del mes"),
    "marketing": gettext_lazy("Aceptan promociones"),
}


def _filtrar(qs, filtro: str):
    hoy = timezone.localdate()
    if filtro == "proximas":
        return qs.filter(proxima_cita__isnull=False)
    if filtro == "vip":
        return qs.filter(etiquetas__nombre__iexact="vip")
    if filtro == "nuevos":
        return qs.filter(creado_en__year=hoy.year, creado_en__month=hoy.month)
    if filtro == "marketing":
        return qs.filter(marketing_consentimiento=True, contacto_bloqueado=False)
    return qs


def lista(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "todos")
    etiqueta = request.GET.get("etiqueta", "")
    orden = request.GET.get("orden", "nombre")
    qs = servicios.anotar_listado(Cliente.objects.activos().buscar(q)).prefetch_related("etiquetas")
    qs = _filtrar(qs, filtro)
    if etiqueta.isdigit():
        qs = qs.filter(etiquetas__pk=etiqueta)
    qs = {
        "reciente": qs.order_by("-creado_en"),
        "visita": qs.order_by("-ultima_visita"),
        "gasto": qs.order_by("-gasto", "nombre"),
    }.get(orden, qs.order_by("nombre", "apellidos"))
    pagina = Paginator(qs.distinct(), 30).get_page(request.GET.get("pagina"))
    contexto = {
        "pagina": pagina,
        "q": q,
        "filtro": filtro,
        "filtros": FILTROS,
        "etiquetas": Etiqueta.objects.annotate(n=Count("clientes")).filter(n__gt=0),
        "etiqueta": etiqueta,
        "orden": orden,
        "total": Cliente.objects.activos().count(),
    }
    if es_htmx(request) and request.headers.get("HX-Target") == "resultados":
        return render(request, "clientes/lista.html#resultados", contexto)
    return render(request, "clientes/lista.html", contexto)


def buscar(request):
    """Autocompletado (formulario de cita, lista de espera)."""
    q = request.GET.get("q", "").strip()
    resultados = Cliente.objects.activos().buscar(q)[:8] if len(q) >= 2 else []
    return render(request, "clientes/_buscar.html", {"resultados": resultados, "q": q})


def nuevo(request):
    form = ClienteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cliente = form.save(usuario=request.user)
        _avisar_duplicados(request, cliente)
        messages.success(request, _("%(nombre)s añadido.") % {"nombre": cliente.nombre})
        return redirect("clientes:ficha", cliente.pk)
    return render(request, "clientes/formulario.html", {"form": form})


def editar(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        form.save(usuario=request.user)
        _avisar_duplicados(request, cliente)
        messages.success(request, _("Ficha actualizada."))
        return redirect("clientes:ficha", cliente.pk)
    return render(request, "clientes/formulario.html", {"form": form, "cliente": cliente})


def _avisar_duplicados(request, cliente):
    otros = list(servicios.duplicados(cliente)[:3])
    if otros:
        nombres = ", ".join(o.nombre_completo for o in otros)
        messages.warning(
            request, _("Ojo: hay otras fichas con el mismo teléfono o email (%(nombres)s).") % {"nombres": nombres}
        )


def ficha(request, pk):
    cliente = get_object_or_404(
        Cliente.objects.prefetch_related(
            "etiquetas",
            Prefetch("tatuajes", queryset=Tatuaje.objects.prefetch_related("fotos")),
        ),
        pk=pk,
    )
    if cliente.anonimizado:
        return render(request, "clientes/anonimizado.html", {"cliente": cliente})
    salud = DatosSalud.objects.filter(cliente=cliente).first()
    proximas = cliente.citas.futuras().select_related("tipo")
    contexto = {
        "cliente": cliente,
        "salud": salud,
        "alertas_salud": salud.alertas() if salud else [],
        "es_menor": cliente.es_menor(),
        "stats": servicios.estadisticas(cliente),
        "proximas": proximas,
        "linea": servicios.linea_de_tiempo(cliente),
        "nota_form": NotaForm(initial={"origen": NotaCliente.Origen.MANUAL}),
        "espera": cliente.lista_espera.filter(activa=True).select_related("tipo"),
    }
    return render(request, "clientes/ficha.html", contexto)


def salud(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    instancia = DatosSalud.objects.filter(cliente=cliente).first() or DatosSalud(cliente=cliente)
    form = DatosSaludForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Datos de salud guardados."))
        return redirect("clientes:ficha", cliente.pk)
    return render(request, "clientes/salud.html", {"form": form, "cliente": cliente})


@require_POST
def marketing(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    form = MarketingForm(request.POST)
    if form.is_valid():
        if form.cleaned_data["accion"] == "alta":
            cliente.dar_consentimiento(form.cleaned_data["origen"], request.user, form.cleaned_data["notas"])
            messages.success(request, _("Consentimiento registrado."))
        else:
            cliente.retirar_consentimiento(form.cleaned_data["origen"], request.user, form.cleaned_data["notas"])
            _descartar_promocionales(cliente)
            messages.success(request, _("Baja registrada: no recibirá mensajes promocionales."))
        registrar(request, Accion.CONSENTIMIENTO, form.cleaned_data["accion"], objeto=cliente)
    return redirect("clientes:ficha", cliente.pk)


def _descartar_promocionales(cliente):
    try:
        from apps.mensajeria.servicios import descartar_promocionales

        descartar_promocionales(cliente)
    except ImportError:
        pass


@require_POST
def nota(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    form = NotaForm(request.POST)
    if form.is_valid():
        n = form.save(commit=False)
        n.cliente, n.autor = cliente, request.user
        n.save()
        messages.success(request, _("Nota guardada."))
    return redirect(reverse("clientes:ficha", args=[cliente.pk]) + "#linea")


@require_POST
def borrar_nota(request, pk):
    n = get_object_or_404(NotaCliente, pk=pk)
    cliente_id = n.cliente_id
    n.delete()
    messages.success(request, _("Nota borrada."))
    return redirect("clientes:ficha", cliente_id)


# --- Tatuajes ---------------------------------------------------------------------------


def tatuaje_nuevo(request, pk):
    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    form = TatuajeForm(request.POST or None, initial={"fecha_inicio": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.cliente = cliente
        t.save()
        messages.success(request, _("Tatuaje añadido."))
        return redirect("clientes:tatuaje", t.pk)
    return render(request, "clientes/tatuaje_formulario.html", {"form": form, "cliente": cliente})


def tatuaje_editar(request, pk):
    t = get_object_or_404(Tatuaje.objects.select_related("cliente"), pk=pk)
    form = TatuajeForm(request.POST or None, instance=t)
    if request.method == "POST":
        if "borrar" in request.POST:
            cliente_id = t.cliente_id
            for f in t.fotos.all():
                borrar_archivo(f.imagen)
                borrar_archivo(f.miniatura)
            t.delete()
            messages.success(request, _("Tatuaje eliminado."))
            return redirect("clientes:ficha", cliente_id)
        if form.is_valid():
            form.save()
            messages.success(request, _("Tatuaje actualizado."))
            return redirect("clientes:tatuaje", t.pk)
    return render(request, "clientes/tatuaje_formulario.html", {"form": form, "cliente": t.cliente, "tatuaje": t})


def tatuaje(request, pk):
    t = get_object_or_404(Tatuaje.objects.select_related("cliente"), pk=pk)
    contexto = {
        "tatuaje": t,
        "cliente": t.cliente,
        "fotos": t.fotos.all(),
        "citas": t.citas.select_related("tipo").order_by("-inicio"),
        "pagos": t.pagos.all(),
        "fotos_form": FotosForm(),
        "realizadas": t.citas.filter(estado=EstadoCita.REALIZADA).count(),
    }
    return render(request, "clientes/tatuaje.html", contexto)


@require_POST
def subir_fotos(request, pk):
    t = get_object_or_404(Tatuaje, pk=pk)
    form = FotosForm(request.POST, request.FILES)
    if form.is_valid():
        for principal, mini in form.cleaned_data["imagenes"]:
            FotoTatuaje.objects.create(
                tatuaje=t,
                tipo=form.cleaned_data["tipo"],
                nota=form.cleaned_data["nota"],
                imagen=principal,
                miniatura=mini,
            )
        messages.success(request, _("Fotos subidas."))
    else:
        for errores in form.errors.values():
            for e in errores:
                messages.error(request, e)
    return redirect("clientes:tatuaje", t.pk)


def foto(request, pk, variante="completa"):
    f = get_object_or_404(FotoTatuaje, pk=pk)
    return servir(f.miniatura if variante == "mini" else f.imagen)


@require_POST
def borrar_foto(request, pk):
    f = get_object_or_404(FotoTatuaje, pk=pk)
    tatuaje_id = f.tatuaje_id
    borrar_archivo(f.imagen)
    borrar_archivo(f.miniatura)
    f.delete()
    messages.success(request, _("Foto eliminada."))
    return redirect("clientes:tatuaje", tatuaje_id)


# --- Etiquetas ------------------------------------------------------------------------------


def etiquetas(request):
    form = EtiquetaForm(request.POST or None)
    if request.method == "POST":
        if "borrar" in request.POST:
            Etiqueta.objects.filter(pk=request.POST.get("borrar")).delete()
            messages.success(request, _("Etiqueta eliminada."))
            return redirect("clientes:etiquetas")
        if form.is_valid():
            form.save()
            messages.success(request, _("Etiqueta creada."))
            return redirect("clientes:etiquetas")
    return render(
        request,
        "clientes/etiquetas.html",
        {"form": form, "etiquetas": Etiqueta.objects.annotate(n=Count("clientes"))},
    )


def tatuajes_de_cliente(request):
    """Opciones del selector de tatuaje al elegir cliente en una cita (HTMX)."""
    cliente_id = request.GET.get("cliente", "")
    tatuajes = Tatuaje.objects.filter(cliente_id=cliente_id) if cliente_id.isdigit() else []
    return render(request, "clientes/_opciones_tatuaje.html", {"tatuajes": tatuajes})


def citas_de_cliente(cliente):
    return Cita.objects.filter(cliente=cliente)


# --- Consentimiento informado (modo tablet) ---------------------------------------------------


def consentimiento(request, pk):
    from apps.agenda.models import Cita
    from apps.nucleo.models import AjustesEstudio
    from apps.nucleo.red import ip_cliente

    from . import consentimiento as servicio
    from .forms import ConsentimientoForm

    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    ajustes = AjustesEstudio.obtener()
    cita = None
    if request.GET.get("cita", "").isdigit():
        cita = Cita.objects.filter(pk=request.GET["cita"], cliente=cliente).first()
    salud = DatosSalud.objects.filter(cliente=cliente).first()
    inicial = {
        "nombre_firmante": cliente.nombre_completo,
        "fecha_nacimiento": cliente.fecha_nacimiento,
        "acepta_marketing": cliente.marketing_consentimiento,
    }
    if salud:
        inicial.update({c: getattr(salud, c) for c in ConsentimientoForm.CAMPOS_SALUD})
    form = ConsentimientoForm(request.POST or None, initial=inicial, edad_minima=ajustes.edad_minima)
    if request.method == "POST" and form.is_valid():
        c = servicio.registrar(
            cliente,
            cita=cita,
            nombre=form.cleaned_data["nombre_firmante"],
            fecha_nacimiento=form.cleaned_data["fecha_nacimiento"],
            salud=form.salud(),
            firma_data_url=form.cleaned_data["firma"],
            autoriza_fotos=form.cleaned_data["autoriza_fotos"],
            acepta_marketing=form.cleaned_data["acepta_marketing"],
            ip=ip_cliente(request),
            usuario=request.user,
        )
        registrar(request, Accion.CONSENTIMIENTO, "Consentimiento informado firmado", objeto=c)
        return render(request, "clientes/consentimiento_listo.html", {"cliente": cliente, "c": c})
    return render(request, "clientes/consentimiento.html", {"form": form, "cliente": cliente, "cita": cita})


def consentimiento_pdf(request, pk):
    from .models import ConsentimientoInformado

    c = get_object_or_404(ConsentimientoInformado, pk=pk)
    registrar(request, Accion.ACCESO_DOCUMENTO, "Consulta de consentimiento firmado", objeto=c)
    return servir(c.pdf, nombre=f"consentimiento-{c.pk}.pdf")


# --- Privacidad: exportar, anonimizar, eliminar ------------------------------------------------


def exportar_datos(request, pk):
    from django.http import HttpResponse

    from . import rgpd

    cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
    contenido = rgpd.exportar_cliente(cliente)
    registrar(request, Accion.EXPORTACION, f"Exportación de datos de {cliente.nombre_completo}", objeto=cliente)
    respuesta = HttpResponse(contenido, content_type="application/zip")
    respuesta["Content-Disposition"] = f'attachment; filename="datos-cliente-{cliente.pk}.zip"'
    return respuesta


def _nombre_confirmado(request, cliente) -> bool:
    escrito = " ".join(request.POST.get("confirmar_nombre", "").split()).lower()
    return escrito == " ".join(cliente.nombre_completo.split()).lower()


@require_POST
def anonimizar(request, pk):
    from apps.nucleo.decoradores import solo_propietaria

    from . import rgpd

    @solo_propietaria
    def _accion(request):
        cliente = get_object_or_404(Cliente.objects.activos(), pk=pk)
        if not _nombre_confirmado(request, cliente):
            messages.error(request, _("Escribe el nombre completo exactamente para confirmar."))
            return redirect("clientes:ficha", pk)
        nombre = cliente.nombre_completo
        rgpd.anonimizar(cliente)
        registrar(request, Accion.ANONIMIZACION, f"Ficha anonimizada (antes: {nombre[:1]}…)", objeto=cliente)
        messages.success(
            request, _("Datos personales eliminados. Se conservan importes y consentimientos en plazo legal.")
        )
        return redirect("clientes:lista")

    return _accion(request)


@require_POST
def eliminar(request, pk):
    from apps.nucleo.decoradores import solo_propietaria

    from . import rgpd

    @solo_propietaria
    def _accion(request):
        cliente = get_object_or_404(Cliente, pk=pk)
        if not _nombre_confirmado(request, cliente):
            messages.error(request, _("Escribe el nombre completo exactamente para confirmar."))
            return redirect("clientes:ficha", pk)
        if not rgpd.puede_eliminarse(cliente):
            messages.error(
                request,
                _(
                    "Tiene consentimientos firmados que la normativa obliga a conservar. Anonimiza la ficha en su lugar."
                ),
            )
            return redirect("clientes:ficha", pk)
        registrar(request, Accion.BORRADO, f"Cliente eliminado (id {cliente.pk})")
        rgpd.eliminar(cliente)
        messages.success(request, _("Cliente eliminado definitivamente."))
        return redirect("clientes:lista")

    return _accion(request)
