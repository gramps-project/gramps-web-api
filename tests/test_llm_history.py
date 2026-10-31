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

"""Tests for how the agent keeps the message history within budget."""

from types import SimpleNamespace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gramps_webapi.api.llm.agent import (
    OMITTED_TOOL_RESULT,
    _compact_history,
    create_agent,
)
from gramps_webapi.api.llm.deps import AgentDeps

CONTEXT_LENGTH = 1000
BIG = "x" * (CONTEXT_LENGTH * 2)


def _ctx():
    return SimpleNamespace(deps=SimpleNamespace(max_context_length=CONTEXT_LENGTH))


def _tool_round(call_id: str) -> list:
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name="search", args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="search", content=BIG, tool_call_id=call_id)
            ]
        ),
    ]


def _conversation() -> list:
    """A question, a follow-up, then many large tool results in the same run."""
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="system"),
                UserPromptPart(content="How am I related to X?"),
            ]
        ),
        ModelResponse(parts=[TextPart(content="What is your name?")]),
        ModelRequest(parts=[UserPromptPart(content="Y")]),
    ]
    for i in range(4):
        messages += _tool_round(str(i))
    return messages


def _contents(messages, part_type) -> list:
    return [p.content for m in messages for p in m.parts if isinstance(p, part_type)]


def test_history_within_budget_is_unchanged():
    messages = _conversation()[:5]
    assert _compact_history(_ctx(), messages) == messages


def test_prompts_and_answers_are_kept():
    """Over budget, the instructions and the conversation text survive."""
    compacted = _compact_history(_ctx(), _conversation())
    assert _contents(compacted, SystemPromptPart) == ["system"]
    assert _contents(compacted, UserPromptPart) == ["How am I related to X?", "Y"]
    assert _contents(compacted, TextPart) == ["What is your name?"]


def test_old_tool_results_are_replaced_oldest_first():
    compacted = _compact_history(_ctx(), _conversation())
    results = _contents(compacted, ToolReturnPart)
    assert results[0] == OMITTED_TOOL_RESULT
    assert results[-1] == BIG
    total = sum(len(r) for r in results)
    assert total <= CONTEXT_LENGTH * 3


def test_latest_tool_results_are_kept():
    """The results the model is about to use are never replaced."""
    messages = _conversation()[:3] + _tool_round("0")
    messages[-1].parts[0].content = "x" * (CONTEXT_LENGTH * 4)
    compacted = _compact_history(_ctx(), messages)
    assert compacted[-1] is messages[-1]


def test_tool_calls_keep_their_results():
    compacted = _compact_history(_ctx(), _conversation())
    calls = [
        p.tool_call_id for m in compacted for p in m.parts if p.part_kind == "tool-call"
    ]
    returns = [
        p.tool_call_id
        for m in compacted
        for p in m.parts
        if p.part_kind == "tool-return"
    ]
    assert calls == returns == ["0", "1", "2", "3"]


def test_input_is_not_modified():
    messages = _conversation()
    _compact_history(_ctx(), messages)
    assert _contents(messages, ToolReturnPart) == [BIG] * 4


def test_model_keeps_first_question(monkeypatch):
    """The model still sees the system prompt and the first question."""
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    seen = {}

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen["messages"] = messages
        return ModelResponse(parts=[TextPart(content="done")])

    history = _conversation() + [ModelResponse(parts=[TextPart(content="answer")])]
    agent = create_agent("gpt-4o-mini")
    deps = AgentDeps(
        tree="tree",
        include_private=False,
        max_context_length=CONTEXT_LENGTH,
        user_id="user",
    )
    with agent.override(model=FunctionModel(model_function)):
        agent.run_sync("follow-up", deps=deps, message_history=history)
    assert _contents(seen["messages"], SystemPromptPart) == ["system"]
    assert _contents(seen["messages"], UserPromptPart) == [
        "How am I related to X?",
        "Y",
        "follow-up",
    ]


def _text_conversation(turns: int) -> list:
    """A long conversation without tool calls, as in the legacy history format."""
    messages = [
        ModelRequest(
            parts=[SystemPromptPart(content="system"), UserPromptPart(content=BIG)]
        ),
        ModelResponse(parts=[TextPart(content=BIG)]),
    ]
    for i in range(turns - 1):
        messages += [
            ModelRequest(parts=[UserPromptPart(content=f"question {i}")]),
            ModelResponse(parts=[TextPart(content=BIG)]),
        ]
    return messages + [ModelRequest(parts=[UserPromptPart(content="current")])]


def _size(messages) -> int:
    return sum(len(p.content) for m in messages for p in m.parts)


def test_text_is_bounded():
    """Without tool results to shorten, the oldest turns are dropped."""
    compacted = _compact_history(_ctx(), _text_conversation(5))
    assert _size(compacted) <= CONTEXT_LENGTH * 3
    assert _contents(compacted, UserPromptPart)[-1] == "current"


def test_system_prompt_survives_dropped_turns():
    compacted = _compact_history(_ctx(), _text_conversation(5))
    assert isinstance(compacted[0].parts[0], SystemPromptPart)
    assert isinstance(compacted[0].parts[1], UserPromptPart)
    assert _contents(compacted, SystemPromptPart) == ["system"]
    assert len(_contents(compacted, UserPromptPart)) < 5


def test_current_turn_is_kept_when_over_budget():
    """The current turn is kept even if it alone exceeds the budget."""
    messages = _text_conversation(2)[:-1] + [
        ModelRequest(parts=[UserPromptPart(content="x" * (CONTEXT_LENGTH * 4))])
    ]
    compacted = _compact_history(_ctx(), messages)
    assert _contents(compacted, SystemPromptPart) == ["system"]
    assert _contents(compacted, UserPromptPart) == ["x" * (CONTEXT_LENGTH * 4)]


def test_dropped_turns_keep_tool_calls_paired():
    messages = _text_conversation(3)[:-1] + _conversation()[2:]
    compacted = _compact_history(_ctx(), messages)
    calls = [
        p.tool_call_id for m in compacted for p in m.parts if p.part_kind == "tool-call"
    ]
    returns = [
        p.tool_call_id
        for m in compacted
        for p in m.parts
        if p.part_kind == "tool-return"
    ]
    assert calls == returns
