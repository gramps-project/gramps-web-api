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

"""Tests for PILLOW_MAX_IMAGE_PIXELS configuration and image handling"""

import io
import os
import pytest
from gramps_webapi.app import create_app
from gramps_webapi.api.image import ThumbnailHandler
from gramps_webapi.const import MIME_PDF
from PIL.Image import DecompressionBombError
from PIL import Image

from .test_endpoints.test_upload import get_image


def make_two_page_pdf(
    color1=(255, 0, 0), color2=(0, 0, 255), size=(200, 200)
) -> io.BytesIO:
    """Create a minimal 2-page PDF with distinct solid colors."""
    page1 = Image.new("RGB", size, color=color1)
    page2 = Image.new("RGB", size, color=color2)
    buf = io.BytesIO()
    page1.save(buf, format="PDF", save_all=True, append_images=[page2])
    buf.seek(0)
    return buf


def test_pdf_thumbnail_returns_first_page_only():
    """_get_image_pdf must return exactly the first page of a multi-page PDF."""
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    buf = make_two_page_pdf(color1=RED, color2=BLUE)
    handler = ThumbnailHandler(buf, MIME_PDF)
    img = handler.get_image()

    # Should be a single PIL Image, not a list
    assert isinstance(img, Image.Image)

    # Center pixel should match the first page's color, not the second's.
    # Allow ±2 tolerance for PDF/rasterization rounding.
    center = img.getpixel((img.width // 2, img.height // 2))[:3]
    assert all(
        abs(a - b) <= 2 for a, b in zip(center, RED)
    ), f"Expected first-page color {RED}, got {center}"
    assert not all(
        abs(a - b) <= 2 for a, b in zip(center, BLUE)
    ), "Got second-page color — first_page/last_page limit not working"


def test_pdf_render_size_capped():
    """Rendered PDF image must not exceed the 2000×2000 cap."""
    buf = make_two_page_pdf(size=(3000, 3000))
    handler = ThumbnailHandler(buf, MIME_PDF)
    img = handler.get_image()
    assert img.width <= 2000 and img.height <= 2000


def test_abort_if_too_large_returns_413():
    """_abort_if_too_large must raise HTTPException with code 413 when over the limit."""
    from werkzeug.exceptions import HTTPException
    from gramps_webapi.api.file import FileHandler
    from gramps_webapi.config import DefaultConfig

    class _BigFileHandler(FileHandler):
        def get_file_size(self):
            return DefaultConfig.MAX_THUMBNAIL_FILE_BYTES + 1

    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "MAX_THUMBNAIL_FILE_BYTES": DefaultConfig.MAX_THUMBNAIL_FILE_BYTES,
    }
    app = (
        create_app(  # create app for test setup of parameter PIL.Image.MAX_IMAGE_PIXELS
            config=opts,
            config_from_env=False,
        )
    )

    handler = object.__new__(_BigFileHandler)
    with app.app_context():
        with pytest.raises(HTTPException) as exc_info:
            handler._abort_if_too_large()
    assert exc_info.value.code == 413


# fixture for restoring Pillow library default config values
@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # save PIL.Image.MAX_IMAGE_PIXELS and ENV_CONFIG_FILE before tests
    saved_max_image_pixels = Image.MAX_IMAGE_PIXELS
    from gramps_webapi.const import ENV_CONFIG_FILE

    # set it to None to prevent the config from loading
    old = os.environ.pop(ENV_CONFIG_FILE, None)

    yield

    # restore
    if old:
        os.environ[ENV_CONFIG_FILE] = old
    Image.MAX_IMAGE_PIXELS = saved_max_image_pixels


def test_file_max_pillow_image_pixels_greater_or_equal():
    img, _, _ = get_image(0, 500, 500)
    fh = ThumbnailHandler(img, "image/png")

    # max image pixels greate or equal than pic -> no error
    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "PILLOW_MAX_IMAGE_PIXELS": 500 * 500,
    }
    create_app(  # create app for test setup of parameter PIL.Image.MAX_IMAGE_PIXELS
        config=opts,
        config_from_env=False,
    )
    fh.get_image()


def test_file_max_pillow_image_pixels_lower():
    width, height = 10, 10
    img, _, _ = get_image(0, width, height)
    fh = ThumbnailHandler(img, "image/png")

    # max image pixels lower than pic -> error
    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "PILLOW_MAX_IMAGE_PIXELS": width * height // 2 - 1,
        # set width*height-1=10*10-1=49 cause PIL throw warning if
        # width*height < PILLOW_MAX_IMAGE_PIXELS and
        # width*height/2 > PILLOW_MAX_IMAGE_PIXELS;
        # throw panic if width*height > PILLOW_MAX_IMAGE_PIXELS
    }
    create_app(
        config=opts,
        config_from_env=False,
    )
    with pytest.raises(DecompressionBombError):
        fh.get_image()


# Tests negative and None values of PILLOW_MAX_IMAGE_PIXELS
def test_file_max_pillow_image_pixels_incorrect():
    img, _, _ = get_image(0, 500, 500)
    fh = ThumbnailHandler(img, "image/png")
    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "PILLOW_MAX_IMAGE_PIXELS": -100,
    }
    create_app(
        config=opts,
        config_from_env=False,
    )
    with pytest.raises(DecompressionBombError):
        fh.get_image()

    opts["PILLOW_MAX_IMAGE_PIXELS"] = None
    create_app(
        config=opts,
        config_from_env=False,
    )
    with pytest.raises(DecompressionBombError):
        fh.get_image()
