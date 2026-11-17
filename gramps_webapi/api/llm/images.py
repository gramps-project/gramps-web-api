#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Images attached to chat messages."""

from __future__ import annotations

import base64
import binascii
import io
from dataclasses import replace

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic_ai.messages import (
    BinaryContent,
    FileUrl,
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UploadedFile,
    UserPromptPart,
)

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# long edge in pixels; larger images are downscaled by most providers anyway
MAX_IMAGE_EDGE = 1568
JPEG_QUALITY = 85
IMAGE_MEDIA_TYPE = "image/jpeg"
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

OMITTED_IMAGE = "[Image omitted from history.]"

_MULTIMODAL = (BinaryContent, FileUrl, UploadedFile)


class InvalidImageError(ValueError):
    """An attached image cannot be used."""


def normalize_image(data: str) -> str:
    """Decode an attached image and re-encode it for the model.

    Accepts base64, optionally as a data URL. Returns a base64 JPEG whose long
    edge is at most MAX_IMAGE_EDGE, so every provider accepts it and it stays
    cheap to pass to a background task.
    """
    if data.startswith("data:"):
        header, separator, data = data.partition(",")
        if not separator or not header.endswith(";base64"):
            raise InvalidImageError("Images must be base64 encoded.")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise InvalidImageError("Images must be base64 encoded.") from e
    if len(raw) > MAX_IMAGE_BYTES:
        raise InvalidImageError("Image is too large.")
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format not in ALLOWED_FORMATS:
                raise InvalidImageError("Unsupported image format.")
            opened.draft("RGB", (MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))  # fast JPEG decoding
            # for an animated GIF, this is the first frame
            img: Image.Image = ImageOps.exif_transpose(opened)
            img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                rgba = img.convert("RGBA")
                img = Image.new("RGB", rgba.size, (255, 255, 255))
                img.paste(rgba, mask=rgba.getchannel("A"))
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=JPEG_QUALITY)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as e:
        raise InvalidImageError("Invalid image.") from e
    return base64.b64encode(output.getvalue()).decode()


def image_parts(images: list[str]) -> list[BinaryContent]:
    """Prompt parts for normalized images."""
    return [
        BinaryContent(data=base64.b64decode(image), media_type=IMAGE_MEDIA_TYPE)
        for image in images
    ]


def _strip_content(content):
    if isinstance(content, _MULTIMODAL):
        return OMITTED_IMAGE
    if isinstance(content, list):
        return [_strip_content(item) for item in content]
    return content


def strip_images(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Replace images and other files in the message history with a placeholder.

    Images are only sent with the turn they are attached to. Stripping them
    keeps the history small, and stops clients from sending files, or URLs
    the server would fetch, through the history.
    """
    stripped: list[ModelMessage] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            parts = [
                (
                    replace(part, content=_strip_content(part.content))
                    if isinstance(part, (UserPromptPart, ToolReturnPart))
                    else part
                )
                for part in msg.parts
            ]
            msg = replace(msg, parts=parts)
        stripped.append(msg)
    return stripped
