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

"""Tests for images attached to AI chat queries."""

import base64
import io

import pytest
from flask import Flask
from PIL import Image, PngImagePlugin
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    BinaryContent,
    FilePart,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from werkzeug.exceptions import HTTPException

from gramps_webapi.api.llm import answer_with_agent
from gramps_webapi.api.llm import images as images_module
from gramps_webapi.api.llm.agent import IMAGE_CHARS, _part_chars, create_agent
from gramps_webapi.api.llm.images import (
    MAX_IMAGE_EDGE,
    OMITTED_IMAGE,
    InvalidImageError,
    normalize_image,
    strip_images,
)
from gramps_webapi.api.resources.chat import _normalize_images
from gramps_webapi.api.tasks import process_chat


def _encode(img: Image.Image, fmt: str) -> str:
    output = io.BytesIO()
    img.save(output, format=fmt)
    return base64.b64encode(output.getvalue()).decode()


def _decode(data: str) -> Image.Image:
    img = Image.open(io.BytesIO(base64.b64decode(data)))
    img.load()
    return img


@pytest.fixture(name="app")
def fixture_app():
    """A minimal app providing the LLM config."""
    app = Flask(__name__)
    app.config.update(
        LLM_MODEL="gpt-4o-mini",
        LLM_BASE_URL=None,
        LLM_SYSTEM_PROMPT=None,
        LLM_VISION=True,
        CELERY_CONFIG={},
    )
    return app


def test_normalize_downscales_to_jpeg():
    """Large images become JPEGs whose long edge fits the limit."""
    png = _encode(Image.new("RGB", (4000, 2000), "red"), "PNG")
    img = _decode(normalize_image(png))
    assert img.format == "JPEG"
    assert img.size == (MAX_IMAGE_EDGE, MAX_IMAGE_EDGE // 2)


def test_normalize_keeps_small_images_and_flattens_alpha():
    """Transparent pixels become white; small images keep their size."""
    png = _encode(Image.new("RGBA", (10, 20), (0, 0, 0, 0)), "PNG")
    img = _decode(normalize_image(png))
    assert img.size == (10, 20)
    assert img.mode == "RGB"
    assert img.getpixel((5, 5)) == (255, 255, 255)


def test_normalize_accepts_data_url():
    """Data URLs, as read by browsers, are accepted."""
    data = _encode(Image.new("L", (8, 8)), "GIF")
    assert _decode(normalize_image(f"data:image/gif;base64,{data}")).size == (8, 8)


@pytest.mark.parametrize(
    "data",
    [
        "not base64!",
        "data:image/png,rawdata",
        base64.b64encode(b"not an image").decode(),
        _encode(Image.new("RGB", (8, 8)), "BMP"),
    ],
)
def test_normalize_rejects_invalid_images(data):
    with pytest.raises(InvalidImageError):
        normalize_image(data)


def test_normalize_rejects_png_with_large_text():
    """Pillow raises ValueError for some invalid files, e.g. huge PNG text."""
    info = PngImagePlugin.PngInfo()
    info.add_text("comment", "a" * (PngImagePlugin.MAX_TEXT_CHUNK + 1), zip=True)
    output = io.BytesIO()
    Image.new("RGB", (1, 1)).save(output, format="PNG", pnginfo=info)
    with pytest.raises(InvalidImageError, match="Invalid image"):
        normalize_image(base64.b64encode(output.getvalue()).decode())


def test_normalize_rejects_large_files(monkeypatch):
    monkeypatch.setattr(images_module, "MAX_IMAGE_BYTES", 10)
    with pytest.raises(InvalidImageError, match="too large"):
        normalize_image(_encode(Image.new("RGB", (100, 100)), "PNG"))


def test_images_need_vision(app):
    """Without LLM_VISION, images are rejected before calling the model."""
    app.config["LLM_VISION"] = False
    with app.app_context():
        with pytest.raises(HTTPException) as excinfo:
            _normalize_images([_encode(Image.new("RGB", (8, 8)), "PNG")])
    assert excinfo.value.code == 422


def test_invalid_image_is_unprocessable(app):
    with app.app_context():
        with pytest.raises(HTTPException) as excinfo:
            _normalize_images(["not base64!"])
    assert excinfo.value.code == 422


def test_strip_images():
    """Images in prompts and tool results are replaced, text is kept."""
    image = BinaryContent(data=b"jpeg", media_type="image/jpeg")
    messages = [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "What does this say?",
                        image,
                        ImageUrl(url="http://localhost/x.png"),
                    ]
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content="It says hi.")]),
        ModelRequest(
            parts=[
                UserPromptPart(content="Thanks"),
                ToolReturnPart(tool_name="t", content=image, tool_call_id="1"),
            ]
        ),
    ]
    stripped = strip_images(messages)
    assert stripped[0].parts[0].content == [
        "What does this say?",
        OMITTED_IMAGE,
        OMITTED_IMAGE,
    ]
    assert stripped[1] == messages[1]
    assert stripped[2].parts[0].content == "Thanks"
    assert stripped[2].parts[1].content == OMITTED_IMAGE
    # the original messages are unchanged
    assert messages[0].parts[0].content[1] is image


def test_image_counts_as_fixed_size():
    """An image's bytes don't count towards the history budget."""
    part = UserPromptPart(
        content=["hi", BinaryContent(data=b"x" * 100_000, media_type="image/jpeg")]
    )
    assert _part_chars(part) == 2 + IMAGE_CHARS


def _use_model(monkeypatch, model_function):
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    def create(**kwargs):
        agent = create_agent(**kwargs)
        agent.model = FunctionModel(model_function)
        return agent

    monkeypatch.setattr("gramps_webapi.api.llm.create_agent", create)


def _prompt_contents(messages) -> list:
    return [
        part.content
        for msg in messages
        if isinstance(msg, ModelRequest)
        for part in msg.parts
        if isinstance(part, UserPromptPart)
    ]


def test_images_reach_the_model_but_not_the_history(app, monkeypatch):
    """The model sees the current turn's images; the returned history doesn't."""
    seen = []

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen.extend(_prompt_contents(messages))
        return ModelResponse(parts=[TextPart(content="A gravestone.")])

    _use_model(monkeypatch, model_function)
    image = normalize_image(_encode(Image.new("RGB", (8, 8)), "PNG"))
    old_history = ModelMessagesTypeAdapter.dump_json(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=[
                            "Earlier",
                            BinaryContent(data=b"old", media_type="image/png"),
                        ]
                    )
                ]
            ),
            ModelResponse(parts=[TextPart(content="Ok.")]),
        ]
    ).decode()
    charged = []
    monkeypatch.setattr(
        "gramps_webapi.api.tasks.update_usage_ai",
        lambda new, tree: charged.append(new),
    )

    with app.app_context():
        result = process_chat(
            tree="tree",
            user_id="user",
            query="What is this?",
            include_private=False,
            message_history_raw=old_history,
            images=[image],
        )

    assert charged == [2]  # the message and its image
    earlier, current = seen
    assert earlier == ["Earlier", OMITTED_IMAGE]
    assert current[0] == "What is this?"
    assert current[1].data == base64.b64decode(image)
    assert current[1].media_type == "image/jpeg"
    history = ModelMessagesTypeAdapter.validate_json(result["message_history_raw"])
    assert _prompt_contents(history) == [
        ["Earlier", OMITTED_IMAGE],
        ["What is this?", OMITTED_IMAGE],
    ]


@pytest.mark.parametrize("with_images,status", [(True, 400), (False, 502)])
def test_provider_rejecting_images(app, monkeypatch, with_images, status):
    """A model that rejects images gets a message saying so."""

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=400, model_name="gpt-4o-mini")

    _use_model(monkeypatch, model_function)
    images = [normalize_image(_encode(Image.new("RGB", (8, 8)), "PNG"))]
    with app.app_context():
        with pytest.raises(HTTPException) as excinfo:
            answer_with_agent(
                prompt="What is this?",
                tree="tree",
                include_private=False,
                user_id="user",
                images=images if with_images else None,
            )
    assert excinfo.value.code == status


def test_files_in_history_responses_are_stripped(app, monkeypatch):
    """Files in model responses can't bypass the image checks via the history."""
    seen = []

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen.extend(part for msg in messages for part in msg.parts)
        return ModelResponse(parts=[TextPart(content="Ok.")])

    _use_model(monkeypatch, model_function)
    charged = []
    monkeypatch.setattr(
        "gramps_webapi.api.tasks.update_usage_ai",
        lambda new, tree: charged.append(new),
    )
    image = BinaryContent(data=b"image", media_type="image/png")
    history = ModelMessagesTypeAdapter.dump_json(
        [
            ModelRequest(parts=[UserPromptPart(content="Draw a tree")]),
            ModelResponse(parts=[TextPart(content="Here:"), FilePart(content=image)]),
        ]
    ).decode()

    with app.app_context():
        result = process_chat(
            tree="tree",
            user_id="user",
            query="What is this?",
            include_private=False,
            message_history_raw=history,
        )

    assert not any(isinstance(part, FilePart) for part in seen)
    assert OMITTED_IMAGE in [getattr(part, "content", None) for part in seen]
    assert base64.b64encode(b"image").decode() not in result["message_history_raw"]
    assert charged == [1]
