#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Parsing of search queries and the SQL that evaluates them.

A query is an AND of clauses, and a clause is an OR of terms: words,
"phrases" or prefixes (trailing `*`). `a OR b c` means `(a OR b) AND c`.

An object is a hit when every clause matches one of its visible documents:
its own text, or the name of a visible person connected to it through a
visible reference (family <- parents, event <- primary participants,
event <- family <- parents). Matching, visibility, grouping, counting and
pagination happen in one SQL statement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import TextClause, bindparam, text
from unidecode import unidecode

from .text import tokenize


@dataclass(frozen=True)
class Term:
    """A word (one token) or a phrase (several tokens), optionally a prefix."""

    tokens: tuple[str, ...]
    prefix: bool = False


Clause = tuple[Term, ...]


def _split(query: str) -> list[tuple[str, bool]]:
    """Split a query at whitespace outside quotes into (token, quoted) pairs."""
    parts: list[tuple[str, bool]] = []
    for match in re.finditer(r'"([^"]*)"(\*?)|(\S+)', query):
        if match.group(3) is not None:
            parts.append((match.group(3), False))
        else:
            parts.append((match.group(1) + match.group(2), True))
    return parts


def _terms(part: str) -> list[Term]:
    """Return the term of a part of the query, and its transliteration.

    Indexed text contains a transliteration of every string (see
    `process_strings`), so "Müller" finds "Muller" and vice versa, the same
    way in every database backend.
    """
    prefix = part.endswith("*")
    terms = []
    for string in (part, unidecode(part)):
        tokens = tuple(tokenize(string))
        if tokens and Term(tokens, prefix) not in terms:
            terms.append(Term(tokens=tokens, prefix=prefix))
    return terms


def parse_query(query: str) -> list[Clause]:
    """Parse a query into clauses (AND) of terms (OR)."""
    clauses: list[list[Term]] = []
    join_next = False
    for part, quoted in _split(query):
        if not quoted and part.upper() == "OR":
            join_next = bool(clauses)
            continue
        if not quoted and part.upper() == "AND":
            join_next = False
            continue
        terms = _terms(part)
        if not terms:
            continue
        if join_next:
            clauses[-1] += terms
        else:
            clauses.append(terms)
        join_next = False
    return [tuple(clause) for clause in clauses]


def to_tsquery(clause: Clause) -> str:
    """Return a clause as a PostgreSQL tsquery string.

    Tokens consist of letters and digits only, so they need no escaping.
    """
    parts = []
    for term in clause:
        tokens = list(term.tokens)
        if term.prefix:
            tokens[-1] += ":*"
        parts.append("(" + " <-> ".join(tokens) + ")")
    return " | ".join(parts)


def to_fts5(clause: Clause) -> str:
    """Return a clause as an SQLite FTS5 query string."""
    parts = []
    for term in clause:
        phrase = '"' + " ".join(term.tokens) + '"'
        parts.append(phrase + ("*" if term.prefix else ""))
    return " OR ".join(parts)


SORT_COLUMNS = {"change": "o.change", "type": "o.obj_type"}

# objects found through a connected person's name rank below direct matches
EXPANDED_WEIGHT = 0.5


def _order_by(sort: Sequence[str] | None, default: str) -> str:
    keys = []
    for key in sort or []:
        descending = key.startswith("-")
        column = SORT_COLUMNS.get(key.lstrip("-+"))
        if column:
            keys.append(f"{column} {'DESC' if descending else 'ASC'}")
    return ", ".join(keys + [default, "o.handle"])


def _filters(
    params: dict[str, Any],
    object_types: Sequence[str] | None,
    change_op: str | None,
    change_value: float | None,
) -> str:
    """Conditions on the hit objects `o`."""
    conditions = []
    if object_types:
        params["types"] = list(object_types)
        conditions.append("o.obj_type IN :types")
    if change_op and change_value is not None:
        if change_op not in {">", "<", ">=", "<="}:
            raise ValueError("Invalid operator for change condition")
        params["change"] = change_value
        conditions.append(f"o.change {change_op} :change")
    return "".join(f" AND {condition}" for condition in conditions)


def _bind(sql: str, params: dict[str, Any]) -> TextClause:
    statement = text(sql)
    if "types" in params:
        statement = statement.bindparams(bindparam("types", expanding=True))
    return statement


def build_search(
    dialect: str,
    tree: str,
    clauses: Sequence[Clause],
    include_private: bool,
    object_types: Sequence[str] | None = None,
    change_op: str | None = None,
    change_value: float | None = None,
    sort: Sequence[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    count_only: bool = False,
) -> tuple[TextClause, dict[str, Any]]:
    """Return the statement and parameters of a search.

    Rows are (handle, obj_type, score, total), or (total,) if `count_only`.
    """
    pg = dialect == "postgresql"
    params: dict[str, Any] = {"tree": tree}
    if include_private:
        doc_visible = "d.variant <> 'redacted'"

        def visible(alias: str) -> str:
            return "1 = 1"

    else:
        doc_visible = "d.variant <> 'full' AND NOT d.private"

        def visible(alias: str) -> str:
            return f"NOT {alias}.private"

    branches = []
    for i, clause in enumerate(clauses):
        if pg:
            params[f"q{i}"] = to_tsquery(clause)
            branches.append(
                f"SELECT d.handle, d.kind, {i} AS clause, ts_rank(d.tsv, q) AS r"
                f" FROM search_doc d, to_tsquery('simple', :q{i}) q"
                f" WHERE d.tree = :tree AND d.tsv @@ q AND {doc_visible}"
            )
        else:
            params[f"q{i}"] = to_fts5(clause)
            branches.append(
                f"SELECT d.handle, d.kind, {i} AS clause, -bm25(search_fts) AS r"
                f" FROM search_fts CROSS JOIN search_doc d ON d.id = search_fts.rowid"
                f" WHERE search_fts MATCH :q{i} AND d.tree = :tree AND {doc_visible}"
            )
    # SQLite keeps the written join order for CROSS JOIN, so the expansions
    # start from the (few) matches instead of scanning the tree
    join = "JOIN" if pg else "CROSS JOIN"
    materialized = "" if pg else "MATERIALIZED "
    families = not object_types or "family" in object_types
    events = not object_types or "event" in object_types
    hits = [
        "SELECT handle, clause, r FROM m WHERE kind = 'own'",
        # a person is also found by their name document
        "SELECT handle, clause, r FROM names",
    ]
    if families:
        hits.append(
            f"""SELECT f.from_handle, n.clause, n.r * {EXPANDED_WEIGHT} FROM names n
            {join} search_ref f ON f.tree = :tree AND f.to_handle = n.handle
                AND f.kind = 'parent'"""
        )
    if events:
        hits.append(
            f"""SELECT e.to_handle, n.clause, n.r * {EXPANDED_WEIGHT} FROM names n
            {join} search_ref e ON e.tree = :tree AND e.from_handle = n.handle
                AND e.kind = 'participant' AND {visible("e")}"""
        )
        hits.append(
            f"""SELECT e.to_handle, n.clause, n.r * {EXPANDED_WEIGHT} FROM names n
            {join} search_ref f ON f.tree = :tree AND f.to_handle = n.handle
                AND f.kind = 'parent'
            {join} search_obj fo ON fo.tree = :tree AND fo.handle = f.from_handle
                AND {visible("fo")}
            {join} search_ref e ON e.tree = :tree AND e.from_handle = f.from_handle
                AND e.kind = 'participant' AND {visible("e")}"""
        )
    filters = _filters(params, object_types, change_op, change_value)
    ctes = f"""
    WITH m AS {materialized}({" UNION ALL ".join(branches)}),
    names AS {materialized}(
        SELECT m.handle, m.clause, m.r FROM m
        {join} search_obj p ON p.tree = :tree AND p.handle = m.handle
            AND {visible("p")}
        WHERE m.kind = 'name'),
    hits AS ({" UNION ALL ".join(hits)}),
    best AS (SELECT handle, clause, max(r) AS r FROM hits GROUP BY handle, clause),
    agg AS (
        SELECT handle, sum(r) AS score FROM best
        GROUP BY handle HAVING count(*) = {len(clauses)})"""
    source = f"""
    FROM agg a JOIN search_obj o ON o.tree = :tree AND o.handle = a.handle
        AND {visible("o")}{filters}"""
    if count_only:
        return _bind(f"{ctes} SELECT count(*) {source}", params), params
    sql = f"""{ctes}
    SELECT o.handle, o.obj_type, a.score, count(*) OVER () AS total {source}
    ORDER BY {_order_by(sort, "a.score DESC")}"""
    return _bind(_paginate(sql, params, limit, offset), params), params


def build_list(
    tree: str,
    include_private: bool,
    object_types: Sequence[str] | None = None,
    change_op: str | None = None,
    change_value: float | None = None,
    sort: Sequence[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    count_only: bool = False,
) -> tuple[TextClause, dict[str, Any]]:
    """Return the statement and parameters listing all visible objects."""
    params: dict[str, Any] = {"tree": tree}
    where = "o.tree = :tree" + ("" if include_private else " AND NOT o.private")
    where += _filters(params, object_types, change_op, change_value)
    if count_only:
        return _bind(f"SELECT count(*) FROM search_obj o WHERE {where}", params), params
    sql = f"""SELECT o.handle, o.obj_type, NULL AS score, count(*) OVER () AS total
    FROM search_obj o WHERE {where}
    ORDER BY {_order_by(sort, "o.change DESC")}"""
    return _bind(_paginate(sql, params, limit, offset), params), params


def _paginate(sql: str, params: dict[str, Any], limit: int | None, offset: int) -> str:
    if limit is None:
        return sql
    params["limit"] = limit
    params["offset"] = offset
    return f"{sql} LIMIT :limit OFFSET :offset"
