from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse
from django.urls import reverse

from apps.nucleo.red import es_htmx


class AccesoVerificadoMiddleware:
    """Todo es privado salvo las vistas marcadas con @vista_publica.

    «Privado» significa sesión iniciada Y segundo factor verificado.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(view_func, "vista_publica", False):
            return None
        user = request.user
        if user.is_authenticated and user.is_verified():
            return None
        if user.is_authenticated:
            logout(request)
        url_login = reverse(settings.LOGIN_URL)
        if es_htmx(request):
            respuesta = HttpResponse(status=401)
            respuesta["HX-Redirect"] = url_login
            return respuesta
        return redirect_to_login(request.get_full_path(), url_login)
