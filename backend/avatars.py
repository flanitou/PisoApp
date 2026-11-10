"""Private, re-encoded profile pictures using Silence session authentication."""

from io import BytesIO
import logging
import os
from pathlib import Path
import re
from uuid import uuid4
import warnings

from flask import jsonify, request, send_file
from PIL import Image, ImageOps
from silence.exceptions import HTTPError

from api import authenticated, database, one


AVATAR_DIR = Path(os.environ.get("AVATAR_DIR", "/app/media/avatars"))
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 9_000_000
IMAGE_SIZE = (256, 256)
SAFE_FILENAME = re.compile(r"[a-f0-9]{32}\.webp\Z")
logger = logging.getLogger(__name__)


def encode_avatar(upload):
    raw = upload.stream.read(MAX_UPLOAD_BYTES + 1)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPError(413, "La foto debe ocupar como máximo 2 MB")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPError(400, "Usa una imagen JPG, PNG o WebP")
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise HTTPError(413, "La imagen tiene demasiados píxeles")
                original.load()
                image = ImageOps.fit(
                    ImageOps.exif_transpose(original).convert("RGBA"),
                    IMAGE_SIZE,
                    method=Image.Resampling.LANCZOS,
                )
                output = BytesIO()
                image.save(output, format="WEBP", quality=85, method=6)
                return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPError(413, "La imagen tiene demasiados píxeles") from exc
    except (OSError, ValueError) as exc:
        raise HTTPError(400, "El archivo no es una imagen válida") from exc


def remove_old(filename):
    if filename and SAFE_FILENAME.fullmatch(filename):
        try:
            (AVATAR_DIR / filename).unlink(missing_ok=True)
        except OSError:
            logger.warning("No se ha podido borrar un avatar anterior")


def register_avatar_routes(app):
    @app.get("/api/users/me")
    @authenticated
    def my_profile(user):
        with database() as cursor:
            profile = one(
                cursor,
                "SELECT u.user_id, u.username, u.role, (a.filename IS NOT NULL) AS has_avatar "
                "FROM users u LEFT JOIN user_avatars a ON a.user_id=u.user_id WHERE u.user_id=%s",
                (user["user_id"],),
            )
        return jsonify(profile)

    @app.get("/api/users/<int:profile_id>/avatar")
    @authenticated
    def get_avatar(user, profile_id):
        with database() as cursor:
            row = one(cursor, "SELECT filename FROM user_avatars WHERE user_id=%s", (profile_id,))
        if not row or not SAFE_FILENAME.fullmatch(row["filename"]):
            raise HTTPError(404, "Este usuario no tiene foto de perfil")
        avatar = AVATAR_DIR / row["filename"]
        if not avatar.is_file():
            raise HTTPError(404, "Foto de perfil no disponible")
        response = send_file(avatar, mimetype="image/webp", conditional=False)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.post("/api/users/me/avatar")
    @authenticated
    def upload_avatar(user):
        if request.content_length and request.content_length > MAX_UPLOAD_BYTES + 200_000:
            raise HTTPError(413, "La foto debe ocupar como máximo 2 MB")
        upload = request.files.get("avatar")
        if upload is None:
            raise HTTPError(400, "Envía la foto en el campo avatar")
        encoded = encode_avatar(upload)

        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.webp"
        path = AVATAR_DIR / filename
        with path.open("xb") as file:
            file.write(encoded)

        try:
            with database() as cursor:
                previous = one(cursor, "SELECT filename FROM user_avatars WHERE user_id=%s FOR UPDATE", (user["user_id"],))
                cursor.execute(
                    "INSERT INTO user_avatars (user_id, filename) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE filename=VALUES(filename)",
                    (user["user_id"], filename),
                )
        except Exception:
            path.unlink(missing_ok=True)
            raise

        remove_old(previous["filename"] if previous else None)
        return jsonify({"user_id": user["user_id"], "has_avatar": True}), 200

    @app.delete("/api/users/me/avatar")
    @authenticated
    def delete_avatar(user):
        with database() as cursor:
            previous = one(cursor, "SELECT filename FROM user_avatars WHERE user_id=%s FOR UPDATE", (user["user_id"],))
            if previous:
                cursor.execute("DELETE FROM user_avatars WHERE user_id=%s", (user["user_id"],))
        remove_old(previous["filename"] if previous else None)
        return "", 204
