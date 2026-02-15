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

"""Tests for the `gramps_webapi.api.file` module."""

import pytest
from gramps_webapi.app import create_app
from gramps_webapi.api.image import ThumbnailHandler
from PIL.Image import DecompressionBombError

from .test_endpoints.test_upload import get_image


def test_file_max_pillow_image_pixels_greater():
    img, _, _ = get_image(0, 500, 500)
    fh = ThumbnailHandler(img, "image/png")

    # max image pixels lower than pic -> error
    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "PILLOW_MAX_IMAGE_PIXELS": 500 * 500,
    }
    app = create_app(
        config=opts,
        config_from_env=False,
    )
    fh.get_image()


def test_file_max_pillow_image_pixels_lower():
    img, _, _ = get_image(0, 500, 500)
    fh = ThumbnailHandler(img, "image/png")

    # max image pixels lower than pic -> error
    opts = {
        "TREE": "test",
        "SECRET_KEY": "test",
        "USER_DB_URI": "sqlite:///:memory:",
        "PILLOW_MAX_IMAGE_PIXELS": 100,
    }
    app = create_app(
        config=opts,
        config_from_env=False,
    )
    with pytest.raises(DecompressionBombError):
        fh.get_image()
