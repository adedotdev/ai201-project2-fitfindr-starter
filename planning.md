# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40 mock listings in listings.json (via load_listings()) for items that match a free-text description and satisfy optional size and price filters, returning a ranked list of candidate items for the agent to present and pass on to suggest_outfit().

**Input parameters:**
- `description` (str): Keywords pulled from the user's query describing what they want (e.g. `"vintage graphic tee"`). Used to score each listing by counting overlapping words against the listing's `title`, `description`, and `style_tags` fields.
- `size` (str | None): Size to filter by, e.g. `"M"`. Matching is case-insensitive and substring-based (e.g. `"M"` matches a listing with `size: "S/M"`). Pass `None` to skip size filtering entirely.
- `max_price` (float | None): Inclusive price ceiling, e.g. `30.0`. Listings priced at or below this value pass the filter. Pass `None` to skip price filtering.

**What it returns:**
A `list[dict]`, where each dict is one listing in the exact shape stored in `listings.json`: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Listings that fail the `size` or `max_price` filters are excluded entirely. Remaining listings are scored by keyword overlap with `description`; any listing scoring 0 (no keyword overlap) is dropped. The final list is sorted highest score first. If nothing satisfies all constraints, the return value is `[]` — never `None`, never an exception.

**What happens if it fails or returns nothing:**
The planning loop checks `len(results) == 0` immediately after calling this tool. If true, it sets `session["error"]` to a specific, actionable message (e.g. `"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price limit, removing the size filter, or using broader keywords."`) and returns the session immediately — `suggest_outfit` and `create_fit_card` are never called, and `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` stay `None`.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the LLM (Groq) to generate 1–2 complete outfit ideas that pair the selected thrifted item with the user's existing wardrobe. If the wardrobe has no items, it asks the LLM for general styling advice about the item instead of referencing owned pieces.

**Input parameters:**
- `new_item` (dict): The listing dict for the item the user is considering — the same shape returned by `search_listings` (must include at least `title`, `category`, `colors`, `style_tags`).
- `wardrobe` (dict): A wardrobe dict of the form `{"items": [...]}`, where each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. `wardrobe["items"]` may be `[]`.

**What it returns:**
A non-empty `str` containing the outfit suggestion in natural language (e.g. `"Pair the graphic tee with your baggy dark-wash jeans and chunky sneakers for an easy streetwear look..."`). When `wardrobe["items"]` is empty, the string instead contains general styling advice about what kinds of pieces/colors/vibes would pair well with `new_item`, with no reference to specific owned items.

**What happens if it fails or returns nothing:**
The function itself guards against this — it never raises and never returns `""`. If the Groq API call raises an exception (network error, missing key, rate limit) or returns a blank/whitespace string, `suggest_outfit` catches that internally and returns a hardcoded fallback string (e.g. `"Style this with neutral basics from your closet — pair it with your most-worn bottoms and a simple layering piece."`). The planning loop treats this fallback exactly like a normal suggestion: it stores it in `session["outfit_suggestion"]` and proceeds to `create_fit_card`. This failure is non-fatal — `session["error"]` is NOT set, because the search result is still valid and shareable even without a tailored outfit.

---

### Tool 3: create_fit_card

**What it does:**
Calls the LLM to turn the outfit suggestion and item details into a short, casual, shareable social-media caption (2–4 sentences) for the thrifted find.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit()` (may be the real suggestion or its fallback string).
- `new_item` (dict): The listing dict for the item — used to pull `title`, `price`, and `platform` into the caption.

**What it returns:**
A `str` of 2–4 sentences written like a real OOTD caption: it mentions the item name, price, and platform once each, describes the outfit vibe in specific terms, and varies in wording across calls (achieved with a higher LLM temperature).

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the function does not call the LLM at all — it returns a descriptive string directly, e.g. `"Couldn't generate a caption because no outfit suggestion was available for this item."` If the LLM call itself raises an exception, the function catches it and returns a similar descriptive fallback string rather than raising. Either way, the planning loop stores whatever string comes back in `session["fit_card"]` and still returns a completed session — `session["error"]` stays `None`, since the listing and (at minimum, fallback) outfit suggestion were already produced successfully. The user sees the fit card panel display the fallback message instead of a caption.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a fixed sequence with one early-exit branch, implemented in `run_agent()`:

1. Call `_new_session(query, wardrobe)` to create the session dict.
2. Parse `query` into `description`, `size`, and `max_price` and store the result in `session["parsed"]`.
3. Call `search_listings(**session["parsed"])` and store the result in `session["search_results"]`.
   - **Branch A (no results):** if `session["search_results"] == []`, set `session["error"]` to a specific message naming the filters that produced no matches, and `return session` immediately. `suggest_outfit` and `create_fit_card` are never invoked.
   - **Branch B (results found):** if `session["search_results"]` is non-empty, set `session["selected_item"] = session["search_results"][0]` and continue to step 4.
4. Call `suggest_outfit(session["selected_item"], session["wardrobe"])` and store the result in `session["outfit_suggestion"]`. Because `suggest_outfit` always returns a non-empty string (real suggestion or fallback — see Tool 2), there is no branch here; the loop always continues to step 5.
5. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])` and store the result in `session["fit_card"]`. Because `create_fit_card` always returns a string (caption or fallback message — see Tool 3), there is no branch here either.
6. Return `session`.

The loop never re-calls a tool and never loops back — each tool runs at most once per interaction. The only point where the loop can terminate before reaching `create_fit_card` is Branch A in step 3. Callers (e.g. `app.py`) determine success by checking `session["error"] is None`.

---

## State Management

**How does information from one tool get passed to the next?**

All state for one interaction lives in a single session dict created by `_new_session()` and threaded through every tool call by the planning loop — no tool reads or writes global state, and no tool calls another tool directly.

- `query` (str): the raw user input, set once and never modified.
- `parsed` (dict): `{"description": str, "size": str | None, "max_price": float | None}` — extracted from `query` in step 2, consumed as the keyword arguments to `search_listings` in step 3.
- `search_results` (list[dict]): the full ranked list from `search_listings`, kept for debugging/UI display even though only the first entry is used.
- `selected_item` (dict | None): `search_results[0]`, set in step 3's Branch B. This is the value passed as `new_item` to both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict): passed in by the caller at session creation, never mutated, consumed by `suggest_outfit`.
- `outfit_suggestion` (str | None): the output of `suggest_outfit`, consumed as the `outfit` argument to `create_fit_card`.
- `fit_card` (str | None): the output of `create_fit_card`, the final user-facing artifact.
- `error` (str | None): `None` unless Branch A fires in step 3. The presence of an error is checked by both the planning loop (to short-circuit) and the caller in `app.py` (to decide which panel to populate).

Because every tool reads its inputs from the session dict and writes its output back into the session dict (rather than tools calling each other), each tool can be tested in isolation by constructing a session dict by hand — which is how Milestone 3 testing is done before Milestone 4 wires the loop together.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to a message naming which filters were applied (e.g. `"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price limit, removing the size filter, or searching with broader keywords."`) and return the session immediately. The UI shows this message in the listing panel; the outfit and fit-card panels stay empty. No retry is attempted automatically. |
| suggest_outfit | Wardrobe is empty | Do not error. Call the LLM with a prompt asking for general styling advice about `new_item` only (vibe, colors, what categories of pieces pair well) instead of referencing wardrobe items. Return that advice string normally; `session["error"]` stays `None` and the loop proceeds to `create_fit_card` as usual. |
| suggest_outfit | LLM call raises an exception or returns a blank string | Catch the exception inside `suggest_outfit`, log it (print/stderr), and return a hardcoded fallback string such as `"Style this with neutral basics from your closet — pair it with your most-worn bottoms and a simple layering piece."` The loop treats this like any other suggestion and proceeds to `create_fit_card`; `session["error"]` stays `None`. |
| create_fit_card | Outfit input is missing or incomplete (empty/whitespace string) | Skip the LLM call and return a descriptive string directly, e.g. `"Couldn't generate a caption because no outfit suggestion was available for this item."` Store it in `session["fit_card"]` and return the session normally; `session["error"]` stays `None` since the listing was found successfully. |

---

## Architecture

```
User query
    │
    ▼
Planning Loop (run_agent)
    │
    ├─► parse query → session.parsed = {description, size, max_price}
    │
    ├─► search_listings(description, size, max_price)
    │       │ search_results = []
    │       ├──► [ERROR] session.error = "No listings matched ..." ──► return session
    │       │
    │       │ search_results = [item, ...]
    │       ▼
    │   session.selected_item = search_results[0]
    │       │
    ├─► suggest_outfit(selected_item, session.wardrobe)
    │       │
    │       ├─ wardrobe.items = []      → LLM gives general styling advice
    │       ├─ wardrobe.items = [...]   → LLM gives outfit using named wardrobe pieces
    │       └─ LLM call fails/blank     → hardcoded fallback advice string
    │       │
    │   session.outfit_suggestion = "..."   (never empty — no error branch here)
    │       │
    ├─► create_fit_card(outfit_suggestion, selected_item)
    │       │
    │       ├─ outfit_suggestion blank  → descriptive fallback string (no LLM call)
    │       └─ outfit_suggestion present→ LLM-generated caption
    │       │
    │   session.fit_card = "..."             (never empty — no error branch here)
    │       │
    │       ▼
    └───────────────────────────────────────────► return session
            |
            │
        error branch from search_listings also returns session directly here
            │
            ▼
    app.py: handle_query()
            │
            ├─ session.error set      → listing panel shows error, others blank
            └─ session.error is None  → listing/outfit/fit-card panels populated
                                          from selected_item / outfit_suggestion / fit_card
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use Claude (Claude Code) for all three tools, one at a time, each in its own request so I can verify before moving to the next tool.

- `search_listings`: Input to Claude = the Tool 1 block from this planning.md (inputs, return shape, failure mode) plus the existing TODO comments and `load_listings()` signature in `utils/data_loader.py`. Expected output = a complete implementation in `tools.py` that filters by `max_price`/`size` before scoring, scores remaining listings by keyword overlap with `description`, drops zero-score listings, and sorts descending. Verification before trusting it: run it directly with 3 manual queries — one that should match multiple listings (`"vintage graphic tee"`, `size=None`, `max_price=30`), one with a size filter that should narrow results (`size="M"`), and one designed to return nothing (`"designer ballgown"`, `size="XXS"`, `max_price=5`) — then manually check the returned dicts have the right fields and the empty case truly returns `[]`, not `None` or an exception.
- `suggest_outfit`: Input to Claude = the Tool 2 block plus the wardrobe schema from `data/wardrobe_schema.json`. Expected output = an implementation that branches on `wardrobe["items"]` being empty vs. non-empty, builds a prompt referencing wardrobe item names for the non-empty case, and wraps the Groq call in a try/except that returns the hardcoded fallback string on failure. Verification: call it once with the example wardrobe and once with `get_empty_wardrobe()`; confirm both calls return non-empty strings, and confirm the example-wardrobe call's output actually references a wardrobe item by name (not just generic advice).
- `create_fit_card`: Input to Claude = the Tool 3 block. Expected output = an implementation that checks for a blank `outfit` up front before calling the LLM, and otherwise builds a prompt with item title/price/platform and a higher temperature setting. Verification: call it with a real outfit string and confirm the item name, price, and platform each appear once in the caption; call it again with `outfit=""` and confirm it returns the fallback string immediately without an API call.

**Milestone 4 — Planning loop and state management:**

Input to Claude = the Planning Loop, State Management, and Architecture (diagram) sections of this planning.md, plus the `_new_session()` skeleton already in `agent.py`. Expected output = a complete `run_agent()` that follows the numbered steps exactly: parse query → `search_listings` → branch on empty results → `suggest_outfit` → `create_fit_card` → return session. Verification before trusting it: re-read the generated code against the diagram's two terminal points (the error return after `search_listings`, and the final return after `create_fit_card`) and confirm there is no other `return` statement in between; then run the two scenarios already stubbed into `agent.py`'s `__main__` block (the happy-path graphic-tee query and the no-results ballgown query) and confirm the first prints a filled-in fit card and the second prints only an error message with `outfit_suggestion`/`fit_card` left `None`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The planning loop parses the query into calls search_listings() with the item description, size, and max price as inputs retrieved from the query. This function parses through listings.json to filter items that satisfy the given parameters, and returns a list containing 3 matching listings sorted by relevance. If there are no matches found, an empty list is returned. The agent tells the user what to try differently and stops. (If this list had instead been [], the agent would send a session error to a message naming the description/size/price used, and return immediately without calling the other two tools.)


**Step 2:**
The loop picks the top result from the list returned in step 1, then calls suggest_outfit() with the user's current wardrobe and the new item as inputs. This function suggests one or more outfit combinations.

**Step 3:**
The loop picks the top outfit suggestion from the previous step, then calls create_fit_card which takes the suggested outfit and the new item as input. The LLM is then prompted with the outfit string plus the item's title, price, and platform, and returns a 2–4 sentence caption mentioning the tee by name, its price, and the platform it's listed on, in a social media-ready tone.

**Final output to user:**
run_agent() returns the completed session to app.py. handle_query() checks `session["error"]` (it's None), formats `session["selected_item"]` into a readable listing summary, and returns it together with `session["outfit_suggestion"]` and `session["fit_card"]`. Gradio renders all three immediately and simultaneously in the "Top listing found," "Outfit idea," and "Your fit card" panels.
