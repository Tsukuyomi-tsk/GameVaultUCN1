"""Cloudinary integration for catalog images, with an automatic
development fallback.

Same contract as integrations/resend_client.py (see the plan's "Contrato
del fallback de terceros"):

- Activates ONLY when any of the 3 Cloudinary credentials is absent. No
  flag forces either path; the real integration is always used when
  credentials exist (`Settings.media_mode`, the single source of truth).
- Never masks a failure: if credentials are present and the Cloudinary
  call fails, the exception propagates — it does not fall back to disk.
- Is unmistakable: a startup warning, a per-upload warning, and every
  `public_id` saved in dev mode carries a "dev:" prefix so the database
  itself is honest about where the file actually lives.
- `Settings._forbid_dev_fallback_in_production` already refuses to start
  in production without real credentials, so this module never guards
  against that itself.

Dev-local files are saved under ./media/ and served by main.py's
StaticFiles mount at /media — the returned `url` is a relative path
under that mount, just like Cloudinary returns an absolute delivery URL.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import cloudinary
import cloudinary.uploader

from app.core.config import settings

# logger propio del modulo — permite filtrar/buscar estos mensajes en los
# logs por "app.integrations.cloudinary_client" en vez de por el logger raiz.
logger = logging.getLogger(__name__)

# Carpeta local donde se guardan las imagenes cuando NO hay credenciales
# reales de Cloudinary (modo desarrollo). Es una ruta relativa al directorio
# desde donde se ejecuta uvicorn (la raiz del proyecto).
_MEDIA_DIR = Path("media")
# Prefijo que se antepone al public_id cuando el archivo vive en disco local
# y no en Cloudinary — asi delete_image() sabe, solo mirando el string,
# a cual de los dos backends tiene que pedirle el borrado.
_DEV_PREFIX = "dev:"

# Transformacion que Cloudinary aplica a CADA imagen subida de verdad:
# limita el tamaño a 1280x1280 (sin recortar el contenido, solo achicando
# si excede ese maximo) y deja que Cloudinary elija la mejor calidad/peso
# automaticamente. Esto es lo que el plan pide como "subida con
# transformacion" — evita que un admin suba una foto de 8000x6000 y la
# app la sirva tal cual, pesada y sin necesidad.
_UPLOAD_TRANSFORMATION = [{"width": 1280, "height": 1280, "crop": "limit"}, {"quality": "auto"}]

# Este bloque se ejecuta UNA sola vez, cuando Python importa este archivo
# por primera vez (no cada vez que se llama a una funcion). Por eso el
# aviso de "MODO DEV" en consola aparece una sola vez al arrancar la app,
# no en cada request.
if settings.media_mode == "cloudinary":
    # Hay credenciales reales: se configura el SDK de Cloudinary una vez,
    # a nivel de modulo, para que cualquier llamada posterior a
    # cloudinary.uploader ya sepa a que cuenta subir los archivos.
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,  # fuerza URLs https en las imagenes que devuelve Cloudinary
    )
else:
    # Faltan una o mas credenciales: se deja constancia clara en el log de
    # que a partir de aca CUALQUIER subida va a caer al modo desarrollo.
    logger.warning(
        "[MODO DEV] Credenciales de Cloudinary ausentes -> las imagenes se "
        "guardan en ./media/, NO se suben de verdad."
    )


def _save_to_disk(*, game_id: int, filename: str, content: bytes) -> tuple[str, str]:
    # Crea la carpeta ./media/ si todavia no existe (parents=True crea
    # tambien carpetas intermedias si hicieran falta; exist_ok=True evita
    # que reviente si la carpeta ya estaba creada de una subida anterior).
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    # Se conserva la extension original del archivo subido (.png, .jpg...);
    # si no tiene extension reconocible, se usa ".bin" como generico.
    extension = Path(filename).suffix or ".bin"
    # Nombre de archivo unico: game_id + un identificador aleatorio (uuid4
    # en hexadecimal) + la extension. El uuid evita que dos imagenes subidas
    # para el mismo juego se pisen entre si aunque el usuario suba archivos
    # que se llamen igual (p. ej. "portada.png" dos veces).
    local_name = f"{game_id}_{uuid.uuid4().hex}{extension}"
    # Escribe el contenido crudo (bytes) del archivo directamente a disco.
    (_MEDIA_DIR / local_name).write_bytes(content)
    # Aviso en el log cada vez que se simula una subida — para que en modo
    # dev nunca se confunda con un archivo realmente subido a Cloudinary.
    logger.warning(
        "[MODO DEV] Imagen simulada para el juego %s guardada en media/%s", game_id, local_name
    )
    # Devuelve (url, public_id):
    # - la url es la ruta relativa por la que StaticFiles va a servir el
    #   archivo (montada en main.py como "/media").
    # - el public_id lleva el prefijo "dev:" para que quede grabado en la
    #   base de datos que este archivo vive en disco local, no en Cloudinary.
    return f"/media/{local_name}", f"{_DEV_PREFIX}{local_name}"


def upload_image(*, game_id: int, filename: str, content: bytes) -> tuple[str, str]:
    """Uploads one catalog image and returns (url, public_id).

    `public_id` is what a later delete needs — real ones come straight
    from Cloudinary; dev-fallback ones are prefixed with "dev:" so
    `delete_image` (and anyone reading the row directly) can always tell
    which backend actually holds the file.
    """
    # Si no hay credenciales reales, se delega todo el trabajo a la funcion
    # que guarda en disco local y se corta la ejecucion aca mismo (return).
    if settings.media_mode != "cloudinary":
        return _save_to_disk(game_id=game_id, filename=filename, content=content)

    # Camino real: se le pide a Cloudinary que suba el archivo.
    # - content: los bytes crudos de la imagen (Cloudinary tambien acepta
    #   una URL o un path de archivo, pero aca siempre se le pasan bytes).
    # - folder: organiza las imagenes de este proyecto dentro de una
    #   carpeta propia en la cuenta de Cloudinary, para no mezclarlas con
    #   otros usos de la misma cuenta.
    # - public_id: el identificador propio que va a tener el archivo del
    #   lado de Cloudinary — se arma a mano (en vez de dejar que Cloudinary
    #   invente uno) para que sea legible y quede asociado al juego.
    # - transformation: aplica el resize/calidad definido arriba.
    result = cloudinary.uploader.upload(
        content,
        folder="gamevault/games",
        public_id=f"game_{game_id}_{uuid.uuid4().hex}",
        transformation=_UPLOAD_TRANSFORMATION,
    )
    # Cloudinary devuelve un diccionario grande con metadata; solo nos
    # interesan la URL segura (https) del archivo ya transformado y el
    # public_id real que Cloudinary le asigno (deberia coincidir con el
    # que mandamos, pero se lee de la respuesta por las dudas).
    return result["secure_url"], result["public_id"]


def delete_image(public_id: str) -> None:
    """Deletes the underlying asset — real Cloudinary asset, or the local
    dev-fallback file — for a GameImage row being removed.
    """
    # Si el public_id tiene el prefijo "dev:", el archivo vive en disco
    # local, no en Cloudinary — hay que borrarlo a mano del filesystem.
    if public_id.startswith(_DEV_PREFIX):
        # Se le quita el prefijo "dev:" para recuperar el nombre real del
        # archivo dentro de la carpeta media/.
        local_name = public_id.removeprefix(_DEV_PREFIX)
        # unlink borra el archivo; missing_ok=True evita que reviente si
        # el archivo ya no existiera por algun motivo (p. ej. borrado a
        # mano, o llamado dos veces por error) — borrar algo que ya no
        # esta no deberia ser un error fatal aca.
        (_MEDIA_DIR / local_name).unlink(missing_ok=True)
        return

    # Camino real: se le pide a Cloudinary que destruya (borre) el asset
    # identificado por ese public_id. Si el public_id no existe del lado
    # de Cloudinary, el SDK no revienta — Cloudinary simplemente responde
    # que no encontro nada que borrar.
    cloudinary.uploader.destroy(public_id)
