# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""The DSL v1 authoring card — the reference a local recipe file is checked against."""

AUTHORING_CARD_V1 = """\
## DSL v1 quick reference (this card is the authoritative summary; lint teaches the rest)

### Document shape — no YAML frontmatter

```
# Recipe Title

## First Atom [phase=<kebab-id> section=<kebab-id> duration=<int> attention_level=<level> hold=<int> equipment=[…]]
Prose with @ingredient{…} annotations.

## Second Atom [phase=… section=… … depends_on=[first-atom]]
More prose.
```

The title is the single `#` heading; sections/phases are inferred from the union of atom metadata (no separate declarations).

### Identifier convention — kebab-case everywhere a slug appears

`phase=`, `section=`, items in `depends_on=[…]`, atom ids (auto-derived from title — `## Brown Beef` → `brown-beef`), inline `@<slug>`, `#<slug>`, `~<name>`, `^{<phase-id>}`. Regex: `[a-z][a-z0-9-]*`. Snake_case still parses with a warning.

### Atom metadata

- `phase=<id>` AND `section=<id>` — REQUIRED on every non-derived, non-note atom (single-section recipes use `section=main`)
- `duration=<int min>` — the atom's WALL-CLOCK time, start to finish, including passive time (an 18-hour rise is `duration=1080`; a 20-minute butter-softening rest is `duration=20`); multiplied by `count=` if >1. NEVER author hands-on minutes here — hands-on time is DERIVED as `duration × attention share`. Timers live inside this duration, so a `~timer` total can never exceed `duration=` (lint AA fires). (`active=` is the retired legacy spelling of this key — lint AB nudges the rename)
- `attention_level=<none|low|medium|high|full>` — the hands-on share of `duration`. `none`/`low`=walk away (0.0), `medium`=stir-and-walk (0.5), `high`=at the stove (0.8), `full`=no other tasks (1.0). A 30-min simmer you check occasionally is `duration=30 attention_level=low` with `~simmer{30%min}` in its prose (30 min on the clock, ~0 hands-on; the ring is the come-check)
- `hold=<int min>` — max minutes output can sit before next step starts (999 = stable)
- `equipment=[skillet, bowl, …]`
- `depends_on=[brown-beef, drain-fat]`
- `count=<int>` (atom iterations), `derived=true` (compiler-lifted prep; schedules but doesn't render), `type=note` (asides; doesn't schedule)

Legacy v0 fields `out=`, `t=`, `a=`, `w=` in HTML comments are NOT valid v1 syntax. The metadata block goes in `[square brackets]` after the title.

### Inline annotations

- `@<slug>{<ingredient line>}` — canonical ingredient (first use; the ingredient list is projected from these). Write it as it should read on the ingredient list — noun + measurement
- `@<slug>{<ingredient>}(<prep>)` — explicit prep slot: braces = what you BUY (noun + measurement, e.g. `2 cloves garlic`), parens = what you DO (`(minced)`). Fond lifts the prep into a scheduled step and shifts its verb form ("Mince the garlic"); the braces stay verbatim on the ingredient list. Placement decides prep-vs-product: `@beef{1 lb ground beef}` is bought ground (no task); `@beef{1 lb beef}(ground)` is a grind task. Prefer this form when the prep is an action; the slot is optional (inline prep in the braces still parses but is only inferred)
- `@<slug>` — bare reference (no new list entry)
- `@<slug>[<part>]{<qty phrase>}` — partition for divided ingredients
- `@<slug>[remainder]` — special: total − sum(named partitions)
- `~<name>{X-Y%min × N}` — timer; `× N` repeats it (per-side, per-batch), and comma-separated segments (`~saute{3-4%min, 1%min}`) model a step's sequential timed parts. The `%` syntax is ONLY for timer brackets — NEVER inside `@{…}` ingredient brackets
- `^{<phase-id>}` — in-recipe step reference by PHASE id (renders as "step N"); use this instead of an absolute "step 2" so the link survives optimizer resequencing (rule B validates the id against the recipe's phases)
- a cross-recipe component is linked with `@<recipe-handle>{<yield>}` — an `@`-ref to another recipe's handle, NOT a caret; the linker resolves it at meal-plan time

### Verbs → attention_level rule of thumb

`sauté` → medium · `brown`/`sear`/`fry` → high · `whisk`/`knead`/`fold` → full · `simmer`/`bake` → low or none · `preheat`/`rest`/`chill` → none · boil water → `low` (the cook watches for the boil — see the timer rule below).

### Authoring quality — what good DSL looks like

- **Atomic, single-verb steps.** Each `##` atom does ONE primary action, and its title is that verb phrase (`## Brown Beef`, not `## Brown Beef and Make Sauce`). A step that browns AND simmers hides parallelism from the optimizer and forces the cook to re-read mid-step — split it.
- **Explicit timers for stated durations.** Any duration your prose states ("about 10 minutes", "until golden, 5-7 min") carries a `~timer{10%min}` / `~name{5-7%min}` — the runtime and the lock screen fire sigiled timers only; un-sigiled minutes in prose never reach them; the schedule reads `duration=`.
- **A timer is a signal, not an annotation.** Add a `~timer` where the ring is something the cook acts on — a simmer (ring = come check), a sear per side (ring = flip), a bake (ring = check), a rest of definite length: time the process you control. But a transition the kitchen signals — water reaching a rolling boil, oil shimmering, butter foaming, an oven preheating — gets NO invented minutes: state no duration in prose, carry no sigil, and put the wall-clock estimate in `duration=` with the matching `attention_level` (`low` for the set-and-check class, `none` for the preheat). A countdown there is noise: the pot boils when it boils, and the cook taps when the oven is hot — the dependency and that tap hold the bake behind a hot oven (a sigil on a preheat is harmless, never required). Durations the source states still get their sigil per the rule above.
- **Repeated and multi-part timing is modeled, not prosed.** "2 minutes per side" is `~sear{2%min × 2}` (the runtime fires one timer per side); a step with two timed movements ("3-4 min, then 1 min more") carries a multi-segment timer `~saute{3-4%min, 1%min}` — or better, splits into two atoms. "Cook per package instructions" states a typical range (`~cook-pasta{9-12%min}`) so the scheduler sees real time.
- **A passive wait belongs to the atom that STARTS it — never a separate "Wait for X" step.** "Spoon the yogurt into the strainer and let strain, ~strain{30%min}" is ONE atom (`duration=32 attention_level=none`): the cook sees one step with its timer, and the scheduler still floats other work into the walk-away window (hands-on derives from `attention_level`, not from splitting). A wait with NO initiating action in the recipe (warming to room temperature, a rise the dough enters by itself after shaping) stands alone. Never fuse a wait into the CONSUMING step instead (the bake never absorbs the rise), and never understate `duration=` — a 90-min rise authored as `duration=1` collapses the whole schedule into a lie.
- **The step DAG converges to ONE final step (single-sink).** Every branch (sauce, pasta, topping) is eventually consumed via some step's `depends_on`; a step nothing depends on is usually a missing edge. Steps that can genuinely run in parallel stay independent — never chain serially "to be safe."
- **Readiness steps stay independent.** Preheating an oven or boiling water does NOT depend on food steps; the step that needs the hot oven/water depends on BOTH the readiness step and its food prerequisites, so the scheduler can float the readiness step into other work.
- **Prep in the prep slot.** When an ingredient carries a prep ACTION, author it as `@slug{noun + measurement}(action)` so it schedules as a real task; keep bought product forms in the braces. Don't bury prep work inside a cooking step's prose.
- **One slug per ingredient, forever.** A recurring ingredient is defined ONCE with `@slug{line}` and referenced bare (`@slug`) after; a divided amount uses partitions (`@salt[coating]{1 tsp salt}` … `@salt[sauce]{1 tsp salt}`). Never mint `@salt2`/`@butter3` for a repeat, and the slug names the FOOD — `@garlic{3 garlic cloves}`, never `@cloves` (a measure word canonicalizes to the wrong entity).
- **One food per slug — consolidation is only for the SAME food.** Garlic powder ≠ onion powder; brown sugar ≠ granulated sugar; black pepper ≠ cayenne. Each distinct source ingredient keeps its OWN `@def` with its own amount — never merge look-alikes into one def ("3 tsp garlic and onion powder" is a rewrite of the recipe, even with the breakdown in parens). "Divided" consolidation is for one identical food split across steps.
- **The braces NAME the food.** `@onion{2 Tbsp}` projects a nameless "2 Tbsp" onto the ingredient list — the slug is a key, not display text. Write `@onion{2 Tbsp onion}(diced)`. Equipment and packaging (parchment, foil, jars, cheesecloth) go in `equipment=[…]`, never in an `@def` — the ingredient list is a shopping list of food. Pantry items used in steps (cooking spray) still get a def or an Also-Needed note so they reach the list.
- **Divided amounts: the total is data, never prose.** Declare the canonical total ONCE in a `[type=note]` atom (`## Also Needed [type=note]` → `@flour{635 g plain flour, divided}.` — feeds the ingredient list, renders no step). Each use is a partition carrying ONLY that step's amount (`@flour[dough]{600 g}`); "the rest" is `@flour[remainder]` — the partition NAME, never `{remainder}` in braces. The cook sees each step in isolation, so partition EVERY other use with its amount — that's what lets the compiler compute and display the remainder ("remaining kosher salt (1/2 tsp)"); an unpartitioned use leaves the cook guessing. Do NOT restate the total in prose ("(from 635 g…, divided)") and do NOT chain forms on one sigil (`@x{total}[part]{qty}` is invalid — one sigil, one form).
- **No markdown in prose.** Never wrap sigils or text in backticks/asterisks — prose is plain text; sigils need no quoting.
- **Partition granularity matches step usage.** If a step uses part of an amount, give THAT step its own partition (`@milk[batter]{100 ml}`) — never "1/3 of the @milk[crepes]{300 ml}" (the cook sees 300 ml and errors). Don't repeat the noun after a sigil (`the remaining @milk milk` renders doubled), and keep every ~timer inside an action sentence — never as its own fragment ("… oven. ~preheat{15%min}." reads as a bare "15 min" step).
- **Equipment lives in the header.** Every tool that gets dirtied goes in `equipment=[…]` — never as a `#sigil` in prose — so dirty-dish counts are real.

### Fully-worked atom

```
## Brown the Beef [phase=cook-filling section=main duration=8 attention_level=high hold=20 equipment=[skillet]]
Brown the @beef{2 lbs ground beef} in a large skillet over medium-high heat, breaking it up with a spoon, about ~brown{6-8%min}.
```
"""
