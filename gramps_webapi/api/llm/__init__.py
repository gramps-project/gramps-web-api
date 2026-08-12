"""Functions for working with large language models (LLMs)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from flask import current_app
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    ModelRetry,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pydantic_ai.usage import UsageLimits

from ..util import abort_with_message, get_logger
from .agent import create_agent
from .deps import AgentDeps


def sanitize_answer(answer: str) -> str:
    """Sanitize the LLM answer."""
    # some models convert relative URLs to absolute URLs with placeholder domains
    answer = answer.replace("https://www.example.com", "")
    answer = answer.replace("https://example.com", "")
    answer = answer.replace("http://example.com", "")
    return answer


def extract_metadata_from_result(result) -> dict[str, Any]:
    """Extract metadata from AgentRunResult.

    Args:
        result: AgentRunResult from Pydantic AI

    Returns:
        Dictionary containing run metadata including tool calls
    """
    tools_used: list[dict[str, Any]] = []
    tool_call_map = {}
    step = 0

    for msg in result.all_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    step += 1
                    tool_call_id = part.tool_call_id
                    tool_info = {
                        "step": step,
                        "name": part.tool_name,
                        "args": (
                            part.args_as_dict()
                            if hasattr(part, "args_as_dict")
                            else part.args
                        ),
                    }
                    tool_call_map[tool_call_id] = tool_info

        elif isinstance(msg, ModelRequest):
            # ModelRequest.parts can contain ToolReturnPart among other types
            for part in msg.parts:  # type: ignore[assignment]
                if isinstance(part, ToolReturnPart):
                    tool_call_id = part.tool_call_id
                    if tool_call_id in tool_call_map:
                        tools_used.append(tool_call_map[tool_call_id])

    usage = result.usage
    metadata = {
        "run_id": result.run_id,
        "timestamp": result.timestamp.isoformat(),
        "usage": {
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "tool_calls": usage.tool_calls,
        },
        "tools_used": tools_used,
    }

    return metadata


def answer_with_agent(
    prompt: str,
    tree: str,
    include_private: bool,
    user_id: str,
    history: list | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    message_history_raw: str | None = None,
):
    """Answer a prompt using Pydantic AI agent.

    Args:
        prompt: The user's question/prompt
        tree: The tree identifier
        include_private: Whether to include private information
        user_id: The user identifier
        history: Optional chat history (legacy {role, message} pairs)
        progress_callback: Optional callback fired at the start of each tool call
        message_history_raw: Serialized message history from a previous response.
            When provided, takes precedence over history.

    Returns:
        AgentRunResult containing the response and metadata
    """
    logger = get_logger()

    # Get configuration
    config = current_app.config
    model_name = config.get("LLM_MODEL")
    base_url = config.get("LLM_BASE_URL")
    max_context_length = config.get("LLM_MAX_CONTEXT_LENGTH", 50000)
    system_prompt_override = config.get("LLM_SYSTEM_PROMPT")
    max_requests = config.get("LLM_MAX_REQUESTS", 15)
    max_tokens = config.get("LLM_MAX_TOKENS", 200_000)

    if not model_name:
        raise ValueError("No LLM model specified")

    agent = create_agent(
        model_name=model_name,
        base_url=base_url,
        system_prompt_override=system_prompt_override,
    )

    deps = AgentDeps(
        tree=tree,
        include_private=include_private,
        max_context_length=max_context_length,
        user_id=user_id,
        progress_callback=progress_callback,
    )

    message_history: list[ModelRequest | ModelResponse] = []
    if message_history_raw:
        try:
            message_history = ModelMessagesTypeAdapter.validate_json(message_history_raw)
        except Exception as e:  # pylint: disable=broad-except
            raise ValueError(f"Invalid message_history_raw: {e}") from e
    elif history:
        for message in history:
            if "role" not in message or "message" not in message:
                raise ValueError(f"Invalid message format: {message}")
            role = message["role"].lower()
            if role in ["ai", "system", "assistant"]:
                message_history.append(
                    ModelResponse(
                        parts=[TextPart(content=message["message"])],
                    )
                )
            elif role != "error":  # skip error messages
                message_history.append(
                    ModelRequest(parts=[UserPromptPart(content=message["message"])])
                )

    usage_limits = UsageLimits(
        request_limit=max_requests,
        total_tokens_limit=max_tokens,
    )

    try:
        logger.debug("Running Pydantic AI agent with prompt: '%s'", prompt)
        result = agent.run_sync(
            prompt,
            deps=deps,
            message_history=message_history,
            usage_limits=usage_limits,
        )
        logger.debug("Agent response: '%s'", result.response.text or "")
        return result
    except UsageLimitExceeded as e:
        logger.warning("Agent usage limit exceeded: %s", e)
        abort_with_message(429, "The AI agent exceeded its usage limits for this request.")
    except ModelHTTPError as e:
        logger.error("Model provider returned an error: %s", e)
        if e.status_code == 429:
            abort_with_message(
                429, "The AI model provider is rate limiting requests. Please try again later."
            )
        if e.status_code in (502, 503, 504, 529):
            # 529 is Anthropic's "overloaded"
            abort_with_message(503, "The AI model provider is temporarily unavailable.")
        abort_with_message(502, "The AI model provider returned an error.")
    except httpx.TimeoutException as e:
        logger.error("Model provider request timed out: %r", e)
        abort_with_message(504, "The AI model did not respond in time. Please try again.")
    except (ModelAPIError, httpx.TransportError) as e:
        # connection refused, DNS failure, protocol error, or an SDK-wrapped equivalent
        logger.error("Model provider request failed: %r", e)
        abort_with_message(503, "The AI model provider is temporarily unavailable.")
    except (UnexpectedModelBehavior, ModelRetry) as e:
        logger.error("Pydantic AI error: %s", e)
        abort_with_message(500, "Error communicating with the AI model")
    except Exception:
        logger.exception("Unexpected error in agent")
        abort_with_message(500, "Unexpected error.")
