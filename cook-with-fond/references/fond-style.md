# The Fond cooking style

How the Fond app played a recipe, and therefore how this skill plays one. The data is
described in `export-format.md`; the recipe language in `dsl-spec.md`, cited here by
section and never restated; the turn-by-turn protocol in `SKILL.md`.

## Prep forward

- A recipe is a dependency graph, not a list. Wave 1 is every step with no
  dependencies, `Prep:`-titled steps first (only one converter wrote that prefix). Later
  waves are a grouping for the mise en place, never the playing order.
- Before the first step: the ingredient list exactly as exported, the wave-1 steps, the
  time-to-serve estimate, "ready?". Nothing later is shown yet.
- `[bracketed]` phrases in a step's text are what the step needs. When the export states
  no amount, none is invented.

## Latest-start-time order

- A step is offered only when every step it depends on is resolved. Among the available
  steps the app offered first the one with the earliest latest start time, from a
  backward pass over the minutes still to cook; ties go to timer steps, then `Prep:`
  steps, then dependency-free steps, then node order. A dependent step can therefore
  come before a dependency-free one.
- One step per turn: title, text with the bracketed phrases emphasised, the done-when
  line, and a note of what is still cooking.

## "Done when"

- Every `until` cue is spoken as "done when …". A step is resolved only when the cook
  says so — never because a clock time passed, never by the skill on its own.

## Timers

- **Legacy node:** a timer step if and only if `until` is present and `time > 0`.
  `until` with `time` null or 0 is a cue with nothing to count; `time > 0` with no `until`
  is hands-on work of about N minutes.
- **DSL atom:** a timer step if and only if it carries a `~timer{}` sigil
  (`dsl-spec.md` §2.4; §6 rule T names the sigil as the runtime's timer-event source).
  `attention_level` never makes a timer: it is the cook's bandwidth claim (§3.4, §8),
  read here only as "occupies the cook" (`medium`, `high`, `full`, unset) or "does not"
  (`none`, `low`).
- **Structure is kept.** Segments are sequential phases of one countdown — "5 minutes,
  then 10 minutes" (§2.4); `× N` is N consecutive countdowns of one segment (§2.4; §6
  rule X); `count=` runs the whole structure once per iteration (§1.4 `count`, §3.7). A
  legacy node's `repeat` is the same fact after projection: `time` is per iteration, and
  a `repeat` node without `until` is hands-on work of `time × repeat`. The count reached
  lives in the conversation. The last ring is a ring like every other — announced, the
  done-when cue named, the step resolved only when the cook says so; the final countdown
  ends the structure, never the step.
- **Duration is the scheduled length.** `duration=` is the atom's wall clock (§1.4) and
  its timers are events within it; the step is scheduled at
  `max(duration, timer total) × count` (§3.4's back-compat duration floor, which §6 rule
  AA makes a no-op for well-formed recipes), applied here at every attention level. When
  the last ring lands before the duration has run out, the step has "about N more
  minutes" and is not finished.
- **Sigil-less `none`/`low` atoms** — a transition the kitchen signals (a preheat, water
  coming to a boil, coming up to a simmer; §7 tip 6) or a walk-away written without its
  sigil — have no countdown and no clock time (§6 rule T: the runtime fires only sigiled
  timers). The step is cooked as written, "about N minutes" at most; the user says when
  the oven or the pot is ready, and a step that depends on it becomes available only
  then. `duration=` feeds only the schedule. The app's legacy projection counted a `none`
  atom's duration down — legacy-projection-only (§5); this skill applies no lift and
  proposes no timer.
- The assistant cannot ring a timer. It suggests one, computes the clock time from the
  cook's clock, and waits to be told it rang.

## Parallelism

- While a timer runs, the next available step is offered. A running legacy timer step,
  and a running DSL `none`/`low` atom with or without a sigil, do not occupy the cook; a
  running `medium`/`high`/`full`/unset atom does, so no other hands-on step is offered
  until it is resolved (a binary reading of §3.4's shares; two `medium` atoms pairing is
  not modelled).
- The time-to-serve estimate simulates one cook on that rule — zero-time steps instant,
  non-occupying steps in parallel, at most one hands-on step at a time — and is always
  an estimate, never a promise. Mid-cook, "how long to go?" is
  `plan --done <ids> --running <id>=<minutes-left>`, each running step contributing only
  the whole minutes left on it.

## Scaling

- The export carries no yield, so a scaled recipe starts by asking how many it serves as
  written. The result is a labelled variant ("×1.5 variant") beside the original, never
  a rewrite of it, and salt, leavening, pan sizes and cooking times do not scale
  linearly.

## History

- A cook counts when its `deleted` is not true and its status is `completed`,
  `recorded`, `rated` or `migrated` (the app's own history filter; `migrated` rows are
  pre-app cooks carrying at most an easy-to-follow rating). Within a cook a recipe counts
  when `isValid`, `userOverride` or `status == "migrated"` holds; a version-1 row has
  neither flag, so the cook's own `migrated` status stands in and no override is assumed.
  Verdict: taste ≥ 4 is a hit, ≤ 2 a miss, `wouldCookAgain` ≥ 4 means would cook again;
  easy-to-follow alone gives none. The verdict and the cook-again rating are one cook's,
  the latest counted cook that rated taste or would-cook-again. Cook-again suggestions are
  limited to recipes cookable from the same export.
- A Markdown cook line names the recipe by title alone. When two recipes in the export
  share that title, the cook is attributed to neither: say so, name both by-lines, and ask
  for the JSON — never credit the cook, its rating or its verdict to one of them.

## Provenance

- Every listing, show, opening turn and completion turn carries the recipe's by-line
  from its own `authorHandle` ("you" only beside a matching profile handle), the source
  host, the Fond handle and the lineage line only when the export has one. Nothing is
  fetched, resolved or linked unasked.
