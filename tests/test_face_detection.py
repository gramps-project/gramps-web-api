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

"""Tests for face detection and head shot regions."""

import io
import os

import pytest
from gramps.gen.utils.resourcepath import ResourcePath

from gramps_webapi.api.faces import (
    HEAD_SHOT_HEIGHT_FACTOR,
    HEAD_SHOT_WIDTH_FACTOR,
    detect_faces,
    head_shot_region,
)

cv2 = pytest.importorskip("cv2")

EXAMPLE_MEDIA_DIR = os.path.join(ResourcePath().doc_dir, "example", "gramps")
PORTRAIT = "E_W_Dahlgren.jpg"
GROUP_PHOTO = "1897_expeditionsmannschaft_rio_a.jpg"


def load_image(filename):
    """Load an example tree image as a BGR array."""
    image = cv2.imread(os.path.join(EXAMPLE_MEDIA_DIR, filename))
    assert image is not None
    return image


def upscale(image, long_side=4000):
    """Upscale an image to simulate a high-resolution photo or scan."""
    height, width = image.shape[:2]
    scale = long_side / max(height, width)
    return cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_CUBIC,
    )


def detect(image):
    """Run face detection on an encoded image like the endpoint does."""
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return detect_faces(io.BytesIO(buffer.tobytes()))


def assert_boxes_close(box1, box2, tolerance=3):
    """Assert two boxes (in percent) agree within the tolerance."""
    for value1, value2 in zip(box1, box2):
        assert abs(value1 - value2) < tolerance, (box1, box2)


def test_portrait():
    faces = detect(load_image(PORTRAIT))
    assert len(faces) == 1
    assert_boxes_close(faces[0], (41.5, 15.2, 66.7, 57.2))


def test_portrait_high_resolution():
    """A face covering a large number of pixels is still detected."""
    image = load_image(PORTRAIT)
    faces_high_res = detect(upscale(image))
    assert len(faces_high_res) == 1
    assert_boxes_close(faces_high_res[0], detect(image)[0])


def test_group_photo():
    faces = detect(load_image(GROUP_PHOTO))
    assert len(faces) >= 4


def test_group_photo_high_resolution():
    """Upscaling neither loses faces nor adds spurious ones."""
    image = load_image(GROUP_PHOTO)
    faces = detect(image)
    faces_high_res = detect(upscale(image))
    assert len(faces) - 1 <= len(faces_high_res) <= len(faces) + 1


def test_boxes_clamped_to_image():
    """A face cut off by the image border yields a box within the image."""
    image = load_image(PORTRAIT)
    height, width = image.shape[:2]
    cropped = image[int(0.2 * height) :, int(0.48 * width) :]
    faces = detect(cropped)
    assert len(faces) == 1
    assert all(0 <= value <= 100 for value in faces[0])


def test_head_shot_region_encloses_face():
    face = (40.0, 40.0, 50.0, 52.0)
    x1, y1, x2, y2 = head_shot_region(face)
    assert x1 < face[0] and y1 < face[1] and x2 > face[2] and y2 > face[3]
    assert x2 - x1 == pytest.approx((face[2] - face[0]) * HEAD_SHOT_WIDTH_FACTOR)
    assert y2 - y1 == pytest.approx((face[3] - face[1]) * HEAD_SHOT_HEIGHT_FACTOR)


def test_head_shot_region_clamped_to_image():
    region = head_shot_region((0.0, 1.0, 20.0, 30.0))
    assert region[0] == 0 and region[1] == 0
    region = head_shot_region((85.0, 80.0, 100.0, 99.0))
    assert region[2] == 100 and region[3] == 100
