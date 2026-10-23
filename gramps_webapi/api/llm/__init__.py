"""Functions for working with large language models (LLMs)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx
from flask import current_app
from openai import OpenAIError
from pydantic_ai import ModelMessagesTypeAdapter, capture_run_messages
from pydantic_ai.exceptions import (
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    ModelRetry,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ..util import abort_with_message, close_db, get_db_outside_request, get_logger
from .agent import create_agent
from .deps import AgentDeps

# e.g. https://www.example.com, followed by the path of a link
_PLACEHOLDER_ORIGIN = re.compile(r"https?://(?:[\w-]+\.)*example\.(?:com|org|net)(?=/)")


def sanitize_answer(answer: str) -> str:
    """Sanitize the LLM answer."""
    # some models convert relative URLs to absolute URLs with placeholder domains
    return _PLACEHOLDER_ORIGIN.sub("", answer)


# object types of links like [Name](/person/I0044) that have a Gramps ID
LINK_TYPES = (
    "person",
    "family",
    "event",
    "place",
    "source",
    "citation",
    "repository",
    "media",
    "note",
)
_LINK = re.compile(rf"\[([^\]]*)\]\(/({'|'.join(LINK_TYPES)})/([^)\s]+)\)")


def clean_answer(answer: str, tree: str, include_private: bool, user_id: str) -> str:
    """Sanitize the LLM answer and remove links to objects the user cannot see.

    Models sometimes link made-up Gramps IDs, e.g. for people they know from
    general knowledge but the tree does not contain. Such links are replaced
    by their text.
    """
    answer = sanitize_answer(answer)
    if not _LINK.search(answer):
        return answer
    db_handle = get_db_outside_request(
        tree=tree, view_private=include_private, readonly=True, user_id=user_id
    )
    try:

        def replace(match: re.Match) -> str:
            text, obj_type, gramps_id = match.groups()
            get_obj = getattr(db_handle, f"get_{obj_type}_from_gramps_id")
            if get_obj(gramps_id) is None:
                get_logger().warning("Removed AI answer link to missing %s", gramps_id)
                return text
            return match.group(0)

        return _LINK.sub(replace, answer)
    finally:
        close_db(db_handle)


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


def _output_limit_reached(messages: list[ModelMessage]) -> bool:
    """Whether the last model response was cut off at the output token limit."""
    responses = [msg for msg in messages if isinstance(msg, ModelResponse)]
    return bool(responses) and responses[-1].finish_reason == "length"


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
    max_output_tokens = config.get("LLM_MAX_OUTPUT_TOKENS")

    if not model_name:
        logger.error("No LLM model specified")
        abort_with_message(500, "The AI model is not configured correctly.")

    try:
        agent = create_agent(
            model_name=model_name,
            base_url=base_url,
            system_prompt_override=system_prompt_override,
        )
    except (UserError, ValueError, OpenAIError) as e:
        # e.g. unknown provider prefix or missing provider API key/base URL
        logger.error("Failed to set up the AI model '%s': %s", model_name, e)
        abort_with_message(500, "The AI model is not configured correctly.")

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
            message_history = ModelMessagesTypeAdapter.validate_json(
                message_history_raw
            )
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

    messages: list[ModelMessage] = []
    try:
        logger.debug("Running Pydantic AI agent with prompt: '%s'", prompt)
        with capture_run_messages() as messages:
            result = agent.run_sync(
                prompt,
                deps=deps,
                message_history=message_history,
                usage_limits=usage_limits,
                # no default, as providers reject values above the model's limit
                model_settings=(
                    ModelSettings(max_tokens=max_output_tokens)
                    if max_output_tokens
                    else None
                ),
            )
        logger.debug("Agent response: '%s'", result.response.text or "")
        if result.response.finish_reason == "length":
            logger.warning(
                "AI answer cut off at the output token limit, see "
                "LLM_MAX_OUTPUT_TOKENS"
            )
        return result
    except UsageLimitExceeded as e:
        logger.warning("Agent usage limit exceeded: %s", e)
        abort_with_message(
            429, "The AI agent exceeded its usage limits for this request."
        )
    except ModelHTTPError as e:
        logger.error("Model provider returned an error: %s", e)
        if e.status_code == 429:
            abort_with_message(
                429,
                "The AI model provider is rate limiting requests. Please try again later.",
            )
        if e.status_code in (502, 503, 504, 529):
            # 529 is Anthropic's "overloaded"
            abort_with_message(503, "The AI model provider is temporarily unavailable.")
        abort_with_message(502, "The AI model provider returned an error.")
    except httpx.TimeoutException as e:
        logger.error("Model provider request timed out: %r", e)
        abort_with_message(
            504, "The AI model did not respond in time. Please try again."
        )
    except (ModelAPIError, httpx.TransportError) as e:
        # connection refused, DNS failure, protocol error, or an SDK-wrapped equivalent
        logger.error("Model provider request failed: %r", e)
        abort_with_message(503, "The AI model provider is temporarily unavailable.")
    except (UnexpectedModelBehavior, ModelRetry) as e:
        if isinstance(e, IncompleteToolCall) or _output_limit_reached(messages):
            logger.warning(
                "AI model response cut off at the output token limit, see "
                "LLM_MAX_OUTPUT_TOKENS"
            )
            abort_with_message(
                400, "The AI model's response exceeded its output token limit."
            )
        logger.error("Pydantic AI error: %s", e)
        abort_with_message(500, "Error communicating with the AI model")
    except Exception:
        logger.exception("Unexpected error in agent")
        abort_with_message(500, "Unexpected error.")
