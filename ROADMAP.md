# Roadmap

Rough timelines and planned breaking changes, so projects building on the API can
plan ahead. Not a commitment, not an issue tracker.

## Versioning

Semver applies to the HTTP API, config options and env vars, not to Python internals.
Only majors break: minors add, patches fix. Deprecations are announced in a minor and
removed no earlier than the next major.

## Releases

| Version | Target | Gramps | Focus |
|---|---|---|---|
| 3.21.x | current | 6.0 | Fixes only |
| 3.22.0 | September 2026 | 6.0 | Features |
| 3.x | as needed | 6.0 | Features |
| 4.0.0 | TBD | 6.0, 6.1 or 6.2 (open) | Multi-tree by default, removal of deprecations |

## Breaking in 4.0

Multi-tree mode becomes the default and single-tree mode goes away
([#885](https://github.com/gramps-project/gramps-web-api/issues/885)).

| Removed | Replacement |
|---|---|
| Unprefixed env vars (`TREE`, `SECRET_KEY`, …) | `GRAMPSWEB_*` |
| `SEARCH_INDEX_DIR` | `SEARCH_INDEX_DB_URI` |
| `EMAIL_USE_TLS` | `EMAIL_USE_SSL` / `EMAIL_USE_STARTTLS` |
| `GET /api/token/create_owner/` | `POST` on same endpoint |
| `tree` arg on `GET /api/oidc/login/` | Tree selection after login |
