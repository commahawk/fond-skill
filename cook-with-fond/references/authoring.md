# Writing a recipe — the authoring protocol

How the Cook-with-Fond skill writes a recipe in Fond's format once the servers have closed:
one `<slug>.recipe.md` the user keeps, labelled by origin, gated by `check`, cooked with
`--dsl`. The language is `dsl-spec.md` (cited here by section, never restated); the syntax
card is the "DSL v1 quick reference" at the end of `SKILL.md` (cited by heading); the
turn-by-turn protocol is `SKILL.md`; the page is `player.md`.

## 1. The model

- One recipe is one plain-text file: a frontmatter envelope between `---` fences, then a DSL
  v1 body exactly as the card teaches it — `# Title`, `## Atom [k=v …]`, sigils.
- Its id is `local:<basename>` — the file name up to its first dot, which must match
  `^[a-z][a-z0-9-]*$` (`check` and `--dsl` refuse any other shape and name it). `convert` and
  the assistant default the basename to the slugified title; two files cannot share a basename
  in one folder — an existing path is refused and the user picks another name; renaming the
  file renames the id and the player's saved state with it (`player.md`: not mid-cook).
- Where it lives: in Claude Code, a folder the user names (the README suggests `fond-recipes/`
  beside the export — never pick one silently; `<folder> --dsl list` lists it); in claude.ai, a
  file written in the sandbox and offered as a download, which the user re-attaches or adds to
  a Project next time; on the paste path, a fenced block the user saves themselves
  (`prompts/paste-this-prompt.md` drafts only). The export is never written.
- No registry, no save, no Fond id, handle or lineage is minted. After 2026-10-29 a checked
  file the user keeps is what "getting a recipe in" means; the file is theirs, for their own
  cooking — the skill never encourages sharing or republishing it.

## 2. The envelope

The frontmatter is the legacy block `dsl-spec.md` §1.2 describes, the one shape both readers
accept. Its top-level keys are exactly `title`, `author`, `yield`, `source_url`,
`attribution`, `lineage` — no other (`check` refuses `id`, `handle`, any parent-version key
and any 28-character alphanumeric value: "a local file never carries a Fond id" / "a uid").

**The frontmatter exception.** The card's heading "Document shape — no YAML frontmatter"
describes what the compiler emits and what the registry stored. A library file carries §1.2
frontmatter because the file IS the store. The card's text is not edited; the body after the
envelope follows the card to the letter, and lint reads only `title` (and `phases`, which the
envelope never declares) from the block.

`attribution` is a list of lines naming sources, and `lineage` a map:

| Key | Variant (filled by `convert`, never typed) | Composed | Transcribed |
|---|---|---|---|
| `author` | the row's `authorHandle` as `"@<handle>"` (`(unknown)` when null) | what the user gives, or absent | the name the user gives, or absent |
| `yield` | from `servings` when the row has one | when known | when known |
| `source_url` | the row's `url` | the page the user handed over | — |
| `attribution` | `- source <sourceAuthor>` when the row has one | a page: its named creator, or its site name when it names none, as the page states it (never a handle, a uid or the user); a printed page: `<book> by <author>`; pasted text: its source | what the user names (`Grandma's card`) when they name anything |
| `lineage.origin` | `variant` | `composed` | `transcribed` |
| `lineage.parent_id`, `parent_handle` | the row's Fond id and handle | never | never |
| `lineage.parent_lineage` | the export's `Lineage:` line verbatim (`export-format.md` §7), only when the row's `lineage` is non-null | — | — |
| `lineage.exported_at` | the export's `exportedAt` | — | — |
| `lineage.credits` | the row's `attributionHandles` verbatim (§5), only when the row's `lineage` is non-null | — | — |
| `lineage.made_on` | `YYYY-MM-DD` from the conversation (`convert --made-on`, optional: without it the draft's `made_on:` is empty and `check` says "fill lineage.made_on with today's date (YYYY-MM-DD)"; the script reads no clock) | the same | the same |
| `lineage.changes` | first `copied from the Fond-format steps the export carries` or `converted by the assistant from the app's steps`, then one line per edit | first: how it was composed (from the user's description; from the page) | first: transcribed from what |

Required on every file: `title`, `lineage.origin`, `lineage.made_on`, `lineage.changes` with
at least one entry; a variant also carries `parent_id` (so its `lineage` block always names
its parent and `Derived from:` prints from the file alone), `author`, `source_url` when the row
has a `url`, `attribution` when it has a `sourceAuthor`, `exported_at`, and `credits` and
`parent_lineage` exactly when the row's `lineage` is non-null; a composed file from a page
carries `source_url` AND `attribution`; one composed from nothing carries neither, and its
first `changes` entry says so.

`changes` is append-only, one line per edit, never containing a colon (the reference reader
turns `a: b` into a map; `check` warns "write -> not :"). Two forms are parsed —
`rename <old> -> <new>` and `split <old> -> <a>, <b>[, …]` — and everything else is free text.
Whenever a slug changes, one of the two is required: the player's reconcile reads them and
nothing else (`player.md`).

The reader is strict where the reference reader guesses: `key: scalar`, a nested map or list
indented under its key, and `- item` scalars; every scalar stays a string (quote `"@cara"`,
since a bare `@` is a YAML indicator; `parent_id` is text whatever it looks like); refused as
`check` errors, never guessed — a compact list `[a, b]`, a colon-space inside a list item, a
duplicated key, a tab, a `lineage.origin` outside the three, a `parent_id` on a composed or
transcribed file, and a `title:` that differs from the `# H1`.

A variant of a row whose lineage is null (synthetic example; the body follows):

```
---
title: Tomato Soup
author: "@ben"
source_url: https://blog.example/soup
lineage:
  origin: variant
  parent_id: rcp-soup-05
  parent_handle: soup-xyz789
  exported_at: 2026-10-08T12:00:00+00:00
  made_on: 2026-10-13
  changes:
    - converted by the assistant from the app's steps
    - add ~simmer{20%min} on simmer-the-soup
---
# Tomato Soup
```

A composed file from a page the user handed over, and a transcription:

```
---
title: Weeknight Dal
source_url: https://blog.example/dal
attribution:
  - Ana
lineage:
  origin: composed
  made_on: 2026-10-13
  changes:
    - composed by the assistant from the page, procedure only
---
```

```
---
title: Nonna's Ragù
author: Nonna
attribution:
  - Nonna's card
lineage:
  origin: transcribed
  made_on: 2026-10-13
  changes:
    - transcribed from the card as written
---
```

## 3. The three origins and their exact lines

The label is printed from `lineage.origin`, never stored. `list` prints one line per file;
`show`, the cook's opening turn and the player's mise screen print the same line first, then
one line each, only when present. The completion turn repeats the `list` line.

| Origin | `list` line |
|---|---|
| composed | `<Title> — composed by the assistant[ · from <host>, credited to <creator>] · local:<slug>` — the host of `source_url` and the `attribution` entry whenever a page was handed over; the creator as the page states it, or its site name, never a "by @" handle |
| variant | `<Title> — local variant of <parent title> <parent by-line head> · local:<slug>` — the head exactly as the export's own by-line prints it for the row (a `sourceAuthor` leads when present, "by (unknown)" for a null handle; never a bare handle, never "by you") |
| transcribed | `<Title> — transcribed by the assistant[ from <attribution source>] · local:<slug>` — the clause only when the user named a source |

The lines after it: `Local file: <path>` · `Source: <source_url>` · `Attribution: <lines>` ·
for a variant `Derived from: Fond id <parent_id>[ (handle <parent_handle>)] — <the parent
row's by-line>` when `--parent` carries the row, else exactly `Derived from: Fond id
<parent_id> (not in this export)` — from the file alone, no handle, no by-line · `Lineage
(parent): <parent_lineage>` ·
`Credits: @<a>, @<b>` (the chain in its recorded order) · `Exported: <exported_at>` ·
`Changes:` followed by every entry, the first never dropped. `plan --dsl` adds `Steps from: a
local file (h=<8hex>)`. A composed or transcribed file prints no lineage line.

Never, for a local file's own identity: "Fond id", "Fond handle", "by you", "saved to Fond",
"original", "adapted", "your recipe", "Fond recipe", "None", the registry's mint word or its
past participle. "Fond id" appears only on the `Derived from:` line naming the parent; the
registry's mint word only inside the verbatim `Lineage (parent):` echo of the parent's own
line; the parent by-line head inside `Derived from:` and the `list` line is the export's own
text for that row, unchanged. "you" is never written into a file or a line about it — the
file may travel — so the `Derived from:` by-line and the player payload are built as after
`strip`, whatever `profile` says. Asked "is this original?", the skill says the file was
composed from the named source (or the user's description), or derived from the Fond recipe,
and calls it neither original nor adapted. `strip` over a `--dsl` input exits 0, writes
nothing and prints "a local file is not an export; its provenance block is the file".

## 4. The rules by input

| The user hands over | Origin | What the assistant does |
|---|---|---|
| their own words, dictated or pasted; a photo of a hand-written or family card | transcribed | keep their wording in the prose, annotated with `@ingredient{…}` and sigils per the card; ask about an unreadable or missing amount, never guess it; no time, `duration=` or countdown the user did not state — a time they give for a process the cook acts on is sigiled; an untimed "bake until golden" stays a cue, the assistant asks roughly how long, and with no answer writes no `duration=` and says the estimate will not count that step |
| a photo of a printed cookbook or magazine page | composed | the procedure only — ingredients with amounts, actions, times, cues — in the assistant's own words, no sentence of the page copied, no headnote; `attribution: - <book> by <author>` |
| one URL | composed | open that one page once, on request, with the assistant's own tool (the script opens no socket); follow no link, fetch no second page; procedure only, never headnotes or prose; `source_url` the URL; `attribution` the page's named creator, or its site name when the page names none, as the page states it (never a handle, a uid or the user); the date the user gives in `made_on` |
| pasted text from a page | composed | as a URL, with the source the user names |
| a recipe the export carries | variant | `convert "<title>" [--made-on <date>]` (§7; the date is today's from the conversation — pass it when you know it, else fill `made_on:` before `check`); the row's `dsl` copied verbatim, or a nodes-only row transliterated; every later edit one `changes` line |
| "make it for six, keep it" / "swap X for Y" | variant | an edit with the entry `scaled ×<f> from <base> servings` (the canonical `@slug{…}` lines carry the scaled amounts; amounts stated inside step prose stay as written and are named in the entry) or `swap <a> for <b>`; a file whose `yield` states servings scales with `scale --dsl` without asking |
| a saved row the export carries no steps for | composed, on request | from the row's `url` opened once on request, or from text the user hands over — `source_url` the row's `url`, `attribution` the page's creator as the page states it (never the row's `authorHandle`); the row stays "saved, no steps in this export" |

Amounts the source does not state are asked for, or written as the assistant's estimate and
marked so in the prose — never invented silently. Times the source states carry their sigil;
no time the source did not state is added.

## 5. Credits, the by-line and the user

- `credits` is the handle list the export's `Lineage:` line prints — the row's
  `attributionHandles`, copied in their recorded order, never re-ordered, de-duplicated or
  extended, a null position as `(unknown)`; present whenever the row's `lineage` is non-null,
  absent when it is null (no chain exists; the by-line author stands alone). It is not the
  registry document's `credits` similarity field.
- The author stands on the by-line (`author`) and is never moved into the chain; `check
  --parent` asserts `credits` equals the row's chain exactly, order included, and "no
  `credits` key" against a null parent lineage.
- An edit adds no name. The user is the file's editor, never a co-author; their handle appears
  in a file or a line only where it is the parent row's own `authorHandle` (a variant of the
  user's own recipe), and "you" never. The dish stays the creator's or unowned.
- A shadow creator's handle — a domain or social handle standing in for a page's or video's
  creator — is text, carried only inside the parent by-line as the export's reader prints it:
  never @-mentioned, linked, fetched or contacted.
- The relation is "derived from" — no parent version is minted (the parent's own `at
  <version>` survives only inside the copied `parent_lineage` line), no lineage node, no
  handle. The body a row carries may be machine-made and the file cannot tell, so the copy
  entry says "the Fond-format steps the export carries", never the creator's authored DSL.

## 6. Timer discipline — authored DSL follows the frozen rule

The card's "A timer is a signal, not an annotation" bullet, applied to what the assistant
writes (`dsl-spec.md` §2.4 for the sigil, §6 for the rules):

- a `~timer{}` sigil on every countdown the cook acts on at the ring — a simmer's come-check,
  a sear per side (`× N`), a bake's check, a rest of definite length — with the doneness cue
  in the prose;
- no sigil on a transition the kitchen signals — a preheat, water coming to a boil, coming up
  to a simmer — which stays a sigil-less `none`/`low` atom with `duration=` as the schedule's
  estimate (a sigil there is harmless, never required);
- a duration the prose states is always sigiled (rule T, gated); `duration=` on every timed
  atom at least its sigil total (rule AA); `attention_level` on every cooking atom (rule S);
  `count=` or `× N` for repeats, never a countdown invented for a repeat the source did not
  state;
- a transcription times only what the user said; a variant gains a sigil only on the user's
  request or from the app's own timed step (§8); `convert` writes a sigil only where the node
  had `until` and `time > 0`.

The reader side is unchanged: the skill and the player cook a local file exactly as `SKILL.md`
cooks any DSL — a countdown iff a sigil, no lift, no inference, no offer.

## 7. The `check` loop

`<file|-> check [--parent <export>] [--json] [--out <path>]` (`-` reads stdin):

1. the envelope (§2) — any error names its key (an empty `made_on`, from `convert` without
   `--made-on`, reads "fill lineage.made_on with today's date (YYYY-MM-DD)"); on a shape the
   strict reader refuses (a tab, a compact list, a map under a list item, a duplicated key)
   `check` ends here with that error and runs no lint;
2. the vendored Fond lint over the body, then the gate: every error and every finding whose
   rule is in the registry's gated set — R S T U V W X Y AA AB AC AD AE — blocks (exit 1, one
   teaching line per finding naming the rule letter and the atom, e.g. `warning [AA]
   @toast-the-spices: timer total 2m exceeds duration=0 — …`). Nothing is auto-repaired:
   `check` reports; the assistant edits. One exemption, on a variant: `--parent <export>` is
   REQUIRED (absent, exit 2 with one line naming it) and the parent row as the export carries
   it — its `dsl`, or for a nodes-only row the `convert` output — is the baseline; a rule U
   (undeclared ordering) or V (non-convergent DAG) finding present in that baseline prints
   "(inherited from the export)" and does not gate, while a U or V absent from it was
   introduced by an edit and gates. On a composed or transcribed file all thirteen gate — the
   assistant wrote the ordering and resolves a gap by asking, never by inventing an edge. The
   registry's ingredient floor (three canonical defs) is printed "(not gated for a local file)"
   and never gates; rule AH is a no-op; rule D runs;
3. with `--parent`, the cross-check: `parent_id`, `parent_handle`, `author`, `attribution`,
   `parent_lineage` and `credits` against the row — a mismatch names the key and the row's
   values;
4. "Plays as:" — each step's kind (timer / hands-on / cue / about N min) and the time-to-serve
   estimate, exactly what `plan --dsl` will say — then `h=<8hex>` (`player.md`) and, when
   nothing blocks, `Passes: nothing blocks local:<slug>.`;
5. `--out <path>` writes the checked text only when nothing blocks, never over an existing
   path (`<path>` exists; pass --out <other> or edit that file) and never beside a recipe
   file that already resolves to the output's id (`foo.md` beside a `foo.recipe.md` to be
   written: the collision line naming both, exit 1, nothing written). With `--out` the
   recipe is constructed, gated and reported under the OUTPUT's basename — `check
   source.md --out foo.recipe.md` says `local:foo`, the id the kept file carries — for a
   file input and for stdin alike. `--json` gives `{ok, findings: [{rule, step, kind,
   message, gated}], notes, plays_as, h}`.

The loop in practice: `convert` prints the draft with the export's own findings under
`Inherited findings:` and, with `--out`, writes nothing when any of them gates; the assistant
repairs the draft in the conversation (AA: `duration=` raised to the sigil total, one `changes`
line per atom — `set duration=15 on rest-the-dough, the sigil total`), makes the edit the user
asked for, and persists it with `check - --parent <export> --out <slug>.recipe.md` (stdin). The
file exists only once the gate reports nothing. After every later edit the assistant runs
`check` again before cooking. The read commands — `--dsl list|show|plan|scale|player` — run the
same gate first and refuse a file with findings (`--dsl list` prints "(does not pass check)"
after such a row); they take `--parent` and never require it: without it rules U and V print
"(not gated without --parent — pass it to gate edits)" and the command proceeds, because a
file written through the skill already passed the ratchet when it was kept.

`check`, `convert` and every `--dsl` command import the vendored lint lazily and need Python
3.9; on an older interpreter they print "Local recipe files need Python 3.9 or newer (this
interpreter is 3.8.x); every command over an export still works" and exit 1.

**What the assistant says.** On a clean gate: "Kept as `<path>` (local:<slug>); `check` reports
nothing." — then the cook. On a failing gate, one line and the findings: "Not kept yet —
`check` reports N finding(s):" followed by the script's lines, then the mechanical fixes it
makes itself; it asks the user only when a fix would change the recipe's meaning — a missing
time ("the card says 'simmer until thick' — roughly how long?"), an ambiguous amount, an
order the source does not give ("which comes first, the sauce or the pasta?") — saying in that
line that the file is not kept yet and why.

## 8. The Option B "yes" — the app's timers as a variant

`SKILL.md` asks once, before the first step, when a recipe's Fond-format steps carry no
timers while the app's steps did. On "yes": `convert "<title>" --made-on <date>`; fix any
inherited findings in the draft; append the `changes` line `add timers from the app's steps`;
for each timed step the notice listed, add one `~<name>{N%min}` (`{S%sec}` for a sub-minute
`time`; `× R` or `count=R` for `repeat` R > 1) inside the sentence of the atom whose title
matches — matched by the assistant, title by title (`show` of the row and of the file), never
by the script — with `duration=` raised to at least the sigil total and one `add
~<name>{N%min} on <atom-slug>` entry per edit; a timed step with no matching atom is recorded
as `no atom for <node title> — timer not added` and said aloud; then `check - --parent <export>
--out <slug>.recipe.md`, then `plan --dsl` or `player --dsl` with `--parent`. A preheat timer
from the app keeps its sigil here — the user asked for the app's timers, and a sigil on a
preheat is harmless. "No" cooks the row as written and creates nothing.

## 9. Refusals — one sentence, naming the rule

- A named creator's or publication's recipe from the model's memory: "I can't write
  <creator>'s recipe from memory — the export has its page at <url>; say the word and I'll
  open that one page" (or: "hand me the page or your own version").
- Bulk or unattended authoring — every saved recipe, every page of a site, a folder of links:
  "One recipe per request; which one first?"
- Any claim that a local file is a Fond recipe, saved to Fond, in a Fond library, on Fond's
  registry, or checked by anyone but `check`: it is a local file the user keeps, composed /
  derived / transcribed as its line says, checked against Fond's rules, entered nowhere.
- Never crawl or fetch a page the user did not hand you; never follow a link on a page they did.
- Editing the export; overwriting a recipe file (a new path, or the user edits that file).
- Minting a Fond id, handle or lineage; writing "you" into a file, or the user's handle
  anywhere but where it is the parent row's own `authorHandle`.
- Carrying a source's prose verbatim — procedure in the assistant's words, never its prose
  verbatim, never a headnote.
- Encouraging the user to republish a variant or a composed recipe from someone else's
  source: the recipe is the creator's; the skill names the credits and does not encourage
  posting it.

The inherited refusals of `SKILL.md` stay in force; nothing is gated on payment, account or
sign-in; nothing is logged.
