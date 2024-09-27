"""Functions to compute vector embeddings."""

from __future__ import annotations

from ..util import get_logger


def embedding_function_factory(model_name: str):
    model = load_model(model_name)

    def embedding_function(queries: list[str]):
        return model.encode(queries)

    return embedding_function


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
