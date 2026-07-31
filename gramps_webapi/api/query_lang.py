#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Douglas Blank
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

"""An "almost Python" expression language, parsed into `object_query.py`'s
JSON `where` shape -- e.g. `"primary_name.surname_list[0].surname == 'Smith'"`
becomes `[{"column": {"json_path": [...]}, "op": "eq", "value": "Smith"}]`.

Uses `ast.parse(expr, mode="eval")` as pure syntax, never `eval()` or
`compile()` -- the tree is inspected and translated node-by-node into plain
JSON, never executed. Safety comes from whitelisting node *shapes*, not
blacklisting names: any AST node this module doesn't explicitly recognize
(function calls other than the one whitelisted `like(...)` form, lambdas,
comprehensions, attribute access building toward dunder names, imports,
walrus, f-strings, ...) is rejected by `_translate_*` simply never handling
it and falling through to a `QueryLangError`.

Deliberately not wired to any HTTP endpoint yet -- see `query.py`'s
`JsonPath`, which followed the same build-it-standalone-first,
wire-it-up-later path this session.

Current scope, matching what `object_query.py`'s wire format actually
supports today:

- Top level is a conjunction of comparisons (`a == b and c > d and ...`)
  -- `or`/`not` have no JSON representation in the current `where` shape
  (a flat list of leaf conditions, implicitly AND'd), so they're rejected
  here too, not silently dropped.
- A comparison is `path OP value` where `OP` is one of
  `== != < <= > >=` or Python's `in` (`path in [v1, v2, ...]`) -- these are
  all the same `ast.Compare` node shape, just different `ops`.
  `path not in [...]`, `is`, `is not` have no wire equivalent and are
  rejected.
- `like(path, 'pattern%')` is the one whitelisted function-call form, for
  the one operator (`Like`) that isn't a Python operator.
- A path is a bare identifier optionally followed by `.attr` / `[index]`
  segments, e.g. `gender` or `primary_name.surname_list[0].surname`.
  Single-segment paths that match the target type's flat column whitelist
  resolve to a plain column reference (a real indexed SQL column); every
  other path becomes a `{"json_path": [...]}` reference.
"""

from __future__ import annotations

import ast
from typing import Any, List, Union

from .query import (
    CITATION,
    EVENT,
    FAMILY,
    MEDIA,
    NOTE,
    PERSON,
    PLACE,
    REPOSITORY,
    SOURCE,
    TAG,
    ObjectTypeSpec,
)

# Namespace -> ObjectTypeSpec. Both the lowercase form and the actual Gramps
# class-name casing (Person, Family, ...) are accepted; no single-letter
# aliases -- those aren't what was asked for, and Gramps' own gramps_id
# prefixes (P = Place, I = Person, ...) don't line up with the object names
# anyway, so a letter scheme here would just invite confusion.
_NAMES = {
    "person": PERSON,
    "family": FAMILY,
    "event": EVENT,
    "place": PLACE,
    "repository": REPOSITORY,
    "source": SOURCE,
    "citation": CITATION,
    "media": MEDIA,
    "note": NOTE,
    "tag": TAG,
}
_NAMESPACES: dict[str, ObjectTypeSpec] = {
    **_NAMES,
    **{name.capitalize(): spec for name, spec in _NAMES.items()},
}


class QueryLangError(ValueError):
    """Raised when an expression doesn't parse or uses unsupported syntax."""


def resolve_namespace(namespace: str) -> ObjectTypeSpec:
    """Look up the `ObjectTypeSpec` for a namespace string (`"person"` or `"Person"`, ...)."""
    try:
        return _NAMESPACES[namespace]
    except KeyError:
        raise QueryLangError(f"unknown namespace: {namespace!r}") from None


_COMPARE_OPS: dict[type, str] = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "lte",
    ast.Gt: "gt",
    ast.GtE: "gte",
    ast.In: "in",
}


def _translate_path(node: ast.AST) -> List[Union[str, int]]:
    """Walk a `Name`/`Attribute`/`Subscript` chain into an ordered segment list.

    `a.b[0].c` is nested as `Attribute(Attribute(Subscript(Attribute(Name)))...)`
    with the outermost node being the *last* segment -- recurse to the base
    `Name` first, then build the list root-to-leaf.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return _translate_path(node.value) + [node.attr]
    if isinstance(node, ast.Subscript):
        index_node = node.slice
        if not isinstance(index_node, ast.Constant) or not isinstance(
            index_node.value, int
        ) or isinstance(index_node.value, bool):
            raise QueryLangError(
                f"subscript index must be a plain integer literal: {ast.dump(node)}"
            )
        return _translate_path(node.value) + [index_node.value]
    raise QueryLangError(f"invalid path expression: {ast.dump(node)}")


def _translate_column(node: ast.AST, spec: ObjectTypeSpec) -> Union[str, dict]:
    """Translate a path into a wire column reference: a plain string if it's
    a single segment matching a real flat column, `{"json_path": [...]}` otherwise.
    """
    segments = _translate_path(node)
    if len(segments) == 1 and isinstance(segments[0], str) and segments[0] in spec.columns:
        return segments[0]
    return {"json_path": segments}


def _translate_value(node: ast.AST) -> Any:
    """Translate a literal: string / int / float / bool / None, or `-<number>`."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _translate_value(node.operand)
        if not isinstance(inner, (int, float)) or isinstance(inner, bool):
            raise QueryLangError(f"unary '-' only supported on numeric literals: {ast.dump(node)}")
        return -inner
    if isinstance(node, ast.Constant):
        return node.value
    raise QueryLangError(f"invalid literal: {ast.dump(node)}")


def _translate_list(node: ast.AST) -> List[Any]:
    if not isinstance(node, ast.List):
        raise QueryLangError(f"expected a list literal, e.g. [1, 2, 3]: {ast.dump(node)}")
    return [_translate_value(elt) for elt in node.elts]


def _translate_compare(node: ast.Compare, spec: ObjectTypeSpec) -> dict:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        # `a < b < c` -- Python allows chained comparisons; we don't.
        raise QueryLangError(
            f"chained comparisons are not supported, use 'and' instead: {ast.dump(node)}"
        )
    op_type = type(node.ops[0])
    if op_type not in _COMPARE_OPS:
        raise QueryLangError(
            f"unsupported comparison operator {op_type.__name__!r} "
            "(supported: == != < <= > >= in)"
        )
    op = _COMPARE_OPS[op_type]
    column = _translate_column(node.left, spec)
    if op == "in":
        value = _translate_list(node.comparators[0])
        if not value:
            raise QueryLangError("'in' requires a non-empty list")
    else:
        value = _translate_value(node.comparators[0])
    return {"column": column, "op": op, "value": value}


def _translate_like_call(node: ast.Call, spec: ObjectTypeSpec) -> dict:
    if len(node.args) != 2 or node.keywords:
        raise QueryLangError("like(path, 'pattern') takes exactly 2 positional arguments")
    column = _translate_column(node.args[0], spec)
    pattern = _translate_value(node.args[1])
    if not isinstance(pattern, str):
        raise QueryLangError("like(...)'s second argument must be a string literal")
    return {"column": column, "op": "like", "value": pattern}


def _translate_comparison_like_node(node: ast.AST, spec: ObjectTypeSpec) -> dict:
    """A single leaf: either a `Compare` or a whitelisted `like(...)` call."""
    if isinstance(node, ast.Compare):
        return _translate_compare(node, spec)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "like"
    ):
        return _translate_like_call(node, spec)
    raise QueryLangError(
        f"expected a comparison (a == b, a in [...], like(a, 'pat')), got: {ast.dump(node)}"
    )


def _translate_top_level(node: ast.AST, spec: ObjectTypeSpec) -> List[dict]:
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, ast.And):
            raise QueryLangError(
                "'or' has no JSON representation in the current where format yet "
                "-- only 'and' is supported"
            )
        conditions = []
        for value in node.values:
            conditions.append(_translate_comparison_like_node(value, spec))
        return conditions
    return [_translate_comparison_like_node(node, spec)]


def parse_expr(namespace: str, expr: str) -> List[dict]:
    """Parse an "almost Python" expression into a `where` condition list.

    >>> parse_expr("person", "gender == 1")
    [{'column': 'gender', 'op': 'eq', 'value': 1}]

    >>> parse_expr("person", "primary_name.surname_list[0].surname == 'Smith'")
    [{'column': {'json_path': ['primary_name', 'surname_list', 0, 'surname']}, 'op': 'eq', 'value': 'Smith'}]

    The result is ready to drop directly into a `POST .../query/` request
    body's `"where"` field. Raises `QueryLangError` on anything outside the
    supported grammar -- never executes the input (`ast.parse` only, no
    `eval`/`compile`/`exec`).
    """
    spec = resolve_namespace(namespace)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as error:
        raise QueryLangError(f"invalid syntax: {error}") from error
    return _translate_top_level(tree.body, spec)
