"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


# Groq client

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _keywords(text: str) -> set[str]:
    """Lowercase, punctuation-stripped word set used for keyword scoring."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# Tool 1: search_listings
def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    filtered = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and size.lower() not in listing["size"].lower():
            continue
        filtered.append(listing)

    query_keywords = _keywords(description)

    scored = []
    for listing in filtered:
        listing_text = " ".join(
            [listing["title"], listing["description"], " ".join(listing["style_tags"])]
        )
        score = len(query_keywords & _keywords(listing_text))
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# Tool 2: suggest_outfit
def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    items = wardrobe.get("items", [])

    item_details = (
        f"Title: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Style: {', '.join(new_item['style_tags'])}"
    )

    if not items:
        prompt = (
            "A user found a secondhand piece they're considering buying:\n\n"
            f"{item_details}\n\n"
            "They don't have any wardrobe items logged yet. Give them general "
            "styling advice for this piece: what colors, categories, and vibes "
            "would pair well with it. Keep it to 2-3 sentences, casual tone."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}, colors: {', '.join(item['colors'])}, "
            f"style: {', '.join(item['style_tags'])})"
            for item in items
        )
        prompt = (
            "A user found a secondhand piece they're considering buying:\n\n"
            f"{item_details}\n\n"
            "Here is their current wardrobe:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair this new item with specific "
            "pieces from their wardrobe (refer to wardrobe items by name). Keep "
            "it casual and specific, 2-4 sentences."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("LLM returned an empty outfit suggestion")
        return text
    except Exception as e:
        print(f"suggest_outfit: falling back after error: {e}")
        return (
            "Style this with neutral basics from your closet — pair it with "
            "your most-worn bottoms and a simple layering piece."
        )


# Tool 3: create_fit_card
def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return (
            "Couldn't generate a caption because no outfit suggestion was "
            "available for this item."
        )

    prompt = (
        "Write a short, casual Instagram/TikTok caption (2-4 sentences) for an "
        "outfit post featuring a secondhand find.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']:.2f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "The caption should feel like a real OOTD post, not a product "
        "description. Mention the item name, price, and platform naturally, "
        "once each. Capture the outfit vibe in specific terms."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("LLM returned an empty caption")
        return text
    except Exception as e:
        print(f"create_fit_card: falling back after error: {e}")
        return (
            f"Couldn't generate a caption for {new_item.get('title', 'this item')} "
            "right now — try again in a moment."
        )
