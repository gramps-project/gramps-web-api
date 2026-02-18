# Gramps Web API

This is the repository for **Gramps Web API**, a Python REST API for [Gramps](https://gramps-project.org).

It allows to query and manipulate a [Gramps](https://gramps-project.org) family tree database via the web.

Gramps Web API is the backend of [Gramps Web](https://www.grampsweb.org/), a genealogy web app based on Gramps, but can also be used as backend for other tools.

## More information

- API documentation for Gramps Web API: https://gramps-project.github.io/gramps-web-api/
- Developer documentation for Gramps Web API: https://www.grampsweb.org/dev-backend/
- Documentation for Gramps Web: https://www.grampsweb.org

## Remote Embedding API

By default, Gramps Web API uses a local [SentenceTransformers](https://www.sbert.net/) model for semantic search embeddings. You can optionally use a remote OpenAI-compatible embedding API (e.g. Ollama, OpenAI, LiteLLM) instead.

| Environment Variable | Description | Default |
|---|---|---|
| `GRAMPSWEB_VECTOR_EMBEDDING_MODEL` | Model name for semantic search embeddings | `""` (disabled) |
| `GRAMPSWEB_EMBEDDING_BASE_URL` | Base URL for a remote OpenAI-compatible embedding API | `None` (use local model) |
| `GRAMPSWEB_EMBEDDING_API_KEY` | API key for authenticated embedding providers | `None` |

**Ollama example:**

```bash
GRAMPSWEB_VECTOR_EMBEDDING_MODEL=nomic-embed-text
GRAMPSWEB_EMBEDDING_BASE_URL=http://localhost:11434
```

**OpenAI example:**

```bash
GRAMPSWEB_VECTOR_EMBEDDING_MODEL=text-embedding-3-small
GRAMPSWEB_EMBEDDING_BASE_URL=https://api.openai.com/v1
GRAMPSWEB_EMBEDDING_API_KEY=sk-...
```

> **Note:** Changing the embedding model requires reindexing all records, since different models produce vectors with different dimensions.

## Related projects

- Gramps Web frontend repository: https://github.com/gramps-project/gramps-web
