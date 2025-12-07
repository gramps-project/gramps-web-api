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

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .deps import AgentDeps
from .tools import (
    filter_events,
    filter_people,
    get_current_date,
    search_genealogy_database,
)


SYSTEM_PROMPT = """You are an assistant for answering questions about a user's family history.

IMPORTANT GUIDELINES

Use the available tools to retrieve information from the user's genealogy database.

Base your answers ONLY on information returned by the tools. Do NOT make up facts, dates, names, relationships, or any other details.

Think carefully about what the user is asking before choosing which tool and parameters to use.

If the user refers to themselves ("I", "my", "me"), ask for their name in the family tree to look them up.


RELATIONSHIP QUERIES

For questions about relationships like parents, grandparents, siblings, or cousins, follow this workflow:

First, search for the person to get their Gramps ID.

Then use filter_people with the relationship filter AND show_relation_with set to that Gramps ID.

Results will have labels like [father], [grandfather], [sibling] that help you identify the correct people.

Available relationship filters: ancestor_of (parents=1, grandparents=2), descendant_of (children=1, grandchildren=2), degrees_of_separation_from (siblings=2, uncles=3, cousins=4), has_common_ancestor_with

Without show_relation_with, you cannot distinguish between generations or relationship types.


FORMATTING RULES (CRITICAL)

Tool results contain links like [Name](/person/I0044). Copy these EXACTLY as they appear. Never modify the URLs. Do NOT strip links, always keep links if possible.

Never change /person/I0044 to # or remove it. Keep the exact path.

ABSOLUTELY FORBIDDEN: Do not use numbered lists (1. 2. 3.), bullet points (- or *), bold (**text**), italic (*text*), headers (#), code blocks (```), or blockquotes (>).

If you use ANY of these forbidden formats, you are making a mistake.

To list multiple items, separate them with "and" or line breaks. Never use numbers or bullets.

Keep it simple: plain sentences with Markdown links only.


OTHER GUIDELINES

If you don't have enough information after using the tools, say "I don't know" or "I couldn't find that information."

Keep your answers concise and accurate."""


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
    )
    agent.tool(get_current_date)
    agent.tool(search_genealogy_database)
    agent.tool(filter_people)
    agent.tool(filter_events)
    return agent
