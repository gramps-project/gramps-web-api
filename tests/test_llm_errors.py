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

"""Tests for how agent failures are mapped to HTTP status codes."""

import httpx
import pytest
from flask import Flask
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from werkzeug.exceptions import HTTPException

from gramps_webapi.api.llm import answer_with_agent


@pytest.fixture(name="app")
def fixture_app():
    """A minimal app providing the LLM config."""
    app = Flask(__name__)
    app.config.update(LLM_MODEL="test-model", LLM_BASE_URL=None, LLM_SYSTEM_PROMPT=None)
    return app


@pytest.mark.parametrize(
    "error,status",
    [
        (httpx.ReadTimeout(""), 504),
        (ModelAPIError(model_name="test-model", message="connection error"), 504),
        (ModelHTTPError(status_code=503, model_name="test-model"), 502),
        (UnexpectedModelBehavior("garbage"), 500),
        (RuntimeError("boom"), 500),
    ],
)
def test_agent_error_status_codes(app, monkeypatch, error, status):
    """Failures from the model provider get a status code of their own."""

    class _Agent:
        def run_sync(self, *args, **kwargs):
            raise error

    monkeypatch.setattr("gramps_webapi.api.llm.create_agent", lambda **kwargs: _Agent())

    with app.app_context():
        with pytest.raises(HTTPException) as excinfo:
            answer_with_agent(
                prompt="Who was my grandmother?",
                tree="tree",
                include_private=False,
                user_id="user",
            )

    assert excinfo.value.code == status
