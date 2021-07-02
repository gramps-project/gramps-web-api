#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Image utilities."""


import io
from pathlib import Path
from typing import BinaryIO

from pdf2image import convert_from_path
from PIL import Image, ImageOps

from gramps_webapi.const import MIME_PDF
from gramps_webapi.types import FilenameOrPath


def image_thumbnail(image: Image, size: int, square: bool = False) -> Image:
    """Return a thumbnail of `size` (longest side) for the image.

    If `square` is true, the image is cropped to a centered square.
    """
    if square:
        # don't enlarge image: square size is at most shorter (!) side's length
        size_orig = min(image.size)
        size_square = min(size_orig, size)
        return ImageOps.fit(
            image,
            (size_square, size_square),
            bleed=0.0,
            centering=(0.0, 0.5),
            method=Image.BICUBIC,
        )
    img = image.copy()
    img.thumbnail((size, size))
    return img


def image_square(image: Image) -> Image:
    """Crop an image to a centered square."""
    size = min(image.size)
    return ImageOps.fit(
        image, (size, size), bleed=0.0, centering=(0.0, 0.5), method=Image.BICUBIC,
    )


def crop_image(image: Image, x1: int, y1: int, x2: int, y2: int) -> Image:
    """Crop an image.

    The arguments `x1`, `y1`, `x2`, `y2` are the coordinates of the cropped region
    in percent.
    """
    width, height = image.size
    x1_abs = x1 * width / 100
    x2_abs = x2 * width / 100
    y1_abs = y1 * height / 100
    y2_abs = y2 * height / 100
    return image.crop((x1_abs, y1_abs, x2_abs, y2_abs))


def save_image_buffer(image: Image, fmt="JPEG") -> BinaryIO:
    """Save an image to a binary buffer."""
    buffer = io.BytesIO()
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


class ThumbnailHandler:
    """Thumbnail handler."""

    # supported MIME types that are not images
    MIME_NO_IMAGE = [MIME_PDF]

    def __init__(self, path: FilenameOrPath, mime_type: str) -> None:
        """Initialize self given a path and MIME type."""
        self.path = Path(path)
        self.mime_type = mime_type
        if self.mime_type.startswith("image/"):
            self.is_image = True
        else:
            if self.mime_type not in self.MIME_NO_IMAGE:
                raise ValueError(
                    "No thumbnailer found for MIME type {}.".format(self.mime_type)
                )
            self.is_image = False

    def get_image(self) -> Image:
        """Get a Pillow Image instance."""
        if self.mime_type == MIME_PDF:
            return self._get_image_pdf()
        return Image.open(self.path)

    def get_cropped(
        self, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ) -> BinaryIO:
        """Return a cropped version of the image at `path`.

        The arguments `x1`, `y1`, `x2`, `y2` are the coordinates of the cropped region
        in terms of the original image's coordinate system.

        If `square` is true, the image is additionally cropped to a centered square.
        """
        img = self.get_image()
        img = crop_image(img, x1, y1, x2, y2)
        if square:
            img = image_square(img)
        return save_image_buffer(img)

    def _get_image_pdf(self) -> Image:
        """Get a Pillow Image instance of the PDF's first page."""
        ims = convert_from_path(self.path, single_file=True, use_cropbox=True, dpi=100)
        return ims[0]

    def get_thumbnail(
        self, size: int, square: bool = False, fmt: str = "JPEG"
    ) -> BinaryIO:
        """Return a thumbnail of `size` (longest side) for the image.

        If `square` is true, the image is cropped to a centered square.
        """
        img = self.get_image()
        img = image_thumbnail(image=img, size=size, square=square)
        return save_image_buffer(img, fmt=fmt)

    def get_thumbnail_cropped(
        self, size: int, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ) -> BinaryIO:
        """Return a cropped thumbnail of `size` (longest side) of the image at `path`.

        The arguments `x1`, `y1`, `x2`, `y2` are the coordinates of the cropped region
        in terms of the original image's coordinate system.

        If `square` is true, the image is cropped to a centered square.
        """
        img = self.get_image()
        img = crop_image(img, x1, y1, x2, y2)
        img = image_thumbnail(image=img, size=size, square=square)
        return save_image_buffer(img)
