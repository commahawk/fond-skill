# Cook with Fond

Cooks a recipe step by step, the way the Fond app did — from the data export you took from
the app, or from a Fond-format recipe file it writes with you (your own words, a photo of a
card, a page you hand it). An early version, still in development — not a replacement for
the Fond app, but a way to keep cooking the recipes you have. An open skill for Claude, plus
a plain prompt for any other assistant (ChatGPT and Gemini instructions included).

From your export it cooks any recipe the way the app did: ingredient list and prep first,
one small step at a time, steps offered in the order the app offered them, a timer suggested
only where the recipe had one, the next free step while something simmers, and an estimate
of when you will eat. It also answers "what did I cook most" from the cooking history in the
same file.

It does not depend on Fond's servers. It reads your export file and nothing else. It
suggests timers and computes clock times ("set a timer for 12 minutes — that is 18:16 on
your clock"); it cannot ring one, so you set the timer on your phone.

It also writes new recipes in Fond's format from your words, a photo or a page you hand it,
labelled as composed, or makes a variant of a recipe in your export, with its credits; it
checks them against Fond's own rules and keeps them as files you own. And it builds an
offline player page for your browser, synced to the chat by one line you paste. With the
pasted prompt, any other assistant can only draft a recipe in Fond's format — an unchecked
block you keep; run `check` with the skill before cooking it.

Version 0.1.0 reads `export_version` 1 and 2.

## 1. Get your export

In the Fond app: **Settings > Export my data**. You receive two files, `fond-export-<date>.json`
and `fond-export-<date>.md`. The `.json` is the one the skill wants; the `.md` works with the
pasted prompt and as a fallback.

Before you share either file with anyone or any hosted assistant, read section 4.

## 2. Install

| Where | How |
|---|---|
| **claude.ai web and desktop** | Turn on Code execution and file creation under Settings > Capabilities, then Customize > Skills > + > Upload a skill and choose `cook-with-fond.zip` (from the Releases page or the download link on getfond.com/sunset#skill). On Team/Enterprise your owner may have disabled skill creation. Then attach your `.json` export to a chat and say "cook …". For a large export see the FAQ. |
| **Claude Code** | Clone the repository to a scratch folder and copy its `cook-with-fond/` folder into `~/.claude/skills/`, or unzip the release there. The skills folder must exist before the copy, or `cp` renames the folder into it: `mkdir -p ~/.claude/skills && git clone https://github.com/commahawk/fond-skill /tmp/fond-skill && cp -r /tmp/fond-skill/cook-with-fond ~/.claude/skills/` (with the zip: `mkdir -p ~/.claude/skills && unzip cook-with-fond.zip -d ~/.claude/skills`). Check that `~/.claude/skills/cook-with-fond/SKILL.md` exists (not `~/.claude/skills/SKILL.md`, and not `…/cook-with-fond/cook-with-fond/SKILL.md`). Skills synced from claude.ai land in `~/.claude/skills/synced/` and do not run shell commands in terminal sessions, so install locally. Then, in a session: "cook the aglio e olio from ~/Downloads/fond-export-2026-10-16.json". |
| **Claude API** | The same folder is the Agent Skills format the API's skills feature accepts; see Anthropic's documentation. Documented here, not tested for this release. |
| **ChatGPT** | In ChatGPT's Plugins, add a new plugin and upload `cook-with-fond-plugin.zip` from the Releases page: the same skill, packaged as a ChatGPT plugin. Tested on Pro (in ChatGPT's Work tab), 2026-10-16: it cooks in the chat as text; the player page is not shown there. Business, Enterprise and Edu: your admin may need to allow plugin uploads. Plus, Go and Free: untested — if the upload is refused, use Codex or the pasted prompt. |
| **Codex** (any ChatGPT plan: the ChatGPT desktop app or the Codex CLI) | Unzip `cook-with-fond.zip` into `~/.agents/skills` (`mkdir -p ~/.agents/skills && unzip cook-with-fond.zip -d ~/.agents/skills`), open Codex on a folder that holds your export, and type `$cook-with-fond` in the CLI or `@cook-with-fond` in the app. Needs Python 3.9 or newer on your computer. Documented by OpenAI; untested by us for this release. |
| **Other coding agents** (Gemini CLI, GitHub Copilot, VS Code, Cursor and others that read Agent Skills) | Copy the same `cook-with-fond/` folder into `~/.agents/skills` or the agent's own skills folder. Untested by us. |
| **Any other assistant** (Gemini — unverified — and any assistant without skills or plugins) | Open `cook-with-fond/prompts/paste-this-prompt.md` (the `prompts/` folder inside the skill), paste its text into a new chat and attach your `.md` export. If your assistant refuses the .md file, rename it to .txt — the content is plain text. The Gemini composer's `.md` attachment support and Gemini's skills are unverified for this release. The prompt drafts only: a recipe in Fond's format comes back as an unchecked block for you to keep and check with the skill. |

The release carries two zips: `cook-with-fond.zip` contains one top-level folder,
`cook-with-fond/`; `cook-with-fond-plugin.zip` holds that same folder, unchanged, under
`skills/cook-with-fond/`, beside a `plugin.json` for ChatGPT's plugin upload. Nothing needs
installing beyond Python 3, which the assistant's own environment provides: 3.8 or newer
for every command over an export, 3.9 or newer for `check`, `convert` and every `--dsl`
command (they load the Fond lint rules that ship inside the folder).

## 3. Use it

Say what you would have said to the app:

- "cook the Spaghetti Aglio e Olio" — the opening turn is the ingredient list, the prep
  steps, the time-to-serve estimate and "ready?"; then one step per turn.
- "next", "done", "what else can I do now?", "how long to go?", "stop"
- "what's in my export", "show me the lentil soup"
- "what did I cook most", "what should I cook again"
- "make it for six" — scaled quantities as a labelled variant; the original stays as written
- "strip my export" — a recipes-only copy to share (see section 4)
- "write this up in Fond's format" — from your words, a photo of a card or a cookbook page, or
  one page you hand it: a local recipe file, composed or transcribed by the assistant, checked
  against Fond's own rules, yours to keep. It never writes a named creator's recipe from memory
  and never fetches a page you did not hand it.
- "make a variant", "add a timer to the simmer", "split the sear" — a local variant of a recipe
  in your export, derived from it with that recipe's author and credits in the file; the export
  itself is never changed. When a recipe's Fond-format steps carry no timers, the assistant
  offers once to add the app's timers as a local variant.
- "build the player" — a self-contained page in your browser that plays the recipe the way the
  chat does: tap a step, watch the countdown, paste one line back into the chat to pick up
  where you left off. In claude.ai it opens on its own when you start cooking; in Claude Code,
  ask for it.

From a terminal, the script works on its own:

```
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json list
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json plan "Aglio e Olio"
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json missing
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json history
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json cook-again
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json scale "Aglio e Olio" --from 4 --to 6
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json strip
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json convert "Aglio e Olio" --made-on 2026-10-17
python3 cook-with-fond/scripts/fond_export.py fond-recipes/aglio-e-olio.recipe.md check --parent fond-export-2026-10-16.json
python3 cook-with-fond/scripts/fond_export.py fond-recipes/aglio-e-olio.recipe.md --dsl plan --parent fond-export-2026-10-16.json
python3 cook-with-fond/scripts/fond_export.py fond-export-2026-10-16.json player "Aglio e Olio"
```

`strip` writes `fond-export-2026-10-16-stripped.json` next to the original (or where
`--out` says) and never overwrites it; `show "<title>"` prints one recipe; `--json` on any
command prints the same answer as JSON. The `.md` export works with `--md` for `list`,
`show`, `plan`, `missing` and `history`.

The four recipe-file commands: `convert "<title>"` prints a variant draft of a recipe in your
export — its author, source and credits copied from the export into the file, never typed —
and writes `<slug>.recipe.md` only when the draft passes the check; `check` runs Fond's own
lint rules over a recipe file and refuses one that fails them, so nothing with a finding is
kept or cooked; `--dsl` cooks from a recipe file (or a folder of them) instead of the export;
`player` builds `<slug>.player.html`, a self-contained page. Each writes only the file you
asked for, to a new path (the player rebuilds its own page in place), and never the export.

**Your recipe files.** A recipe the assistant writes is one plain-text `<slug>.recipe.md` with
its provenance at the top — composed by the assistant from the source you handed it, a local
variant of a recipe in your export with that recipe's author and credits, or transcribed from
your own words. In Claude Code it lives in a folder you name (we suggest `fond-recipes/` beside
the export); in claude.ai the assistant hands the file back as a download — re-attach it, or add
it to a Project, next time (on a phone the download is unverified for this release). It is never
a Fond recipe, never in a Fond library and entered in no registry: Fond's servers close on
2026-10-29, and the file is what you keep.

**The player page.** In Claude Code the page is written beside the recipe file and you open it
in your browser; in claude.ai the assistant publishes it as a private artifact on your own
account when you start cooking, beside the chat, and republishes it after an edit. It shows a
countdown while it is open and cannot ring
when the page is closed, so set a phone or kitchen timer too. Built for a desktop browser; on a
phone it is unverified for this release.

A fresh clone runs the sample: `python3 cook-with-fond/scripts/fond_export.py
cook-with-fond/fixtures/sample-export.json plan "<a title from list>"` prints the
ingredient list, the waves and the time-to-serve estimate with no installation step.

What you get depends on the file, not on how it reached you: run `list` — its first line
prints the `export_version`. A version-1 export makes the recipes you created cookable and
lists the recipes you saved by title and author only. If your export says `export_version:
2`, saved recipes are cookable too, with the author's handle and source on each.

## 4. Privacy

The skill never reads the Contact section of your export, never fetches anything unasked
and never uploads anything itself.

**The skill never uploads your file. In Claude Code the file stays on disk and only the
recipe you are cooking (and the listing) is sent to the assistant, like any message; in
claude.ai, ChatGPT or Gemini the file you attach is handled under that provider's terms — and
so are a recipe file the skill hands back to you, a player page published as a private
artifact and any `FOND1` line you paste into the chat. The skill writes the file and sends
nothing.**

Your export and its Markdown contain your e-mail, name and phone number (the `contact`
block in the `.json`, the `## Contact` block in the `.md`). Remove them before uploading:

- with the script: `python3 cook-with-fond/scripts/fond_export.py fond-export-<date>.json
  strip` writes a recipes-only copy, `fond-export-<date>-stripped.json`, with no `contact`
  and no `profile` block; or
- without Python: open the `.md` in any text editor, delete everything from the line
  `## Contact` down to the next `##` heading, and save. For the `.json`, delete the
  `"contact": { … },` block.

The recipes keep their author handle, Fond id, source URL and lineage in either copy, so a
shared file still says who created each recipe.

## 5. FAQ

**The zip will not upload to claude.ai.** Check that Code execution and file creation are on
under Settings > Capabilities, and that the zip has one top-level folder, `cook-with-fond/`,
with `SKILL.md` directly inside it. On Team/Enterprise an owner may have disabled skill
uploads; ask them, or use Claude Code.

**Which plans?** claude.ai skills are listed by Anthropic for Free, Pro, Max, Team and
Enterprise. In ChatGPT the plugin upload was tested on Pro, in the Work tab; on Business, Enterprise and Edu
it depends on your admin; Plus, Go and Free are untested, and Codex is included in every
ChatGPT plan. Gemini is unverified for this release.

**"It does not see my file."** In claude.ai attach the `.json` to the chat where you ask to
cook; in Claude Code name the path. The skill only ever runs the script against the file
you name, so if the script was never run, say "use the cook-with-fond skill on
<file>".

**My export is large and the chat refuses it.** Three paths: Claude Code (the file stays on
disk and only one recipe at a time enters the conversation); a claude.ai Project with the
file added as project knowledge; or shrink the file first with `strip`, which also removes
your contact details.

**My assistant refuses the .md file.** Rename it to .txt; the content is plain text.

**Will it keep up with Fond's export format?** This version reads `export_version` 1 and 2,
the only two the app ever produced. A file with a higher `export_version` is not refused:
the script warns ("newer than this skill knows"), reads it as version 2 and ignores the
fields it does not know, so what it prints is best-effort. A file with no integer
`export_version` is refused as not a Fond export. Nothing here promises against future
format drift.

**Does it ring timers?** No. It suggests a timer and gives you the clock time; you set it on
a phone or kitchen timer. It never marks a step done on its own.

**Did my saved recipes come along?** In a version-2 export, yes — ingredients, steps and
timings where the recipe had them, with the author's handle and source. In a version-1
export only the recipes you created have steps; saved recipes are listed by title and
author ("saved, no steps in this export").

**Can it fetch a recipe's source page?** Only if you ask. It never crawls or fetches on its
own, and the Fond web addresses close with the service.

**Is a recipe it wrote a Fond recipe now?** No. It is a local file you keep, labelled composed,
a local variant or transcribed, checked against Fond's rules and entered nowhere; the Fond
recipe your variant derives from is named in the file, with its author and credits.

**Which Python do the recipe-file commands need?** 3.9 or newer for `check`, `convert` and
every `--dsl` command (they load the Fond lint rules that ship inside the folder); every
command over an export, the player included, runs on 3.8 or newer.

## 6. Support and licence

Offered as-is, free and open source (MIT). Questions go to GitHub Issues on
`github.com/commahawk/fond-skill`; there is no support.

- Code and instruction text: MIT, Copyright (c) 2026 Deglaze Corp. — see `LICENSE`.
- `references/dsl-spec.md` (the Fond DSL specification §1-§8): CC BY 4.0, "Fond DSL, © 2026
  Deglaze Corp." — see `LICENSE-SPEC`.

The fixtures under `fixtures/` are synthetic: invented titles, handles and ids, empty
contact values. No real export is in this repository.
