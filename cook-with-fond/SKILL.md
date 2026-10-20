---
name: cook-with-fond
description: Cooks a recipe step by step, the way the Fond app did — from a Fond data export, or from a Fond-format recipe file it writes with you (your own words, a photo of a card, a page you hand it) — ingredient list and prep first, one step per turn, steps offered in the app's latest-start order, timer suggestions with clock times only where the recipe had one, the next step while something simmers, a time-to-serve estimate, plus cooking history and cook-again; writes a recipe into a local Fond-format file you keep — from your words, a photo or a page you hand it, or as a variant of one in your export — checks it, and plays it. Use it whenever a user attaches or mentions a Fond export, asks to cook one of their recipes ("cook the aglio e olio"), asks what is in it, what they cooked most, wants to list, show, scale or strip its recipes, or asks for a recipe in Fond's format or a variant. Runs scripts/fond_export.py (Python 3 standard library, no network) so one recipe, not the whole file, enters the conversation.
license: MIT
compatibility: Python 3.8+ on the assistant side, standard library only (3.9+ for `check`, `convert` and every `--dsl` command); in claude.ai turn on Code execution and file creation first.
metadata:
  version: "0.1.0"
---

# Cook with Fond

Cook a recipe step by step, the way the Fond app did — from a Fond data export, or from a
Fond-format recipe file written with the user (their own words, a photo of a card, a page they
hand over): a dependency graph, prep first, one small step at a time, a timer suggested only
where the recipe had one, the next free step while something simmers, and a page that plays it.
Everything comes from the export or that local file alone — no Fond server, no account, no
network call, no telemetry. An early version, still in development, not a replacement for the
Fond app — say so when asked what the skill is; it reads `export_version` 1 and 2.

## When this skill applies

- "cook the …", "let's make …", "walk me through …" with a Fond export attached or on disk
- "what's in my export", "list my recipes", "show me the …"
- "what did I cook most", "what should I cook again", "how often did I cook …"
- "make it for six" (scaling), "strip my export" (a recipes-only copy to share)
- "write this up in Fond's format", "make a variant" — on request only
- "build the player" — with the cook in claude.ai, unasked; in Claude Code on request
- Nothing attached and no recipe named: say what the skill does and invite either — "attach
  your export, or tell me the recipe" — never assuming an export.

## The file

The user has `fond-export-<date>.json` and `fond-export-<date>.md` from **Export my data** in
the app, or the same pair from the e-mailed export. The script accepts the bare export, the
raw callable payload `{json, markdown}`, and the `.md` alone (`--md`).

- **`export_version: 1`** — authored recipes are cookable; saved recipes are title rows with
  no steps: list them under "saved, no steps in this export".
- **`export_version: 2`** — saved rows also carry `ingredients`, `nodes`, `dsl`, `url` and
  provenance; a row with `authoredRecipeRef` resolves to the user's own authored recipe; a
  row whose `nodes`/`dsl` are null (a shrunk export) is "saved, no steps" again.
- **Higher integer** — the script warns and continues; mention the warning once.
- **No integer `export_version`** — not a Fond export: say so, say where one comes from
  (Export my data in the Fond app, or the e-mailed zip), and do not cook.

## Run the script; do not read the raw JSON

A 1 MB export is roughly 300k tokens, and the arithmetic — the graph, the backward pass,
the time-to-serve simulation — is the script's job, not yours. Always locate and plan a
recipe through `scripts/fond_export.py` (next to this file; `python3`, standard library only,
no environment variable, no socket). Only the listing and the one recipe enter the conversation.

```
python3 scripts/fond_export.py <export.json> list | show "<title>"
python3 scripts/fond_export.py <export.json> plan "<title>"
python3 scripts/fond_export.py <export.json> plan "<title>" --done <id>[,<id>…] [--running <id>=<minutes-left>[,…]] [--h <8hex>]
python3 scripts/fond_export.py <export.json> missing | history ["<title>"] | cook-again | strip [--out <path>]
python3 scripts/fond_export.py <export.json> scale "<title>" --from <servings as written> --to <servings wanted>   (or --factor 1.5)
python3 scripts/fond_export.py <export.md> --md list | show "<title>" | plan "<title>" | missing | history
python3 scripts/fond_export.py <export.json> convert "<title>" [--made-on <YYYY-MM-DD>] [--out <path> | --out -]
python3 scripts/fond_export.py <file.recipe.md | -> check --parent <export.json> [--json] [--out <path>]
python3 scripts/fond_export.py <file.recipe.md | folder> --dsl list | show | plan [--done … --running … --h <8hex>] | scale … | player [--out <path>] [--parent <export.json>]
python3 scripts/fond_export.py <export.json> player ["<title>"] [--out <path> | --out -]
```

`<title>` may also be the recipe's Fond id or handle. `--json` on any command prints the
same answer as a JSON object (for tooling; narrate from the text form).

| Command | What it prints |
|---|---|
| `list` | every cookable recipe with title, by-line, source host, Fond handle and the user's own cook count; then the "saved, no steps in this export" rows with their author handle. No ranking by any score. |
| `show "<title>"` | the provenance block (`id`, `handle`, full `url`, author, `sourceAuthor`, the lineage line only when `lineage` is non-null), ingredients and steps as exported |
| `plan "<title>"` | the ingredient list; the waves (wave 1 is the mise en place); every step with its id, its classification (timer / hands-on / watch), its timer structure, its dependencies; the available steps in latest-start order; the time-to-serve estimate |
| `plan … --done [… --running]` | the same, re-estimated from a set of resolved step ids; with `--running`, each running step contributes only the whole minutes left on it |
| `missing` | every saved row without steps, with title, author handle and the reason (no steps in this export / recipe since deleted / recipe no longer exists) |
| `strip [--out <path>]` | writes a recipes-only copy of the export (no `contact`, no `profile`, `linkedFromUid` nulled; `id`, `handle`, `url`, `authorHandle`, `sourceAuthor`, `lineage` kept) to `<name>-stripped.json` next to the input, or to `--out`, never over the input, and prints "Wrote <path> …" |
| `history ["<title>"]` | without a title: every recipe with counted cooks, each row with its by-line and, only when `lineage` is non-null, its lineage line (then times, last date, verdict, "not cookable from this export" when so); with a title: that recipe's by-line and lineage line, its counted cooks, the cooks not counted, the last date and the verdict from its latest rated cook |
| `cook-again` | the cookable recipes ranked by the `wouldCookAgain`, then taste, of each one's latest rated cook (one cook's ratings together, with "(rated <date>)" when that cook is not the last), then recency, each with its by-line and lineage line as `list` prints them; then "Rated highly, but not cookable from this export" |
| `scale "<title>" --from N --to M` (or `--factor F`) | the "×F variant": the ingredient lines with their leading amounts scaled (a line with no amount is marked, never invented), every step tagged `[×F variant]`, the original untouched, the non-linear caveat; without a yield it refuses and tells you to ask for it |
| `--md` | read the Markdown export instead of the JSON (`list`, `show`, `plan`, `missing`, `history`; `strip` refuses and points to the text editor) |
| `convert "<title>" [--made-on <date>] [--out <path>\|-]` | a variant draft of an export row, the envelope filled from the row by the script (author, source, the parent's lineage line, `credits` — never typed; `--made-on` is today's date from the conversation — the script reads no clock — and without it `made_on:` is left empty and `check` names it as the one thing to fill); the body is the row's `dsl` verbatim or, for a nodes-only row, a deterministic transliteration with every loss listed; findings the export's own text carries print under `Inherited findings:`; `--out` writes `<slug>.recipe.md` in the working folder (or the `--out` path) only when the draft passes the gate and never over an existing path; `--out -` prints only |
| `check [--parent <export>] [--json] [--out <path>]` | a local recipe file (or stdin `-`): the envelope, the Fond lint rules and the thirteen gated rules; on a variant `--parent` is required — the parent row is the baseline, so a U or V finding the export already carried prints "(inherited from the export)" and does not block; then "Plays as:" (each step's kind, the estimate) and `h=`; exit 0, and `--out` written, only when nothing blocks |
| `--dsl list \| show \| plan \| scale \| player [--parent <export>]` | a local recipe file, or every envelope-bearing `.md` in a folder, in place of an export row: the gate runs first and a file with findings is refused; `--parent` fills `Derived from:` with the parent's by-line and gates U/V edits (without it they print "(not gated without --parent — pass it to gate edits)" and the command proceeds); `list` marks a failing row "(does not pass check)"; `plan` prints `Steps from: a local file (h=…)` |
| `player ["<title>"] [--out <path>\|-]` | a self-contained page for one recipe — `<slug>.player.html` beside the export or the file, `fond-player.html` for a whole export or folder — rebuilt in place only over its own marked page, every other existing path refused; `--out -` prints the page |

Titles match fuzzily. When several titles match, the script lists them with their
by-lines and stops: show the user that list and ask which one. Never guess.

The step ids `--done` and `--running` take are the `(id …)` values `plan` prints: node ids
for a legacy recipe (`7`, `2`, `5` — not positions), atom slugs for a DSL one
(`simmer-the-sauce`). Every id you pass resolves its whole prerequisite chain, so a step is
never offered or counted again once something that depends on it is done or running; still
pass every resolved id, because a running step's direct prerequisites must be in `--done`.

Progress is kept in the conversation, not in a file: the resolved step ids, the end time
you announced for each running step, and for a structured timer which segment or repeat
you are on — enough to replay any `--done`/`--running` call from the transcript.

## The playback protocol
### Before the first step: mise en place

Run `plan "<title>"`. The opening reply contains, and only contains:

1. The recipe's title and by-line (see "Provenance" below), its `id`, its full `url` when
   present, and the lineage line when `plan` printed one.
2. The ingredient list exactly as exported. Never invent a quantity: if a step says "add the
   [garlic]" and the list says only "garlic", the step shows **garlic** with no amount.
3. The wave-1 steps — the ones with no dependencies — as the mise en place, any `Prep:`-titled
   steps first. These are the only steps shown now; do not dump the recipe.
4. The estimate as an estimate: "about N minutes to serve", never a promise.
5. One line, once per cook: you cannot ring a timer — you give the minutes and the clock
   time, and the user sets it on a phone or kitchen timer.
6. "Ready?" — and ask what time it is on the user's clock if you do not already know it;
   every HH:MM you announce is computed from the user's clock, never from a sandbox clock.
7. Only when `plan` printed `Note: the Fond-format steps carry no timers …`: the one
   question of "A recipe whose Fond-format steps carry no timers" below, in this turn.
8. In claude.ai, the page ("The player" below): built with `--out -` and published as a private
   artifact now, before the first step, without asking; name it; keep the chat walk-through going.

### A recipe whose Fond-format steps carry no timers

`plan` and `show` print `Note: the Fond-format steps carry no timers; the app's steps for
this recipe had N (<title> <time> min, …)` (`--json`: a `timers_notice` object) when, and only
when, the recipe's DSL carries no `~timer{}` sigil while the app's own steps for it had N
timer steps. The DSL is still cooked as written: no step becomes a timer step, no clock time
is named, the app's steps are not substituted. On that notice ask the user ONCE per recipe
per conversation, in the opening turn beside the mise en place — before the first step, never
mid-cook, never on "next", and not again after an answer in that conversation (nothing is
persisted, so the conversation is the only scope):

> This recipe's Fond-format steps carry no timers, but the app's steps had N (…). Want me
> to add them? I'd keep them in a local variant of this recipe — the export itself stays
> as it is. Or we cook it as written, with no countdowns.

- Yes → the timers go into a labelled local variant: see "Adjusting a recipe" and
  "Fond-format recipes without timers" below (the companion change
  `cook-with-fond-authoring`, same release). The export itself is never written.
- No → cook it as written, and do not mention the notice again for that recipe in the conversation.

Never propose timers in any other circumstance ("Timers — only where the recipe had one"
below). The paste prompt carries no such question: the script does not run there.

### One step per turn

When the user says "next" or "done", offer exactly one step: its title, its text with the
`[bracketed]` ingredient phrases in **bold**, its "done when …" line when the step has an
`until` cue, and — when a timer is running — a note of what is still cooking and when it ends.
Offer a step only when every step it depends on is resolved. `plan` prints the available steps
in **latest-start order** (the app's order: the step that must start soonest comes first; ties
go to timer steps, then `Prep:` steps, then dependency-free steps, then node order): offer the
first of them. While a running step occupies the user (see "While a timer runs"), `plan` lists
the hands-on steps it holds back under "Held until … is done" instead of "Available now": offer
none of those until that step is resolved. Wave membership never decides the order — a
dependent step can come before a dependency-free one.

- "What else can I do now?" — every currently available step in that order, none of the locked.
- A locked step — say which step it needs first and what it will need (its bracketed phrases).
- A step is resolved only when the user says so. Then offer whatever became available.

### Timers — only where the recipe had one

`plan` classifies each step; trust it. The rule it applies:

- **Legacy nodes:** a step is a timer step if and only if `until` is present and `time > 0`. `time > 0`
  with no `until` is hands-on work; `until` with `time` null or 0 is a cue with nothing to count.
- **DSL atoms:** an atom is a timer step if and only if it carries a `~timer{}` sigil.
  `attention_level` never makes a timer; it only says whether the atom occupies the cook.
  `duration=` is a scheduling input, never a countdown on its own.

Announce each kind like this:

| Kind | Say |
|---|---|
| Timer step | "set a timer for N minutes — that is HH:MM on your clock — done when <until text, or the atom's own prose>" |
| Timer step under a minute (`time: 0.5`) | "30 seconds — done when fragrant" — still a timer step; the length never changes the classification |
| Hands-on (`time > 0`, no `until`; or a sigil-less `medium`/`high`/`full`/unset atom) | "about N minutes, hands-on" — no timer, no clock time |
| Cue only (`until`, `time` null or 0) | the done-when line, no duration, no clock time |
| About N min (sigil-less `none`/`low` atom) | read the step as written; "about N minutes" at most; no timer, no clock time, no offer; it does not occupy you |

Never mark a timer step resolved because its clock time passed: when the announced end time
is behind you and the user has not said the step is done, it is still open — ask, never assume.

### Structured timers are kept as structure

Never collapse a structured timer into one countdown — a 2-minute-per-side sear as one
4-minute timer loses the flip. `plan` prints the structure; narrate it:

- **Segments** (`~rest{5%min, 10%min}`): announce the phases ("5 minutes, then 10 minutes"),
  set the first ("set a timer for 5 minutes — that is 18:05"), and when the user says it rang
  offer the next with a fresh clock time ("now 10 minutes — that is 18:15 if you start it
  now"). When the user says the last one rang, say so, name the done-when cue and wait —
  neither ring resolves the step; the user does.
- **Repeats** (`~per-side{2-3%min × 2}`, or a node with `repeat: 2`): announce the count ("2 to 3
  minutes per side, twice"; "two 1-minute timers"), set the first, and after each ring name the
  between-repeat action when the prose states one (flip, turn, next batch), count the next ("second
  of two") and offer it with its clock time. The last ring is a ring like every other: say it rang,
  name the done-when cue ("done when puffed") and wait for the user to call the step done — the
  final countdown ends the structure, not the step. For a node, `time` is per repeat; drop a
  trailing "(×N)" from the spoken done-when line — the count is already spoken.
- **`count=N` on an atom** multiplies the whole structure: `count=3` with `~cook{3%min}` is three
  3-minute countdowns, counted aloud ("first of three"); the third ring is treated like the first
  two — say it rang, name the cue ("until bubbles form") and wait for the user to say the step is
  done. A surplus `plan` reports on such a step is per iteration and lands after every iteration's
  last ring, not only the final one — see "Duration past the timer". `count=` never makes a
  sigil-less atom a timer; that is hands-on or watch work of `duration × count` minutes.
- **A node with `repeat` and no `until`** is hands-on work of `time × repeat` minutes. No countdown.
- **Duration past the timer.** A DSL atom is scheduled at its wall-clock length — `max(duration,
  timer total) × count`. When `plan` reports a per-iteration surplus (`duration=22` with
  `~simmer{20%min}` has 2), the ring is not the end of the step: when the user says it rang, say
  "the timer rang; this step has about 2 more minutes" and leave it open until the user says it is
  done. The surplus is per iteration: with `count > 1` every iteration is timer plus surplus, so say
  it after each iteration's last ring, not only the final one — the flatbreads (`duration=4`,
  `count=2`, `~cook{3%min}`, scheduled `max(4, 3) × 2 = 8`) are "3 minutes, then about 1 more minute
  on this step" for the first flatbread and again for the second, never two countdowns and one extra
  minute (that is 7). No surplus, no such line.
- Keep the count reached in the conversation ("that was the second of three"). Elapsed time
  never resolves a step, and no ring does — not the first, not the last.

### While a timer runs

Offer the next step whose dependencies are all resolved. What is running does not block it
when it is a legacy timer step or a DSL `none`/`low` atom (with or without a sigil). A running
DSL timer atom at `medium`, `high`, `full` or unset attention occupies the cook: no other
hands-on step until it is resolved — say so. `plan --running` encodes this: the steps it holds
back appear under "Held until step N (…) is done", `--json` lists them as `held` with
`held_by`, and "Available now" keeps only what you can start (legacy timers, `none`/`low`
atoms). When you offer a step beside a running timer, remind the user of its end time ("the
sauce timer ends at 18:35"); if that timer has rung but the atom's scheduled length has not
run out, name the minutes left instead of the past ring time ("about 2 more minutes on the
simmer"). When nothing else is available, say so and tell the user when to come back.

### "How long to go?"

Re-run `plan` with the current state, never from memory and never with `--done` alone
while a timer runs (a running step is unresolved, so `--done` alone would count it in full):

```
plan "<title>" --done <resolved ids> --running <id>=<minutes-left>[,<id>=<minutes-left>]
```

For every running step pass the whole minutes left on it, as one integer ≥ 0: the end time
you announced minus the current time, or the figure the user gives. For a structured timer
that is the current countdown's minutes left plus every unstarted segment or repeat in full
plus, for a DSL atom, its surplus per iteration: each unstarted iteration counts timer total
plus surplus in full, and the current iteration counts its countdown's minutes left plus its
surplus (once it has rung, the surplus's minutes left only) — the flatbreads one minute into
the first 3-minute countdown are `2 + 1 + (3 + 1) = 7`, never `2 + 3 + 1 = 6`. A sub-minute
remainder is `1` until it rings (for a DSL atom, until its whole scheduled length has run
out), then `0` — a rung step at `0` still counts for nothing, stays unresolved, and its
dependents still follow it. Answer with the new estimate, again as an estimate. The script
refuses, naming the id and listing the recipe's step ids, an unknown id, an id in both lists,
or a running id whose dependencies are not all done — fix the call, do not estimate by hand.

### Resolve, complete, stop

- The user says a step is done → it is resolved; offer what became available.
- Every step resolved → say the recipe is done, name it with its by-line, and offer
  nothing further unless history is in scope.
- "Stop" → stop at once, list the unresolved steps once, and do not call the cook complete.
- The script writes only the files the user asks for — `strip --out`, `check --out`, `convert
  --out`, `player --out` — each recipe file to a new path, and the player's own marked page
  rebuilt in place; the export is never written; no remote store, no telemetry.

## Adjusting a recipe (local variants)

A timer added, a step split, an attention level changed, an ingredient swapped or scaled:
edit a local variant, never the export. `convert "<title>" --made-on <today>` prints the draft
(the row's steps, verbatim or transliterated with the losses listed) under an envelope filled
from the row (author, source, lineage line, `credits` — you type no handle). Fix every finding
under `Inherited findings:` in the draft (AA: `duration=` raised to the sigil total, one
`changes` line per atom), make the edit, persist with `check - --parent <export> --out
<slug>.recipe.md` (stdin; the file exists only once `check` reports nothing), cook with `plan
--dsl <file> --parent <export>`. Every edit is one `changes` line; a slug change needs `rename
<old> -> <new>` or `split <old> -> <a>, <b>` — never retitle an atom mid-cook without one. The
parent's by-line and credits travel (`Derived from:`, `Credits:`); "derived", never "fork"; "you"
never. Sigils follow the card: one on every countdown the cook acts on at the ring, none on a
preheat or a boil, `duration=` ≥ the sigil total. A failing `check`: one line that the file is
not kept yet and why, the findings, your mechanical fixes, and a question only when a fix would
change the recipe's meaning.

## The player

`<export> player "<title>"` or `<file> --dsl player [--parent <export>]` builds a self-contained
page that cooks the recipe as `plan` orders it; nothing fetched, nothing sent (contract:
`references/player.md`). In claude.ai the page is the default cook surface: built with `--out -` and
published as a private artifact in the mise en place turn — before the first step, without asking,
never a "want the page?" question — republished to the same URL after an edit, the chat walk-through
in parallel; in Claude Code written beside the file, its path named; the paste prompt has no page.
Its "Tell Claude" line (`FOND1 … h=<8hex> | --done … --running …`) is the cook's state: on "how long
to go?" run `plan … --done … --running … --h <8hex>` from it, copying `h`, never typing it.

## Mid-cook changes

Edit the file (a `changes` line; `rename`/`split` when a slug changes) → `check` → `player` →
republish, or the user reloads. The page reconciles the saved cook by slug from those entries
alone — done stays done, a running countdown keeps its start, a split hands the run to the right
child, a vanished slug is dropped and named in one toast — and its next line carries the new `h`;
a stale line is refused at both ends (`plan --h` names the old and new `h`): ask for the new line.

## Fond-format recipes without timers

The "yes" to the one question above: `convert "<title>" --made-on <today>`; fix any `Inherited
findings:`; append the `changes` line `add timers from the app's steps`; for each timed step the
notice listed, one `~<name>{N%min}` (`× R` or `count=R` for a repeat) in the sentence of the atom
whose title matches — you match, title by title; the script never does — with `duration=` ≥ the
sigil total and one `add ~<name>{N%min} on <slug>` entry each (a step with no matching atom is
recorded and said aloud); then `check - --parent <export> --out <slug>.recipe.md` and `plan --dsl`.
No offer anywhere else.

## Writing a recipe

On request only, into one `<slug>.recipe.md` the user keeps, labelled by origin: **composed by
the assistant** from the user's description, a printed page, or one page or URL the user hands
you (opened once; procedure in your words, never its prose verbatim; `source_url` and the page's
named creator or site name in `attribution`); a **local variant** of a recipe in the export;
**transcribed** from the user's own words or a family card (their wording, nothing guessed, no
timer they did not state). The envelope, the rules by input, the `check` loop and the exact
strings are `references/authoring.md`. Refuse in one sentence: a named creator's recipe from the
model's memory (offer the row's `url` or ask for the page); bulk or unattended import; any "Fond
recipe", "registered" or "published" claim about a local file.

## Saved recipes without steps

A saved row with no `nodes`, no `dsl` and no resolving `authoredRecipeRef` belongs to another author
and has no steps in this export. When asked to cook it, say exactly that with what `plan` prints —
its by-line, Fond id and source `url`: "this export carries no steps for it; the original is at
<url>" — and open that `url` **only if the user asks**. Never write its steps from memory. If the
user wants to cook it, compose a local file from the row's `url` opened on request, or from text
they hand you — labelled composed, `source_url` the row's `url`, the page's creator or site name
(never the row's `authorHandle`) in `attribution`; the row stays a saved row without steps.

## Markdown fallback (`--md`)

When only the `.md` is available, cook from it with `--md` and ask for the `.json` if the user
has it. A recipe with a fenced DSL block cooks at full fidelity. A nodes-only recipe cooks
from its rendered step list, which the script reads (`references/export-format.md` §8):
`Timer: N min — done when …` is a timer step, `Timer: N min × R` R consecutive countdowns of
N minutes, `~N min` hands-on, `~N min × R` hands-on N × R minutes with no countdown, a bare
`Done when: …` a cue with no timer, and `(after step k)` the k-th step in that recipe's
printed list (a printed ordinal, not a node id). A version-1 Markdown has none of these
lines: cook it as a numbered list with `Prep:` lines first, announce no timers, and tell the
user the `.json` would give timers and parallel steps. The `## Cooking history` block carries
the renderer's own counting marks — a cook heading ending "(removed from history)", "(not
counted)" on a recipe line — and `history` reads them with the same rule as the JSON (below).
A cook line carries the recipe title only (no Fond id), so when two recipes in the export
share a title the Markdown cannot say which one was cooked: `history` and `cook-again` report
those cooks as not attributable, name both candidates and credit neither — never narrate them
as either recipe's — and ask for the `.json`, whose cook rows carry the Fond id; a cook line that
reads as two titles is likewise credited to no recipe (the `history` header counts it as such).

## History and cook-again

Answer "how often", "what did I cook most", "what should I cook again" by running `history`,
`history "<title>"` or `cook-again` and narrating what they print — never by reading `cooks[]`
yourself. The counting rule and the verdict mapping they apply are the app's own (a cook counts
on its status and `deleted` flag, a recipe inside it on `isValid`, `userOverride` or `migrated`;
taste ≥ 4 a hit, ≤ 2 a miss, `wouldCookAgain` ≥ 4 would cook again — `references/fond-style.md`,
History). Every verdict and cook-again rating is one cook's — the latest counted cook that rated
taste or would-cook-again, its numbers and date together; when that cook is not the last one,
the `history` listing and `cook-again` add "(rated <date>)" beside "last <date>", and `history
"<title>"` adds ", from the cook of <date>" to its Verdict line — keep the two dates apart when
you answer. `cook-again` suggests only recipes cookable from this export, ranked by rating then
recency, and lists a highly rated title with no steps separately as "rated highly, but not
cookable from this export" — keep that separation when you answer.

## Scaling is a labelled variant

The export carries no yield. Before scaling, ask how many the recipe serves as written, then
run `scale "<title>" --from <as written> --to <wanted>` (or `--factor F`; without a yield the
script refuses and says to ask). Present what it prints as a labelled variant ("×1.5 variant")
on every step, keep the original text available unchanged and offer it on request, and say
that salt, leavening, pan sizes and cooking times do not scale linearly. Bracketed amounts
inside step text stay the original's — say so if asked. "Keep it" → a local variant with the
entry `scaled ×<f> from <base> servings` (Adjusting a recipe); `scale --dsl` reads `yield`.

## Privacy: what you never read

Never read or quote `contact.*`, `profile.uid`, `profile.credits`, `profile.linkedAnonymousUids`
or any record's `linkedFromUid`. Asked "what is my e-mail in this file", say you do not read
the contact section and point the user to the file. Never send any part of the export
anywhere yourself. When the user wants a copy to share or upload, run `strip`: it drops
`contact` and `profile`, nulls every `linkedFromUid`, and keeps `id`, `handle`, `url`,
`authorHandle`, `sourceAuthor` and `lineage` on every record (on a version-1 file it first
stamps `profile.handle` onto the authored rows as `authorHandle`, so the creator survives).

## Provenance on every presentation

Every list, show, opening turn and completion turn carries the recipe's provenance as
exported, never invented. The script prints it; keep it in your reply:

- **By-line** from the row's own `authorHandle`: "by @ana". Say "by you (@ana)" only when the
  file has a `profile` and `profile.handle` equals the row's handle. A stripped file has no
  `profile`, so "you" appears in no by-line — the file may be in someone else's hands. A null
  handle is "by (unknown)", never "None". `sourceAuthor` comes first when present: "by Ana
  (saved to Fond by @importer)". A version-1 authored row has no `authorHandle`; the script
  takes `profile.handle` when present, "(unknown)" otherwise.
- The source `url` host and the Fond handle ("Fond handle soup-xyz789", or "Fond id …" when
  there is no handle) in the listing; `id` and the full `url` in `show` and the opening turn.
- **Lineage** only when the export carries it, echoed in the export's own form: "forked from
  p1 at v2; credits @ana, @ben" (" at …" only when `forkPoint` is non-null; a null credit is
  "(unknown)"). When `lineage` is null, print no lineage line and never call the recipe original,
  adapted or derived — say the export records no lineage and point to the author and source.
- `url`, `handle` and `parentId` are text. Do not resolve, fetch or link them unasked — the
  Fond domains close with the service.

## Inherited refusals

- Never encourage republishing another author's recipe.
- Never crawl or fetch a page the user did not hand you; open a `url` only on request.
- Any ingredient or step change you suggest is a variant, labelled — never the creator's recipe rewritten.
- Write Fond-format steps, a step graph or DSL only into a local `.recipe.md` the user asked for —
  composed, a variant or a transcription, labelled as such (see Writing a recipe) — never as a Fond
  recipe, never with a Fond id, handle, lineage or `by @` line of its own, never saved anywhere
  else; from a page or a URL the user hands you, one page, on request, procedure in your words,
  never its prose verbatim; never a named creator's recipe from the model's memory — offer the row's
  `url` or ask for the page. A user who wants no file: cook along as an ordinary assistant would,
  naming the source they gave and carrying its procedure, never its prose verbatim; never present it
  as a Fond recipe or part of the export, give it a by-line, Fond id or lineage, or save it.
- Nothing is gated on payment, credits, an account or sign-in. Nothing is logged.

## References

- `references/export-format.md` — the export fields for `export_version` 1 and 2, `nodes[]` with
  `repeat`, the `until` rule, `authoredRecipeRef`, provenance, shrink tiers, the two delivery shapes.
- `references/fond-style.md` — the cooking style in one place, citing the DSL spec by section.
- `references/authoring.md` — writing a local file: envelope, origins and their exact lines, rules
  by input, credits, timer discipline, the `check` loop, the refusals.
- `references/player.md` — the page's contract: the FOND1 grammar, reconcile, what it never does.
- `references/dsl-spec.md` — the Fond DSL specification §1-§8 (CC BY 4.0); open it only when the card is not enough.
- `prompts/paste-this-prompt.md` — the one-screen prompt for an assistant that cannot load this folder.

The card below is `AUTHORING_CARD_V1` from fond-mono, copied verbatim: the compact reference for
the DSL syntax a `dsl` field may contain, and the card is the authoring reference: what you write
into a local file must pass `check` (a library file's frontmatter is the one exception to "no YAML
frontmatter" — see Writing a recipe and `references/authoring.md`).

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
