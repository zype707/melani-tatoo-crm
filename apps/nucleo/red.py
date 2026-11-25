from django.conf import settings


def ip_cliente(request) -> str | None:
    """IP del cliente teniendo en cuenta los proxies de confianza.

    Con N proxies de confianza, la IP real es la N-ésima empezando por la
    derecha de X-Forwarded-For (las de la izquierda las puede falsear el
    cliente). Sin proxies de confianza se usa REMOTE_ADDR.
    """
    n = settings.PROXIES_DE_CONFIANZA
    if n > 0:
        cabecera = request.META.get("HTTP_X_FORWARDED_FOR", "")
        partes = [p.strip() for p in cabecera.split(",") if p.strip()]
        if len(partes) >= n:
            return partes[-n][:45]
    return (request.META.get("REMOTE_ADDR") or None) and request.META["REMOTE_ADDR"][:45]


def user_agent(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:200]


def es_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"
