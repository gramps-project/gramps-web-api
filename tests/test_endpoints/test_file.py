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

"""Tests for the file and thumbnail endpoints using example_gramps."""

import unittest
from io import BytesIO

from PIL import Image

from gramps_webapi.const import MIME_AVIF

from . import BASE_URL, get_test_client
from .checks import check_requires_token, check_success
from .util import fetch_header

TEST_URL = BASE_URL + "/media/"


class TestFile(unittest.TestCase):
    """Test cases for the /api/media/{}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_file_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "b39fe1cfc1305ac4a21/file")

    def test_get_file_endpoint(self):
        """Test reponse for files."""
        media_objects = check_success(self, TEST_URL)
        assert len(media_objects) == 7
        for obj in media_objects:
            rv = check_success(
                self, "{}{}/file".format(TEST_URL, obj["handle"]), full=True
            )
            assert rv.mimetype == obj["mime"]


class TestThumbnail(unittest.TestCase):
    """Test cases for the /api/media/{}/thumbnail endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_thumbnail_small_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "b39fe1cfc1305ac4a21/thumbnail/20")

    def test_get_thumbnail_small(self):
        """Test reponse for thumbnails."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self, "{}{}/thumbnail/20".format(TEST_URL, obj["handle"]), full=True
            )
            assert rv.mimetype == MIME_AVIF
            img = Image.open(BytesIO(rv.data))
            assert img.format == "AVIF"
            # long side should be 20 px
            assert max(img.width, img.height) == 20

    def test_get_thumbnail_square(self):
        """Test reponse for square thumbnails."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self,
                "{}{}/thumbnail/20?square=1".format(TEST_URL, obj["handle"]),
                full=True,
            )
            # should be small & square
            img = Image.open(BytesIO(rv.data))
            assert img.width == 20
            assert img.height == 20

    def test_get_thumbnail_with_checksum(self):
        """Test that the checksum query param is accepted and does not alter the response."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self, "{}{}/thumbnail/20".format(TEST_URL, obj["handle"]), full=True
            )
            rv_checksum = check_success(
                self,
                "{}{}/thumbnail/20?checksum=abc123".format(TEST_URL, obj["handle"]),
                full=True,
            )
            assert rv.data == rv_checksum.data

    def test_get_thumbnail_large_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "b39fe1cfc1305ac4a21/thumbnail/10000")

    def test_get_thumbnail_large(self):
        """Test reponse for thumbnails (large)."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            # large thumb: return original image size
            rv = check_success(
                self, "{}{}/file".format(TEST_URL, obj["handle"]), full=True
            )
            full_img = Image.open(BytesIO(rv.data))
            rv = check_success(
                self, "{}{}/thumbnail/10000".format(TEST_URL, obj["handle"]), full=True
            )
            thumb = Image.open(BytesIO(rv.data))
            assert full_img.width == thumb.width
            assert full_img.height == thumb.height
            # large square thumb: return cropped original image size
            rv = check_success(
                self,
                "{}{}/thumbnail/10000?square=1".format(TEST_URL, obj["handle"]),
                full=True,
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

    def test_get_cropped_requires_token(self):
        """Test authorization required."""
        check_requires_token(
            self, TEST_URL + "b39fe1cfc1305ac4a21/cropped/10/80/20/100"
        )

    def test_get_cropped(self):
        """Test reponse for cropped image."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self, "{}{}/file".format(TEST_URL, obj["handle"]), full=True
            )
            full_img = Image.open(BytesIO(rv.data))
            rv = check_success(
                self,
                "{}{}/cropped/10/80/20/100".format(TEST_URL, obj["handle"]),
                full=True,
            )
            assert rv.mimetype == MIME_AVIF
            img = Image.open(BytesIO(rv.data))
            assert img.format == "AVIF"
            # allow 1 px difference due to rounding
            self.assertAlmostEqual(img.width, 0.1 * full_img.width, delta=1)
            self.assertAlmostEqual(img.height, 0.2 * full_img.height, delta=1)

    def test_get_cropped_with_checksum(self):
        """Test that the checksum query param is accepted and does not alter the response."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self,
                "{}{}/cropped/10/80/20/100".format(TEST_URL, obj["handle"]),
                full=True,
            )
            rv_checksum = check_success(
                self,
                "{}{}/cropped/10/80/20/100?checksum=abc123".format(
                    TEST_URL, obj["handle"]
                ),
                full=True,
            )
            assert rv.data == rv_checksum.data


class TestCroppedThumbnail(unittest.TestCase):
    """Test cases for the /api/media/{}/cropped/thumbnail endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_cropped_thumbnail_small_requires_token(self):
        """Test authorization required."""
        check_requires_token(
            self, TEST_URL + "b39fe1cfc1305ac4a21/cropped/10/10/90/90/thumbnail/20"
        )

    def test_get_cropped_thumbnail_small(self):
        """Test reponse for thumbnails."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/20".format(TEST_URL, obj["handle"]),
                full=True,
            )
            assert rv.mimetype == MIME_AVIF
            img = Image.open(BytesIO(rv.data))
            assert img.format == "AVIF"
            # long side should be 20 px
            assert max(img.width, img.height) == 20

    def test_get_cropped_thumbnail_square(self):
        """Test reponse for square thumbnails."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/20?square=1".format(
                    TEST_URL, obj["handle"]
                ),
                full=True,
            )
            # should be small & square
            img = Image.open(BytesIO(rv.data))
            assert img.width == 20
            assert img.height == 20

    def test_get_cropped_thumbnail_with_checksum(self):
        """Test that the checksum query param is accepted and does not alter the response."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/20".format(TEST_URL, obj["handle"]),
                full=True,
            )
            rv_checksum = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/20?checksum=abc123".format(
                    TEST_URL, obj["handle"]
                ),
                full=True,
            )
            assert rv.data == rv_checksum.data

    def test_get_cropped_thumbnail_large_requires_token(self):
        """Test authorization required."""
        check_requires_token(
            self, TEST_URL + "b39fe1cfc1305ac4a21/cropped/10/10/90/90/thumbnail/10000"
        )

    def test_get_cropped_thumbnail_large(self):
        """Test reponse for thumbnails (large)."""
        media_objects = check_success(self, TEST_URL)
        for obj in media_objects:
            # large thumb: return original image size
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90".format(TEST_URL, obj["handle"]),
                full=True,
            )
            full_img = Image.open(BytesIO(rv.data))
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/10000".format(
                    TEST_URL, obj["handle"]
                ),
                full=True,
            )
            thumb = Image.open(BytesIO(rv.data))
            assert full_img.width == thumb.width
            assert full_img.height == thumb.height
            # large square thumb: return cropped original image size
            rv = check_success(
                self,
                "{}{}/cropped/10/10/90/90/thumbnail/10000?square=1".format(
                    TEST_URL, obj["handle"]
                ),
                full=True,
            )
            thumb = Image.open(BytesIO(rv.data))
            assert thumb.width == thumb.height
            assert min(full_img.width, full_img.height) == thumb.height


class TestMapTile(unittest.TestCase):
    """Test cases for the /api/media/{}/tile endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_map_tile_requires_token(self):
        """Test that unauthenticated request returns 401 and authenticated request is reachable."""
        rv = self.client.get(TEST_URL + "b39fe1cfc1305ac4a21/tile/5/16/11")
        self.assertEqual(rv.status_code, 401)
        # With auth the endpoint must be reachable (404 expected — no map:bounds on this object)
        header = fetch_header(self.client)
        rv = self.client.get(TEST_URL + "b39fe1cfc1305ac4a21/tile/5/16/11", headers=header)
        self.assertNotEqual(rv.status_code, 500)

    def test_get_map_tile_no_bounds_returns_404(self):
        """Media without map:bounds attribute returns 404."""
        media_objects = check_success(self, TEST_URL)
        header = fetch_header(self.client)
        for obj in media_objects:
            rv = self.client.get(
                f"{TEST_URL}{obj['handle']}/tile/5/16/11",
                headers=header,
            )
            self.assertEqual(rv.status_code, 404)

    def test_get_map_tile_max_zoom_returns_transparent_png(self):
        """When z > max_zoom, endpoint returns 200 with a transparent 256×256 PNG."""
        header = fetch_header(self.client)
        # z=10 > max_zoom=5: short-circuits before checking bounds, so any handle works
        rv = self.client.get(
            f"{TEST_URL}b39fe1cfc1305ac4a21/tile/10/512/341?max_zoom=5",
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.mimetype, "image/png")
        img = Image.open(BytesIO(rv.data))
        self.assertEqual(img.size, (256, 256))
        self.assertTrue(all(p[3] == 0 for p in img.getdata()))

    def test_get_map_tile_invalid_z_returns_400(self):
        """Negative or out-of-range z returns 400."""
        header = fetch_header(self.client)
        for bad_z in ("tile/-1/0/0", "tile/29/0/0"):
            rv = self.client.get(
                f"{TEST_URL}b39fe1cfc1305ac4a21/{bad_z}",
                headers=header,
            )
            self.assertEqual(rv.status_code, 400)


class TestFaceDetection(unittest.TestCase):
    """Test cases for the /api/media/{}/face_detection endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_faces_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "b39fe1cfc1305ac4a21/face_detection")

    def test_get_faces(self):
        """Test reponse for face detection."""
        rv = check_success(
            self,
            f"{TEST_URL}F8JYGQFL2PKLSYH79X/face_detection",
            full=True,
        )
        faces = rv.json
        assert len(faces) == 1
        x1, y1, x2, y2 = faces[0]
        assert 20 < x1 < 70
        assert 50 < x2 < 80
        assert 0 < y1 < 20
        assert 20 < y2 < 60
        assert x2 > x1
        assert y2 > y1
