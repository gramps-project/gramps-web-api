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

"""Pydantic AI tools for LLM interactions."""

from __future__ import annotations

from datetime import datetime
from functools import wraps

from pydantic_ai import RunContext

from ..search import get_semantic_search_indexer
from ..util import get_logger
from .deps import AgentDeps


def log_tool_call(func):
    """Decorator to log tool usage."""
    logger = get_logger()

    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug("Tool called: %s", func.__name__)
        return func(*args, **kwargs)

    return wrapper


@log_tool_call
def get_current_date(_ctx: RunContext[AgentDeps]) -> str:
    """Get the current date.

    Use this tool when you need to know today's date or the current time.
    This is helpful for date-related queries or calculating time periods.

    Returns:
        The current date in ISO format (YYYY-MM-DD).
    """
    logger = get_logger()

    result = datetime.now().date().isoformat()
    logger.debug("Tool get_current_date returned: %s", result)
    return result


@log_tool_call
def search_genealogy_database(
    ctx: RunContext[AgentDeps], query: str, max_results: int = 20
) -> str:
    """Search the genealogy database for relevant information.

    Use this tool to find information about people, families, events, places,
    or any other genealogical data in the user's family tree. The search uses
    semantic similarity to find the most relevant results.

    Args:
        query: The search query describing what information you're looking for
        max_results: Maximum number of results to return (default: 20, max: 50)

    Returns:
        A formatted string containing the search results with relevant genealogical data.
    """

    logger = get_logger()

    # Limit max_results to reasonable bounds
    max_results = min(max(1, max_results), 50)

    try:
        searcher = get_semantic_search_indexer(ctx.deps.tree)
        _, hits = searcher.search(
            query=query,
            page=1,
            pagesize=max_results,
            include_private=ctx.deps.include_private,
            include_content=True,
        )

        if not hits:
            return "No results found in the genealogy database."

        # Build context from search results
        context_parts: list[str] = []
        max_length = ctx.deps.max_context_length
        current_length = 0

        for hit in hits:
            content = hit.get("content", "")
            if current_length + len(content) > max_length:
                logger.debug(
                    "Reached max context length (%d chars), stopping at %d results",
                    max_length,
                    len(context_parts),
                )
                break
            context_parts.append(content)
            current_length += len(content) + 2  # +2 for the newlines

        result = "\n\n".join(context_parts)
        logger.debug(
            "Tool search_genealogy_database returned %d results (%d chars) for query: %r",
            len(context_parts),
            len(result),
            query,
        )
        return result

    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error searching genealogy database: %s", e)
        return f"Error searching the database: {str(e)}"
