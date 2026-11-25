import logging

from .models import RegistroAuditoria
from .red import ip_cliente, user_agent

log = logging.getLogger("estudio.auditoria")
Accion = RegistroAuditoria.Accion


def registrar(request, accion: str, descripcion: str = "", *, objeto=None, usuario=None, **datos):
    """Registra una acción sensible. Nunca debe romper la petición."""
    try:
        if usuario is None and request is not None and getattr(request, "user", None):
            usuario = request.user if request.user.is_authenticated else None
        RegistroAuditoria.objects.create(
            usuario=usuario,
            accion=accion,
            descripcion=descripcion[:255],
            objeto_tipo=objeto._meta.label_lower if objeto is not None else "",
            objeto_id=str(objeto.pk) if objeto is not None else "",
            ip=ip_cliente(request) if request is not None else None,
            user_agent=user_agent(request) if request is not None else "",
            datos=datos,
        )
    except Exception:  # pragma: no cover - la auditoría nunca bloquea
        log.exception("No se pudo registrar la auditoría (%s)", accion)
