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
To find relationships, prefer using the relationship filters over search alone, as semantic similarity can be unreliable for names.

- For ancestors (parents, grandparents, great-grandparents): Use ancestor_of with the person's Gramps ID and generations parameter. Note: ancestor_of returns ALL ancestors up to that many generations, so generations=2 returns both parents AND grandparents.
- For descendants (children, grandchildren, great-grandchildren): Use descendant_of with the person's Gramps ID and generations parameter. Note: descendant_of returns ALL descendants up to that many generations.
- For lateral relationships (siblings, cousins, uncles, in-laws): Use degrees_of_separation_from with the person's Gramps ID and degrees_of_separation parameter. Examples: siblings=2, uncles=3, first cousins=4.
- For finding cousins and extended family who share an ancestor: Use has_common_ancestor_with.
- Workflow: First search to find the person and get their Gramps ID, then use the appropriate relationship filter with that ID.

FORMATTING RULES:
- Use ONLY plain text with Markdown links. No other formatting is allowed.
- Tool results contain Markdown links like [Name](/person/I0044) - preserve these EXACT link formats: [Text](/path/ID)
- NEVER modify URLs. NEVER add domains. Keep all URLs as relative paths starting with /
- FORBIDDEN: bold (**text**), italic (*text*), headers (# Header), numbered lists (1. item), bullet lists (- item, * item), code blocks (```), blockquotes (>)
- Structure your response using line breaks and simple sentences only.

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
