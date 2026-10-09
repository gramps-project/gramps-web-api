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

"""Face detection in images using YuNet."""

from importlib.resources import as_file, files
from typing import BinaryIO

from .util import abort_with_message

# YuNet's receptive field limits the face sizes it can detect, so the image
# is downscaled rather than processed at full resolution. Detection runs at
# two sizes: the larger keeps small faces in group photos detectable, the
# smaller brings close-up faces back into the range the model can see.
FACE_DETECTION_MAX_SIDES = (1280, 640)
# Minimum confidence (0 to 1) YuNet must assign to a candidate for it to be
# returned. Increasing it gives fewer wrong boxes but misses more faces, first
# the small, blurred or partly hidden ones; decreasing it finds more of those,
# including tiny faces in background crowds, at the cost of more boxes on
# things that are not faces.
FACE_DETECTION_SCORE_THRESHOLD = 0.5
# Overlap (intersection over union) above which two boxes are considered the
# same face, e.g. when found in both detection passes, and only the more
# confident one is kept. Increasing it keeps more overlapping boxes, which can
# duplicate faces; decreasing it can drop one of two people standing very close.
FACE_DETECTION_NMS_THRESHOLD = 0.3
# part of the cache key; bump whenever detection results can change
FACE_DETECTION_VERSION = 3

# Detected regions are used to tag people, and a tag typically serves as the
# person's profile photo, which should show the whole head rather than the
# tight face box YuNet returns (roughly forehead to chin). The face box is
# therefore enlarged around its centre into a head shot.
# Head shot width and height as multiples of the face box width and height.
HEAD_SHOT_WIDTH_FACTOR = 1.5
HEAD_SHOT_HEIGHT_FACTOR = 1.4
# Vertical shift of the head shot centre relative to the face box centre, as a
# fraction of the face box height; negative values move it up to include hair.
HEAD_SHOT_VERTICAL_SHIFT = 0.1


def head_shot_region(
    face: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Enlarge a face box (x1, y1, x2, y2 in percent) into a head shot.

    The result is cut off at the image borders.
    """
    x1, y1, x2, y2 = face
    width = (x2 - x1) * HEAD_SHOT_WIDTH_FACTOR
    height = (y2 - y1) * HEAD_SHOT_HEIGHT_FACTOR
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2 + (y2 - y1) * HEAD_SHOT_VERTICAL_SHIFT

    def clamp(value: float) -> float:
        return min(100.0, max(0.0, value))

    return (
        clamp(center_x - width / 2),
        clamp(center_y - height / 2),
        clamp(center_x + width / 2),
        clamp(center_y + height / 2),
    )


def detect_faces(stream: BinaryIO) -> list[tuple[float, float, float, float]]:
    """Detect faces in an image (stream) using YuNet."""
    import cv2
    import numpy as np

    file_bytes = np.asarray(bytearray(stream.read()), dtype=np.uint8)
    cv_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if cv_image is None:
        abort_with_message(422, "File is not a valid image file")
    return detect_faces_in_array(cv_image)


def detect_faces_in_array(
    image,
    score_threshold: float = FACE_DETECTION_SCORE_THRESHOLD,
    max_sides: tuple[int, ...] = FACE_DETECTION_MAX_SIDES,
) -> list[tuple[float, float, float, float]]:
    """Detect faces in a decoded BGR image (numpy array) using YuNet.

    Returns boxes as (x1, y1, x2, y2) in percent of the image size.
    """
    import cv2
    import numpy as np

    ref = files("gramps_webapi") / "data/face_detection_yunet_2023mar.onnx"
    with as_file(ref) as model_path:
        face_detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold=score_threshold
        )

    height, width = image.shape[:2]
    long_side = max(height, width)
    boxes: list[list[float]] = []
    scores: list[float] = []
    for size in sorted({min(s, long_side) for s in max_sides}, reverse=True):
        scale = size / long_side
        if scale == 1:
            scaled = image
        else:
            scaled = cv2.resize(
                image,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        face_detector.setInputSize((scaled.shape[1], scaled.shape[0]))
        faces = face_detector.detect(scaled)[1]
        if faces is None:
            continue
        for face in faces:
            boxes.append([float(v) / scale for v in face[:4]])
            scores.append(float(face[14]))

    if not boxes:
        return []

    # merge detections of the same face from the different passes
    keep = cv2.dnn.NMSBoxes(
        boxes, scores, score_threshold, FACE_DETECTION_NMS_THRESHOLD
    )

    def clamp(value: float) -> float:
        return min(100.0, max(0.0, value))

    detected_faces = []
    for i in np.asarray(keep, dtype=int).flatten():
        x, y, w, h = boxes[i]
        detected_faces.append(
            (
                clamp(100 * x / width),
                clamp(100 * y / height),
                clamp(100 * (x + w) / width),
                clamp(100 * (y + h) / height),
            )
        )
    return detected_faces
