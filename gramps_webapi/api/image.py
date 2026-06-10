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
import math
import os
import shutil
import tempfile
from importlib.resources import as_file, files
from pathlib import Path
from typing import BinaryIO, Callable

import ffmpeg
from pdf2image import convert_from_path
from PIL import Image, ImageOps
from PIL.Image import Image as ImageType

from gramps_webapi.const import MIME_PDF
from gramps_webapi.types import FilenameOrPath

from .util import abort_with_message


def image_thumbnail(image: ImageType, size: int, square: bool = False) -> ImageType:
    """Return a thumbnail of `size` (longest side) for the image.

    If `square` is true, the image is cropped to a centered square.
    """
    img = ImageOps.exif_transpose(image)
    assert img is not None, "img is None"  # for type checker. Can't happen in practice.
    if square:
        # don't enlarge image: square size is at most shorter (!) side's length
        size_orig = min(img.size)
        size_square = min(size_orig, size)
        return ImageOps.fit(
            img,
            (size_square, size_square),
            bleed=0.0,
            centering=(0.5, 0.5),
            method=Image.Resampling.BICUBIC,
        )
    img.thumbnail((size, size))
    return img


def image_square(image: ImageType) -> ImageType:
    """Crop an image to a centered square."""
    size = min(image.size)
    return ImageOps.fit(
        image,
        (size, size),
        bleed=0.0,
        centering=(0.0, 0.5),
        method=Image.Resampling.BICUBIC,
    )


def crop_image(image: ImageType, x1: int, y1: int, x2: int, y2: int) -> ImageType:
    """Crop an image.

    The arguments `x1`, `y1`, `x2`, `y2` are the coordinates of the cropped region
    in percent.
    """
    # Apply EXIF orientation before cropping so that the percentage coordinates
    # (which are defined in display/viewing space) map to the correct pixels.
    image = ImageOps.exif_transpose(image)
    assert image is not None  # for type checker
    width, height = image.size
    x1_abs = x1 * width / 100
    x2_abs = x2 * width / 100
    y1_abs = y1 * height / 100
    y2_abs = y2 * height / 100
    return image.crop((x1_abs, y1_abs, x2_abs, y2_abs))


def save_image_buffer(image: ImageType, fmt="AVIF") -> BinaryIO:
    """Save an image to a binary buffer."""
    buffer = io.BytesIO()
    supports_alpha = fmt.upper() in ("AVIF", "PNG", "WEBP")
    if image.mode == "RGBA" and not supports_alpha:
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    image.save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


class ThumbnailHandler:
    """Generic thumbnail handler."""

    # supported MIME types that are not images
    MIME_NO_IMAGE = [MIME_PDF]

    def __init__(self, stream: BinaryIO, mime_type: str) -> None:
        """Initialize self given a binary stream and MIME type."""
        self.stream = stream
        self.mime_type = mime_type
        if self.mime_type.startswith("image/"):
            self.is_image = True
            self.is_video = False
        elif self.mime_type.startswith("video/"):
            self.is_image = False
            self.is_video = True
        else:
            if self.mime_type not in self.MIME_NO_IMAGE:
                raise ValueError(
                    "No thumbnailer found for MIME type {}.".format(self.mime_type)
                )
            self.is_image = False
            self.is_video = False

    def get_image(self) -> ImageType:
        """Get a Pillow Image instance."""
        if self.mime_type == MIME_PDF:
            return self._get_image_pdf()
        if self.is_video:
            return self._get_image_video()
        return Image.open(self.stream)

    def get_cropped(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        square: bool = False,
        fmt: str = "AVIF",
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
        return save_image_buffer(img, fmt=fmt)

    def _get_image_pdf(self) -> ImageType:
        """Get a Pillow Image instance of the PDF's first page."""
        ims = self._apply_to_path(
            convert_from_path,
            first_page=1,
            last_page=1,
            use_cropbox=True,
            dpi=100,
            size=(2000, 2000),
        )
        return ims[0]

    def _apply_to_path(self, func: Callable, *args, **kwargs):
        """Apply a function to a file path instead of the buffer.

        The first argument of the callable f must be the file path.
        """
        fh, temp_filename = tempfile.mkstemp()
        try:
            with open(temp_filename, "wb") as f:
                shutil.copyfileobj(self.stream, f, length=131072)
                f.flush()
                output = func(temp_filename, *args, **kwargs)
        finally:
            os.close(fh)
            os.remove(temp_filename)
        return output

    def _get_image_video(self) -> ImageType:
        """Get a Pillow Image instance of the video's first frame."""
        out, _ = self._apply_to_path(
            lambda path: (
                ffmpeg.input(path, ss=0)
                .output("pipe:", format="image2", pix_fmt="rgb24", vframes=1)
                .run(capture_stdout=True, capture_stderr=True)
            )
        )
        return Image.open(io.BytesIO(out))

    def get_thumbnail(
        self, size: int, square: bool = False, fmt: str = "AVIF"
    ) -> BinaryIO:
        """Return a thumbnail of `size` (longest side) for the image.

        If `square` is true, the image is cropped to a centered square.
        """
        img = self.get_image()
        img = image_thumbnail(image=img, size=size, square=square)
        return save_image_buffer(img, fmt=fmt)

    def get_thumbnail_cropped(
        self,
        size: int,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        square: bool = False,
        fmt: str = "AVIF",
    ) -> BinaryIO:
        """Return a cropped thumbnail of `size` (longest side) of the image at `path`.

        The arguments `x1`, `y1`, `x2`, `y2` are the coordinates of the cropped region
        in terms of the original image's coordinate system.

        If `square` is true, the image is cropped to a centered square.
        """
        img = self.get_image()
        img = crop_image(img, x1, y1, x2, y2)
        img = image_thumbnail(image=img, size=size, square=square)
        return save_image_buffer(img, fmt=fmt)


class LocalFileThumbnailHandler(ThumbnailHandler):
    """Thumbnail handler for local files."""

    def __init__(self, path: FilenameOrPath, mime_type: str) -> None:
        """Initialize self given a path and MIME type."""
        self.path = Path(path)
        try:
            with open(self.path, "rb") as f:
                stream = io.BytesIO(f.read())
        except FileNotFoundError:
            abort_with_message(404, "Media file not found")
        super().__init__(stream=stream, mime_type=mime_type)


def _tile_bounds_lonlat(z: int, x: int, y: int) -> tuple:
    """Return (lon_min, lat_min, lon_max, lat_max) for an XYZ slippy map tile."""
    n = 2**z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon_min, lat_min, lon_max, lat_max


def _lat_to_tile_pixel_y(lat: float, z: int, y_tile: int, tile_size: int = 256) -> float:
    """Convert latitude to pixel y within a slippy map tile (Web Mercator)."""
    lat_rad = math.radians(lat)
    y_merc = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0
    return y_merc * (2**z) * tile_size - y_tile * tile_size


def transparent_png_tile(tile_size: int = 256) -> BinaryIO:
    """Return a buffer containing a fully transparent RGBA PNG tile."""
    return save_image_buffer(Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0)), fmt="PNG")


def get_map_tile(
    image: ImageType,
    bounds: list,
    z: int,
    x: int,
    y: int,
    tile_size: int = 256,
) -> BinaryIO:
    """Return a 256×256 RGBA PNG map tile for a georeferenced image.

    bounds: [[lat_min, lon_min], [lat_max, lon_max]]
    Source image assumed equirectangular (linear lat/lon → pixel).
    Destination tile uses Web Mercator for correct geographic placement.
    """
    image = ImageOps.exif_transpose(image)
    assert image is not None

    img_lat_min, img_lon_min = bounds[0]
    img_lat_max, img_lon_max = bounds[1]
    img_width, img_height = image.size

    tile_lon_min, tile_lat_min, tile_lon_max, tile_lat_max = _tile_bounds_lonlat(z, x, y)

    ov_lon_min = max(img_lon_min, tile_lon_min)
    ov_lon_max = min(img_lon_max, tile_lon_max)
    ov_lat_min = max(img_lat_min, tile_lat_min)
    ov_lat_max = min(img_lat_max, tile_lat_max)

    tile_img = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))

    if ov_lon_min >= ov_lon_max or ov_lat_min >= ov_lat_max:
        return save_image_buffer(tile_img, fmt="PNG")

    # Source pixels: linear equirectangular mapping
    lon_span = img_lon_max - img_lon_min
    lat_span = img_lat_max - img_lat_min
    src_x1 = (ov_lon_min - img_lon_min) / lon_span * img_width
    src_x2 = (ov_lon_max - img_lon_min) / lon_span * img_width
    # y=0 is top (lat_max), y=height is bottom (lat_min)
    src_y1 = (img_lat_max - ov_lat_max) / lat_span * img_height
    src_y2 = (img_lat_max - ov_lat_min) / lat_span * img_height

    # Destination pixels: Mercator-correct placement within the tile
    tile_lon_span = tile_lon_max - tile_lon_min
    dst_x1 = round((ov_lon_min - tile_lon_min) / tile_lon_span * tile_size)
    dst_x2 = round((ov_lon_max - tile_lon_min) / tile_lon_span * tile_size)
    dst_y1 = round(_lat_to_tile_pixel_y(ov_lat_max, z, y, tile_size))
    dst_y2 = round(_lat_to_tile_pixel_y(ov_lat_min, z, y, tile_size))

    dst_w = dst_x2 - dst_x1
    dst_h = dst_y2 - dst_y1
    if dst_w <= 0 or dst_h <= 0:
        return save_image_buffer(tile_img, fmt="PNG")

    crop = image.crop((src_x1, src_y1, src_x2, src_y2))
    if crop.mode != "RGBA":
        crop = crop.convert("RGBA")
    crop = crop.resize((dst_w, dst_h), Image.Resampling.LANCZOS)
    tile_img.paste(crop, (dst_x1, dst_y1), crop)

    return save_image_buffer(tile_img, fmt="PNG")


def detect_faces(stream: BinaryIO) -> list[tuple[float, float, float, float]]:
    """Detect faces in an image (stream) using YuNet."""
    # Read the image from the input stream
    import cv2
    import numpy as np

    file_bytes = np.asarray(bytearray(stream.read()), dtype=np.uint8)
    cv_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    assert cv_image is not None, "cv_image is None"  # for type checker

    # Load the YuNet model
    ref = files("gramps_webapi") / "data/face_detection_yunet_2023mar.onnx"
    with as_file(ref) as model_path:
        face_detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold=0.5
        )

    # Set input image size for YuNet
    height, width, _ = cv_image.shape
    face_detector.setInputSize((width, height))

    # Detect faces
    faces = face_detector.detect(cv_image)

    # Check if any faces are detected
    if faces[1] is None:
        return []

    # Extract and normalize face bounding boxes
    detected_faces = []
    for face in faces[1]:
        x, y, w, h = map(float, np.asarray(face)[:4])
        detected_faces.append(
            (
                100 * x / width,
                100 * y / height,
                100 * (x + w) / width,
                100 * (y + h) / height,
            )
        )

    return detected_faces
