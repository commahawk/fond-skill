# The player page — its contract

What `player` builds, what the page does, how it syncs with the chat, and what it never does.
The protocol it plays is `SKILL.md`'s; the recipe files it plays are `authoring.md`'s.

## 1. Building and publishing

- `<export> player ["<title>"] [--out <path> | --out -]` builds `<slug>.player.html` beside the
  export for one recipe, or `fond-player.html` for the whole export (its pick screen lists
  every cookable row); `<file|folder> --dsl player [--out …] [--parent <export>]` does the same
  beside a recipe file or a library folder, running the gate first (a file with findings is
  refused with them; `--parent` fills the variant's `Derived from:` line and gates U/V edits).
- The page is `scripts/player.template.html` with the recipe's payload embedded — built by the
  script's own plan and graph functions, never re-derived, so the page's order, kinds,
  countdown structures and estimate are `plan`'s by construction. The payload JSON is embedded
  HTML-safe: every `<`, `>`, `&`, U+2028 and U+2029 is written as a `\uXXXX` escape, so no
  title, step text, URL or author label from an export or a file can close the payload's
  script element or open a comment.
- The first line of a built page is its marker, `<!-- fond-player built by fond_export.py
  h=<8hex> id=<id> -->`. The `id` is the recipe's own (`rcp-…`, `local:<slug>`) or, on a
  multi-recipe page, the collection's: `export:<exportedAt>` for a whole export (its header
  timestamp), `library:<8hex>` for a folder (SHA-256 over its sorted `local:` ids). `player`
  rebuilds a page in place only when the existing file's first line is that marker with the
  same id (any `h=`, so an edited recipe rebuilds); a page for another recipe or another
  collection is refused naming both ids, and any other existing path is refused (exit 1) —
  never a recipe file, never the export. `--out -` prints the page.
- In claude.ai the page is the default cook surface: the assistant runs `player … --out -`
  and publishes it as a private artifact on the user's own account in the mise en place turn —
  before the first step, without asking, never a question about wanting it — names it, and keeps
  the chat walk-through going in parallel for the user who prefers typing or has the page closed;
  after an edit it republishes to the same URL. In Claude Code the page is written beside the
  file, its path named, and the user opens it in a browser. The paste prompt has no page: there
  the chat walk-through stands alone. The page is self-contained: no external script, stylesheet,
  font or image, no fetch of any kind, no account, no telemetry; it works offline once opened.
- The payload carries, per recipe: `id`, `title`, `h`, `source` (`dsl`, `nodes`, `md` or
  `local`), `byline`, `lineage`, `provenance_lines` (exactly the lines `show` prints, built with
  the profile masked as after `strip`, so "you" never reaches a page that travels), `url`,
  `ingredients`, `wave1`, `estimate_minutes`, `credits`, `changes`, `aliases` (parsed from the
  file's `rename`/`split` entries; a malformed entry is a `check` warning and is skipped, never
  guessed) and `steps[]` — each with its id, title, text, kind, occupancy, scheduled length,
  dependencies, static latest-start rank, needs, done-when cue and countdown phases (the
  sigil's segments × repeats × `count`, or `time` × `repeat`).

## 2. What the page shows

- **Pick list**: `N steps · about M min · DSL | legacy steps | local variant | composed |
  transcribed`, then ` · in progress` or ` · cooked` from saved state.
- **Mise screen**: ingredients, the wave-1 prep, the provenance exactly as `show` prints it
  (the origin line, `Derived from:`, `Credits:`, `Changes:` …), Start.
- **Cook screen**: tiles ranked by the static latest-start order — available (tap = the app's
  tap: a timer tile starts its countdown, any other tile is done), held (names the running
  step that occupies the cook), locked (a faded title only; press-and-hold peeks at the text;
  no timing until unlocked), running (mm:ss from an absolute end time, `<p> of <n>` for a
  structured timer, "Rang. Tap to start the next N min", then "about N more min" past the
  last ring of an atom whose duration runs past its sigil) and done. A sigil-less `none`/`low`
  atom reads `About N min · no timer`; hands-on work `About N min, hands-on`. The estimate;
  Undo for seven seconds after a tap.
- **"Tell Claude"**: the words (the recipe named by its id — a `local:` id never reads "Fond
  id" — the clock time, done steps, running steps with their end times, next up) and the
  FOND1 line (§3). **"Pick up from Claude"**: a paste box for a FOND1 line, which warns before
  a pasted line would undo done steps or stop running ones ("This line would undo …. Tap Apply
  again to use it anyway.").
- A ring is always shown on the step. The chime and vibration are best-effort while the page
  is open and may be blocked; nothing sounds once the page is closed, the phone is locked or
  the app is in the background — the page says so and tells the cook to set a phone or kitchen
  timer too. The skill "cannot ring a timer" stays true. No ring resolves a step; the cook taps.

## 3. The FOND1 line and `h`

```
FOND1 <rid> <j|m|l> d=<id>[,<id>…] r=<id>:<p>/<n>@HH:MM[+<days>d][!][,…] t=HH:MM[+<days>d] h=<8hex> | --done <ids> --running <id>=<N>[,…]
```

- `rid` the recipe's id (`rcp-…` or `local:<slug>`); the letter `j` for an export JSON, `m` the
  Markdown, `l` a local file; `d=` the done step ids; `r=` each running step as `id:<phase>/<phase
  count>@<end time on the cook's clock>`, `!` when it has rung; `t=` the time the line was
  made; `h=` the version stamp; after `|`, the exact replay tail for `plan "<id>" --done …
  --running … --h <h>` (each running step as the whole minutes left on it — no clock, so a
  phase of any length replays through it unchanged). A clock time may carry a day offset
  `+<days>d`, the calendar days after the day of `t=` on the cook's clock: the page writes it
  on an end that falls on a later day than `t=` (`@05:00+2d` for a 36-hour rest one hour in,
  `@00:05+1d` for a countdown past midnight), never on `t=`, so every end reads back to the
  minute; a bare end is the first such time after `t=` (a rung one, the last at or before
  it), which also reads a line from before the offset existed. The retired `:o@`
  form is never produced and a line carrying it is refused naming the step.
- `h` is the first eight hex digits of SHA-256 over the recipe's body — for a local file the
  text after the envelope, for a DSL row its `dsl` text, both normalised (CRLF to LF, trailing
  whitespace stripped per line, exactly one final newline); for a nodes row the canonical JSON
  (sorted keys, no whitespace) of the slim node fields the graph reads. An envelope-only edit —
  a new `changes` line — leaves `h` unchanged; any body edit changes it. Every payload row
  carries an `h`, so a line never reads `h=undefined`; a page whose payload lacks one refuses to
  boot ("Rebuild this page with the skill's player command"). The script prints `h` on `show`,
  in `plan`'s `Steps from:` line and in `plan --json`.
- A stale line is refused by both ends: the page's paste box with "That line is from an
  earlier version of this recipe. Ask Claude for a line from the current one.", the script
  (`plan … --h <8hex>`, either mode) with "that line is for h=<old>; the recipe is now h=<new>
  — paste the line from the updated player, or tell me which steps are done". A line without
  `h=` (an earlier line) is accepted by both. A present `h=` that is not eight hex digits, 0-9
  and a-f (`h=garbage`, seven or nine digits, upper case), is refused by both — the page names
  the stamp and applies nothing, `--h` exits 2 — and is never read as an earlier line. The
  assistant copies `h` from the pasted line and never types it.
- A pasted line carries each running step's current phase and its end only, so the page
  reconstructs the start of that iteration's first segment by assuming the earlier segments
  ran back to back; after a later edit merges segments, that assumption is what the minutes
  left are computed from. The loss is bounded by the segments already past.

## 4. Where the state lives

- In the browser's storage, under `fond-player-v2:<rid>` (state v2: the done ids with their
  times, the running steps with their phase, start, the start of the current iteration and
  the phase count when started, when the cook began, and `h`). Absent or blocked storage
  degrades to the visit: the cook still works, nothing is saved.
- In the FOND1 line the cook copies — the portable state on every platform.
- In claude.ai, across a republish, in the `{rid, state}` snapshot the artifact host takes
  through `window.claude.hot` — the one host hook the page calls (the must-not-publish check
  whitelists it by name and bans every other `window.claude.*`). Nowhere else: nothing is
  written to a file or sent anywhere.
- Safari scopes `file://` storage per file, so a page rebuilt from disk starts without the
  stored state there — the FOND1 line carries it over. Renaming a recipe file renames its id
  and therefore its storage key: not mid-cook.

## 5. Reconcile — a saved cook survives an edit

When a saved or hot-restored state has the page's recipe id but a different `h` (a republish
after an edit), the page reconciles the cook onto the new payload by slug, from the declared
`aliases` only — never inferred — instead of clearing it:

- a done step stays done at its time, whatever changed; a done step with a `split` entry is
  done in every child;
- a running step keeps the moment its current iteration first started and its phase index
  clamped to the new phase count, so elapsed time is never lost: after segments merge, the
  minutes left are the new structure's total minus the minutes elapsed since that iteration
  first started, floored at zero; past a reduced `count=` the step shows rung for the cook to
  tap;
- a running step with a `split <old> -> <a>, <b>` entry goes to the child that corresponds to
  its phase when the children match the old phase count, else to the first child that is a
  timer — the earlier children done, the later ones open — and to none when no child is a
  timer (dropped and named);
- a `rename <old> -> <new>` onto an id that is already done keeps one done entry, at the
  earlier time;
- a running step that is no longer a timer leaves running and is available or held as its
  dependencies allow ("tap it when it's done"); a slug that vanished without an entry is
  dropped and named "no longer in the recipe" (the page cannot tell a rename from a removal);
- every prerequisite of a done or running step is implied done, as the paste box implies it;
- `h` is stamped on every state — a fresh cook from the mise screen, a pasted line, a
  reconcile — so a reopen with the same payload reconciles nothing and shows no notice; a
  phase already past does not chime again.

One toast reports it: `Recipe updated. Kept <k> done, <r> running.[ <Title> is now a timer.][
<Title> is no longer a timer — tap it when it's done.][ Dropped: <Title>, <Title> (no longer in
the recipe).]` A state from an earlier page version (not v2) is cleared with one toast
instead.

## 6. The mid-cook loop

The user asks for a change while a page is open → the assistant edits the file (a `changes`
line; a `rename` or `split` entry whenever a slug changes — never retitle an atom mid-cook
without one) → `check` → `player --dsl <file>` rebuilds the page → claude.ai: republish to the
same URL, the hot snapshot carries `{rid, state}`, the page boots, reconciles, toasts once;
Claude Code: the user reloads the file and the browser's storage supplies the state → the next
FOND1 line carries the new `h`. "How long to go?" from a pasted line is `plan --dsl <file>
--done … --running … --h <8hex>`; on a stale `h` the assistant asks for the line from the
updated page, or for the done steps by name. An export's own recipes never change, so their
pages reconcile only if the template itself changes between releases.

## 7. What the page never does

It never talks (no per-step conversation, no question about adding a countdown, no cue the
recipe did not carry, no offer of any kind); never infers what a step "really" is — a
sigil-less atom is a tap-when-done tile whatever its duration, and `kind` and `phases` come
from the payload only; never reclassifies a kind; never repairs or edits a recipe (no edit
control, no rename, no split — those are text edits to the file through the assistant); never
writes a file or changes the export; never fetches; never sends anything; never gates anything
on payment, account or sign-in; never sounds when the page is closed or backgrounded; never
resolves a step on its own. Its engine matches `plan` state for state — for any sequence of
taps the page's available, held and locked sets, minutes left and estimate equal `plan
--done … --running …` over the same ids — and its FOND1 line parses back to the same cook (the
engine tests under `tests/engine/`).
