#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
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

"""Pydantic AI agent for LLM interactions."""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .deps import AgentDeps
from .tools import (
    filter_events,
    filter_families,
    filter_people,
    get_current_date,
    get_family,
    get_person,
    search_genealogy_database,
)


def _part_chars(part) -> int:
    """Rough character count of a message part."""
    content = getattr(part, "content", None)
    if content is not None:
        return len(content) if isinstance(content, str) else len(str(content))
    args = getattr(part, "args", None)
    if args is not None:
        return len(str(args))
    return 0


def _trim_history(
    ctx: RunContext[AgentDeps], messages: list[ModelMessage]
) -> list[ModelMessage]:
    """Drop oldest complete user turns when history exceeds 3× the context budget.

    A "turn" is everything from one ModelRequest[UserPromptPart] up to (but not
    including) the next. Turns are always dropped as units to keep ToolCallPart /
    ToolReturnPart pairs intact.
    """
    budget = ctx.deps.max_context_length * 3

    turn_starts = [
        i
        for i, msg in enumerate(messages)
        if isinstance(msg, ModelRequest)
        and any(isinstance(p, UserPromptPart) for p in msg.parts)
    ]

    total = sum(_part_chars(p) for msg in messages for p in msg.parts)

    while total > budget and len(turn_starts) > 1:
        drop_to = turn_starts[1]
        total -= sum(_part_chars(p) for msg in messages[:drop_to] for p in msg.parts)
        messages = messages[drop_to:]
        turn_starts = [i - drop_to for i in turn_starts[1:]]

    return messages


SYSTEM_PROMPT = """You are an assistant for answering questions about a user's family history.

Use the available tools to retrieve information from the genealogy database. Base your answers ONLY on what the tools return — never invent facts, dates, names, or relationships. If you cannot find the information, say so. If the user refers to themselves ("I", "my", "me"), ask for their name in the family tree.


MULTI-STEP LOOKUPS

Whenever a search or filter result contains a Gramps ID, immediately call get_person or get_family to retrieve the full record. Search results are summaries — only the full record contains family links, children, spouses, and complete event details.


RELATIONSHIP QUERIES

For questions about parents, grandparents, siblings, or cousins, follow this workflow:

1. Search for the person to get their Gramps ID.
2. Use filter_people with the relationship filter AND show_relation_with set to that Gramps ID.

Results include labels like [father], [grandfather], [sibling] that identify the relationship. Without show_relation_with you cannot distinguish between generations.

Available relationship filters: ancestor_of (parents=1, grandparents=2), descendant_of (children=1, grandchildren=2), degrees_of_separation_from (siblings=2, uncles=3, cousins=4), has_common_ancestor_with

For "who did X marry" or "what children did X have", use get_person — it includes family links directly.


FORMATTING

Use Markdown freely. When tool results contain links like [Name](/person/I0044), include them in your response exactly as they appear — never modify the path and never drop the link. Every person, family, event, place, source, citation, repository, note, and media object should be linked."""


def create_agent(
    model_name: str,
    base_url: str | None = None,
    system_prompt_override: str | None = None,
) -> Agent[AgentDeps, str]:
    """Create a Pydantic AI agent with the specified model.

    Args:
        model_name: The name of the LLM model to use. If it contains a colon (e.g.,
            "mistral:mistral-large-latest" or "openai:gpt-4"), it will be treated
            as a provider-prefixed model name and Pydantic AI will handle provider
            detection automatically. Otherwise, it will be treated as an OpenAI
            compatible model name.
        base_url: Optional base URL for the OpenAI-compatible API (ignored if
            model_name contains a provider prefix)
        system_prompt_override: Optional override for the system prompt

    Returns:
        A configured Pydantic AI agent
    """
    # If model name has a provider prefix (e.g., "mistral:model-name"),
    # let Pydantic AI handle provider detection automatically
    if ":" in model_name:
        model: str | OpenAIChatModel = model_name
    else:
        # Otherwise, use OpenAI-compatible provider with optional base_url
        provider = OpenAIProvider(base_url=base_url)
        model = OpenAIChatModel(
            model_name,
            provider=provider,
        )

    system_prompt = system_prompt_override or SYSTEM_PROMPT

    agent = Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=system_prompt,
        capabilities=[ProcessHistory(_trim_history)],
    )
    agent.tool(get_current_date)
    agent.tool(search_genealogy_database)
    agent.tool(get_person)
    agent.tool(get_family)
    agent.tool(filter_people)
    agent.tool(filter_events)
    agent.tool(filter_families)
    return agent
