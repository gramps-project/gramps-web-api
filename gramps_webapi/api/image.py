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
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable

import ffmpeg
from pdf2image import convert_from_path
from PIL import Image, ImageOps
from PIL.Image import Image as ImageType
from pkg_resources import resource_filename  # type: ignore[import-untyped]

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
    width, height = image.size
    x1_abs = x1 * width / 100
    x2_abs = x2 * width / 100
    y1_abs = y1 * height / 100
    y2_abs = y2 * height / 100
    return image.crop((x1_abs, y1_abs, x2_abs, y2_abs))


def save_image_buffer(image: ImageType, fmt="JPEG") -> BinaryIO:
    """Save an image to a binary buffer."""
    buffer = io.BytesIO()
    if image.mode != "RGB":
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

    def _get_image_pdf(self) -> ImageType:
        """Get a Pillow Image instance of the PDF's first page."""
        ims = self._apply_to_path(
            convert_from_path, single_file=True, use_cropbox=True, dpi=100
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


def detect_faces(stream: BinaryIO) -> list[tuple[float, float, float, float]]:
    """Detect faces in an image (stream) using YuNet."""
    # Read the image from the input stream
    import cv2
    import numpy as np

    file_bytes = np.asarray(bytearray(stream.read()), dtype=np.uint8)
    cv_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    assert cv_image is not None, "cv_image is None"  # for type checker

    # Load the YuNet model
    model_path = resource_filename(
        "gramps_webapi", "data/face_detection_yunet_2023mar.onnx"
    )
    face_detector = cv2.FaceDetectorYN.create(
        model_path, "", (320, 320), score_threshold=0.5
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
