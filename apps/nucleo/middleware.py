class CabecerasSeguridadMiddleware:
    """Cabeceras que Django no pone por sí solo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            "Permissions-Policy",
            "camera=(self), microphone=(self), geolocation=(), payment=(), usb=(), interest-cohort=()",
        )
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and "Cache-Control" not in response:
            # Datos personales: que ningún navegador ni proxy los guarde.
            response["Cache-Control"] = "private, no-store"
        return response


class SaludMiddleware:
    """Responde /salud/ antes que nada (sin validar el Host ni redirigir a HTTPS),
    para que la comprobación de salud de Render funcione con su propia cabecera Host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/salud/" and request.method in ("GET", "HEAD"):
            from django.db import connection
            from django.http import HttpResponse

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception:
                return HttpResponse("bd no disponible", status=503, content_type="text/plain")
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
