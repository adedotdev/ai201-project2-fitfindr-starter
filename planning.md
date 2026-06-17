# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the 40 mock listings in `listings.json` for items matching a free-text description, with optional size and price filters. Returns a ranked list for the agent to pass on to `suggest_outfit`.

**Input parameters:**
- `description` (str): keywords from the user's query, e.g. `"vintage graphic tee"`. Scored against each listing's `title`, `description`, and `style_tags` by word overlap.
- `size` (str | None): e.g. `"M"`. Case-insensitive substring match (`"M"` matches `"S/M"`). `None` skips size filtering.
- `max_price` (float | None): inclusive price ceiling, e.g. `30.0`. `None` skips price filtering.

**What it returns:**
A `list[dict]` in the exact shape stored in `listings.json` (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`). Anything failing the size/price filters is dropped first; what's left is scored by keyword overlap, anything scoring 0 is dropped, and the rest is sorted best-match-first. If nothing qualifies, it returns `[]` — never `None`, never an exception.

**What happens if it fails or returns nothing:**
The loop checks for an empty list right after calling this. If empty, it sets `session["error"]` to something specific and actionable (e.g. `"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price limit, removing the size filter, or using broader keywords."`) and returns immediately — `suggest_outfit` and `create_fit_card` never run.

---

### Tool 2: suggest_outfit

**What it does:**
Asks the LLM (Groq) for 1–2 outfit ideas pairing the selected item with the user's wardrobe. If the wardrobe is empty, it asks for general styling advice instead.

**Input parameters:**
- `new_item` (dict): the listing dict the user's considering — same shape `search_listings` returns.
- `wardrobe` (dict): `{"items": [...]}`, where each item has `id`, `name`, `category`, `colors`, `style_tags`, optional `notes`. `items` can be `[]`.

**What it returns:**
A non-empty `str`. Normally it names specific wardrobe pieces (e.g. `"Pair the graphic tee with your baggy dark-wash jeans and chunky sneakers..."`). With an empty wardrobe, it gives general advice on what would pair well instead.

**What happens if it fails or returns nothing:**
It can't return `""` or raise - that's handled internally. If the Groq call errors out or comes back blank, it catches that and returns a hardcoded fallback (e.g. `"Style this with neutral basics from your closet - pair it with your most-worn bottoms and a simple layering piece."`). The loop treats this exactly like a real suggestion and moves on to `create_fit_card`. No error is set — the listing itself is still valid even without a tailored outfit.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion and item details into a short, shareable caption (2-4 sentences) for the find.

**Input parameters:**
- `outfit` (str): whatever `suggest_outfit()` returned — real suggestion or its fallback.
- `new_item` (dict): the listing dict, used for `title`, `price`, `platform`.

**What it returns:**
A 2-4 sentence `str` written like a real OOTD caption - item name, price, and platform mentioned once each, vibe described specifically, wording varied across calls (higher LLM temperature).

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace, it skips the LLM entirely and returns something descriptive, e.g. `"Couldn't generate a caption because no outfit suggestion was available for this item."` If the LLM call itself errors, same idea, a fallback string, not an exception. Either way the loop just stores whatever comes back in `session["fit_card"]`; `session["error"]` stays `None` since the listing (and at least a fallback outfit) already succeeded.

---

### Additional Tools (if any)

None — three tools cover the full flow.

---

## Planning Loop

**How does the agent decide what to call next?**

It's a fixed sequence with one real branch, in `run_agent()`:

1. Create the session with `_new_session(query, wardrobe)`.
2. Parse `query` into `description`, `size`, `max_price`, stored in `session["parsed"]`. This is regex-based, not LLM-based: price and size get pulled from anywhere in the query (`\$\d+` and `size <token>` patterns), while description comes from the first sentence only — later sentences tend to be wardrobe context, not the ask (e.g. `"...under $30. I mostly wear baggy jeans..."`).
3. Call `search_listings(**session["parsed"])`, store the result in `session["search_results"]`.
   - **No results:** set a specific error message naming what was searched for, and return right away. `suggest_outfit`/`create_fit_card` never run.
   - **Got results:** set `session["selected_item"] = search_results[0]` and keep going.
4. Call `suggest_outfit(selected_item, wardrobe)`, store it in `session["outfit_suggestion"]`. No branch needed here — it always returns something usable.
5. Call `create_fit_card(outfit_suggestion, selected_item)`, store it in `session["fit_card"]`. Same deal — always returns a string.
6. Return the session.

Nothing loops or re-calls a tool. The only early exit is step 3's no-results branch. Callers check `session["error"] is None` to know if it worked.

---

## State Management

**How does information move between tools?**

Everything lives in one session dict, created by `_new_session()` and passed through the whole run. Tools don't call each other and don't touch anything outside the session — they read their inputs from it and the loop writes their output back in.

- `query` (str): the raw input, untouched after creation.
- `parsed` (dict): `{description, size, max_price}` from step 2, fed into `search_listings`.
- `search_results` (list[dict]): full ranked list, kept around even though only `[0]` gets used.
- `selected_item` (dict | None): `search_results[0]`, passed into both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict): passed in at session creation, never mutated.
- `outfit_suggestion` (str | None): output of `suggest_outfit`, fed into `create_fit_card`.
- `fit_card` (str | None): output of `create_fit_card` — the final artifact.
- `error` (str | None): only set on the no-results branch. Both the loop and `app.py` check this.

Since every tool just reads/writes the session dict instead of calling each other, each one can be tested alone by handing it a session dict by hand — that's how I tested them before wiring up the loop.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` naming the filters that were applied (e.g. `"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price limit, removing the size filter, or searching with broader keywords."`) and return right away. Listing panel shows the message; outfit/fit-card panels stay empty. No auto-retry. |
| suggest_outfit | Wardrobe is empty | Not an error — prompt the LLM for general styling advice about the item instead of referencing wardrobe pieces. Returns normally, loop continues to `create_fit_card`. |
| suggest_outfit | LLM call errors or returns blank | Caught internally, logged, falls back to a hardcoded suggestion. Loop continues as if it were a normal result. |
| create_fit_card | Outfit input missing or blank | Skip the LLM, return a descriptive string directly (e.g. `"Couldn't generate a caption because no outfit suggestion was available for this item."`). Stored normally; `session["error"]` stays `None` since the listing was already found. |

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

**Milestone 3 — Individual tool implementations:**

Using Claude (Claude Code) for all three tools, one at a time, verifying each before moving to the next.

- `search_listings`: gave Claude the Tool 1 block above plus `load_listings()`'s signature. Expected a filter -> score -> drop-zero -> sort pipeline. Verified with three queries by hand — one that should match several listings (`"vintage graphic tee"`, no size, `max_price=30`), one that narrows by size (`size="M"`), and one designed to return nothing (`"designer ballgown"`, `size="XXS"`, `max_price=5`) - checked the fields on the matches and that the empty case truly returns `[]`.
- `suggest_outfit`: gave Claude the Tool 2 block plus the wardrobe schema. Expected it to branch on `wardrobe["items"]` being empty, and to wrap the Groq call in a try/except with the hardcoded fallback. Verified by calling it once with the example wardrobe and once with an empty one. Both non-empty strings, and the example-wardrobe case actually names a wardrobe item.
- `create_fit_card`: gave Claude the Tool 3 block. Expected a guard against blank `outfit` before any LLM call, plus a higher temperature setting. Verified by checking the item name/price/platform show up once each in a real caption, and that an empty `outfit` returns the fallback immediately with no API call.

**Milestone 4 — Planning loop and state management:**

Gave Claude the Planning Loop, State Management, and Architecture sections, plus the `_new_session()` skeleton already in `agent.py`. Expected a `run_agent()` matching the numbered steps exactly. Verified by checking the generated code only has two `return` points (matching the diagram's two terminal points), then running the happy-path and no-results scenarios already stubbed into `agent.py`'s `__main__` block.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The loop parses this into `{"description": "a vintage graphic tee", "size": None, "max_price": 30.0}` and calls `search_listings()` with those values. It filters down to items $30 or under, scores them against "vintage graphic tee", and returns a sorted list. Since the list isn't empty, the loop sets `selected_item = search_results[0]` and keeps going. (If it *had* come back empty, the agent would set an error naming the filters used and stop here. The other two tools wouldn't run.)

**Step 2:**
The loop calls `suggest_outfit(selected_item, wardrobe)`, where the wardrobe is the example one with the user's baggy jeans and chunky sneakers already in it. The LLM gets the item details plus the wardrobe item names and returns something like *"Pair this graphic tee with your baggy dark-wash jeans and chunky sneakers for an easy thrifted streetwear look."* Stored in `outfit_suggestion`.

**Step 3:**
The loop calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM gets the outfit text plus the item's title/price/platform and returns a 2–4 sentence caption mentioning all three, in a casual OOTD tone. Stored in `fit_card`.

**Final output to user:**
`run_agent()` returns the session to `app.py`. Since `session["error"]` is `None`, `handle_query()` formats `selected_item` into a readable summary and returns it alongside `outfit_suggestion` and `fit_card`. Gradio shows all three at once. No separate accept/reject step, the user just sees the item, the styling idea, and the caption together.
