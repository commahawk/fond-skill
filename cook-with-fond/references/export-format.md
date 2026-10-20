# The Fond export — field reference

What the files from **Export my data** contain, so `scripts/fond_export.py` (and anyone
reading an export by hand) knows exactly which fields exist, in which version, and what
each one means. This document describes data; the cooking behaviour built on it is in
`fond-style.md` and `SKILL.md`, and the DSL text itself is specified in `dsl-spec.md`.

| Skill version | Reads `export_version` | Notes |
|---|---|---|
| 0.1.0 (this folder) | `1` and `2` | warns and continues on a higher integer; refuses a file with no integer `export_version` ("not a Fond export — the file is `fond-export-<date>.json` from Export my data") |

Version 2 is a strict superset of version 1: no field is renamed, removed or retyped.
**Read keys, not versions** — a version-1 file produced late in the service's life may
already carry a key that this reference lists under version 2 (see `url` on saved rows),
and a version-2 file may carry `null` where a degrade tier removed content. Everything
below that says "version 2" means "present from version 2 on; absent or `null` before".

## 1. Where the file comes from, and its two shapes

The app's **Export my data** button and the operator-run export batch both produce the
same two files from the same builder: `fond-export-<date>.json` and
`fond-export-<date>.md`. The Markdown is a rendering of the JSON, not a second source of
truth; everything in the `.md` is derived from the `.json`.

The reader accepts two JSON shapes:

1. **The bare export** — a JSON object whose top-level keys are the seven listed in §2.
2. **The raw callable payload** — `{"json": <bare export>, "markdown": "<the .md text>"}`,
   exactly those two keys. Older clients and some download paths save this wrapper
   unchanged. The reader unwraps `json` and may use `markdown` as the `--md` input.

Pretty-printed and compact JSON both parse. The `.md` on its own is read with `--md` (§8).

## 2. Top level

Exactly seven keys, in both versions:

| Key | Type | Meaning |
|---|---|---|
| `export_version` | integer | `1` or `2` (see the table above) |
| `exportedAt` | ISO 8601 string | when the export was built (UTC) |
| `profile` | object | the user's own public profile fields (§3) |
| `contact` | object | the user's contact details (§3) — **never read by the skill** |
| `authoredRecipes` | array | recipes the user created, newest `datePublished` first (§4) |
| `savedRecipes` | array | recipes the user saved, newest `savedAt` first (§5) |
| `cooks` | array | cooking history, newest `startedAt` first (§6) |

Timestamps everywhere are ISO 8601 strings or `null`.

## 3. `profile` and `contact`

```json
"profile": {
  "uid": "<account id>", "handle": "ana", "createdAt": "2024-03-01T10:00:00+00:00",
  "totalCooks": 12, "totalRecipes": 3, "credits": 0, "linkedAnonymousUids": []
},
"contact": { "email": "", "displayName": "", "phoneNumber": "", "tiktokUsername": "" }
```

Both objects exist in both versions and their key sets do not change. The Markdown may
place the `## Contact` block last (version 2) so a user can delete it before sharing.

**Fields the skill never reads:** `contact.*`, `profile.uid`, `profile.credits`,
`profile.linkedAnonymousUids`, and the `linkedFromUid` of every authored, saved and cook
record (the account ids of earlier anonymous sessions). The one `profile` field the skill
does read is `profile.handle`, and only for the by-line rule in §7.

`strip` writes a copy without `contact` and `profile`, with every `linkedFromUid` set to
`null`, and with every record's `id`, `handle`, `url`, `authorHandle`, `sourceAuthor` and
`lineage` untouched (§7 says why `authorHandle` must survive).

## 4. `authoredRecipes[]`

A recipe the user created: a text, photo or form import, a DSL-born save through the
service, or a recipe written in the app. One row per recipe document. A recipe imported
from a **page or a video** is not an authored row: it is a saved row (§5) whose recipe
document's `author` is the account the import mapped the domain or creator handle to — a
shadow account created on first import, or the creator's own account once they have
claimed that handle (the lookup matches an existing account before creating a shadow,
and the exporter follows account merges) — and the importer holds the saved row. Its
`authorHandle` is the creator's stand-in in every case; the saved row's `reason` never
tells an import apart (current grants carry `reason: "importer"`, older ones carry
`author`).

| Key | Type | Version | Meaning |
|---|---|---|---|
| `id` | string | 1 | the recipe document id — the canonical storage and lineage key |
| `linkedFromUid` | string or null | 1 | never read; `null` for the user's own records |
| `handle` | string or null | 1 | the public alias (`<kebab-title>-<6 chars>`, e.g. `soup-xyz789`) |
| `title` | string or null | 1 | |
| `url` | string or null | 1 | the source page; from version 2 falls back to `source.url` when the document's own `url` is empty |
| `datePublished` | ISO string or null | 1 | |
| `isPublic` | boolean | 1 | |
| `ingredients` | array | 1 | the recipe's ingredient lines — see "Ingredient lines" below |
| `nodes` | array (or a JSON string) | 1 | the legacy step graph — the full node documents, see §9 |
| `dsl` | string or null | 1 | the recipe's DSL v1 text when the recipe has one; `null` otherwise (most exports carry none; a few are all-DSL) |
| `authorHandle` | string or null | 2 | the creator's public handle — the exporting user's own handle, resolved through account merges; `null` when that account has no handle; **never an account id** |
| `sourceAuthor` | string or null | 2 | the author named by the source page, when the document records one (§7) |
| `lineage` | object or null | 2 | fork lineage, `null` unless the document is a fork (§7) |

A version-1 authored row has **no `authorHandle` key**. The reader then takes
`profile.handle` as the creator's handle when `profile` is present, and treats the handle
as unknown when it is not (a hand-edited or stripped version-1 file). `strip` stamps that
fallback onto each version-1 authored row as `authorHandle` before it removes `profile`.

**Ingredient lines.** On most recipes `ingredients[]` holds plain strings ("2 cloves
garlic"). Newer imports may hold objects; the export's own Markdown renderer prints the
first present of `text`, `original`, `name`, and a reader should do the same. Quantities
are whatever the source gave: the export never adds one, and neither does the skill.

## 5. `savedRecipes[]`

A recipe the user saved from another creator (or their own). One row per saved entry.
Every page or video import is here, not under §4: the recipe document belongs to the
account the import mapped the source's domain or creator handle to (a shadow account on
first import, the creator's own once claimed), and the user who imported it holds the
saved row — identified by that `authorHandle`, never by `reason`.

### Version 1 — metadata only

| Key | Type | Meaning |
|---|---|---|
| `id` | string | the recipe document id |
| `linkedFromUid` | string or null | never read |
| `title` | string or null | `null` when the recipe document no longer exists |
| `handle` | string or null | the recipe's public alias |
| `authorHandle` | string or null | the creator's public handle (never their e-mail or id) |
| `reason` | string or null | how it was saved (`url`, `shared`, `importer`, `author`, …) — a grant's own label, never a way to tell an import apart (older import grants carry `author`, current ones `importer`) |
| `savedAt` | ISO string or null | |
| `cookCount` | integer | how many times this user cooked it |
| `deleted` | boolean | the user removed it from their library |
| `url` | string or null | **late version 1:** the source page, present on files built after the saved-row URL change (fond-app commit `680c40a1`); absent on earlier files; always present from version 2 |

A version-1 saved row carries no steps, so the skill lists it under "saved, no steps in
this export" and never fetches `url` unasked — with one exception: a version-1 saved row
whose `id` is one of the `authoredRecipes[]` ids (the user's own recipe, saved) is listed
once, as the authored recipe, because its steps are in the export. Version 2 marks that
case explicitly with `authoredRecipeRef` (below).

### Version 2 — live rows carry what is needed to cook

For a saved row whose recipe document exists and whose entry is not deleted, version 2
adds:

| Key | Type | Meaning |
|---|---|---|
| `url` | string or null | the source page (document `url`, else `source.url`) |
| `ingredients` | array of strings | the ingredient lines, plain strings |
| `nodes` | array (or a JSON string) or null | the step graph, **slimmed** to `id`, `title`, `text`, `time`, `until`, `dependencies`, plus `repeat` only when the node carries it (`es`/`ls` dropped) — `null` only in degrade tier 3 (§10) |
| `dsl` | string or null | the DSL v1 text when the recipe has one; `null` when it has none, in degrade tier 2, or when the latency tier skipped the read (§10) |
| `servings` | `null` | always `null` — no yield exists anywhere in the data; scaling asks the user |
| `sourceAuthor` | string or null | §7 |
| `lineage` | object or null | §7 |

The version-1 fields (`id`, `linkedFromUid`, `title`, `handle`, `authorHandle`, `reason`,
`savedAt`, `cookCount`, `deleted`) are unchanged.

A saved row is **cookable** when it carries a non-null, non-empty `nodes` or `dsl`, or an
`authoredRecipeRef` that resolves (below). Otherwise it is "saved, no steps in this
export". `missing` lists exactly those rows.

Saved rows **never** carry `oginstructions`, `ogingredients` or `description` (the source
page's own prose): procedure and provenance travel, expressive text does not.

### Three row shapes that stay one line

| Row | Shape |
|---|---|
| **Own recipe in the saved list** (`id` is in `authoredRecipes`) | the version-1 fields plus `authoredRecipeRef: "<id>"` and **no** `nodes`, `ingredients`, `dsl`, `url`, `sourceAuthor` or `lineage`, whether or not `deleted` — the content exists once, on the authored row, and the reader follows the reference |
| **Deleted** (`deleted: true`) | the version-1 shape; no content fields, so nothing deleted is resurrected |
| **Recipe document gone** | the version-1 shape with `title: null`; the export does not fail |

## 6. `cooks[]`

```json
{
  "id": "cook-synthetic-01", "linkedFromUid": null, "mealName": "Sunday dinner",
  "status": "rated", "startedAt": "2026-03-01T17:00:00+00:00", "completedAt": "2026-03-01T18:10:00+00:00",
  "deleted": false,
  "recipes": [
    { "id": "<recipe id>", "title": "Soup", "isValid": true, "status": "rated", "userOverride": false,
      "completedAt": "2026-03-01T18:05:00+00:00",
      "ratings": { "easyFollow": 4, "taste": 5, "wouldCookAgain": 5 }, "feedback": "great" }
  ]
}
```

Version 2 adds the app's own counting flags — `deleted` on the cook, `status` and
`userOverride` on each recipe row — and changes nothing else; a version-1 row has none of
the three.

| Field | Type | Version | Meaning |
|---|---|---|---|
| `deleted` (cook) | boolean | 2 | the user removed the cook from their history; `false` when the cook document had no flag |
| `recipes[].status` | string or null | 2 | the cook-recipe document's own status: `migrated` on a pre-app cook (the migration wrote it with a heuristic `isValid`), `recorded`, `rated` or `skipped` from the review flow; `null` when absent |
| `recipes[].userOverride` | boolean | 2 | an invalid cook the user marked as cooked; the app counted it; `false` when absent |

- **A cook counts** when `deleted` is not true and `status` is `completed`, `recorded`,
  `rated` or `migrated` — the app's own history filter. `aborted`, `active` and anything
  else do not count. `migrated` rows are pre-app cooks: at most an `easyFollow` rating,
  counted for frequency and recency only.
- **Within a cook, a recipe counts** when `recipes[].isValid` is `true`, **or**
  `userOverride` is `true`, **or** `status` is `"migrated"` — the app's own rule
  (`isValid` alone would drop an arbitrary share of migrated cooks). On a version-1 row,
  which has neither `status` nor `userOverride`, the cook's own `status: "migrated"`
  stands in for the recipe's (the migration wrote both) and `userOverride` is taken as
  false — so a version-1 export cannot show a removed cook or an override, and a reader
  counts them as the app did before the flags existed. `ratings` holds whichever of
  `easyFollow`, `taste`, `wouldCookAgain` (1–5, an integer or a float — the app's review
  screen writes doubles such as `4.0`) were given; it is `{}` when none were.
  `feedback` is free text or `null`.
- **Verdict mapping used by the skill:** `taste ≥ 4` = hit, `taste ≤ 2` = miss,
  `wouldCookAgain ≥ 4` = would cook again, from the latest counted cook that rated either —
  that one cook's taste, `wouldCookAgain` and date together, never the best of each across
  cooks; an `easyFollow` alone gives no verdict. Cook-again suggestions are limited to
  recipes that are cookable in the same export, ranked by that rating then recency (the
  newest counted cook).
- `recipes[].id` is a recipe document id, so a cook joins to `authoredRecipes[]`,
  `savedRecipes[]` (or a saved row's `authoredRecipeRef`) by `id`.

## 7. Provenance — the fields that travel with every copy

Every authored row and every live version-2 saved row carries the provenance its recipe
document actually has — never a fabricated one. These fields are shown on every listing,
`show` and cook, and `strip` leaves all of them untouched.

| Field | Meaning | When `null` |
|---|---|---|
| `id` | the recipe document id — canonical storage and lineage key | never |
| `handle` | the public alias; "Fond handle soup-xyz789" in listings | the document has none (then the listing says "Fond id <id>") |
| `url` | the source page; shown as its host in listings, in full on `show` | no source page |
| `authorHandle` | the creator's public handle; authored rows carry it from version 2 (§4), saved rows in both versions | the account has no handle → shown as "(unknown)" |
| `sourceAuthor` | the author the source page names — the first non-empty of the document's `source.author`, `source.creator_handle`, `source.handle`, `source.creator`, `source.name` | the document has no `source` dict, or it names no author (an import stamp such as `{"type": "import", "via": …}` yields `null`) |
| `lineage` | `{"parentId": "<id>", "forkPoint": "<version or null>", "attributionHandles": ["ana", "ben"]}` — the recipe is a fork of `parentId`, taken at version `forkPoint` (`null` when the parent had no saved version at fork time), crediting the chain of creators by public handle in order (an unresolvable position is `null`, shown as "(unknown)") | **the document is not a fork** — every recipe imported through the app and every DSL recipe created rather than forked; the creator of such a recipe is `authorHandle`, not lineage |

**The null rule for `lineage`:** `null` means "the export records no lineage", nothing
more. The reader prints no lineage line for it and does not call the recipe original,
adapted or derived.

**By-line rule** (how `authorHandle` and `sourceAuthor` are presented): "by @ana" from the
row's own `authorHandle`; "by Ana (saved to Fond by @importer)" when `sourceAuthor` is
present; "by (unknown)" for a null handle; "by you (@ana)" only when `profile` is present
and `profile.handle` equals the row's `authorHandle` — never "you" in a stripped file.
Because `strip` removes `profile`, an authored row's `authorHandle` is then the only copy
of its creator's handle, which is why `strip` never drops or nulls it.

**What the export never carries:** any account id of another user (the attribution chain
is exported as handles only), the recipe's `author` id, and the similarity fields a
registry pass may have stamped on a document (`credits`, `closest_recipe_id`,
`relation_to_closest`, `ownership`) — those are detector output, not creator-declared
lineage. The only account-id-bearing fields are `profile.uid`,
`profile.linkedAnonymousUids` and the `linkedFromUid` on records, none of which the skill
reads.

`parentId`, `handle` and `url` are provenance **text**: the reader shows them and never
resolves, fetches or links them unasked.

## 8. The Markdown export

The `.md` is a rendering of the JSON by `fond-functions/python/utils/user_export.py` as
deployed (fond-app `d142ab74` = Cloud Run `exportuserdata-00003-bit`). The contract is
that shipped output — not a hand-written approximation of it — and
`fixtures/sample-export.md` is that renderer's output over `fixtures/sample-export.json`.
**Regeneration note:** the fixture is regenerated offline by a short scratch script that
stubs `google.cloud.firestore_v1.base_query` (the renderer's one third-party import) in
`sys.modules`, loads `user_export.py` by file path with `importlib` and writes
`to_markdown(<the fixture JSON>)` — no credentials, no Firestore, no network; the script
is recorded in the fond-mono pull request, never shipped in this folder (the public
mirror does not depend on fond-functions). `fixtures/sample-export-v1.md` stays as
committed: it is byte-identical to the version-1 renderer users received
(`exportuserdata-00002-5wq`) over `sample-export-v1.json`. The first lines of a file:

```
# Your Fond data export

Exported 2026-10-08T12:00:00+00:00 · export version 2
```

Sections, in order: `## Profile`, `## Recipes you created (N)`, `## Recipes you saved
(N)`, `## Cooking history (N)`, and `## Contact` **last** (so a user can delete it before
sharing the file); a version-1 file placed `## Contact` second.

### Version 1 recipe sections

An authored recipe is a `### <title>` section with `- **Handle:**`, `- **Published:**`,
`- **Public:**`, `- **Source:**` lines, then `**Ingredients**` as a bullet list,
`**Steps**` as a numbered list of each node's `text` (its `title` when `text` is empty)
— **no timing information** — and, when the recipe has one, `**Recipe DSL**` followed by
the DSL text in a plain ``` fence. Every saved recipe is one line:

```
- **Tomato Soup** by @ben — saved 2026-09-10T08:30:00+00:00 (url), cooked 1× — https://blog.example/soup
```

(`— recipe since deleted` is appended for a deleted row; late version-1 files append
` — <url>` when the row has one.) A version-1 `.md` therefore cooks as a numbered list,
prep first, with no timers; the `.json` gives timers and parallel steps.

### Version 2 recipe sections

Authored recipes and **cookable** saved recipes render as sections of the same shape. A
saved section, exactly as the fixture carries it:

````
### Tomato Soup

by @ben

- **Saved:** 2026-09-10T08:30:00+00:00 (url)
- **Cooked:** 1×
- **Fond id:** rcp-soup-05 (handle soup-xyz789)
- **Source:** https://blog.example/soup

**Ingredients**

- 1 onion
- 2 tbsp butter
- 1 can tomatoes
- 2 cups stock
- salt

**Steps**

1. Prep: Dice the onion — Dice the [onion]. [~3 min]
2. Sweat the onion — Melt the [butter] and sweat the onion until soft. [~5 min] (after step 1)
3. Simmer the soup — Add the [tomatoes] and the [stock]; simmer. [Timer: 20 min — done when thickened and glossy] (after step 2)
4. Blend and serve — Blend smooth, season with [salt] and serve. [~3 min] (after step 3)
````

An authored section carries `- **Published:**` and `- **Public:**` in place of the
`Saved`/`Cooked` lines; a plain `Lineage:` line follows the key lines only when `lineage`
is non-null, and the DSL fence follows the Steps list when the row has a `dsl`:

````
### Skillet Steak Supper

by Cara · on Fond by @ana

- **Published:** 2026-09-20T18:00:00+00:00
- **Public:** yes
- **Fond id:** rcp-steak-01 (handle skillet-steak-supper-a1b2c3)
- **Source:** https://blog.example/skillet-steak-supper

Lineage: forked from rcp-parent-77 at v2; credits @cara, @ben
````

````
**Recipe DSL**

```
# Skillet Steak Supper
```
````

Line by line:

- **The by-line** is on its own line after the heading and comes from the row itself
  (its `authorHandle`), never from the Profile block: `by @<authorHandle>`; `by (unknown)`
  for a null handle; and `by <sourceAuthor> · on Fond by @<authorHandle>` when
  `sourceAuthor` is present — the source author first, the Fond handle only after "on
  Fond" (a source author written `@cara` is never the Fond creator), and `· on Fond by
  (unknown)` when the handle is null (sourceAuthor kept, handle null — "(unknown)" is
  never a handle).
- `- **Saved:** <savedAt>` carries ` (<reason>)` only when the row has a `reason`;
  `- **Cooked:** N×` is the row's `cookCount`, `0×` included (saved sections only).
- `- **Fond id:** <id>` carries ` (handle <handle>)` only when the row has a handle;
  `- **Source:** <url>` appears only when the row has a url.
- `Lineage: forked from <parentId>` is a plain line (no bullet, no bold), then
  " at <forkPoint>" only when `forkPoint` is non-null, then "; credits @a, @b" with a null
  handle as "(unknown)"; the string "None" never appears.
- `**Ingredients**` appears only when the row has at least one ingredient text,
  `**Steps**` only when its `nodes` are non-empty, and the `**Recipe DSL**` fence after
  the Steps list only when `dsl` is present.

**Step lines.** A step line is `k. <title> — <text> [<timing>] (after step k, …)`: the
title is **not bolded**; ` — <text>` is omitted when the node has no text, the
`[<timing>]` bracket when the node has no timing, the `(after …)` tag when the step has
no dependencies; a node with neither title nor text prints as `k. (untitled step)` and a
non-dict node as `k. <value>` — a reader takes neither for a title. The fixture's
Weeknight Garlic Pasta shows every timing form:

```
1. Prep: Slice the garlic — Thinly slice the [garlic]. [~2 min]
2. Prep: Grate the cheese — Grate the [parmesan] and set it aside.
3. Boil the water — Bring a large pot of [water] to a boil and salt it well. [Done when: the water is at a rolling boil]
4. Cook the pasta — Drop the [spaghetti] in and stir once. [Timer: 12 min — done when al dente] (after step 3)
5. Sizzle the garlic — Warm the [olive oil] with the sliced garlic over low heat. [Timer: 0.5 min — done when fragrant] (after step 1)
6. Toss the pasta — Toss the drained pasta with the oil, the [parsley] and a pinch of [chili flakes]. [~8 min] (after step 4, 5)
7. Puff the flatbreads — Toast each [flatbread] in a dry pan until puffed. [Timer: 1 min × 2 — done when puffed (×2)]
8. Fry the eggs — Fry the [eggs] one at a time in the garlic oil. [~2 min × 3] (after step 5)
9. Serve — Plate the pasta with the cheese, a flatbread and an egg each. (after step 6, 7, 8, 2)
```

The bracket carries the node's timing:

| Node | `[<timing>]` |
|---|---|
| `until` present, `time > 0` | `[Timer: N min — done when <until>]` |
| … and `repeat` R > 1 | `[Timer: N min × R — done when <until>]` (N is per-iteration) |
| `until` present, `time` null or 0 | `[Done when: <until>]` — an untimed cue, not a timer |
| `time > 0`, no `until` | `[~N min]` (hands-on) |
| … and `repeat` R > 1 | `[~N min × R]` (hands-on, N per-iteration, no countdown) |
| neither | nothing — a `time` of 0 prints no bracket at all |

N is printed as the shortest decimal (`0.5 min` for thirty seconds, never `30 sec`); then
`(after step k, …)` from the node's dependencies.

**Known limits of reading the `.md`** (the JSON is authoritative): a title that itself
contains ` — ` splits at its first ` — ` — the renderer does not bold titles, so the
reader cannot tell where the title ends and the tail of the title lands in the text (the
timing, cue and dependencies still read); only a TRAILING bracket whose whole content is a
timing (`Timer: …`, `Done when: …`, `~N min[ × R]`, `~N sec`) is read as one, so
`[~2 cups stock]` on an untimed step is an ingredient that stays in the text; the
first ` ~N min` in a step line is read as its hands-on time; and a **version-1** own-recipe
row (`… (own), cooked N×` — that render wrote no `(Fond id <id>)` tail) resolves by title
and the profile's handle, so two of your recipes sharing a title cannot be told apart
there, whereas a version-2 row's tail names the authored recipe's id and resolves by id.

**One-line rows.** Deleted rows, rows whose recipe document is gone, `authoredRecipeRef`
rows and degraded rows stay one line, **interleaved with the full sections in the
export's own order (newest `savedAt` first)** — so a one-line row may follow a section,
as the fixture's four do after its Tomato Soup section:

```
- **Grandma's Stew** by @ben — saved 2026-08-01T12:00:00+00:00 (shared), cooked 1× — https://blog.example/stew
- **Weeknight Garlic Pasta** by @ana — saved 2026-08-16T07:00:00+00:00 (own), cooked 2× — one of your own recipes: see "Weeknight Garlic Pasta" under Recipes you created (Fond id rcp-pasta-02)
- **Old Favourite Curry** by @ben — saved 2026-05-01T12:00:00+00:00 (cooked) — recipe since deleted
- **—** — saved 2026-04-01T12:00:00+00:00 (url)
```

The parts, in this order, each only when the row has it: `- **<title>**`, ` by @<handle>`,
` — saved <savedAt>`, ` (<reason>)`, `, cooked N×` (above zero only), ` — recipe since
deleted`, ` (from earlier anonymous session <uid>)` (ops-script exports only),
` — <url>`, ` — one of your own recipes: see "<title>" under Recipes you created (Fond id
<id>)`. A missing document prints its title as `—` with no `by` part and no url. A
one-line row carries no recipe handle, `sourceAuthor` or lineage, and no Fond id except
the `authoredRecipeRef` row's `(Fond id <id>)` tail, which a reader takes as the row's
own id (a save of your own recipe shares its document) and resolves against the authored
sections by id, never by title — the Markdown's one inherent loss beside the step ids
(the parity test `tests/test_md_parity.py` names every such field). Degrade tier 1 (§10)
renders **every** saved row one-line.

The `## Cooking history` section lists each cook as `### <startedAt> — <mealName>
(<status>)` — ending " (removed from history)" when the cook's `deleted` is true, after
the " — from earlier anonymous session …" suffix when both are present — with one line
per recipe: completed or not, "(not counted)" only when none of `isValid`, `userOverride`
and `status == "migrated"` holds, the ratings as "easy to follow 4/5, taste 5/5, would
cook again 5/5", and the feedback in quotes. A version-1 Markdown has no "(removed from
history)" and wrote "(not counted)" from `isValid` alone; a reader applies the cook's own
`migrated` status to such a line, as it does to a version-1 JSON row. A cook line carries
the recipe title only — no Fond id — so a reader attributes it by title only when exactly
one recipe in the export carries that title; a title two recipes share leaves the cook
unattributable (the JSON row's `id` resolves it).

**The cook line, exactly:** `- <title> — completed <completedAt>` or `- <title> — not
completed`, then ` (not counted)` when the row does not count, then `; <ratings>` ("no
rating" when none were given), then `; feedback: "<text>"` when there is feedback;
`<completedAt>` is an ISO 8601 timestamp (the renderer prints the Firestore timestamp's
`isoformat()`). The title is free text and may itself contain " — " (a recipe named
"Soup — Quick") or even the slot's own words (a recipe named "Soup — completed early;
feedback: fake"), and the feedback is written raw. So a reader cuts the line at a
structural slot — " — completed <ISO timestamp>" (a "completed" followed by anything
else, such as "early", is title text) or " — not completed" — from which the rest of the
line is exactly the renderer's tail: an optional " (not counted)", an optional "; " and
the ratings ("<label> <n>/5" items joined by ", ", or "no rating"; `<n>` may be a
decimal — "4.0", "4.5" — because the app stores ratings as doubles), an optional
`; feedback: "` and anything to the end of the line. Never at the first dash, which would
credit a cook of "Soup — Quick" to a recipe named "Soup"; never at the first
"completed", which would credit a cook of "Soup — completed early; feedback: fake" to
"Soup". When exactly one slot qualifies, the title is everything before it, and "(not
counted)" and the ratings are read from that slot's tail, never from the title or the
quoted feedback. When two or more qualify — a title or a feedback that spells out a whole
slot and tail — each names a different title, and the line is credited to no recipe (no
title, no completion, no rating; the reader warns, and the `history` header counts it as
credited to no recipe) rather than to a guess; the JSON row's
`id` resolves it. A line with no qualifying slot (a hand-edited row) is read whole as the
title. The renderer writes the feedback raw, so a feedback holding a line break splits the
cook line across physical lines: the first physical line still parses (its feedback slot
runs to the end of that line, closing quote or not), and the lines after an unclosed
feedback quote, up to and including the line that closes it, are never cook rows or cook
headings — not even one that starts with "- " (a feedback listing "- Garlic Bread"), spells
out a whole cook line, or is shaped like a `### <timestamp> — <meal> (<status>)` heading. A feedback whose own line ends in a quote mark can still end that run early;
the JSON row is unambiguous.

## 9. The legacy `nodes[]` schema

A node is one step of the recipe's dependency graph, as the app played it:

```json
{ "id": 7, "title": "Cook the pasta", "text": "Add the [spaghetti] to the boiling [water].",
  "time": 12, "until": "al dente", "dependencies": [2], "repeat": 2, "es": 0, "ls": 0 }
```

| Key | Type | Meaning |
|---|---|---|
| `id` | integer (occasionally a string) | the node's key within the recipe; **not positional** (§8, the ordinal rule); a missing id is patched with a safe generated one |
| `title` | string | the step's short name; `Prep:`-titled steps are mise en place (only one converter wrote that prefix); missing → `Step <position>` (the app itself showed "Untitled Step"; the skill numbers the step so two untitled steps stay distinguishable) |
| `text` | string | the instruction; `[bracketed]` phrases are the step's ingredient needs, emphasised when spoken, never given an invented quantity; missing → `""` |
| `time` | number or null | minutes — an integer or a float (`0.5` is thirty seconds); `null` and `0` mean no duration; **per-iteration** when `repeat` is present |
| `until` | string or null | the done-when cue; its presence is what makes a step a timer step (§9.1) |
| `dependencies` | array of node ids | the steps that must be resolved first; missing → `[]`; an unknown id is dropped; a cycle is refused with the steps named |
| `repeat` | integer, optional | iteration count (≥ 2 when present): a `× N` timer or `count=N` on the DSL atom this node was projected from collapsed into **one** node with `repeat`; `time` and `until` stay per-iteration and the projection appends "(×N)" to `until`. **The app ignores this key** (it reads `id`, `title`, `text`, `dependencies`, `time`, `until` only and plays one countdown); **the skill plays it** — `repeat` countdowns of `time` minutes, or hands-on `time × repeat` when there is no `until`, dropping the "(×N)" tag when it speaks the count |
| `es`, `ls` | numbers, optional | the converter's earliest/latest start; present on authored rows (full documents), dropped from version-2 saved rows; the skill ignores them and recomputes |

Authored rows carry the node documents in full, so keys beyond these may appear; a reader
ignores what it does not know. `nodes` is occasionally serialised as a JSON **string**
rather than an array; the reader parses it and builds the same graph.

### 9.1 The `until` / `time` rule

The app's own predicate, mirrored exactly:

| `until` | `time` | The step is | Spoken as |
|---|---|---|---|
| present | `> 0` | a **timer step** | "set a timer for N minutes — that is HH:MM — done when <until>"; with `repeat` R: R consecutive countdowns of N minutes |
| present | null or `0` | an **untimed cue** | the done-when text, no duration, no clock time (the app showed the timer icon whenever `until` was present, but there is nothing to count) |
| absent | `> 0` | **hands-on work** | "about N minutes, hands-on"; with `repeat` R: "about N × R minutes", no countdown |
| absent | null or `0` | instant | nothing |

A timer step is never resolved by the clock passing; the cook says when it is done. The
duration does not decide the classification (`time: 0.5` with `until` is a timer step).
The time-to-serve simulation counts `time`, or `time × repeat`, for each node.

## 10. Degrade tiers — what a large export loses, in order

The in-app export must fit a fixed size guard (5 MiB for JSON + Markdown together). When
a version-2 export is over it, the builder rebuilds in this order and stops at the first
tier that fits; the JSON key set never changes:

| Tier | Markdown | JSON |
|---|---|---|
| 0 | full | full |
| 1 | every saved recipe one line (no saved sections) | unchanged |
| 2 | as tier 1 | saved `dsl` → `null` |
| 3 | as tier 1 | saved `dsl` → `null`, saved `nodes` → `null` |
| — | still too large → the export is refused with a hint to request it by e-mail | |

A separate **latency tier** can fire first: when the build is running out of its time
budget, the saved `dsl` read is skipped (saved `dsl: null`) and saved rows render one line
— the shape of tiers 1+2 — while `nodes`, `ingredients`, `url` and `servings: null` still
ride because they come from documents already read. The size ladder may then still step
to tier 3.

What this means for a reader: a version-2 saved row with `nodes: null` and `dsl: null` is
**not cookable** (list it under "saved, no steps in this export", with its `url` offered on
request); a row with `nodes` but `dsl: null` cooks from `nodes`; the authored rows are never
degraded. The operator-run export batch (the e-mailed export) never degrades at all.

## 11. Quick checklist for a reader

- Unwrap `{json, markdown}` when present; require an integer `export_version`.
- Cookable = non-null, non-empty `nodes` or `dsl`, or a resolving `authoredRecipeRef`.
- `dsl` wins over `nodes` when both are present.
- Timer iff `until` present and `time > 0`; `repeat` multiplies countdowns, never sums them.
- `(after step k)` in the `.md` is an ordinal; `dependencies` in the `.json` are ids.
- By-line from the row's `authorHandle` (version-1 authored rows: `profile.handle`);
  `sourceAuthor` first when present; lineage line only when `lineage` is non-null.
- A cook counts when `deleted` is not true and its status is in
  `completed|recorded|rated|migrated`; a recipe row counts when `isValid`, `userOverride`
  or `status == "migrated"` holds (version 1: the cook's status stands in, no override).
- Never read `contact.*`, `profile.uid`, `profile.credits`, `profile.linkedAnonymousUids`,
  `linkedFromUid`; never fetch `url`, `handle` or `parentId` unasked.

## 12. Format drift

This reference matches the export builder as of October 2026 (version 1 shipped;
version 2 specified and being built as the service closed). The files you hold do not
change after the service ends, but a reader written against this reference should keep
treating unknown keys as ignorable and missing keys as absent rather than as errors.
