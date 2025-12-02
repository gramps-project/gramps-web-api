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
- Think carefully about what the user is asking before choosing which tool and parameters to use.

RELATIONSHIP QUERIES:
- To find multi-generational relationships, you must traverse relationships step by step.
- First, search for the person to find their immediate family (parents/children).
- Then search for those relatives to find their immediate family.
- Continue until you reach the desired relationship level.
- Do NOT assume relationships beyond what is explicitly stated in the results.
- The ancestor_of/descendant_of filters return ALL ancestors/descendants combined across multiple generations.

FORMATTING RULES:
- Format your responses as plain text with Markdown links ONLY.
- Tool results contain Markdown links like [Name](/person/I0044) - you MUST preserve these EXACT link formats: [Text](/path/ID)
- NEVER modify the URLs. NEVER add domains like "https://example.com" or any other hostname.
- Keep all URLs as relative paths starting with / (e.g., /person/I0044, /event/E1948, /family/F0123).
- Do NOT use any other Markdown formatting: no bold (**), no italic (*), no headers (#), no lists (1., -, *), no code blocks.
- Use plain text paragraphs with links only.

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
