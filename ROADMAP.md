# Roadmap

Release timing and breaking changes, for projects building on the API.
Features live in the issue tracker; dates here are estimates.

## Versioning

Semver applies to the HTTP API, config options and env vars, not to Python internals.
Only majors break: minors add, patches fix. Deprecations are announced in a minor and
removed no earlier than the next major.

Exception: an optional feature can be removed in a minor, at the earliest one minor after
its deprecation, if neither clients nor deployments have to change. Its config options
and API parameters are then still accepted but ignored.

## Releases

| Version | Target | Gramps | Breaking changes |
|---|---|---|---|
| 3.24.x | current | 6.0 | none |
| 3.25.0 | early November 2026 | 6.0 | semantic search removed |
| 3.x | as needed | 6.0 | none |
| 4.0.0 | TBD | 6.1 | multi-tree by default, removals below |
| 5.0.0 | TBD | 6.2 | TBD |

## Notable in 3.24

- User database migrations for task locking (#1049) and web push (#1001)
- Configuration via the database is deprecated (#1050)
- The non-shared `PostgreSQL` backend is deprecated (#981)
- The server locale is always English, regardless of `LANG`/`LC_*` (#1042)
- Media archives are stored in `EXPORT_DIR/media_archives/<tree>/` (or the media bucket) and expire by age instead of being deleted on download (#1059)
- Search reindexing after import or restore runs as separate tasks, so the import task finishes before search is up to date (#1046)
- Remove support for Python 3.10 (#1067)
- Semantic search is deprecated, with a warning if `VECTOR_EMBEDDING_MODEL` is set

## Notable in 3.25

- Semantic search is removed (#1074). `VECTOR_EMBEDDING_MODEL`, the `semantic` parameter of
  `/search/` and `/search/index/` and the `--semantic` option of the `search` CLI command
  are still accepted but ignored. `server.semantic_search` in `/metadata/` is always false
- The Docker images no longer contain PyTorch, Sentence Transformers or an embedding model

## Breaking in 4.0

> Note: Depending on the (unknown) release date of Gramps 6.1, these breaking changes may be moved to 5.0 instead.

Multi-tree mode becomes the default and single-tree mode goes away
([#885](https://github.com/gramps-project/gramps-web-api/issues/885)).

| Removed | Replacement |
|---|---|
| Unprefixed env vars (`TREE`, `SECRET_KEY`, …) | `GRAMPSWEB_*` |
| `SEARCH_INDEX_DIR` | `SEARCH_INDEX_DB_URI` |
| `EMAIL_USE_TLS` | `EMAIL_USE_SSL` / `EMAIL_USE_STARTTLS` |
| `GET /api/token/create_owner/` | `POST` on same endpoint |
| `tree` arg on `GET /api/oidc/login/` | Tree selection after login |

Support for the `PostgreSQL` backend will be dropped in 4.0, because it is not compatible with multi-tree mode. Note that both the `SharedPostgreSQL` and `SQLite` backends will continue to be fully supported.

Configuration via the database is removed in 4.0, so that all configuration is in env vars or config files. The `config` table will be dropped, and the `config` API endpoints will return 404.