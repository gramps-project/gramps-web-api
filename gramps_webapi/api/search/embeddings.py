"""Functions to compute vector embeddings."""

from ..util import get_logger


def embedding_function_factory(model: str):
    logger = get_logger()

    logger.debug("Initializing embedding model.")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model)
    logger.debug("Done initializing embedding model.")

    def embedding_function(queries: list[str]):
        # import numpy as np

        # return np.random.rand(len(queries), 348)
        # print(len(queries))
        return model.encode(queries)

    return embedding_function
