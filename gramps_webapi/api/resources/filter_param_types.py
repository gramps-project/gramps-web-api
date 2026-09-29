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

"""Types of filter rule parameters.

Gramps rules only declare a label per parameter. The Gramps filter editor
chooses the input widget from the label text; `_LABEL_TYPES` mirrors its
table (gramps/gui/editors/filtereditor.py, which cannot be imported without
GTK), leaving out labels no rule uses. Labels it doesn't know are text.
`_LABEL_TYPES` also covers labels the editor treats as text although their
values have a specific format, and `_RULE_TYPES` covers labels whose meaning
depends on the rule.
"""

from typing import Any

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

_ = glocale.translation.gettext

TEXT: dict[str, Any] = {"type": "text"}
BOOLEAN: dict[str, Any] = {"type": "boolean"}
DATE: dict[str, Any] = {"type": "date"}
DATETIME: dict[str, Any] = {"type": "datetime"}
TAG: dict[str, Any] = {"type": "tag"}
GOQL: dict[str, Any] = {"type": "goql"}


def _id(namespace: str) -> dict[str, Any]:
    return {"type": "id", "namespace": namespace}


def _filter(namespace: str) -> dict[str, Any]:
    return {"type": "filter", "namespace": namespace}


def _integer(minimum: int, maximum: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "integer", "min": minimum}
    if maximum is not None:
        result["max"] = maximum
    return result


def _gramps_type(default_types: str, custom_types: str) -> dict[str, Any]:
    return {
        "type": "gramps_type",
        "default_types": default_types,
        "custom_types": custom_types,
    }


def _select(options: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "type": "select",
        "options": [{"value": value, "label": label} for value, label in options],
    }


_COMPARISON = _select(
    [
        ("less than", "less than"),
        ("equal to", "equal to"),
        ("greater than", "greater than"),
    ]
)

# Keys are untranslated labels. Gramps rules use both translated and
# untranslated labels, so lookups try both.
_LABEL_TYPES: dict[str, dict[str, Any]] = {
    # From the Gramps filter editor
    "Reference count:": _integer(0, 999),
    "Number of instances:": _integer(0, 999),
    "Reference count must be:": _COMPARISON,
    "Number must be:": _COMPARISON,
    "Number of generations:": _integer(1, 32),
    "Source ID:": _id("Source"),
    "Person filter name:": _filter("Person"),
    "Event filter name:": _filter("Event"),
    "Source filter name:": _filter("Source"),
    "Repository filter name:": _filter("Repository"),
    "Place filter name:": _filter("Place"),
    "Personal event:": _gramps_type("event_types", "event_types"),
    "Family event:": _gramps_type("event_types", "event_types"),
    "Event type:": _gramps_type("event_types", "event_types"),
    "Personal attribute:": _gramps_type("attribute_types", "person_attribute_types"),
    "Family attribute:": _gramps_type("attribute_types", "family_attribute_types"),
    "Event attribute:": _gramps_type("attribute_types", "event_attribute_types"),
    "Media attribute:": _gramps_type("attribute_types", "media_attribute_types"),
    "Relationship type:": _gramps_type(
        "family_relation_types", "family_relation_types"
    ),
    "Note type:": _gramps_type("note_types", "note_types"),
    "Name type:": _gramps_type("name_types", "name_types"),
    "Surname origin type:": _gramps_type("name_origin_types", "name_origin_types"),
    "Place type:": _gramps_type("place_types", "place_types"),
    "Inclusive:": BOOLEAN,
    "Case sensitive:": BOOLEAN,
    "Include Family events:": BOOLEAN,
    "Primary Role:": BOOLEAN,
    "Tag:": TAG,
    "Confidence level:": _select(
        [
            ("0", "Very Low"),
            ("1", "Low"),
            ("2", "Normal"),
            ("3", "High"),
            ("4", "Very High"),
        ]
    ),
    "Date:": DATE,
    "Day of Week:": _select(
        [
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ]
    ),
    "Units:": _select([("0", "kilometers"), ("1", "miles"), ("2", "degrees")]),
    # Text in the Gramps filter editor
    "Person ID:": _id("Person"),
    "Changed after:": DATETIME,
    "but before:": DATETIME,
    "On date:": DATE,
    "Number of relationships:": _integer(0),
    "Number of children:": _integer(0),
    "Citation attribute:": _gramps_type(
        "source_attribute_types", "source_attribute_types"
    ),
    "Source attribute:": _gramps_type(
        "source_attribute_types", "source_attribute_types"
    ),
    # Our MatchesQuery rule (no Gramps rule uses this label)
    "Expression:": GOQL,
}

_LABEL_TYPES_ANY_LANGUAGE: dict[str, dict[str, Any]] = {
    **{_(label): param_type for label, param_type in _LABEL_TYPES.items()},
    **_LABEL_TYPES,
}

# Labels whose type depends on the rule: (namespace, rule) -> {index: type}
_RULE_TYPES: dict[tuple[str, str], dict[int, dict[str, Any]]] = {
    ("Citation", "HasSourceIdOf"): {0: _id("Source")},
    ("Repository", "HasRepo"): {
        1: _gramps_type("repository_types", "repository_types")
    },
    ("Place", "WithinArea"): {1: _integer(0)},
    ("Media", "IsReferencedByObjectType"): {
        0: _select(
            [
                (name, name)
                for name in [
                    "Person",
                    "Family",
                    "Event",
                    "Place",
                    "Citation",
                    "Source",
                ]
            ]
        )
    },
}


def _label_type(label: str, namespace: str) -> dict[str, Any]:
    """Return the type of a parameter from its label alone."""
    if label in (_("ID:"), "ID:"):
        return _id(namespace)
    if label in (_("Filter name:"), "Filter name:"):
        return _filter(namespace)
    return _LABEL_TYPES_ANY_LANGUAGE.get(label, TEXT)


def get_param_types(namespace: str, rule_class: type[Rule]) -> list[dict[str, Any]]:
    """Return the types of a rule's parameters, one per label."""
    overrides = _RULE_TYPES.get((namespace, rule_class.__name__), {})
    return [
        overrides.get(index) or _label_type(label, namespace)
        for index, label in enumerate(rule_class.labels)
    ]
