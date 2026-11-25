"""Proveedor de IA (OpenAI, Responses API). Solo se llama desde el servidor.

La interfaz `Proveedor` permite cambiar de proveedor escribiendo otro
adaptador con los mismos dos métodos.
"""

import json
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


class ErrorIA(Exception):
    """Error con un mensaje apto para mostrar a la usuaria."""

    codigo = "error"

    def __init__(self, mensaje: str, codigo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        if codigo:
            self.codigo = codigo


@dataclass
class Resultado:
    texto: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


class Proveedor(Protocol):
    def texto(self, instrucciones: str, entrada: str, max_tokens: int = 600) -> Resultado: ...

    def json(
        self, instrucciones: str, entrada: str, nombre: str, esquema: dict, max_tokens: int = 900
    ) -> tuple[dict, Resultado]: ...


class ProveedorOpenAI:
    def __init__(self):
        from openai import OpenAI

        self.cliente = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.IA_TIMEOUT_SEGUNDOS, max_retries=1)

    def _llamar(self, instrucciones, entrada, max_tokens, formato=None) -> Resultado:
        import openai

        argumentos = {
            "model": settings.IA_MODELO,
            "instructions": instrucciones,
            "input": entrada,
            "max_output_tokens": max_tokens,
            "store": False,  # que OpenAI no conserve la conversación
        }
        if formato:
            argumentos["text"] = {"format": formato}
        try:
            r = self.cliente.responses.create(**argumentos)
        except openai.APITimeoutError as exc:
            raise ErrorIA("La IA ha tardado demasiado. Inténtalo de nuevo en un momento.", "timeout") from exc
        except openai.AuthenticationError as exc:
            raise ErrorIA("La clave de OpenAI no es válida. Revisa OPENAI_API_KEY.", "auth") from exc
        except openai.NotFoundError as exc:
            raise ErrorIA(f"El modelo «{settings.IA_MODELO}» no está disponible. Revisa IA_MODELO.", "modelo") from exc
        except openai.RateLimitError as exc:
            raise ErrorIA("OpenAI rechazó la petición por límite de uso o saldo. Revisa tu cuenta.", "limite") from exc
        except openai.APIConnectionError as exc:
            raise ErrorIA("No hay conexión con OpenAI ahora mismo.", "conexion") from exc
        except openai.APIError as exc:
            raise ErrorIA("La IA devolvió un error. Prueba otra vez más tarde.", "api") from exc
        uso = getattr(r, "usage", None)
        return Resultado(
            texto=(r.output_text or "").strip(),
            tokens_entrada=getattr(uso, "input_tokens", 0) or 0,
            tokens_salida=getattr(uso, "output_tokens", 0) or 0,
        )

    def texto(self, instrucciones, entrada, max_tokens=600) -> Resultado:
        return self._llamar(instrucciones, entrada, max_tokens)

    def json(self, instrucciones, entrada, nombre, esquema, max_tokens=900):
        formato = {"type": "json_schema", "name": nombre, "schema": esquema, "strict": True}
        resultado = self._llamar(instrucciones, entrada, max_tokens, formato)
        try:
            return json.loads(resultado.texto), resultado
        except json.JSONDecodeError as exc:
            raise ErrorIA("La IA devolvió una respuesta que no se pudo interpretar.", "formato") from exc


_proveedor_pruebas: Proveedor | None = None


def obtener() -> Proveedor:
    if _proveedor_pruebas is not None:
        return _proveedor_pruebas
    if not settings.OPENAI_API_KEY:
        raise ErrorIA("La IA no está configurada (falta OPENAI_API_KEY).", "no_configurada")
    return ProveedorOpenAI()
