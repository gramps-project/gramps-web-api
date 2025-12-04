"""Functions for working with large language models (LLMs)."""

from __future__ import annotations

from datetime import datetime

from flask import current_app
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

from .agent import create_agent
from .deps import AgentDeps
from ..util import abort_with_message, get_logger


def sanitize_answer(answer: str) -> str:
    """Sanitize the LLM answer."""
    # some models convert relative URLs to absolute URLs with placeholder domains
    answer = answer.replace("https://www.example.com", "")
    answer = answer.replace("https://example.com", "")
    answer = answer.replace("http://example.com", "")
    return answer


def answer_with_agent(
    prompt: str,
    tree: str,
    include_private: bool,
    user_id: str,
    history: list | None = None,
) -> str:
    """Answer a prompt using Pydantic AI agent.

    The agent has access to tools including genealogy database search.

    Args:
        prompt: The user's question/prompt
        tree: The tree identifier
        include_private: Whether to include private information
        user_id: The user identifier
        history: Optional chat history

    Returns:
        The agent's response
    """
    logger = get_logger()

    # Get configuration
    config = current_app.config
    model_name = config.get("LLM_MODEL")
    base_url = config.get("LLM_BASE_URL")
    max_context_length = config.get("LLM_MAX_CONTEXT_LENGTH", 50000)
    system_prompt_override = config.get("LLM_SYSTEM_PROMPT")

    if not model_name:
        raise ValueError("No LLM model specified")

    # Create agent
    agent = create_agent(
        model_name=model_name,
        base_url=base_url,
        system_prompt_override=system_prompt_override,
    )

    # Create dependencies
    deps = AgentDeps(
        tree=tree,
        include_private=include_private,
        max_context_length=max_context_length,
        user_id=user_id,
    )

    # Build message history for the agent
    message_history: list[ModelRequest | ModelResponse] = []
    if history:
        for message in history:
            if "role" not in message or "message" not in message:
                raise ValueError(f"Invalid message format: {message}")
            role = message["role"].lower()
            if role in ["ai", "system", "assistant"]:
                # AI/assistant messages become ModelResponse
                message_history.append(
                    ModelResponse(
                        parts=[TextPart(content=message["message"])],
                    )
                )
            elif role != "error":  # skip error messages
                # User messages become ModelRequest
                message_history.append(
                    ModelRequest(parts=[UserPromptPart(content=message["message"])])
                )

    try:
        logger.debug("Running Pydantic AI agent with prompt: '%s'", prompt)
        result = agent.run_sync(prompt, deps=deps, message_history=message_history)
        response_text = result.response.text or ""
        logger.debug("Agent response: '%s'", response_text)
        return sanitize_answer(response_text)
    except (UnexpectedModelBehavior, ModelRetry) as e:
        logger.error("Pydantic AI error: %s", e)
        abort_with_message(500, "Error communicating with the AI model")
    except Exception as e:
        logger.error("Unexpected error in agent: %s", e)
        abort_with_message(500, "Unexpected error.")
