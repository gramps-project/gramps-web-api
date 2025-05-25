"""Functions for working with large language models (LLMs)."""

from __future__ import annotations

from flask import current_app
from openai import APIError, OpenAI, RateLimitError

from ..search import get_semantic_search_indexer
from ..util import abort_with_message, get_logger


def get_client(config: dict) -> OpenAI:
    """Get an OpenAI client instance."""
    if not config.get("LLM_MODEL"):
        raise ValueError("No LLM specified")
    return OpenAI(base_url=config.get("LLM_BASE_URL"))


def sanitize_answer(answer: str) -> str:
    """Sanitize the LLM answer."""
    # some models convert relative URLs to absolute URLs with this domain
    answer = answer.replace("https://www.example.com", "")
    return answer


def answer_prompt(prompt: str, system_prompt: str, config: dict | None = None) -> str:
    """Answer a question given a system prompt."""
    if not config:
        if current_app:
            config = current_app.config
        else:
            raise ValueError("Outside of the app context, config needs to be provided")

    messages = []

    if system_prompt:
        messages.append(
            {
                "role": "system",
                "content": str(system_prompt),
            }
        )

    messages.append(
        {
            "role": "user",
            "content": str(prompt),
        }
    )

    client = get_client(config=config)  # type: ignore
    model = config.get("LLM_MODEL")  # type: ignore
    assert model is not None, "No LLM model specified"  # mypy; shouldn't happen

    try:
        response = client.chat.completions.create(
            messages=messages,  # type: ignore
            model=model,
        )
    except RateLimitError:
        abort_with_message(500, "Chat API rate limit exceeded.")
    except APIError:
        abort_with_message(500, "Chat API error encountered.")
    except Exception:
        abort_with_message(500, "Unexpected error.")

    try:
        answer = response.to_dict()["choices"][0]["message"]["content"]  # type: ignore
    except (KeyError, IndexError):
        abort_with_message(500, "Error parsing chat API response.")
        raise  # mypy; unreachable

    return sanitize_answer(answer)


def answer_prompt_with_context(prompt: str, context: str) -> str:

    system_prompt = (
        "You are an assistant for answering questions about a user's family history. "
        "Use the following pieces of context retrieved from a genealogical database "
        "to answer the question. "
        "If you don't know the answer, just say that you don't know. "
        "Use three sentences maximum and keep the answer concise."
        "In your answer, preserve relative Markdown links."
    )

    system_prompt = f"""{system_prompt}\n\n{context}"""
    return answer_prompt(prompt=prompt, system_prompt=system_prompt)


def contextualize_prompt(prompt: str, context: str) -> str:

    system_prompt = (
        "Given a chat history and the latest user question "
        "which might reference context in the chat history, "
        "formulate a standalone question which can be understood "
        "without the chat history. Do NOT answer the question, "
        "just reformulate it if needed and otherwise return it as is."
    )

    system_prompt = f"""{system_prompt}\n\n{context}"""

    return answer_prompt(prompt=prompt, system_prompt=system_prompt)


def retrieve(tree: str, prompt: str, include_private: bool, num_results: int = 10):
    searcher = get_semantic_search_indexer(tree)
    total, hits = searcher.search(
        query=prompt,
        page=1,
        pagesize=num_results,
        include_private=include_private,
        include_content=True,
    )
    return [hit["content"] for hit in hits]


def answer_prompt_retrieve(
    prompt: str,
    tree: str,
    include_private: bool,
    history: list | None = None,
) -> str:
    logger = get_logger()

    if not history:
        # no chat history present - we directly retrieve the context

        search_results = retrieve(
            prompt=prompt, tree=tree, include_private=include_private, num_results=20
        )
        if not search_results:
            abort_with_message(500, "Unexpected problem while retrieving context")

        context = ""
        max_length = current_app.config["LLM_MAX_CONTEXT_LENGTH"]
        for search_result in search_results:
            if len(context) + len(search_result) > max_length:
                break
            context += search_result + "\n\n"
        context = context.strip()

        logger.debug("Answering prompt '%s' with context '%s'", prompt, context)
        logger.debug("Context length: %s characters", len(context))
        return answer_prompt_with_context(prompt=prompt, context=context)

    # chat history is present - we first need to call the LLM to merge the history
    # and the prompt into a new, standalone prompt.

    context = ""
    for message in history:
        if "role" not in message or "message" not in message:
            raise ValueError(f"Invalid message format: {message}")
        if message["role"].lower() in ["ai", "system", "assistant"]:
            context += f"*Assistant message:* {message['message']}\n\n"
        elif message["role"].lower() == "error":
            pass
        else:
            context += f"*Human message:* {message['message']}\n\n"
    context = context.strip()

    logger.debug("Contextualizing prompt '%s' with context '%s'", prompt, context)
    new_prompt = contextualize_prompt(prompt=prompt, context=context)
    logger.debug("New prompt: '%s'", new_prompt)

    # we can now feed the standalone prompt into the same function but without history.
    return answer_prompt_retrieve(
        prompt=new_prompt, tree=tree, include_private=include_private
    )
