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

import pytest
from gramps_webapi.app import create_app
from gramps_webapi.api.image import ThumbnailHandler
from PIL.Image import DecompressionBombError
from PIL import Image

from .test_endpoints.test_upload import get_image


# fixture for restoring Pillow library default config values
@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # save PIL.Image.MAX_IMAGE_PIXELS before tests
    saved_max_image_pixels = Image.MAX_IMAGE_PIXELS

    yield

    # restore
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
    create_app( # create app for test setup of parameter PIL.Image.MAX_IMAGE_PIXELS
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
        "PILLOW_MAX_IMAGE_PIXELS": width*height//2-1,
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
