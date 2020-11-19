#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the file and thumbnail endpoints using example_gramps."""

import unittest
from io import BytesIO

from PIL import Image

from gramps_webapi.const import MIME_JPEG

from . import get_test_client


class TestFile(unittest.TestCase):
    """Test cases for the /api/media/{}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_file_endpoint(self):
        """Test reponse for files."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        assert len(media_objects) == 7
        for obj in media_objects:
            rv = self.client.get("/api/media/{}/file".format(obj["handle"]))
            assert rv.mimetype == obj["mime"]


class TestThumbnail(unittest.TestCase):
    """Test cases for the /api/media/{}/thumbnail endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_thumbnail_endpoint_small(self):
        """Test reponse for thumbnails."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            rv = self.client.get("/api/media/{}/thumbnail/20".format(obj["handle"]))
            assert rv.mimetype == MIME_JPEG
            img = Image.open(BytesIO(rv.data))
            # long side should be 20 px
            assert max(img.width, img.height) == 20

    def test_thumbnail_endpoint_square(self):
        """Test reponse for square thumbnails."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            rv = self.client.get(
                "/api/media/{}/thumbnail/20?square=1".format(obj["handle"])
            )
            # should be small & square
            img = Image.open(BytesIO(rv.data))
            assert img.width == 20
            assert img.height == 20

    def test_thumbnail_endpoint_large(self):
        """Test reponse for thumbnails (large)."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            # large thumb: return original image size
            rv = self.client.get("/api/media/{}/file".format(obj["handle"]))
            full_img = Image.open(BytesIO(rv.data))
            rv = self.client.get("/api/media/{}/thumbnail/10000".format(obj["handle"]))
            thumb = Image.open(BytesIO(rv.data))
            assert full_img.width == thumb.width
            assert full_img.height == thumb.height
            # large square thumb: return cropped original image size
            rv = self.client.get(
                "/api/media/{}/thumbnail/10000?square=1".format(obj["handle"])
            )
            thumb = Image.open(BytesIO(rv.data))
            assert thumb.width == thumb.height
            assert min(full_img.width, full_img.height) == thumb.height


class TestCropped(unittest.TestCase):
    """Test cases for the /api/media/{}/cropped endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_cropped_endpoint(self):
        """Test reponse for cropped image."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            rv = self.client.get("/api/media/{}/file".format(obj["handle"]))
            full_img = Image.open(BytesIO(rv.data))
            rv = self.client.get(
                "/api/media/{}/cropped/10/80/20/100".format(obj["handle"])
            )
            assert rv.mimetype == MIME_JPEG
            img = Image.open(BytesIO(rv.data))
            # allow 1 px difference due to rounding
            self.assertAlmostEqual(img.width, 0.1 * full_img.width, delta=1)
            self.assertAlmostEqual(img.height, 0.2 * full_img.height, delta=1)


class TestCroppedThumbnail(unittest.TestCase):
    """Test cases for the /api/media/{}/cropped/thumbnail endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_thumbnail_endpoint_small(self):
        """Test reponse for thumbnails."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            rv = self.client.get(
                "/api/media/{}/cropped/10/10/90/90/thumbnail/20".format(obj["handle"])
            )
            assert rv.mimetype == MIME_JPEG
            img = Image.open(BytesIO(rv.data))
            # long side should be 20 px
            assert max(img.width, img.height) == 20

    def test_thumbnail_endpoint_square(self):
        """Test reponse for square thumbnails."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            rv = self.client.get(
                "/api/media/{}/cropped/10/10/90/90/thumbnail/20?square=1".format(
                    obj["handle"]
                )
            )
            # should be small & square
            img = Image.open(BytesIO(rv.data))
            assert img.width == 20
            assert img.height == 20

    def test_thumbnail_endpoint_large(self):
        """Test reponse for thumbnails (large)."""
        # get all media handles
        media_objects = self.client.get("/api/media/").json
        for obj in media_objects:
            # large thumb: return original image size
            rv = self.client.get(
                "/api/media/{}/cropped/10/10/90/90".format(obj["handle"])
            )
            full_img = Image.open(BytesIO(rv.data))
            rv = self.client.get(
                "/api/media/{}/cropped/10/10/90/90/thumbnail/10000".format(
                    obj["handle"]
                )
            )
            thumb = Image.open(BytesIO(rv.data))
            assert full_img.width == thumb.width
            assert full_img.height == thumb.height
            # large square thumb: return cropped original image size
            rv = self.client.get(
                "/api/media/{}/cropped/10/10/90/90/thumbnail/10000?square=1".format(
                    obj["handle"]
                )
            )
            thumb = Image.open(BytesIO(rv.data))
            assert thumb.width == thumb.height
            assert min(full_img.width, full_img.height) == thumb.height
