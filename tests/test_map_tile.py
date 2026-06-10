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

"""Unit tests for map tile generation."""

import unittest

from PIL import Image

from gramps_webapi.api.image import (
    _lat_to_tile_pixel_y,
    _tile_bounds_lonlat,
    get_map_tile,
    transparent_png_tile,
)


class TestTileBoundsLonlat(unittest.TestCase):
    def test_world_tile(self):
        """z=0, x=0, y=0 covers the entire world."""
        lon_min, lat_min, lon_max, lat_max = _tile_bounds_lonlat(0, 0, 0)
        self.assertAlmostEqual(lon_min, -180.0)
        self.assertAlmostEqual(lon_max, 180.0)
        self.assertGreater(lat_max, 85.0)
        self.assertLess(lat_min, -85.0)

    def test_z1_nw_tile(self):
        """z=1, x=0, y=0 covers the NW quadrant."""
        lon_min, lat_min, lon_max, lat_max = _tile_bounds_lonlat(1, 0, 0)
        self.assertAlmostEqual(lon_min, -180.0)
        self.assertAlmostEqual(lon_max, 0.0)
        self.assertGreater(lat_max, 85.0)
        self.assertAlmostEqual(lat_min, 0.0, places=5)

    def test_z1_se_tile(self):
        """z=1, x=1, y=1 covers the SE quadrant."""
        lon_min, lat_min, lon_max, lat_max = _tile_bounds_lonlat(1, 1, 1)
        self.assertAlmostEqual(lon_min, 0.0)
        self.assertAlmostEqual(lon_max, 180.0)
        self.assertAlmostEqual(lat_max, 0.0, places=5)
        self.assertLess(lat_min, -85.0)

    def test_tile_lon_width_decreases_with_zoom(self):
        """Longitude span halves at each zoom level."""
        _, _, lon_max_z1, _ = _tile_bounds_lonlat(1, 0, 0)
        lon_min_z1, _, _, _ = _tile_bounds_lonlat(1, 0, 0)
        _, _, lon_max_z2, _ = _tile_bounds_lonlat(2, 0, 0)
        lon_min_z2, _, _, _ = _tile_bounds_lonlat(2, 0, 0)
        span_z1 = lon_max_z1 - lon_min_z1
        span_z2 = lon_max_z2 - lon_min_z2
        self.assertAlmostEqual(span_z1, 2 * span_z2, places=5)


class TestGetMapTile(unittest.TestCase):
    def _open_png(self, buffer):
        buffer.seek(0)
        return Image.open(buffer)

    def test_tile_is_256x256(self):
        """Output is always 256×256."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        self.assertEqual(tile.size, (256, 256))

    def test_tile_is_png(self):
        """Output format is PNG."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        self.assertEqual(tile.format, "PNG")

    def test_tile_is_rgba(self):
        """Output mode is RGBA."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        self.assertEqual(tile.mode, "RGBA")

    def test_transparent_tile_on_no_overlap(self):
        """Tile outside image bounds is fully transparent."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        # Image covers eastern hemisphere; z=1, x=0, y=0 is western hemisphere
        bounds = [[0.0, 0.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=1, x=0, y=0))
        pixels = list(tile.getdata())
        self.assertTrue(all(p[3] == 0 for p in pixels))

    def test_world_image_mostly_fills_tile(self):
        """Image covering the whole world fills most of the tile."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        pixels = list(tile.getdata())
        opaque = sum(1 for p in pixels if p[3] > 0)
        self.assertGreater(opaque, 256 * 256 * 0.9)

    def test_partial_overlap_mixes_transparent_and_opaque(self):
        """Image in NE quadrant leaves the rest of the tile transparent."""
        img = Image.new("RGB", (100, 100), (0, 0, 255))
        bounds = [[0.0, 0.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        pixels = list(tile.getdata())
        transparent = sum(1 for p in pixels if p[3] == 0)
        opaque = sum(1 for p in pixels if p[3] > 0)
        self.assertGreater(transparent, 0)
        self.assertGreater(opaque, 0)

    def test_rgba_source_image_preserves_alpha(self):
        """Semi-transparent source pixels remain semi-transparent in the tile."""
        img = Image.new("RGBA", (100, 100), (0, 255, 0, 128))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        pixels = [p for p in tile.getdata() if p[3] > 0]
        self.assertTrue(all(p[3] < 255 for p in pixels))

    def test_zoom_in_covers_subset(self):
        """Zooming in on an overlapping tile yields non-empty result."""
        img = Image.new("RGB", (256, 256), (200, 100, 50))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        # z=3, center tile — should have image content
        tile = self._open_png(get_map_tile(img, bounds, z=3, x=4, y=3))
        pixels = list(tile.getdata())
        opaque = sum(1 for p in pixels if p[3] > 0)
        self.assertGreater(opaque, 0)

    def test_equator_is_at_tile_center(self):
        """With a world-covering image, lat=0 maps to pixel y=128 in the z=0 tile."""
        # Verify Mercator correction: equator is vertically centred
        img = Image.new("RGB", (256, 256), (255, 0, 0))
        bounds = [[-85.0, -180.0], [85.0, 180.0]]
        tile = self._open_png(get_map_tile(img, bounds, z=0, x=0, y=0))
        # The equator row (y=128) must be opaque (image covers it)
        row_128 = [tile.getpixel((x, 128)) for x in range(256)]
        self.assertTrue(all(p[3] > 0 for p in row_128))


class TestLatToTilePixelY(unittest.TestCase):
    def test_equator_at_center(self):
        """Latitude 0 maps to y=128 in the z=0 world tile."""
        self.assertAlmostEqual(_lat_to_tile_pixel_y(0.0, z=0, y_tile=0), 128.0, places=3)

    def test_equator_at_top_of_southern_tile(self):
        """Latitude 0 is the top edge of tile z=1, x=0, y=1."""
        self.assertAlmostEqual(_lat_to_tile_pixel_y(0.0, z=1, y_tile=1), 0.0, places=3)

    def test_north_pole_limit_at_tile_top(self):
        """~85° N is near y=0 in the z=0 world tile."""
        y = _lat_to_tile_pixel_y(85.05, z=0, y_tile=0)
        self.assertLess(y, 5)

    def test_mercator_is_nonlinear(self):
        """45°N is NOT halfway between 0° and 85°N in Mercator tile space."""
        y_0 = _lat_to_tile_pixel_y(0.0, z=0, y_tile=0)
        y_45 = _lat_to_tile_pixel_y(45.0, z=0, y_tile=0)
        y_85 = _lat_to_tile_pixel_y(85.0, z=0, y_tile=0)
        midpoint = (y_0 + y_85) / 2
        self.assertNotAlmostEqual(y_45, midpoint, delta=5)


class TestTransparentPngTile(unittest.TestCase):
    def test_transparent_tile_is_256x256_rgba_png(self):
        buf = transparent_png_tile()
        buf.seek(0)
        img = Image.open(buf)
        self.assertEqual(img.size, (256, 256))
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.format, "PNG")
        self.assertTrue(all(p[3] == 0 for p in img.getdata()))
