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

"""Tests for how the configured model name is resolved."""

import pytest
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel

from gramps_webapi.api.llm.agent import create_agent


@pytest.mark.parametrize(
    "model_name", ["gpt-4o-mini", "qwen2.5:7b", "qwen2.5:7B-Instruct", "llama3.1"]
)
def test_openai_compatible_model_uses_base_url(monkeypatch, model_name):
    """Names without a known provider prefix go to the configured base URL.

    This includes Ollama names with a tag after the colon.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    agent = create_agent(model_name, base_url="http://ollama:11434/v1/")
    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == model_name
    assert agent.model.base_url == "http://ollama:11434/v1/"


def test_provider_prefixed_model(monkeypatch):
    """A known provider prefix is resolved by Pydantic AI."""
    monkeypatch.setenv("MISTRAL_API_KEY", "key")
    agent = create_agent("mistral:mistral-large-latest")
    assert isinstance(agent.model, MistralModel)
    assert agent.model.model_name == "mistral-large-latest"


def test_ollama_model_uses_base_url(monkeypatch):
    """The configured base URL is used for Ollama instead of OLLAMA_BASE_URL."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://other:11434/v1/")
    agent = create_agent("ollama:qwen2.5:7b", base_url="http://ollama:11434/v1/")
    assert isinstance(agent.model, OllamaModel)
    assert agent.model.model_name == "qwen2.5:7b"
    assert agent.model.base_url == "http://ollama:11434/v1/"


def test_ollama_model_without_base_url(monkeypatch):
    """Without a configured base URL, OLLAMA_BASE_URL is used."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/v1/")
    agent = create_agent("ollama:qwen2.5:7b")
    assert isinstance(agent.model, OllamaModel)
    assert agent.model.base_url == "http://ollama:11434/v1/"
