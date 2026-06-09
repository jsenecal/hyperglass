"""Test HyperglassMultiModel."""

# Third Party
from pydantic import BaseModel

# Local
from ..main import MultiModel


class Item(BaseModel):
    """Test item."""

    id: str
    name: str


class Items(MultiModel, model=Item, unique_by="id"):
    """Multi Model Test."""


ITEMS_1 = [
    {"id": "item1", "name": "Item One"},
    Item(id="item2", name="Item Two"),
    {"id": "item3", "name": "Item Three"},
]

ITEMS_2 = [
    Item(id="item4", name="Item Four"),
    {"id": "item5", "name": "Item Five"},
]

ITEMS_3 = [
    {"id": "item1", "name": "Item New One"},
    {"id": "item6", "name": "Item Six"},
]


def test_multi_model():
    model = Items(*ITEMS_1)
    assert model.count == 3
    assert len([o for o in model]) == model.count  # noqa: C416 (Iteration testing)
    assert model["item1"].name == "Item One"
    model.add(*ITEMS_2)
    assert model.count == 5
    assert model[3].name == "Item Four"
    model.add(*ITEMS_3, unique_by="id")
    assert model.count == 6
    assert model["item1"].name == "Item New One"


# Ids where one is a strict prefix of another, to exercise substring resolution.
SUBSTRING_ITEMS = [
    {"id": "route", "name": "Route"},
    {"id": "route_table", "name": "Route Table"},
]


def test_filter_matches_exact_id_only():
    """filter() must resolve an exact id even when another id is a superstring."""
    model = Items(*SUBSTRING_ITEMS)
    result = model.filter("route")
    assert [item.id for item in result] == ["route"]


def test_matching_is_substring_and_overmatches():
    """matching() is intentionally a partial match — it returns both here.

    Documents why query-type resolution must use filter(), not matching():
    `matching("route")` also pulls in `route_table`.
    """
    model = Items(*SUBSTRING_ITEMS)
    ids = sorted(item.id for item in model.matching("route"))
    assert ids == ["route", "route_table"]


def test_merge_preserves_first_seen_order():
    """_merge_with()/add() must keep deterministic insertion (first-seen) order.

    Order previously came from set iteration (hash-seed dependent), which made
    matching()[0] non-deterministic across process restarts.
    """
    model = Items(*[{"id": f"item{n}", "name": str(n)} for n in range(10)])
    model.add({"id": "item10", "name": "ten"}, unique_by="id")
    assert [item.id for item in model] == [f"item{n}" for n in range(11)]
    # Re-adding an existing id updates in place without reordering.
    model.add({"id": "item3", "name": "three-updated"}, unique_by="id")
    assert [item.id for item in model] == [f"item{n}" for n in range(11)]
    assert model["item3"].name == "three-updated"
