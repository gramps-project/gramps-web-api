# Fast paged/filtered/sorted queries in gramps-web-api — PR plan

## Context

This spins out of the `gramps-connect` planning work (see `PLAN.md`), specifically Layer 4
("filter pushdown fix"), which turned out to be a bigger and more interesting problem than
originally scoped once we actually measured things. This file is scoped to just that problem,
as a standalone PR (or small PR series) against `gramps-web-api`, independent of the rest of
the `gramps-connect` monorepo.

**The bet**: this is the key change needed to make a new version of Gramps fast on large
(100k+ person) datasets — not a local-first cache, not real-time collaboration, just making
the existing web API's list/filter/sort/page path actually use SQL instead of deserializing
everything.

## Grounding — verified this session, not from memory

- **The original discourse-thread bug** (linked from `PLAN.md`) is confirmed still live:
  `GrampsObjectsResource.get()` (`gramps_webapi/api/resources/base.py:589-620`) unconditionally
  does `objects = list(iter_objects_method())` — full deserialization of every object — before
  any filter, sort, or page is applied. Sorting (`sort_objects`) and pagination
  (`objects[offset : offset + pagesize]`) both happen afterward, in Python, on the fully
  materialized list.
- **Measured independently against a real 100k-person tree** (gramps-bench generated,
  imported via the real `/api/importers/gramps/file` endpoint): `GET /api/people/?page=1` and
  `?page=999` both took ~8 seconds, flat regardless of offset — confirming the whole table is
  processed every time regardless of which page is requested. This matches the original
  discourse post's own number almost exactly (8.26s there vs. 7.6–8.5s here, independently
  measured on different data).
- **A real but unused/incomplete fast path already exists**: `gramps_webapi/api/util.py` has
  `is_dbapi = isinstance(self.basedb, DBAPI)` gating `_iter_handles()`, which runs
  `SELECT handle FROM person WHERE private=0` directly via `db.dbapi.execute()`/`.fetchall()`,
  bypassing object deserialization. This is real, committed, shipped code — but:
  - `GrampsObjectsResource.get()` doesn't call it at all; it uses the raw `iter_objects_method()`
    path directly.
  - Even where it is used, `isinstance(basedb, DBAPI)` excludes `SharedPostgreSQL` — confirmed
    via class hierarchy: `SharedDBAPI(DbGeneric)` and `DBAPI(DbGeneric)`
    (`shareddbapi.py:78`, `dbapi.py:103`) are **sibling classes**, not parent/child, despite
    near-identical structure (including a duplicated copy of `_create_secondary_columns()`).
    `SharedPostgreSQL` is the backend actually deployed in production per `PLAN.md`'s grounding
    notes, so the one existing fast path currently excludes exactly the backend that needs it.
  - There is a separate, untracked (`?? gramps_webapi/api/resources/summary.py`, not committed,
    not wired to any route) sketch of a similar idea with the same `isinstance(basedb, DBAPI)`
    gap, and no filter/sort/page support at all — not usable as-is, only as a minimal reference
    for the `db.dbapi.execute()` calling convention and its privacy-check pattern
    (`WHERE private=0` unless `PERM_VIEW_PRIVATE`).
- **`page`/`pagesize` already exist as query params** (`base.py`, `PageInfoSchema`) but only
  slice the fully-materialized list — see above. Fixing filtering without also fixing this
  would leave pagination just as broken.
- **Name sorting is genuinely complex and not something to reimplement**: `Sort.by_person_surname_key`
  (`gramps_webapi/api/resources/sort.py:73`) uses `Name.get_surname()` + `locale.sort_key()`
  (ICU collation or `strxfrm`, `grampslocale.py:793`); the richer `by_person_sorted_name_key`
  goes through `NameDisplay.sorted_name()` → `name.sort_as` → a pluggable per-record format
  table (`name.py:969`). None of this is a fixed algorithm — it's genuinely
  locale/format-dependent.
  - However: `Surname.get_schema()` (`gen/lib/surname.py:103`) already stores `prefix` and
    `surname` as **separate fields** — "van Dam" is already `prefix="van"`, `surname="Dam"` at
    the data level. The existing `given_name`/`surname` secondary columns (derived via
    `_get_person_data()`, `gen/db/generic.py:2736`) already read only `.surname`, not a merged
    string — so they're already prefix-excluded, matching common library/genealogical sort
    convention, with no extra work needed.
  - Known existing approximation, not introduced by this plan: `_get_person_data()` takes
    `surname_list[0]`, not whichever entry has `primary=True`. Pre-existing behavior in Gramps'
    own dbapi backend, not something this PR changes.
- **This work does not require touching gramps core.** Unlike the "accelerate arbitrary filter
  rules" problem (see `dsblank/gramps#2177`, open, adds `register_rule_override` to
  `DbReadBase` — a genuinely separate, complementary effort, further discussed below), pushing
  flat-column filter/sort/page to SQL only needs `db.dbapi.execute()`, which already exists and
  is already used elsewhere in gramps-web-api. This keeps `gramps-connect`'s "gramps core
  unmodified, consumed as-is" decision intact for this specific piece.
- **Separately confirmed, explicitly out of scope for this PR**: bulk XML import
  (`/api/importers/gramps/file`) is badly super-linear — 20m03s for 100k people vs. a few
  seconds for 3,000 in our own testing (>100x slower for 33x more data). Real problem, wrong
  subsystem — import and list/filter/sort/page are unrelated code paths. Worth its own
  investigation later.
- **`SharedPostgreSQL`'s `_hack_query()` blind string-replace hack is being phased out upstream —
  but not on the backend this plan targets, not yet.** Confirmed via direct `addons-source` repo
  inspection (later session): PR `gramps-project/addons-source#943` ("replace `_hack_query()`
  with proper dialect methods") landed on the **`PostgreSQL`** addon (single-user backend, on
  `maintenance/gramps61`+ branches) — *not* `SharedPostgreSQL` (the multi-user backend
  gramps-web-api actually targets per `PLAN.md`'s grounding). `SharedPostgreSQL/sharedpostgresql.py`
  still has the old `_hack_query()` on every branch checked (`maintenance/gramps60`,
  `maintenance/gramps61`, and the local working copies). Porting to `SharedPostgreSQL` is planned
  but not done as of this note. Two details worth carrying forward once it lands:
  - The `?`→`%s` qmark-to-format placeholder translation survives, just narrower (per commit
    `cdca6f9d3`): `Connection.execute()` keeps doing qmark→format and `REGEXP`→`~`. This plan's
    `?`-style compiled SQL (see Design §2) needs no changes when the port happens.
  - `desc` (a reserved word in Postgres, and a real `Media` secondary column) is now handled by
    quoting (`_quote_column()`) rather than physically renaming the column to `desc_`. Marked for
    removal once gramps core PR `#2178` (adds `_quote_column` to the `DBAPI` base) merges — a
    second upstream gramps-core PR, alongside `#2177` below. Only matters once `Media` support is
    added (explicit non-goal here); the compiler will need to quote identifiers selectively at
    that point, not before.
- **`Like`'s case-sensitivity is not portable across backends, and the upstream `_hack_query`
  removal doesn't fix it.** Confirmed by reading the updated `PostgreSQL` addon's
  `Connection.execute()` (`maintenance/gramps61`, post-`#943`): it translates only `?`→`%s` and
  `REGEXP`→`~` (plus `BLOB`/`LIMIT` rewrites) — no `LIKE`→`ILIKE` translation, no pattern
  case-folding. SQLite's `LIKE` is case-insensitive for ASCII by default; PostgreSQL's `LIKE` is
  case-sensitive (`ILIKE` is the case-insensitive form there). So `query.py`'s `Like` expression
  (`gramps_webapi/api/query.py`) will silently behave differently per backend today —
  `Like("surname", "smith%")` matches "Smith" on SQLite, not on PostgreSQL. Not fixed by this
  plan; not fixed upstream either. **Planned follow-up**: a PR against `addons-source`'s
  `PostgreSQL` and `SharedPostgreSQL` backends to translate `LIKE`→`ILIKE` (or equivalent) so
  case-insensitive matching is consistent across backends, mirroring the existing
  `REGEXP`→`~` translation. Out of scope for gramps-web-api itself once that lands, but until it
  does, gramps-web-api callers should not assume `Like` is case-insensitive on PostgreSQL.
- **Live-verified against a real 100k-person `SharedPostgreSQL` database (later session), not
  just SQLite.** A local PostgreSQL 16 instance + the un-migrated `SharedPostgreSQL` addon
  (confirmed still un-migrated per the note above) were used to actually run the plan's own
  "Verification plan" methodology end to end, not just reason about it. Bulk-loading tip worth
  keeping: rather than the known-slow XML import path (~20 min for 100k people, see the bulk-XML
  grounding note above), a pre-existing fully-imported 100k-person SQLite tree was bulk-copied
  directly into the Postgres tables (adding `treeid`) via `psycopg2`'s `COPY`, bypassing all
  per-object Python processing — 2.8M+ rows across 11 tables in ~23 seconds. Three things learned
  that change or sharpen earlier notes:
  - **The `_hack_query()` corruption is worse than the `Media.desc` note above implies, but also
    self-correcting, and the two facts cancel out.** It's not a one-time DDL-time rename: the
    *same* blind `.replace("desc", "desc_")` also runs inside `Connection.execute()` on **every
    query**, not just schema creation. Confirmed live: `event.description` (which merely
    *contains* "desc" as a substring) is physically stored as `desc_ription`, corrupted by the
    exact same mechanism as `Media.desc`. First attempt at a fix (a static
    logical-name→physical-name override table in `query.py`) was wrong and made it worse —
    since the runtime hack already transforms a plain, correct `description` into the correct
    `desc_ription` on its own, adding a compensating override caused *double* corruption
    (`desc_ription` → `desc__ription`). Correct fix, verified live: emit plain logical column
    names (`query.py`'s existing `_quote_column()`, no override) and let the live backend's own
    hack do the (identical, idempotent-per-request) transformation it already does for every
    other existing gramps-web-api/gramps-core query against this backend. No code change was
    needed beyond what Design §6 already had — the override attempt was reverted.
  - **The addon's `CREATE COLLATION` uses the `libc` provider, not `icu`**, despite this plan's
    original Phase 4 sketch assuming ICU (`provider = icu`). Confirmed via
    `sharedpostgresql.py`'s `check_collation()`: plain `CREATE COLLATION "%s" (LOCALE = '%s')`,
    no `provider` clause. This means a requested locale (e.g. `de_DE.UTF-8`) must actually be
    `locale-gen`-installed on the Postgres *server's* OS for `check_collation()` to succeed — a
    real deployment prerequisite this plan hadn't flagged. Confirmed working end-to-end once the
    locale was generated and Postgres restarted to pick up the regenerated locale archive.
  - **A privacy-test bug in this plan's own test suite, not the endpoint code.** The live
    100k-row dataset (with real private records, unlike `example_gramps`) caught that
    `tests/test_endpoints/test_people_query.py`'s `test_private_people_excluded_without_permission`
    used `ROLE_MEMBER` as the "lacks `PERM_VIEW_PRIVATE`" role — but `PERMISSIONS[ROLE_MEMBER]`
    already grants `PERM_VIEW_PRIVATE` in this codebase (`ROLE_GUEST` is the actual baseline
    without it). The test passed the whole time anyway, vacuously: `example_gramps` has zero
    private people, so `assertGreaterEqual(owner_count, member_count)` held regardless of whether
    filtering worked. Fixed to use `ROLE_GUEST` and to create-then-delete one real private person
    so the check can't pass vacuously again.
  - **Performance result**: `GET /api/people/?page=1`/`?page=999` reproduced the original bug
    exactly on live Postgres (10.8s / 7.6s, flat regardless of page). `POST /api/people/query/`:
    2.2s cold first query, then ~49ms/request walking forward via keyset to a simulated "page
    999" depth (~19,800 rows deep, 99 requests in 4.6-4.9s), and 0.043-0.057s for a query
    starting at that depth — confirming the plan's core bet (flat, fast, depth-independent) holds
    on real Postgres with real data, not just SQLite.

## Non-goals (explicit)

- **Relationship-graph filter rules** (`IsDescendantOf`, `HasCommonAncestorWith`, anything
  walking `family_list`/`event_ref_list`/etc.) are not solved by this. Those need either the
  slow path (as today) or `dsblank/gramps#2177`'s per-rule override mechanism — a different,
  complementary fix at a different layer. This PR only accelerates comparisons against the
  existing flat secondary columns (`gender`, `surname`, `given_name`, `gramps_id`, `private`,
  date-derived fields already flattened, etc.).
- **GraphQL.** Considered and explicitly rejected for now — it's an API contract layer, not a
  query execution fix; the actual open risk (does SQL pushdown work at all) is orthogonal to
  REST vs. GraphQL, and standing up a GraphQL server is a bigger commitment than this needs
  before that risk is retired.
- ~~**Multi-object-type support.** Scoped to `Person` only for the first PR...~~ **Superseded.**
  The pattern proved out small first (Person only, Phases 1-4), then was generalized to all ten
  object types once proven — see "Extending beyond Person" below. No longer a non-goal.
- **Bulk import performance.** See grounding notes above — real, but a separate subsystem.

## Design

### 1. Fix the `DBAPI` / `SharedDBAPI` gap

`isinstance(basedb, DBAPI)` is used in at least two places (`api/util.py`'s `is_dbapi`,
the untracked `summary.py` sketch) to gate SQL-fast-path code, and it currently excludes
`SharedPostgreSQL`. Smallest fix: check for the actual capability needed (a `.dbapi` attribute
exposing `.execute()`/`.fetchall()`) rather than a specific class — e.g. a small marker
protocol/mixin both `DBAPI` and `SharedDBAPI` satisfy, or a `hasattr(basedb, "dbapi")` check.
Standalone, low-risk, immediately unblocks everything else, and fixes the existing (currently
dead-for-Postgres) `_iter_handles()` fast path as a side effect.

### 2. A small query AST — expressions for `where` and `order_by` only

Not a general query language, not GraphQL, not raw SQL passthrough. `select`/`limit`/`after`
stay flat fields; only `where` and `order_by` need real tree structure:

```python
# WHERE — comparison leaves
Eq(column, value); Ne(column, value)
Lt(column, value); Lte(column, value)
Gt(column, value); Gte(column, value)
Like(column, pattern)
In(column, values)

# WHERE — boolean combinators
And(*exprs); Or(*exprs); Not(expr)

# ORDER BY — a list, multi-column sort is the common case
OrderBy(column, direction)  # "asc" | "desc"

# Top level
Query(
    select=["handle", "given_name", "surname"],  # whitelist-checked, flat list
    where=And(Eq("gender", 1), Like("surname", "A%")),
    order_by=[OrderBy("surname", "asc"), OrderBy("given_name", "asc")],
    limit=50,
    after=cursor_handle,  # keyset pagination, not OFFSET — see below
)
```

**Safety is structural, not enforced by escaping**: every column name in `select`/`where`/
`order_by` is checked against a fixed whitelist (the same secondary columns already flattened
server-side — `Person.get_secondary_fields()` plus derived `given_name`/`surname`) before the
compiler ever touches it. Values are always bound as query parameters, never string-interpolated.
There is no path from client input to a raw SQL string — the grammar is closed by construction.

### 3. Pagination: keyset (`after=<handle>`), not `OFFSET`

`OFFSET`-based pagination still degrades at depth even with SQL pushdown — the DB has to skip
N rows via the index either way. Given we already found the *current* implementation flat at
any depth (because it materializes everything, not because of `OFFSET` itself), doing this
properly the first time means keyset pagination from the start: `WHERE (surname, handle) >
(?, ?) ORDER BY surname, handle LIMIT ?` — using `handle` as a tiebreaker for stable ordering
when sort values collide. Avoids revisiting this later.

### 4. Locale-aware sorting via Postgres native collation, not reimplemented in Python or SQL

Per the grounding notes: sort by the already-separate `surname`/`given_name` columns directly
(no new precomputed "formatted name" column needed for the common case), with a `COLLATE`
clause chosen per-request from the caller's `locale` param (already threaded through
gramps-web-api requests today, e.g. `?locale=en`):

```sql
-- one-time setup per supported locale, not per query or per user.
-- Check pg_collation for existence first rather than CREATE COLLATION IF
-- NOT EXISTS, which needs PostgreSQL 12+ -- see grounding notes (fixed
-- upstream for the *PostgreSQL* addon in commit d8e352d9e; SharedPostgreSQL's
-- own check_collation() still uses CREATE COLLATION IF NOT EXISTS as of this
-- note, so this plan's own setup code should not copy that pattern either).
SELECT 1 FROM pg_collation WHERE collname = 'de-DE-icu';
-- if not found:
CREATE COLLATION "de-DE-icu" (provider = icu, locale = 'de-DE');

-- per request
SELECT handle, given_name, surname FROM person
WHERE gender = $1
ORDER BY surname COLLATE "de-DE-icu", given_name COLLATE "de-DE-icu"
LIMIT $2;
```

Known, accepted approximation: this sorts by the tree's canonical name representation (surname
excluding prefix, per-record `sort_as` format choices not replicated), not a per-viewing-user
format preference. Locale (collation) is per-request; name *format* is not.

### 5. Privacy, non-optional

Every compiled query includes `AND private = 0` unless the caller has `PERM_VIEW_PRIVATE`,
matching the one thing the untracked `summary.py` sketch already got right. Not a query option
— baked into the compiler so it can't be omitted by a malformed or malicious request.

### 6. Extending beyond `Person`: one `ObjectTypeSpec` + one thin resource per type

Once Phases 1-4 proved the pattern on `Person` alone, generalizing to the other nine object
types (`Family`, `Event`, `Place`, `Repository`, `Source`, `Citation`, `Media`, `Note`, `Tag`)
turned out to be mostly mechanical, matching the shape already sketched in "Relationship to
other in-flight work": an `ObjectTypeSpec` (table name, column whitelist, text-column subset for
`COLLATE` eligibility, `has_privacy` flag) built per type from `get_secondary_fields()`, plus a
shared `ObjectQueryResource` base class with `spec` as the only per-subclass difference — the
same pattern `GrampsObjectResourceHelper` subclasses already use with `gramps_class_name`
(`resources/people.py`/`families.py`). All ten specs live in `query.py`; all ten thin resource
classes (and the shared request/response schemas, response schema generalized from
`PersonQueryResponseSchema` to `ObjectQueryResponseSchema`) live in `resources/object_query.py`,
registered as `POST /api/<type>/query/` for each type.

Two things had to be handled that didn't matter with `Person` alone:
- **Not every type has a `private` column.** `Tag` doesn't. `ObjectTypeSpec.has_privacy` is
  derived (`"private" in columns`), not declared, and `compile_query()`/`_resolve_after()` both
  skip the privacy predicate when it's `False`.
- **`Media.desc` is a reserved SQL word on PostgreSQL** (see grounding notes on gramps core PR
  `#2178`). Rather than wait for that upstream fix, `query.py` gained a small, minimal
  `_quote_column()` (a hardcoded `{"desc", "order", "where", "select"}` set, mirroring
  addons-source's own `_quote_column()` list) applied everywhere a column name is interpolated
  into SQL — `SELECT`, `WHERE`, `ORDER BY`, and the keyset seek comparisons. A no-op for every
  column not on that list, so it changes no previously-compiled SQL text. This is addon-adjacent
  duplication that PR `#2178` would make unnecessary; kept deliberately minimal (a fixed list,
  not general identifier quoting) so it's easy to delete once core provides it.

## Relationship to other in-flight work

- **`dsblank/gramps#2177`** (open, gramps core): adds `register_rule_override` so DB backends
  can plug in fast implementations for individual named filter rules. Complementary, not
  overlapping — that's for rules needing relationship-graph traversal; this PR is for the flat
  secondary-column case, entirely within gramps-web-api, no gramps core changes needed.
- **gramps core PR `#2178`** (open): adds `_quote_column` to the `DBAPI` base class, so
  addon backends can quote reserved-word secondary columns (e.g. `Media.desc`) instead of
  physically renaming them. `query.py` grew its own minimal, addon-mirroring `_quote_column()`
  ahead of this landing (see Design §6) rather than blocking `Media` support on it; that local
  copy becomes removable once `#2178` merges.
- **`dsblank/object-ql`**: explored and set aside for this purpose — it compiles to Python
  expression evaluation (`eval`-shaped), which isn't a closed grammar and can't be mechanically
  compiled to SQL or safely whitelisted. The abstract AST above is a fresh, SQL-first design,
  not built on top of it.

## Phases

1. ✅ Fix the `DBAPI`/`SharedDBAPI` isinstance gap (small, standalone, easy to review in
   isolation). `hasattr(basedb, "dbapi")` in `api/util.py` and `resources/summary.py`.
2. ✅ Query AST + SQL compiler module (`api/query.py`): expression types, whitelist enforcement,
   parameterized emission. Unit-testable without a running server (`tests/test_query.py`).
3. ✅ Wired into a new `POST /api/people/query/` endpoint:
   `select`/`where`/`order_by`/`limit`/`after`, privacy-enforced.
4. ✅ Locale collation support: reuses gramps core's existing `Connection.check_collation()`
   (no new migration needed — it was already there) via `_resolve_collation()`; request-locale →
   collation name mapping, applied to text `ORDER BY` columns and their keyset comparisons.
   Caught and fixed a real bug in the first pass: resolving the system locale by default (rather
   than only on an explicit `locale` param) silently changed sort order for every request — see
   `tests/test_endpoints/test_people_query.py`'s
   `test_no_locale_uses_plain_codepoint_order_not_system_locale` regression test.
5. ✅ Extended beyond `Person` to all ten object types (Design §6) — done sooner than originally
   scoped, once Phases 1-4 proved the pattern held up in practice. `POST /api/<type>/query/` for
   `people`/`families`/`events`/`places`/`repositories`/`sources`/`citations`/`media`/`notes`/`tags`.

## Verification plan

✅ Executed live (later session) against a real 100k-person `SharedPostgreSQL` database — see the
"Live-verified against a real 100k-person `SharedPostgreSQL` database" grounding note above for
the full results and what it found. Summary:
- `gramps-bench`-generated 100k-person dataset — loaded via direct SQL bulk-copy from a
  pre-existing SQLite tree rather than the known-slow XML import endpoint (23s vs. ~20min for
  2.8M+ rows across 11 tables; the import endpoint itself remains a separate, unfixed issue, see
  the bulk-XML-import grounding note above).
- Before/after timing on `page=1` vs. `page=999`: old path reproduced the original flat-~8s bug
  exactly (10.8s / 7.6s live); new path was flat and fast at depth (~49ms/request at simulated
  "page 999" depth, vs. 2.2s cold-start first query) — the plan's core bet confirmed on real
  Postgres, not just SQLite.
- Correctness spot-checks done: `Event`/`Media` queries against the live (corrupted-by-legacy-hack)
  schema return correct data with no override needed (see grounding note); locale collation
  (`de_DE`) succeeds live once the OS locale is installed and Postgres restarted; privacy
  filtering verified exactly (100000 vs. 89932, matching the real `private=0` count precisely)
  after fixing a test-suite bug that had made this check vacuous (see grounding note).
- Not done: a spot-check of prefixed-surname ("van Dam"-style) sort order against the real Python
  `Sort.by_person_surname_key` output specifically — the generated 100k dataset's surname content
  wasn't inspected for this case. Worth doing if prefixed-surname sorting specifically becomes a
  concern.
