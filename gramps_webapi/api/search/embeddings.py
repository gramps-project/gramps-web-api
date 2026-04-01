"""Functions to compute vector embeddings."""

from typing import Callable, List, Optional

import requests

from ..util import get_logger


def load_model(model_name: str):
    """Load the sentence transformer model.

    Since the model takes time to load and is subsequently cached,
    this can also be used for preloading the model in the flask app.
    """
    logger = get_logger()
    logger.debug("Initializing embedding model.")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    logger.debug("Done initializing embedding model.")
    return model


def create_remote_embedding_function(
    base_url: str, model_name: str, api_key: Optional[str] = None
) -> Callable[[List[str]], List[List[float]]]:
    """Create an embedding function that calls a remote OpenAI-compatible API.

    Returns a callable with signature (texts: list[str]) -> list[list[float]].
    """
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[:-3]
    url = f"{stripped}/v1/embeddings"

    def _embed(texts: List[str]) -> List[List[float]]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": model_name, "input": texts}
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()["data"]
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    return _embed
