Fond DSL, © 2026 Deglaze Corp., CC BY 4.0

# Fond DSL — v1 Specification

The Fond DSL is a CookLang-superset for representing recipes as atomic, schedulable, projection-ready programs. A single source file projects to **Classic** (the creator's prose), **Optimized** (a parallelized schedule), and **agent-readable JSON** without losing fidelity.

This document is the canonical spec. The implementation lives alongside in `render_classic.py`, `lint.py`, `qty.py`, `schedule.py`, and `testscript.py`.

---

## 1. File shape

A recipe file is `<name>.recipe.md`. Round-tripping a creator's published prose into a `_legacy.md` companion is the import-fixture convention; the `_legacy.md` is the import target, the `.recipe.md` is the canonical source.

The canonical document shape — what the compiler emits and what hand-authored DSL should look like going forward — is:

```
# Recipe Title

## First Atom [phase=<id> section=<id> attention_level=<word> …]
Prose with @ingredient{…} annotations.

## Second Atom [phase=<id> section=<id> attention_level=<word> depends_on=[first-atom]]
More prose.

…
```

That's the whole thing. No YAML frontmatter. The first `# Heading` (single `#`) is the recipe title. Every subsequent `## Heading` is an atom.

### 1.1 Sections and phases are inferred from atom metadata

Each atom carries `phase=<id>` and `section=<id>` in its metadata. The union of those ids across all atoms IS the structural map of the recipe — there is no separate declaration.

Display titles for sections and phases derive from the ids: snake_case → "Title Case" (`cook_filling` → "Cook Filling"). The Classic renderer can apply a small convention layer on top (e.g., "For the …" prefix for sections in cookbook-style render), but the language itself has no place to author a different title.

For **single-component recipes** that don't need sub-blocks, pick one section id (commonly `main`) and use it on every atom. For **multi-component recipes** (filling + topping, base sauce + garnish, etc.), use a descriptive section id per component. The compiler emits both forms.

### 1.2 Legacy frontmatter (backward-compatible)

Earlier corpus authoring used a YAML frontmatter block between `---` fences to declare `title`, `sections`, `phases`, `author`, `yield`, `attribution`, etc. The parser still accepts this for backward compatibility — existing recipes work unchanged. New compiler output does not emit it.

Document-level metadata that used to live in frontmatter (yield, author, attribution chain, license, source_url, lineage, nutrition) is **server-side data**, keyed by `recipe_id` and stored alongside the document when the recipe is saved. It does not live in the creator-authored source. This separation keeps the DSL focused on what the cook/scheduler/UI projections actually need.

One server-side field deserves explicit mention: **`handle`**, the kebab-case human-readable identifier exposed in cross-recipe references (`@<handle>{…}`, §2.6). A handle is `<kebab-title-prefix>-<suffix6>`: the title slug truncated at a word boundary to 43 chars plus a 6-char suffix derived from the recipe UUID (`steamed-rice-2x7ngf`). **The suffix uses a lowercase alphabet** (`[a-z0-9]`) so the whole handle is a valid kebab slug (§1.6) and can stand wherever an `@<slug>` can — that trailing suffix block is also what makes a recipe reference self-disambiguating against a pantry-ingredient slug, so the cross-recipe form needs no marker sigil (no `./`, no `@@`). The handle is deterministic in (title, recipe_id) — no corpus-wide collision counter — so lazy heal-on-read and backfill converge on identical values. The server resolves handle → UUID at save/link time; bare legacy slugs still resolve via the `slug` fallback. The handle is the *language-level* name an agent writes; the server resolves it to the recipe's UUID at link time, so the DSL stays readable while persistence stays stable.

### 1.3 Atom header

```
## <Title> [k=v k=v …]
```

- **Title**: human-readable, must slugify to a unique id within the recipe. Diacritics normalize (`Sauté` → `saute`).
- **Slug** = lowercase, non-alphanumeric → spaces → collapsed hyphens. `## Brown the Beef` → `brown-the-beef`.
- **Metadata block** `[…]` is space-separated key=value pairs. Optional.

### 1.4 Atom metadata keys

| Key | Type | Purpose |
|---|---|---|
| `phase` | string | Phase id; required on every non-derived non-note atom. The phase groups atoms into Classic paragraphs and into scheduler dependency rounds. |
| `section` | string | Section id; required on every atom (regular and derived). Each atom's section drives the ingredient-list projection and the Classic sub-headings. |
| `duration` | int (min) | **Wall-clock duration** of the atom in minutes, including passive stretches (rises, rests, oven time) — multiplied by `count` if >1. Hands-on time is never authored: the scheduler derives it as `duration × attention_level share` (§3.4). A 20-minute butter-softening rest is `duration=20 attention_level=none`. |
| `active` | int (min) | **Legacy alias for `duration`** (`duration` wins if both are set). Retired because the name taught the wrong semantics — models authored hands-on minutes into it, collapsing makespan. After the rename, "active" means exactly one thing system-wide: derived hands-on time (`active_minutes`), never an authored field. Rule AB nudges the rename. |
| `attention_level` | enum | Envelope category — see §3.4 |
| `attention` | float 0.0–1.0 | Legacy scalar; `attention_level` wins if both set |
| `hold` | int (min) | Max time the output can sit before next step starts |
| `count` | int ≥1 | Number of iterations of this whole atom (and its timer) |
| `equipment` | list | Equipment claimed (`[skillet, saucepan]`) — see §3.5 |
| `depends_on` | list | Step ids this atom requires (`[brown-the-beef]`) |
| `derived` | bool | Marks an atom lifted by the compiler — see §1.4 |
| `derived_from` | typed ref | What the compiler lifted from (`ingredient:potatoes`) |
| `optional` | bool | Step is optional in this projection |
| `type` | enum | `note` for tip-style asides; defaults to regular atom |
| `iteration` | int | Deprecated alias for `count`; will be removed |

### 1.5 Atom types

- **Regular atom**: has `phase=` AND `section=`, renders in Classic, schedules.
- **Derived atom**: `derived=true`, does *not* render in Classic, *does* schedule. Used for compiler-lifted prep work (e.g. peel-and-cube-potatoes lifted from an ingredient line). Must declare `section=`. (Note: a separate Mise en Place derived block for canonical ingredient defs is **no longer required** — canonicals inline on first use, see §3.1.)
- **Note**: `type=note`, does not schedule, renders as a trailing `**Title:** prose` paragraph.

### 1.6 Identifier convention — kebab-case

Every **slug-position token** in the DSL is kebab-case: lowercase ASCII alphanumeric with `-` separators, no whitespace, no underscores, no other punctuation. Regex: `[a-z][a-z0-9-]*`.

Slug positions are:

| Where | Example |
|---|---|
| `phase=<id>` | `phase=cook-filling` |
| `section=<id>` | `section=topping` |
| Items in `depends_on=[…]` | `depends_on=[brown-the-lamb, drain-fat]` |
| Atom slug (derived from title) | `## Sauté Vegetables` → `saute-vegetables` |
| `^{…}` step reference body (intra-recipe phase id) | `^{simmer-filling}` |
| `@<slug>` / `#<slug>` / `~<name>` | `@brown-sugar`, `#dutch-oven`, `~rest` |
| Cross-recipe reference handle (`@<handle>`) | `@steamed-rice-2x7ngf` (§2.6) |

**Why kebab specifically:** agents emit it natively, URL/Markdown conventions agree, and one rule is better than the old "snake in slugs, spaces in canonicals" split that was effectively two conventions wearing one hat.

**Backward compatibility (deprecation window).** The linter accepts snake_case (`_`) in slug positions and normalizes it to kebab on parse, emitting a Rule O warning. Multi-word canonical slugs with spaces (`@brown sugar`) are also normalized to kebab with a warning. New compiler output emits kebab only.

**Display rule.** When a slug renders inline in Classic prose, both `-` and `_` become spaces, so `@brown-sugar` reads "brown sugar." This keeps the display layer indifferent to the deprecation window.

---

## 2. Inline annotations

Five sigils carry structured data inside prose. All are CookLang-compatible at the parser level; the partition extension is additive.

### 2.0 Bracket content rules (one place where Fond diverges from CookLang)

Fond is a CookLang superset in *syntax shape* (`@`, `#`, `~` sigils) but the bracket *content* differs by annotation type. Getting this wrong is the most common compiler bug.

| Annotation | Bracket contains | `%` allowed? |
|---|---|---|
| Canonical ingredient `@x{…}` | the creator's verbatim ingredient line ("2 lbs ground lamb (beef works too)") | **No** |
| Partition def `@x[part]{…}` | a qty phrase that reads naturally before the slug ("1/4 cup", "a splash of") | **No** |
| Recipe reference `@<handle>{…}` (§2.6) | a yield/qty phrase for the referenced recipe's output ("300 g", "to serve") or empty | **No** |
| Timer `~name{…}` | CookLang's `qty%unit` shorthand, optionally with range/multiplier | **Yes** |

Rationale: canonical brackets feed the ingredient *list* projection (display the creator's exact wording). Partition brackets feed the inline render template `<bracket> <slug>` so the prose reads naturally. Timer brackets feed the runtime UI with structured `(qty, unit, segments)` data.

### 2.1 Ingredients — `@`

```
@<slug>{<creator's verbatim ingredient line>}   # canonical definition
@<slug>{<ingredient>}(<prep>)                    # canonical + explicit prep slot (§2.1.1)
@<slug>                                          # bare reference; no list entry
@<slug>[<part>]{<phrase>}                        # partition definition
@<slug>[<part>]                                  # partition reference
@<slug>[remainder]                               # special: total − sum(others)
@<handle>{<yield>}                               # cross-recipe reference (§2.6); the slug is another recipe's handle
```

**Slug rules:** kebab-case (`@tomato-paste`). See §1.6 for the global identifier convention. Snake_case (`@tomato_paste`) and multi-word (`@tomato paste`) are accepted with a deprecation warning.

A reference to **another recipe** reuses the `@` sigil — a sub-recipe *is* an ingredient (CookLang's composition model). It's distinguished from a pantry ingredient purely by its handle's trailing UUID suffix (§1.2, §2.6), so it needs no special marker.

**Display rule:** the slug (with `-` and `_` → ` `) is what appears inline in Classic. The `{…}` text is consumed for either the ingredient list (canonical) or the partition's qty (partition def).

**Partition def render template:** `<bracket text> <display slug>`.

| Source | Renders as | List contribution |
|---|---|---|
| `@meat{2 pounds ground beef}` | "meat" | "2 pounds ground beef" |
| `@meat` | "meat" | (none) |
| `@flour[wet]{1/4 cup}` | "1/4 cup flour" | (none — covered by canonical) |
| `@flour[remainder]` | "flour" | (none) |
| `@flour[wet]{1/4 cup of}` | "1/4 cup of flour" | (none) |

The bracket text is whatever phrase the creator wants before the slug. Want "of"? Write `{1/4 cup of}`. Want plural? Write `{2 large eggs}` and use a slug that pluralizes (`@eggs`).

#### 2.1.1 Prep slot — `(…)`

An optional parenthetical **immediately after** the `{…}` carries the ingredient's **prep**: a transformation the creator does to the ingredient. It borrows CookLang's preparation-note shape (`@onion{1}(diced)`) but gives it real semantics — the prep slot is *compiled*, not just displayed.

```
@garlic{2 cloves garlic}(minced)          # prep: Fond renders/schedules "Mince the garlic"
@beef{1 lb ground beef}                    # product: bought ground — no task
@onion{1 large onion}(finely diced, about ½ cup)
```

**Two slots, one contract.** The braces hold *what you buy*; the prep slot holds *what you do*:

| Slot | Holds | Fond's promise |
|---|---|---|
| `{…}` | The ingredient as it appears on the **ingredient list** — noun + measurement + product form ("ground beef", "1 (14 oz) can tomatoes") | Surfaces verbatim on the list. **Verb forms are never shifted.** |
| `(…)` | The **prep action** — a transformation ("minced", "finely diced") | May be lifted into a derived prep atom (§77), **scheduled** where it fits best, and **verb-shifted** to the imperative (§336: `minced` → "Mince"). Not an ingredient-list entry. |

**This resolves prep-vs-product by placement, not inference.** "Ground" written in the braces means the ingredient *is bought* ground (`@beef{1 lb ground beef}` — product, no task); the same word in the prep slot means the cook *does* it (`@beef{1 lb beef}(ground)` — a grind task). The creator decides which by *where they write it*, and the presence of a prep slot is their explicit signal that Fond may surface that transformation as a step and shift its verb form. Nothing outside the prep slot is ever reshaped.

**Yield.** A prep may state its yield inside the slot (`(diced, about ½ cup)` → "Dice … to yield about ½ cup", §336).

**Parse rule (no paren collision).** The prep slot is the single `(…)` group *immediately following* the closing `}`. Parentheses *inside* the braces are literal ingredient text — `@tomato{1 (14 oz) can tomatoes}` has no prep slot. Grammar: `@<slug>(\[<part>\])?\{<phrase>\}(\(<prep>\))?`.

**Fallback (the bridge to the past).** The older inline form — prep as a clause inside the braces (`@onion{1 large yellow onion, diced}`) — still parses; the compiler infers the prep heuristically (best-effort prep-vs-product classification) for legacy conversions and quick authoring. **The explicit slot is authoritative:** when a prep slot is present it overrides inference. Converters SHOULD emit the explicit slot when confident and leave prep inline when unsure — an unresolved inline prep is a gap that invites the creator to disambiguate.

**Double-lift.** If a slug's prep is given in its slot *and* an explicit prep atom already exists for that ingredient, the authored atom wins — the compiler does not materialize the prep twice.

### 2.2 Equipment — `#`

Same five shapes as `@`, with `#` instead. Currently the linter accepts and the renderer strips, but the scheduler doesn't yet claim from a multi-equipment pool — equipment is metadata-only for now (the `equipment=[…]` field on the atom header is what the scheduler sees).

### 2.3 Step references — `^{phase-id}` (intra-recipe)

A caret is an **intra-recipe** narrative reference: it points at a phase within *this* recipe and renders as that phase's computed step number. It is *not* a dependency (use `depends_on=` on the atom header for scheduling edges, §1.4) and it is *not* a cross-recipe link (use a recipe reference, §2.6).

```
Source:  Make the filling through ^{simmer-filling}.
Classic: Make the filling through step 2.
```

The body is a `phase-id` (kebab). Numbers are computed from the atom-bearing phase order across sections, so the reference survives the optimizer resequencing the recipe — which is exactly why an author writes `^{simmer-filling}` instead of a hard-coded "step 2". This abstraction has no CookLang equivalent (CookLang has no step ids); it is a Fond extension.

**Linter behavior.** Rule B requires the referenced phase to exist in the document. Rule O requires the body to be a kebab slug. There is no colon form — a `:` inside a caret body is now invalid (cross-recipe composition moved to the `@` recipe reference, §2.6).

### 2.4 Timers — `~`

```
~{15%min}                  → "15 minutes"
~name{15%min}              → "15 minutes" (name is metadata for runtime UI)
~name{10-12%min}           → "10 to 12 minutes"
~name{5%min, 10%min}       → "5 minutes, then 10 minutes"
~per_side{2-3%min × 2}     → "2 to 3 minutes" (the ×2 segment count is metadata)
```

Multi-segment timers are sequential phases of one logical countdown. The `× N` shorthand is for identical segments — the runtime queues N consecutive timer events.

### 2.5 Partitions — `[part]`

The `[part]` token always sits between slug and bracket (or after slug for bare ref). See §2.1.

Reserved partition names:
- `[remainder]` — compiler-computed: `total − Σ(named partitions)`. Cook-surface renders display the computed amount when it is determinate — "remaining kosher salt (1/2 tsp)" — because playback shows steps in isolation and the cook can't do the subtraction mid-recipe. Determinate requires a parseable canonical total and ≥1 quantified named partition covering every other use; otherwise the render stays the bare "remaining <noun>". Classic keeps the creator's prose either way.
- `[each]` — per-iteration; pair with `count=N` on the step.

### 2.6 Recipe references — `@<handle>{…}`

Cross-recipe composition follows CookLang: **a referenced recipe is an ingredient.** When a dish is assembled from components that are themselves recipes — a cake plus its frosting, a roast plus its gravy, a bowl plus a special sauce — the sub-recipe is written with the ordinary `@` sigil, using the other recipe's `handle` (§1.2) as the slug:

```
@<handle>{<yield>}    # reference + ingredient-list entry, e.g. @raspberry-frosting-9k2m4p{300 g}
@<handle>             # bare reference; no list entry
```

This is the same shape as a canonical ingredient (§2.1) — deliberately, because a sub-recipe *is* an ingredient of the parent dish. No marker sigil (`./`, `@@`) is needed: the handle's trailing lowercase UUID suffix (`-9k2m4p`, §1.2) is what distinguishes a recipe reference from a pantry ingredient, and we control handle minting so the two namespaces never collide.

```
Source (a fish-katsu-curry recipe):
  To serve, pour the sauce over @steamed-rice-2x7ngf{} and top with the fish katsu.

Single-recipe Classic render (suffix stripped for display):
  To serve, pour the sauce over steamed rice and top with the fish katsu.

Meal-plan render (with the Steamed Rice recipe linked):
  To serve, pour the sauce over steamed rice (Steamed Rice) and top with the fish katsu.
```

**Display rule.** Inline, a recipe reference renders like any `@<slug>`: the suffix block is stripped and the title-prefix is shown with `-` → ` ` (`@steamed-rice-2x7ngf` → "steamed rice"). The `{…}` yield feeds the ingredient-list projection, where the entry surfaces as a component with a link to the referenced recipe.

**Resolution model.** At the language level the handle is a human-readable string; the backend resolves it to a stable corpus UUID at save time. A meal planner is the natural consumer — it loads each referenced handle's DSL, splices the sub-recipe's DAG in as an upstream producer of the referenced component, and emits one combined LS-tethered schedule across all the recipes in the plan.

**Linter behavior.** The single-document linter treats `@<handle>{…}` exactly like a canonical ingredient (bracket-content rules apply — Rule N still forbids `qty%unit` shorthand). It does **not** verify that the handle resolves; existence checks against the corpus happen when the recipe is saved or a meal is planned, not in the single-document linter (which can't see other recipes). Rule O validates the handle as a kebab slug.

*Granular cross-recipe pointers* (referencing one specific phase/atom/ingredient *inside* another recipe, e.g. the old `^{handle:artifact}` colon form) are **out of scope for v1** — whole-recipe composition covers the real cases. The colon form is removed.

---

## 3. Semantic rules

### 3.1 Source-order ingredient projection

The ingredient list is *projected* from `@<slug>{…}` canonical annotations in source order, grouped by the atom's `section=` metadata. The creator never writes a separate ingredient block — the renderer composes it.

**Canonical defs inline on first use.** When an ingredient first appears in any atom's prose, write the full `@<slug>{<creator's verbatim ingredient line>}`. Subsequent mentions of the same slug use bare `@<slug>` (no brackets) so the prose stays lean and the ingredient list isn't duplicated. The compiler MUST NOT emit a separate "Mise en Place" derived block to collect canonicals — that pattern existed in earlier corpus authoring but is deprecated; it adds an extra atom that doesn't render in Classic and doesn't schedule meaningfully.

### 3.2 Round-trip rule

The Classic render must **semantically** equal the legacy creator prose. **Byte-identical is not required** — minor normalizations (consistent slug-display, structural sub-headers, "of"/"the" smoothing) are acceptable when they preserve cook intent. The convention: *"add a clarifying word, never betray the user's intent."*

### 3.3 Phase concatenation

Atoms within a phase render their prose joined by a single space. **Invariant: every atom prose must end with sentence-final punctuation** (`.`, `!`, `?`, `…`). Linter Rule E enforces.

### 3.4 Attention envelope

The `attention_level` field is the cook's bandwidth claim during the body of the atom. Five categories:

| Level | Scheduler value | What it means | Examples |
|---|---|---|---|
| `none` | 0.0 | Fire-and-forget. No mid-task interaction. A `~timer` here is a countdown the cook acts on at the ring — the ring means check the bake (or end the rest); the doneness cue stays in the prose. Without one the atom is a transition the kitchen signals (a preheat) and `duration=` is the schedule's estimate — nothing counts down. | Preheat oven, bake, rest, chill, rise |
| `low` | 0.0 | Set-and-check. A `~timer` here is a countdown the cook acts on at the ring — the ring means come check; the doneness cue stays in the prose. Without one the atom is a transition the kitchen signals (water coming to a boil) and `duration=` is the schedule's estimate — nothing counts down. | Boil water, simmer covered, slow caramelise, cook pasta |
| `medium` | 0.5 | Multitaskable. Cook can pair with another `medium`. | Sauté veg, stir-and-walk, whisk glaze |
| `high` | 0.8 | At-the-stove. Can pair with `low`/`none` only. | Brown meat, sear, fry, stir-fry |
| `full` | 1.0 | Fully consumed. Nothing else fits. | Whisk batter, knead, plate, dough work |

**Rule of thumb — match the envelope to the verb:**
- "Sauté" → `medium`
- "Brown" / "Sear" → `high`
- "Whisk" / "Knead" / "Mix" / "Fold" → `full`
- "Simmer" / "Bake" → `low` or `none`
- "Boil water" → `low` (§7 rule 6 — the cook watches for the boil; a transition the kitchen signals: the estimate lives in `duration=`, no minutes in prose, no sigil)

Setup and finish moments (≤1 min each — drop pasta, check al dente, drain) are runtime UI concerns, not scheduler concerns. The scheduler only sees the body attention.

`none` and `low` collapse to 0.0 for scheduling and are alike to the runtime (§5) — neither fires anything by itself; they differ only in the cook's posture (walk away; set and check). A countdown exists iff the atom carries a `~timer` sigil (rule T), and `duration=` never alarms.

**Hands-on derivation.** `duration=` is the atom's wall-clock duration (§1.4); the attention share is the coefficient that turns it into hands-on minutes: `hands-on ≈ duration × share`, capped at the authored `duration` value. Reported `active_minutes` is the sum of these per-atom contributions. Realistic makespan is the defining metric — a small approximation penalty on hands-on accuracy is the accepted trade.

**Back-compat duration floor.** For `none`/`low`/`medium` atoms the scheduler floors the atom's scheduled duration at its `~timer` total (`max(duration, timer_total) × count`), so recipes authored under the retired hands-on-minutes convention (wall time only in the timer) still schedule honestly. Under the wall-clock convention the floor is a no-op — rule AA enforces that timers fit inside `duration=`.

### 3.5 Equipment

`equipment=[…]` is metadata on the atom header. Currently used by the linter and the canonical UI surface. The scheduler does *not* yet treat equipment as a separate resource pool — see §6.

### 3.6 Hold times

`hold=N` is the maximum minutes the output can sit between the atom finishing and a downstream consumer starting. The scheduler tethers upstream atoms forward when needed to respect this — but only when the tether doesn't grow the makespan (tether-with-rollback, §4).

### 3.7 Iteration

`count=N` means "execute this atom N times." Used with timer `× N` segments, this drives the runtime UI's per-iteration timer events. For scheduling, total active is `active × count`.

`count` does **not** multiply partition qtys for relative partitions (`[remainder]`, fraction-of-total). Named partitions inside a `count=N` atom *are* multiplied — they represent per-iteration usage.

---

## 4. Scheduler model

The scheduler is RCPSP/max with LS-tethering and rollback.

1. **Forward pass** — minute-by-minute greedy, respecting `earliest_start` floor and bandwidth (sum of running `attention_level` values ≤ 1.0).
2. **Hold-violation detection** — find edges where `downstream.start − upstream.finish > upstream.hold`.
3. **LS tether** — for each violating upstream, propose `earliest_start = LS` (computed from current resource-aware backward pass).
4. **Tether-with-rollback** — re-run forward pass with the proposal; if makespan grew, revert and accept the hold violations as warnings (the cook will hustle a bit).
5. **Iterate** until clean or budget exhausted.

This handles the common case (true tethering) and refuses to amplify bandwidth-induced false violations (NYT was the canary).

---

## 5. Projections

Same source, three views:

| Projection | Audience | Strips | Computes |
|---|---|---|---|
| **Classic** | human reader | metadata, partition tags, timer brackets, handle suffixes | phase concatenation, step refs, recipe-reference display, ingredient list |
| **Optimized** | runtime / scheduler | nothing (uses all metadata) | LS-tethered DAG, makespan, slack table |
| **Agent JSON** (planned) | LLM tools | nothing | full structured tree with prose, partitions, timers, deps |

Readers cook the DSL as written. No projection, player or scheduler infers a countdown from `duration=`, `attention_level` or prose minutes; the two lifts in the legacy `nodes[]` projection are legacy-projection-only and not part of these semantics.

---

## 6. Linter rules

Implemented in `lint.py`. All rules are mechanical; no LLM calls.

| Rule | Severity | What it catches |
|---|---|---|
| A | error | `depends_on` references a non-existent step id |
| B | error | `^{phase-id}` in prose references an undeclared phase (intra-recipe only; a `:` in a caret body is invalid — cross-recipe links use `@<handle>`, §2.6) |
| C | error | `@x[part]` reference with no prior partition def |
| D | warning | Partition qty sum ≠ canonical total |
| E | warning | Atom prose missing sentence-final punctuation |
| F | warning | Partition bracket qty duplicates adjacent prose |
| G | error | Timer body fails to parse as `X[-Y]%unit [× N][, …]` |
| H | error | `count=N` not a positive integer |
| I | error | `depends_on` cycle |
| J | error | (Strict mode only — when legacy frontmatter declares `phases:`) Phase declared but no atom references it, OR phase used but not declared. In the canonical (no-frontmatter) mode, phases are inferred from atom metadata so Rule J doesn't fire — phase ids in atoms ARE the declarations. Whitespace-in-id detection (e.g., `phase=Cook Rice` parsed as `phase=Cook`) is now handled by Rule O regardless of frontmatter mode. |
| K | error/warn | `attention_level` not in `{none, low, medium, high, full}` (error); both `attention_level` and `attention` set (warn) |
| L | error | Modern format required: non-derived atom either uses legacy v0 fields (`out=`, `t=`, `a=`, `w=`) OR is missing `phase=`. Without `phase`, the atom can't be grouped or scheduled — recipe silently passes A–K but is unschedulable. |
| M | error | Recipe must contain at least one non-derived non-note atom with `phase=`. Catches the case where the agent submits something that isn't even Fond DSL (fabricated YAML, raw prose, schema.org JSON). |
| N | error | Canonical `@x{…}` or partition `@x[part]{…}` brackets must not use CookLang `qty%unit` shorthand (`{2%lbs}`, `{4%tbsp}`, `{1/4%cup}`). They hold creator-prose / natural-language qty phrases respectively. Only timer `~name{X%min}` brackets use `%`. Compatible: prose containing `%` like `1% milk` or `85% lean` is fine. |
| O | warn/error | Identifier shape (§1.6). Slug-position tokens (`phase=`, `section=`, `depends_on` items, `^{}` body, `@x`/`#x`/`~x` slugs) must be kebab-case. Snake_case (`_`) and multi-word canonical slugs (`@brown sugar`) produce a **warning** (deprecated; auto-normalized). Spaces inside an unbracketed metadata value (`phase=Cook Rice`) produce an **error** — the metadata parser stops at whitespace, leaving the value truncated to `Cook`. A recipe reference `@<handle>` (§2.6) is validated as a kebab slug like any other `@x`. A def slug that is itself a **measure word** (`@cloves`, `@bunch`) is an **error** — it canonicalizes to the wrong entity (cloves-the-spice); the slug names the food. |
| T | suggest (gated) | Un-sigiled duration: a non-derived atom's prose states a duration ("about 17 minutes", "3-4 min", "1 hour") but the atom carries **no** `~timer` sigil. The runtime and the lock screen only fire sigiled timers — an unmodeled simmer never alerts the cook. (Scheduling reads `duration=`, the wall-clock duration; the timer sigil is the runtime's event source, and rule AA keeps the two consistent.) A transition the kitchen signals (a preheat, water coming to a boil) states no minutes in prose and carries no sigil — its estimate lives in `duration=` (§7 tip 6). Gated like AA, at `suggest` severity; atoms that already carry any timer are assumed modeled. |
| U | suggest (gated) | Undeclared ordering: a recipe with ≥3 non-derived atoms declares **zero** `depends_on` edges. The scheduler treats dependency-free atoms as fully parallel, so an undeclared bread flow (mix → rise → shape → bake) presents every step as immediately available. Almost always a conversion/authoring omission on multi-step recipes; genuinely order-free recipes (e.g. assemble-a-board) are the rare exception this stays a suggestion for. |
| V | suggest (gated) | Non-convergent step DAG: a recipe with ≥3 non-derived atoms and ≥1 `depends_on` edge whose dependency graph has **more than one sink** (a step no other step depends on). A recipe's DAG is single-sink — every branch flows into the one terminal step (plate/serve) — so an extra sink is almost always an orphaned branch (a sauce nothing consumes): a missing `depends_on` on the consuming step. V is the partial form of the flattening U catches at zero edges; genuinely order-free recipes remain U's exception, so V only fires once ordering is partially declared. |
| W | warn (gated) | Numbered ingredient slug: a canonical def whose slug is another def's slug plus a numeric suffix (`@salt` … `@salt2`). One ingredient = one slug forever — a repeat is a bare `@slug` reference; a divided amount is a partition (`@salt[coating]{…}`). Numbered slugs split one ingredient into fake distinct entries on the derived list. |
| X | suggest (gated) | Repeated action not modeled: atom prose says "per side" / "on each side" but its timer has a single segment with no `× N`. The runtime fires one timer event per repeat only when the repeat is declared — `~sear{2%min × 2}` — otherwise the cook gets one 2-minute timer for a 4-minute two-side task. |
| Y | warn (gated) | Partition defs without a canonical total: `@x[a]{…}`/`@x[b]{…}` appear but no canonical `@x{…}` def exists anywhere. The ingredient list is projected from canonical defs preferentially, so the ingredient degrades on the derived list. Declare the total once — best in a `[type=note]` atom — then partition the uses. |
| P | error | Backtick in atom prose. Converting agents leak markdown code-spans around sigils (`` `@eggs{…}` ``); backticks are never DSL syntax and reach clients as literal characters. The legacy renderer strips them defensively, but the source must not carry them. |
| Q | error | `{remainder}` as a partition's brace phrase (`@x[dough]{remainder}`). The remainder special is the partition **name** — `@x[remainder]`, no braces — which the linter can compute against the canonical total. A literal "remainder" in the qty slot renders as the word itself. |
| Z | error | Chained sigil forms: `[`/`{` immediately following a def's closing `}` (`@x{total}[part]{qty}`) or a second bracket directly after a partition (`@x[a][b]`). One sigil carries ONE form; the parser takes the first and the tail leaks into prose as garbage. The prep slot `(...)` is the only legal suffix. |
| R | suggest (gated) | Divided total restated in prose: a canonical `…, divided` def wrapped in a parenthetical after a partition of the same slug — "(from @x{total, divided})". The total is DATA (it feeds the ingredient list); restating it in prose renders verbosely in every client. Declare it once in a `[type=note]` atom; partitions carry only the step amount. |
| S | suggest (gated) | Attention coverage: fewer than half of the recipe's non-derived atoms declare `attention_level=` ("N of M non-derived atoms lack attention_level; optimizer can't find parallelism without it"). The attention coefficient is the scheduler's admission input (§3.4) — an atom without one defaults to fully-consuming, so under-annotated recipes schedule serially. Fires once per recipe when coverage drops below 50%. |
| AA | warn (gated) | Time conservation (first two-letter rule; single letters are exhausted): an atom's `~timer` total exceeds its `duration=` wall-clock value by any amount (strict since 2026-07-15, in whole minutes; a `duration=` below one minute compares as one minute) (`~rise{18%hr}` on `duration=5`), or `duration=` fails to parse as an integer (which silently scheduled as a 0-minute atom). `duration=` is the atom's wall clock — the scheduler models time from it; put the wall minutes in `duration=` and let `attention_level` carry the hands-on share (§3.4). Checks the legacy `active=` alias identically. Gated (blocks submit and saving to the corpus) but deliberately NOT an error: errors suppress scheduling, and the back-compat duration floor must keep old-corpus compile output honest. |
| AB | suggest (gated) | Legacy field spelling: the atom uses `active=` instead of `duration=`. The old name taught the wrong semantics (hands-on vs wall clock) — rename the key; the value is unchanged. Parsed identically in the meantime (`duration` wins if both are set). |
| AC | warn (gated) | Nounless canonical def: the braces never NAME the food (`@onion{2 Tbsp}` projects a nameless "2 Tbsp" onto the ingredient list). The braces are the ingredient-list display line; the slug is a key, not display text. Partitions are exempt — they carry only the step's amount by design. Promoted from the conversion fidelity battery (F6) so both agent populations face it. |
| AD | warn (gated) | Non-food def: equipment or packaging (parchment, foil, canning jars, cheesecloth, toothpicks) authored as an `@ingredient` def. It belongs in `equipment=[…]` — the ingredient list is a shopping list of FOOD. Promoted from the fidelity battery (F7). |
| AE | warn (gated) | Pantry prose gap: a pantry item (cooking spray) is used in step prose but no def or note-atom entry carries it, so it never reaches the ingredient list and the cook discovers the need mid-recipe. An `Also Needed [type=note]` atom with a def is enough. Promoted from the fidelity battery (F8). |
| AF | suggest | One atom, one timed movement: two SEPARATE `~timer` sigils in one atom play back as a single long step with buried timers. Split the step; a single multi-segment timer (`~x{3%min, 1%min}`) remains the form for sequential parts of ONE movement. |
| AG | suggest | Wait-split anti-pattern: a bare "Wait for X" atom (single dependency, timer-only content) splits one operation into two playback steps. The passive tail belongs to the atom that STARTS it ("strain the yogurt, ~strain{30%min}" — one atom, `attention_level=none`); standalone waits with no initiating action stay separate. |
| AH | suggest | Unrecognized prep-slot clause: the explicit slot is AUTHORITATIVE — a clause the classifier can't parse still lifts as a VERBATIM prep step ("Prep the tomatillos: waxy coating rubbed away"); deliberately-unliftable markers (optional/garnish/to taste) never lift. Rephrase with known participles for a clean imperative title. |
| AI | error | Duplicate atom id: two `##` titles slugify identically — the scheduler keys nodes by slug, so the earlier atom is SILENTLY SWALLOWED (its duration vanishes from makespan, its edges from the DAG). Retitle one. Rule A additionally rejects `depends_on` edges that point at `type=note` atoms (notes never schedule; the edge dangles). |

Rule D uses a dependency-free quantity parser (Python `fractions`, a small unit factor table and no unit library) for unit arithmetic, with custom recipe units (cup, tbsp, tsp, stick) and a dimensionless `count` for item-counted ingredients. Handles unicode fractions, mixed fractions, plus-additions, "another tablespoon" word substitution, parenthetical equivalent stripping, and fraction-of-total relative qty.

---

## 7. Rules of thumb (write-time)

1. **Atomic units = creator's sentence-level verbs.** "Heat butter" is one atom. "Add onion and carrots, cook 8 minutes" is one atom. Multiple sentences belong in one atom only if they're a single tightly-coupled action.
2. **"Meanwhile" in creator prose is a hint to atomize.** Each side of the "Meanwhile" should be its own atom.
3. **Partition tag everything that's divided.** If the canonical ingredient says "divided" or "plus more," each use of the slug is a partition. Bare `@x` is for ingredients used in one place.
4. **Use `[remainder]` for "the rest" language.** Don't try to compute and write the literal qty — let the compiler compute (lint checks the sum; cook surfaces display the amount, §2.5). Creator's "the remaining" stays in prose; `[remainder]` is the data tag. The computation needs every other use partitioned with its amount — an unpartitioned use makes the remainder indeterminate.
5. **Match the envelope to the verb.** Sauté = `medium`, brown/sear/fry = `high`, whisk/knead = `full`, simmer/boil = `low`.
6. **Use `none` only for truly fire-and-forget steps.** Preheat oven, bake, rest, chill. Boil water is `low` (the cook needs to know when it's boiling). A `~timer` marks a countdown the cook acts on at the ring — time the process you control: a simmer (`~simmer{30%min}`, ring = come check), a sear per side (`~sear{3-5%min × 2}`, ring = flip), a bake (`~bake{25%min}`, ring = check), a rest with a definite length. Do not time a transition the kitchen signals — preheating an oven, bringing water to a boil, coming up to a simmer: no prose minutes, no timer, the wall-clock estimate in `duration=` where the scheduler reads it; the player shows the step as 'about N min' and the cook taps when the oven or the pot says so. Long passive processes with a definite length (rises, rests, chills, bakes) carry the `~timer` whose ring the cook acts on; transitions the kitchen signals (preheat, boil) stay sigil-less, their `duration=` holds the schedule's estimate, and the dependency (plus the cook's tap) holds the bake behind a hot oven. A sigil on a preheat is harmless, never required.
7. **`count=N` ≠ N atoms.** Use `count` when the same atomic action repeats with the same context (8 pancakes, 4 fillets). Use N atoms when each iteration has distinct context (first batch chicken vs. remaining chicken in NYT — different bandwidth, different oil partition).
8. **Derived atoms get `section=`, regular atoms get `phase=`.** Don't mix.
9. **Atom prose ends in sentence-final punctuation.** Always. The phase-concatenation rule depends on it.
10. **Synthetic prep steps read as an imperative instruction.** A compiler-lifted prep atom's text is an imperative sentence: the prep verb in imperative mood, then the base ingredient carried by `@<slug>{<base phrase>}` (the bare food, *without* the prep clause). Participles map to the imperative (`chopped`→`Chop`, `sliced`→`Slice`, `minced`→`Mince`, `diced`→`Dice`, …); adverbs stay in front (`Roughly chop`, `Finely slice`); compounds map pairwise (`peeled and thinly sliced` → `Peel and thinly slice`); trailing modifiers follow the base (`Finely slice @onions{3 green onions} on the diagonal.`); noun-form cuts lift too (`2 large carrots, small dice` → `Cut @carrots{2 large carrots} into small dice.`). Examples: `Roughly chop @pancetta{4 ounces pancetta}.`, `Rinse @lentils{1 1/4 cups red lentils}.` The base `@def` is the **bold raw introduction** of the ingredient; steps that later *consume* the prepped ingredient render the reference in prepped short form, unbracketed (`the chopped onion`). `to yield` is **reserved** — used only for yield-clarity and transformation preps: an explicit yield parenthetical on the source line moves after the base (`1 large yellow onion, diced (about ½ cup)` → `Dice @onion{1 large yellow onion} to yield about ½ cup.`); a transformation (juice/zest *of* X) may likewise state its yield. The UI can mark the derived atom as "Fond added."

---

## 8. Five-level attention envelope (reference)

Repeating §3.4 for emphasis because this is the field most often miscalibrated at write time:

| Word | Scheduler value | One-line gloss |
|---|---|---|
| `none` | 0.0 | Walk away; a `~timer` here is a countdown you act on at the ring. |
| `low` | 0.0 | Set it; a `~timer` here rings when it is time to come check — the cue is in the prose. |
| `medium` | 0.5 | At the stove with a stir-and-walk rhythm. |
| `high` | 0.8 | At the stove, engaged; can pair only with passive tasks. |
| `full` | 1.0 | Cannot do anything else. |

If the recipe has very few `none`/`low` atoms, the optimizer can't find parallelism. If everything's `full`, the cook is forced to single-thread.

<!-- Copied from fond-mono DSL_SPEC.md sections 1-8 at commit 44a3a305f44d90bb9de3ac2df84229c14d943aee (DSL_SPEC.md last changed in 44a3a30 2026-10-12), with exactly five in-text edits: the section 6 rule-D parser sentence, the section 1.2 save phrase, the section 2.6 resolution-model parenthetical, the section 2.6 linter sentence and the section 6 rule-AA gating parenthetical, and without the horizontal rule that precedes section 9 (openspec change cook-with-fond-skill, capability fond-dsl-open-release). The file names in the preamble and §6 (`lint.py`, `schedule.py`, `testscript.py`, `qty.py`, `render_classic.py`) refer to Fond's internal reference implementation, not included in this release. -->
