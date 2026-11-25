"""Validación y reprocesado de imágenes subidas.

Toda imagen que entra al sistema (fotos de clientes, referencias de la página
pública, flash, logotipo) pasa por aquí:

1. Límite de tamaño antes de leerla.
2. Firma binaria («magic bytes»): JPEG, PNG o WebP. La extensión y el
   Content-Type que manda el navegador no se usan para nada.
3. Pillow la verifica y se rechazan las «bombas de descompresión».
4. Se re-codifica desde cero a JPEG/PNG, sin EXIF (GPS, modelo de móvil...) y
   con nombre aleatorio. Un archivo malicioso disfrazado de imagen no
   sobrevive a este paso.
"""

import uuid
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELES = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELES
FORMATOS = {"JPEG", "PNG", "WEBP"}
FIRMAS = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
)
FONDO = (244, 241, 232)  # hueso, para aplanar transparencias


def _firma_valida(cabecera: bytes) -> bool:
    if any(cabecera.startswith(f) for f, _ in FIRMAS):
        return True
    return cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP"


def _abrir(archivo) -> Image.Image:
    max_bytes = settings.SUBIDAS_MAX_MB * 1024 * 1024
    if getattr(archivo, "size", 0) > max_bytes:
        raise ValidationError(f"La imagen supera {settings.SUBIDAS_MAX_MB} MB.")
    archivo.seek(0)
    if not _firma_valida(archivo.read(16)):
        raise ValidationError("Solo se aceptan imágenes JPG, PNG o WebP.")
    try:
        archivo.seek(0)
        Image.open(archivo).verify()
        archivo.seek(0)
        imagen = Image.open(archivo)
        imagen.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationError("La imagen está dañada o no es válida.") from exc
    if imagen.format not in FORMATOS:
        raise ValidationError("Solo se aceptan imágenes JPG, PNG o WebP.")
    if imagen.width * imagen.height > MAX_PIXELES:
        raise ValidationError("La imagen es demasiado grande.")
    return imagen


def _a_rgb(imagen: Image.Image) -> Image.Image:
    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode in ("RGBA", "LA", "P"):
        imagen = imagen.convert("RGBA")
        fondo = Image.new("RGB", imagen.size, FONDO)
        fondo.paste(imagen, mask=imagen.split()[-1])
        return fondo
    return imagen.convert("RGB")


def _jpeg(imagen: Image.Image, calidad: int) -> bytes:
    salida = BytesIO()
    imagen.save(salida, "JPEG", quality=calidad, optimize=True, progressive=True)
    return salida.getvalue()


def procesar_imagen(archivo, *, max_lado: int = 2560, lado_miniatura: int = 480, calidad: int = 85):
    """Devuelve (principal, miniatura) como ContentFile JPEG limpios."""
    imagen = _a_rgb(_abrir(archivo))
    imagen.thumbnail((max_lado, max_lado), Image.LANCZOS)
    miniatura = imagen.copy()
    miniatura.thumbnail((lado_miniatura, lado_miniatura), Image.LANCZOS)
    nombre = uuid.uuid4().hex
    return (
        ContentFile(_jpeg(imagen, calidad), name=f"{nombre}.jpg"),
        ContentFile(_jpeg(miniatura, 78), name=f"{nombre}_m.jpg"),
    )


def procesar_logo(archivo) -> ContentFile:
    """Logotipo: PNG cuadrado de 512 px, conservando la transparencia."""
    imagen = ImageOps.exif_transpose(_abrir(archivo)).convert("RGBA")
    imagen.thumbnail((512, 512), Image.LANCZOS)
    salida = BytesIO()
    imagen.save(salida, "PNG", optimize=True)
    return ContentFile(salida.getvalue(), name=f"logo-{uuid.uuid4().hex[:8]}.png")


def procesar_png_firma(datos: bytes) -> ContentFile:
    """Firma dibujada en el canvas (PNG). Se valida y se re-codifica."""
    archivo = BytesIO(datos)
    archivo.size = len(datos)
    imagen = _abrir(archivo)
    if imagen.format != "PNG" or imagen.width > 3000 or imagen.height > 2000:
        raise ValidationError("Firma no válida.")
    imagen = imagen.convert("RGBA")
    limpia = Image.new("RGB", imagen.size, (255, 255, 255))
    limpia.paste(imagen, mask=imagen.split()[-1])
    salida = BytesIO()
    limpia.save(salida, "PNG", optimize=True)
    return ContentFile(salida.getvalue(), name=f"firma-{uuid.uuid4().hex}.png")
