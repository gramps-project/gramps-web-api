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

IMPORTANT GUIDELINES:
- Use the available tools to retrieve information from the user's genealogy database.
- Base your answers ONLY on information returned by the tools. Do NOT make up facts, dates, names, relationships, or any other details.

CRITICAL LINKING RULES:
- Tool results contain Markdown links like [Name](/person/I0044) for people, families, events, places, and other entities.
- You MUST preserve these EXACT link formats: [Text](/path/ID)
- NEVER modify the URLs. NEVER add domains like "https://example.com" or any other hostname.
- Keep all URLs as relative paths starting with / (e.g., /person/I0044, /event/E1948, /family/F0123).
- When showing links, use the EXACT format from the tool results without any modification.

OTHER GUIDELINES:
- If you don't have enough information after using the tools, say "I don't know" or "I couldn't find that information."
- Keep your answers concise and accurate."""


def create_agent(
    model_name: str,
    base_url: str | None = None,
) -> Agent[AgentDeps, str]:
    """Create a Pydantic AI agent with the specified model.

    Args:
        model_name: The name of the LLM model to use
        base_url: Optional base URL for the OpenAI-compatible API

    Returns:
        A configured Pydantic AI agent
    """
    provider = OpenAIProvider(base_url=base_url)
    model = OpenAIChatModel(
        model_name,
        provider=provider,
    )
    agent = Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=SYSTEM_PROMPT,
    )
    agent.tool(get_current_date)
    agent.tool(search_genealogy_database)
    agent.tool(filter_people)
    agent.tool(filter_events)
    return agent
