from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# search_listings
def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("jacket", size="M", max_price=None)
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


# suggest_outfit
def test_suggest_outfit_with_wardrobe_returns_nonempty_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(outfit, str)
    assert outfit.strip() != ""


def test_suggest_outfit_empty_wardrobe_does_not_crash():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(outfit, str)
    assert outfit.strip() != ""


# create_fit_card
def test_create_fit_card_empty_outfit_returns_fallback_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert card.strip() != ""


def test_create_fit_card_whitespace_outfit_returns_fallback_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("   ", item)
    assert isinstance(card, str)
    assert card.strip() != ""


def test_create_fit_card_with_outfit_mentions_item_and_price():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = suggest_outfit(item, get_example_wardrobe())
    card = create_fit_card(outfit, item)
    assert isinstance(card, str)
    assert card.strip() != ""
    assert f"{item['price']:.2f}" in card or str(int(item["price"])) in card
