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
| 3.25.x | current | 6.0 | semantic search removed |
| 3.26.0 | late November 2026 | 6.0 | Gramps QL removed, `/query/` request body |
| 3.x | as needed | 6.0 | none |
| 4.0.0 | TBD | 6.1 | multi-tree by default, removals below |
| 5.0.0 | TBD | 6.2 | TBD |

## Breaking in 3.26

The `gql` query parameter on object list endpoints (Gramps QL) is removed, together with
the `gramps_ql` key in `GET /api/metadata/`. Requests using `gql` are rejected with 422.
Use the `MatchesQuery` filter rule with a GOQL query in `rules` instead.

The `POST /api/<objects>/query/` endpoints take every part of a query that names fields
only as a [GOQL](https://github.com/dsblank/gramps-object-query-language) string
([#1164](https://github.com/gramps-project/gramps-web-api/pull/1164)). The removed JSON
forms repeated GOQL's grammar, and no known client used them except gramps-connect's
`order_by` objects; gramps-connect switches with this release.

| Removed | Replacement |
|---|---|
| `where` (JSON condition tree) | `where_expr`, e.g. `"gender == 1"` |
| `select` entries as objects (`{"json_path": [...], "as": ...}`, `{"count_of": ...}`) | strings, e.g. `"birth.date as b"`, `"count(events) as n"` |
| `order_by` entries as objects (`{"column": ..., "direction": ...}`) | strings, `-` for descending, e.g. `"-change"` |

A request with a removed form gets a 422. New: an `env` field supplies values for
`Env.NAME` in `where_expr`.

A 422 for a query string now has a short `message` naming the body field
(`"Invalid 'where_expr'"`), `type: "invalid_query"`, and GOQL's full text in
`messages`, keyed like a schema error: `{"json": {"where_expr": ["..."]}}`, with the
entry index for `select` and `order_by` (`{"json": {"select": {"1": ["..."]}}}`).

GOQL's syntax is now part of the API contract, and
`tests/test_endpoints/test_query_conformance.py` checks that the strings clients send
keep their meaning when GOQL is upgraded.

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