# FitFindr

A small tool-calling agent for secondhand shopping. You describe what you're looking
for, and it searches a mock listings dataset, suggests an outfit pairing the find with
your wardrobe, and writes a shareable caption for it — all through a Gradio UI.

Full spec (tool contracts, planning loop logic, state shape, diagram) is in
[`planning.md`](planning.md). This README is the shorter version: how it actually works,
plus how I used AI to build it.

## Setup

```bash
pip install -r requirements.txt
```

Then `python app.py` and open the URL it prints.

## How the loop decides what to do

`run_agent()` isn't three tools fired in sequence - it makes one real decision per run.
It parses the query (regex, not an LLM call: price and size are pulled from anywhere in
the text, description comes from the first sentence only, since later sentences are
usually wardrobe context, not the ask), calls `search_listings`, and then branches:

- **No results** -> set a specific error ("No listings matched 'designer ballgown' (size
  XXS, under $5). Try raising your price limit...") and return immediately.
  `suggest_outfit` and `create_fit_card` never get called.
- **Got results** → take the top one, pass it into `suggest_outfit`, then pass *that*
  output into `create_fit_card`, and return everything.

I didn't just trust this by reading the code - I mocked `suggest_outfit` and
`create_fit_card` and ran the no-results query, and confirmed both mocks were never
called. That's the actual proof the branch works, not just that it looks right.

## Tools

- **`search_listings(description, size, max_price)`** - filters the 40 mock listings by
  size/price, scores what's left by keyword overlap with `description`, drops zero
  scores, sorts best-first. Returns `[]` (never `None`, never an exception) if nothing
  matches.
- **`suggest_outfit(new_item, wardrobe)`** - asks Groq (`llama-3.3-70b-versatile`) for
  1-2 outfits pairing the item with named pieces from `wardrobe["items"]`. Empty
  wardrobe? It asks for general styling advice instead. Always returns a non-empty
  string — if the API call fails, it falls back to a hardcoded suggestion rather than
  raising.
- **`create_fit_card(outfit, new_item)`** - turns the outfit + item details into a
  2-4 sentence OOTD-style caption (higher temperature so it varies between calls). If
  `outfit` is blank, it skips the LLM entirely and returns a fallback message.

## State

One session dict, threaded through every call — no tool calls another tool, nothing
lives outside it. `selected_item` flows into both `suggest_outfit` and `create_fit_card`;
`outfit_suggestion` flows into `create_fit_card`; `error` is the only thing the loop
checks to decide whether to keep going. I confirmed the same object is actually flowing
through (not getting re-derived) by checking
`session["selected_item"] is session["search_results"][0]` - `True` - and by seeing
wardrobe items named in the outfit suggestion show up again, verbatim, in the fit card.

## Error handling, with real examples

| Tool | Failure | What happens |
|---|---|---|
| `search_listings` | No matches | `"No listings matched 'designer ballgown' (size XXS, under $5). Try raising your price limit, removing the size filter, or using broader keywords."` - loop stops there, other two tools never run |
| `suggest_outfit` | Empty wardrobe | Switches to general advice: *"This adorable Y2K baby tee would pair perfectly with some distressed denim jeans or a flowy skirt..."* - no wardrobe items referenced, no crash |
| `suggest_outfit` | Groq call fails/blank | Caught internally, falls back to a hardcoded suggestion string; loop proceeds normally |
| `create_fit_card` | Blank outfit | `"Couldn't generate a caption because no outfit suggestion was available for this item."` — returned instantly, no LLM call made |

## AI usage

I used Claude (Claude Code) to implement against the specs in `planning.md`, tool by
tool. Two specific examples:

- **`search_listings`**: gave Claude the Tool 1 spec block (inputs, return shape, failure
  mode), it wrote the filter -> score -> drop-zero -> sort pipeline. I verified it with three
  hand-picked queries - a multi-match, a size-narrowing one, and a deliberately
  impossible one — and checked the impossible one actually returned `[]`, not `None`.
- **`run_agent`**: gave Claude the Planning Loop, State Management, and diagram sections,
  plus the existing `_new_session()` skeleton. The spec hadn't pinned down *how* to parse
  the query, so Claude proposed the regex approach as part of writing the function.
  Planning.md's original verification plan for this step was just "re-read the code and
  run the two `__main__` scenarios" - I went further and added a `unittest.mock`-based
  test proving the no-results branch never invokes the other two tools, since reading
  code doesn't prove a function wasn't called as well as a mock assertion does.

## One honest gap

`planning.md` never committed to a query-parsing strategy before I wrote `agent.py`,
even though the TODO in the code explicitly asked for that to be decided and documented
first. The regex approach got decided while writing the function, not before. I've
since backfilled the decision into the Planning Loop section, but the order was backwards
for that one piece. Also worth knowing: the parser doesn't strip leading articles ("a
vintage graphic tee" keeps the "a") — harmless for scoring, but the kind of rough edge
an LLM-based parser wouldn't have.
