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

logger = logging.getLogger(__name__)

_MEDIA_DIR = Path("media")
_DEV_PREFIX = "dev:"

# A transformation is applied on every real upload — "subida con
# transformacion" per the plan — capping catalog images to a sane display
# size regardless of what an admin uploads, without a second cropping step.
_UPLOAD_TRANSFORMATION = [{"width": 1280, "height": 1280, "crop": "limit"}, {"quality": "auto"}]

if settings.media_mode == "cloudinary":
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
else:
    logger.warning(
        "[MODO DEV] Credenciales de Cloudinary ausentes -> las imagenes se "
        "guardan en ./media/, NO se suben de verdad."
    )


def _save_to_disk(*, game_id: int, filename: str, content: bytes) -> tuple[str, str]:
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    extension = Path(filename).suffix or ".bin"
    local_name = f"{game_id}_{uuid.uuid4().hex}{extension}"
    (_MEDIA_DIR / local_name).write_bytes(content)
    logger.warning(
        "[MODO DEV] Imagen simulada para el juego %s guardada en media/%s", game_id, local_name
    )
    return f"/media/{local_name}", f"{_DEV_PREFIX}{local_name}"


def upload_image(*, game_id: int, filename: str, content: bytes) -> tuple[str, str]:
    """Uploads one catalog image and returns (url, public_id).

    `public_id` is what a later delete needs — real ones come straight
    from Cloudinary; dev-fallback ones are prefixed with "dev:" so
    `delete_image` (and anyone reading the row directly) can always tell
    which backend actually holds the file.
    """
    if settings.media_mode != "cloudinary":
        return _save_to_disk(game_id=game_id, filename=filename, content=content)

    result = cloudinary.uploader.upload(
        content,
        folder="gamevault/games",
        public_id=f"game_{game_id}_{uuid.uuid4().hex}",
        transformation=_UPLOAD_TRANSFORMATION,
    )
    return result["secure_url"], result["public_id"]


def delete_image(public_id: str) -> None:
    """Deletes the underlying asset — real Cloudinary asset, or the local
    dev-fallback file — for a GameImage row being removed.
    """
    if public_id.startswith(_DEV_PREFIX):
        local_name = public_id.removeprefix(_DEV_PREFIX)
        (_MEDIA_DIR / local_name).unlink(missing_ok=True)
        return

    cloudinary.uploader.destroy(public_id)
