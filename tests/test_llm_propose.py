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

"""Tests for the AI assistant's tools that propose changes."""

import re
from unittest.mock import MagicMock, patch

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gramps_webapi.api.llm import answer_with_agent
from gramps_webapi.api.llm.agent import create_agent
from gramps_webapi.api.llm.deps import AgentDeps, Proposal
from gramps_webapi.api.llm.propose import (
    ObjectData,
    propose_change,
    propose_delete,
)
from gramps_webapi.api.tasks import apply_transactions
from gramps_webapi.api.util import close_db, get_db_outside_request
from gramps_webapi.app import create_app
from gramps_webapi.auth import user_db
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from tests import ExampleDbSQLite

USER_ID = "test_user"
DATA = TypeAdapter(ObjectData)


@pytest.fixture(scope="module")
def app():
    """App with a copy of the example tree of its own, as tests write to it."""
    test_db = ExampleDbSQLite(name="example_gramps_propose")
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        app = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "LLM_MODEL": "gpt-4o-mini",
                "LLM_ALLOW_WRITE_PROPOSALS": True,
                "TREE": test_db.name,
            },
            config_from_env=False,
        )
    with app.app_context():
        user_db.create_all()
    app.config["TEST_TREE"] = test_db.dirname
    yield app


@pytest.fixture
def tree(app):
    with app.app_context():
        yield app.config["TEST_TREE"]


@pytest.fixture
def ctx(tree):
    """Tool context whose agent may propose changes."""
    context = MagicMock()
    context.deps = AgentDeps(
        tree=tree,
        include_private=True,
        max_context_length=50000,
        user_id=USER_ID,
        proposal=Proposal(),
    )
    return context


def _data(**kwargs):
    return DATA.validate_python(kwargs)


def _read(tree, func):
    """Call `func` with a freshly opened read-only database."""
    db = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=USER_ID
    )
    try:
        return func(db)
    finally:
        close_db(db)


def _new_id(result: str) -> str:
    """The Gramps ID of a newly proposed object from a tool's result."""
    match = re.search(r"add \w+ (\S+)\.$", result)
    assert match, result
    return match.group(1)


def _items(proposal, class_name, change_type):
    return [
        item
        for item in proposal.transaction
        if item["_class"] == class_name and item["type"] == change_type
    ]


def test_add_person_with_birth(ctx, tree):
    """A new person with a birth gets a new birth event, indexed as birth."""
    num_people = _read(tree, lambda db: db.get_number_of_people())
    result = propose_change(
        ctx,
        _data(
            object_type="person",
            given_name="Anna",
            surname="Garner",
            gender="female",
            birth={"date": "about 1880", "place": "P1435"},
        ),
    )
    assert result.startswith("Proposed (not applied yet): add person"), result
    proposal = ctx.deps.proposal
    (event,) = _items(proposal, "Event", "add")
    assert event["new"]["date"]["quality"] == 0
    assert event["new"]["date"]["modifier"] == 3  # about
    (person,) = _items(proposal, "Person", "add")
    assert person["new"]["gramps_id"] == _new_id(result)
    assert person["new"]["primary_name"]["first_name"] == "Anna"
    assert person["new"]["primary_name"]["surname_list"][0]["surname"] == "Garner"
    assert person["new"]["birth_ref_index"] == 0
    assert person["new"]["event_ref_list"][0]["ref"] == event["handle"]
    assert len(proposal.summaries) == 1
    # nothing was written
    assert _read(tree, lambda db: db.get_number_of_people()) == num_people


def test_update_existing_birth(ctx):
    """Changing a birth changes the existing birth event."""
    result = propose_change(
        ctx,
        gramps_id="I0044",
        data=_data(object_type="person", birth={"date": "21 June 1856"}),
    )
    assert result == "Proposed (not applied yet): change person I0044.", result
    (event,) = _items(ctx.deps.proposal, "Event", "update")
    assert event["new"]["gramps_id"] == "E1656"
    assert event["new"]["date"]["dateval"][:3] == [21, 6, 1856]
    # the place is kept
    assert event["new"]["place"] == event["old"]["place"]
    assert not _items(ctx.deps.proposal, "Event", "add")


def test_update_adds_missing_birth(ctx):
    """A person without birth event gets one."""
    result = propose_change(
        ctx, gramps_id="I0552", data=_data(object_type="person", birth={"date": "1850"})
    )
    assert result.startswith("Proposed"), result
    (event,) = _items(ctx.deps.proposal, "Event", "add")
    (person,) = _items(ctx.deps.proposal, "Person", "update")
    assert person["new"]["birth_ref_index"] == 0
    assert person["new"]["event_ref_list"][0]["ref"] == event["handle"]


def test_sourced_fact(ctx):
    """New source, citation and fact build on each other in one changeset."""
    source_id = _new_id(
        propose_change(ctx, _data(object_type="source", title="Parish register"))
    )
    citation_id = _new_id(
        propose_change(
            ctx,
            _data(object_type="citation", source=source_id, page="p. 12"),
        )
    )
    result = propose_change(
        ctx,
        gramps_id="I0044",
        data=_data(
            object_type="person",
            events=[{"event_type": "Occupation", "description": "Farmer"}],
            citations=[citation_id],
        ),
    )
    assert result.startswith("Proposed"), result
    proposal = ctx.deps.proposal
    assert len(proposal.changes) == 3
    (source,) = _items(proposal, "Source", "add")
    (citation,) = _items(proposal, "Citation", "add")
    assert citation["new"]["source_handle"] == source["handle"]
    (event,) = _items(proposal, "Event", "add")
    assert event["new"]["description"] == "Farmer"
    (person,) = _items(proposal, "Person", "update")
    assert citation["handle"] in person["new"]["citation_list"]
    # the birth and death indices are kept
    assert person["new"]["birth_ref_index"] == 0
    assert person["new"]["death_ref_index"] == 1


def test_add_family(ctx):
    """A new family is added to its members' family lists."""
    child_id = _new_id(
        propose_change(ctx, _data(object_type="person", given_name="Child"))
    )
    result = propose_change(
        ctx,
        _data(
            object_type="family",
            father="I0044",
            children=[child_id],
            relationship="Married",
            marriage={"date": "1880"},
        ),
    )
    assert result.startswith("Proposed"), result
    proposal = ctx.deps.proposal
    (family,) = _items(proposal, "Family", "add")
    people = {
        item["new"]["gramps_id"]: item["new"]
        for item in proposal.transaction
        if item["_class"] == "Person"
    }
    assert family["handle"] in people["I0044"]["family_list"]
    # the child was added and then updated with its parent family
    assert family["handle"] in people[child_id]["parent_family_list"]
    (marriage,) = _items(proposal, "Event", "add")
    assert family["new"]["event_ref_list"][0]["ref"] == marriage["handle"]


def test_delete_event(ctx):
    """Deleting an event removes it from the people who reference it."""
    result = propose_delete(ctx, "event", "E1657")
    assert result == "Proposed (not applied yet): delete event E1657.", result
    proposal = ctx.deps.proposal
    (event,) = _items(proposal, "Event", "delete")
    (person,) = _items(proposal, "Person", "update")
    assert event["handle"] not in [
        ref["ref"] for ref in person["new"]["event_ref_list"]
    ]


@pytest.mark.parametrize(
    "call, message",
    [
        (
            lambda ctx: propose_change(
                ctx, gramps_id="I9999", data=_data(object_type="person", given_name="X")
            ),
            "No person",
        ),
        (
            lambda ctx: propose_change(
                ctx,
                gramps_id="I0044",
                data=_data(object_type="person", birth={"date": "soon"}),
            ),
            "Cannot parse the date",
        ),
        (
            lambda ctx: propose_change(
                ctx,
                gramps_id="I0044",
                data=_data(object_type="person", events=[{"event_type": "Party"}]),
            ),
            "Unknown type",
        ),
        (
            lambda ctx: propose_change(ctx, _data(object_type="citation", page="1")),
            "needs a source",
        ),
        (
            lambda ctx: propose_change(ctx, _data(object_type="event")),
            "through the person or family",
        ),
        (lambda ctx: propose_delete(ctx, "note", "N9999"), "No note"),
        (
            lambda ctx: propose_change(
                ctx, gramps_id="F0017", data=_data(object_type="family", children=None)
            ),
            "no field to change",
        ),
        (
            # the birth of I0044 (E1656), sent again as another event
            lambda ctx: propose_change(
                ctx,
                gramps_id="I0044",
                data=_data(object_type="person", events=[{"event_type": "Birth"}]),
            ),
            "Use the birth field",
        ),
        (
            lambda ctx: propose_change(
                ctx,
                gramps_id="F0017",
                data=_data(
                    object_type="family",
                    events=[{"event_type": "Marriage"}],
                ),
            ),
            "Use the marriage field",
        ),
    ],
)
def test_errors(ctx, call, message):
    """Invalid changes are reported to the model and not proposed."""
    propose_change(ctx, _data(object_type="note", text="Kept"))
    result = call(ctx)
    assert result.startswith("Nothing was proposed"), result
    assert message in result
    # the earlier change is unaffected
    assert len(ctx.deps.proposal.changes) == 1
    assert len(ctx.deps.proposal.summaries) == 1


def test_approve(ctx, tree):
    """The proposal can be applied, but not after the objects changed."""
    propose_change(
        ctx, gramps_id="I0044", data=_data(object_type="person", given_name="Lew")
    )
    transaction = ctx.deps.proposal.transaction
    apply_transactions(tree=tree, user_id=USER_ID, payload=transaction, force=False)
    name = _read(
        tree,
        lambda db: db.get_person_from_gramps_id("I0044")
        .get_primary_name()
        .get_first_name(),
    )
    assert name == "Lew"
    # applying it again fails: the person's old state no longer matches
    with pytest.raises(ValueError):
        apply_transactions(tree=tree, user_id=USER_ID, payload=transaction, force=False)


def _tools_and_prompt(**kwargs):
    seen = {}

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        seen["tools"] = {tool.name for tool in info.function_tools}
        seen["prompt"] = str(messages[0].parts[0].content)
        return ModelResponse(parts=[TextPart(content="done")])

    agent = create_agent("gpt-4o-mini", **kwargs)
    deps = AgentDeps(
        tree="tree", include_private=False, max_context_length=1000, user_id="user"
    )
    with agent.override(model=FunctionModel(model_function)):
        agent.run_sync("question", deps=deps)
    return seen["tools"], seen["prompt"]


def test_tools_only_when_allowed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    tools, prompt = _tools_and_prompt()
    assert not {"propose_change", "propose_delete"} & tools
    assert "propose_change" not in prompt
    tools, prompt = _tools_and_prompt(allow_write_proposals=True)
    assert {"propose_change", "propose_delete"} <= tools
    assert "propose_change" in prompt


def _answer(app, monkeypatch, tree, proposal):
    """Run the agent with a model that proposes a change."""

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="propose_change",
                        args={
                            "gramps_id": "I0044",
                            "data": {"object_type": "person", "gender": "unknown"},
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="Proposed.")])

    def create(**kwargs):
        agent = create_agent(**kwargs)
        agent.model = FunctionModel(model_function)
        return agent

    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setattr("gramps_webapi.api.llm.create_agent", create)
    return answer_with_agent(
        prompt="Set the gender of I0044 to unknown",
        tree=tree,
        include_private=True,
        user_id=USER_ID,
        proposal=proposal,
    )


def test_agent_proposes(app, monkeypatch, tree):
    proposal = Proposal()
    _answer(app, monkeypatch, tree, proposal)
    (person,) = _items(proposal, "Person", "update")
    assert person["new"]["gender"] == 2


def test_agent_proposals_disabled(app, monkeypatch, tree):
    """Without LLM_ALLOW_WRITE_PROPOSALS, the agent can't propose anything."""
    monkeypatch.setitem(app.config, "LLM_ALLOW_WRITE_PROPOSALS", False)
    proposal = Proposal()
    _answer(app, monkeypatch, tree, proposal)
    assert not proposal.changes


def test_duplicate_event(ctx):
    """An event like one the person has already is not added again."""
    first = propose_change(
        ctx,
        gramps_id="I0044",
        data=_data(
            object_type="person",
            events=[{"event_type": "Residence", "date": "1870"}],
        ),
    )
    assert first.startswith("Proposed"), first
    again = propose_change(
        ctx,
        gramps_id="I0044",
        data=_data(
            object_type="person",
            events=[{"event_type": "Residence", "date": "1870"}],
        ),
    )
    assert again.startswith("Nothing was proposed"), again
    assert "exists already" in again


def test_unknown_field():
    """Fields the format doesn't have are errors, so the model learns of them."""
    with pytest.raises(ValidationError, match="nickname"):
        _data(object_type="person", nickname="Lilibet")


@pytest.mark.parametrize(
    "gramps_id, data",
    [
        # children are only ever added, so an empty list changes nothing
        ("F0017", {"object_type": "family", "children": []}),
        # the gender I0044 has already (test_approve changes the given name)
        ("I0044", {"object_type": "person", "gender": "male"}),
    ],
)
def test_no_effect(ctx, gramps_id, data):
    """A change that changes nothing is not proposed, also after other changes."""
    propose_change(ctx, _data(object_type="note", text="Kept"))
    result = propose_change(ctx, gramps_id=gramps_id, data=_data(**data))
    assert result == "Nothing was proposed: this would not change anything."
    assert len(ctx.deps.proposal.changes) == 1
