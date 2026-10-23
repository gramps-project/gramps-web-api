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

"""Tests for how the agent is set up from the configuration."""

import pytest
from flask import Flask
from pydantic_ai.messages import ModelResponse, SystemPromptPart, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel

from gramps_webapi.api.llm import answer_with_agent
from gramps_webapi.api.llm.agent import create_agent
from gramps_webapi.api.llm.deps import AgentDeps


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


@pytest.mark.parametrize(
    "config,max_tokens", [({}, None), ({"LLM_MAX_OUTPUT_TOKENS": 1000}, 1000)]
)
def test_response_tokens_are_capped(monkeypatch, config, max_tokens):
    """Responses are only capped if configured, as model limits differ."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    seen = {}

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen["settings"] = info.model_settings
        return ModelResponse(parts=[TextPart(content="done")])

    def create(**kwargs):
        agent = create_agent(**kwargs)
        agent.model = FunctionModel(model_function)
        return agent

    monkeypatch.setattr("gramps_webapi.api.llm.create_agent", create)
    app = Flask(__name__)
    app.config.update(LLM_MODEL="gpt-4o-mini", **config)
    with app.app_context():
        answer_with_agent(
            prompt="question", tree="tree", include_private=False, user_id="user"
        )
    assert (seen["settings"] or {}).get("max_tokens") == max_tokens


def _tools_and_prompt() -> tuple[dict, str]:
    """Run the agent once and return the tool definitions and system prompt it got."""
    seen = {}

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen["tools"] = {tool.name: tool for tool in info.function_tools}
        seen["prompt"] = "".join(
            part.content
            for part in messages[0].parts
            if isinstance(part, SystemPromptPart)
        )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = create_agent("gpt-4o-mini")
    deps = AgentDeps(
        tree="tree", include_private=False, max_context_length=1000, user_id="user"
    )
    with agent.override(model=FunctionModel(model_function)):
        agent.run_sync("question", deps=deps)
    return seen["tools"], seen["prompt"]


def test_search_tool_is_fulltext(monkeypatch):
    """The search tool only offers full-text search."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    tools, prompt = _tools_and_prompt()
    search_tool = tools["search_genealogy_database"]
    assert "search_type" not in search_tool.parameters_json_schema["properties"]
    assert "semantic" not in search_tool.description.lower()
    assert "semantic" not in prompt.lower()
    assert "search_genealogy_database matches exact names" in prompt


def test_prompt_asks_to_link_the_subject(monkeypatch):
    """The prompt asks to link the person the question is about."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    _, prompt = _tools_and_prompt()
    assert "This includes the person the user asked about" in prompt


def test_get_note_tool(monkeypatch):
    """The agent can read notes in full."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    tools, prompt = _tools_and_prompt()
    assert "get_note" in tools
    assert "`/note/ID` → get_note" in prompt
