#!/usr/bin/env python3
# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""fond_export.py — read a Fond data export and cook from it, offline.

Imports only the standard library and its own vendored copies under `scripts/fond_dsl/`
(drift-tested against the reference implementation in fond-mono); nothing in this folder
reads the environment, opens a socket or reads a clock. The assistant runs this script so
that only the listing and the one recipe being cooked enter the conversation, never the
whole file.

The write rule: the script writes only the files the user asks for — `strip --out`,
`check --out`, `convert --out`, `player --out` — each recipe file to a NEW path (an
existing path is refused: "`<path>` exists; pass --out <other> or edit that file") whose
basename is a local id (`check` and `convert` refuse any other `--out` name before the
draft is read, so no file lands under a name `check` would refuse as a file) and shares
that basename with no recipe file already in its folder (the collision line, exit 1,
nothing written: both would be the one `local:<basename>`), and the
player's own marked page rebuilt in place (its first line is the page's marker
comment carrying the same `id=`; a marked page for another id, and any other existing
file, is refused). The export is never written; no remote store, no telemetry. Every
write goes through `_write_new`.

    python3 fond_export.py <export.json> list
    python3 fond_export.py <export.json> show "<title>"
    python3 fond_export.py <export.json> plan "<title>"
    python3 fond_export.py <export.json> plan "<title>" --done <id>[,<id>…]
    python3 fond_export.py <export.json> plan "<title>" --done <ids> --running <id>=<minutes-left>[,…] [--h <8hex>]
    python3 fond_export.py <export.json> missing
    python3 fond_export.py <export.json> strip [--out <path>]
    python3 fond_export.py <export.json> history ["<title>"]
    python3 fond_export.py <export.json> cook-again
    python3 fond_export.py <export.json> scale "<title>" --from <servings> --to <servings>   (or --factor F)
    python3 fond_export.py <export.md> --md list | show "<title>" | plan "<title>" | missing | history
    python3 fond_export.py <export.json> convert "<title>" [--made-on YYYY-MM-DD] [--out <path> | --out -]
    python3 fond_export.py <file.recipe.md | -> check [--parent <export>] [--json] [--out <path>]
    python3 fond_export.py <file.recipe.md | folder> --dsl list | show ["<title>"] | plan ["<title>"] [--done … --running … --h …] | scale … [--parent <export>]
    python3 fond_export.py <export.json> player ["<title>"] [--out <path> | --out -]
    python3 fond_export.py <file.recipe.md | folder> --dsl player ["<title>"] [--out <path> | --out -] [--parent <export>]

`player` builds one self-contained page from `scripts/player.template.html` — `<slug>.player.html`
beside the export or the recipe file, `fond-player.html` for a whole export or folder — whose
engine matches `plan` state for state and whose FOND1 line carries `h=`; `--out -` prints the
page (the claude.ai artifact is published from it). Nothing in the page is fetched or sent.

`--json` prints the same answer as a JSON object (for tests and tooling). A title may
also be the recipe's Fond `id` or `handle` (or a local file's `local:<slug>`). Exit codes:
0 ok, 1 refused (not an export, cycle, no steps, a gated `check` finding, an existing
path, the Python 3.9 floor), 2 ambiguous title or bad arguments (`check` on a variant
without `--parent` among them).

Local recipe files (recipe-authoring): `check`, `convert` and every `--dsl` command import
the vendored lint lazily and need Python 3.9; every command over an export runs on 3.8.
`convert` fills the envelope from the row and never types a handle; `--made-on` (optional) is
today's date from the conversation, since the script reads no clock — without it the draft's
`made_on:` is empty and `check` reports it as the one value to fill; it takes no `--from` (one
verb: the row's Fond-format steps when the export carries them, else the app's steps). `--parent <export>` supplies
a variant's parent row: REQUIRED by `check` (the write boundary), taken and never
required by the read commands (`--dsl list|show|plan|scale`), which print rule U and V
"(not gated without --parent — pass it to gate edits)" without it. The FOND1 line's `h=`
is `sha256(body)[:8]` (`plan --h` refuses a stale one).

Semantics (cook-playback and fond-export-format specs, OpenSpec change
cook-with-fond-skill):
  * graph from `dsl` when present, else legacy `nodes[]` (nodes-as-string tolerated,
    missing id/title/text/dependencies patched); a cycle is refused by name;
  * legacy timer step  iff  `until` present AND `time > 0`; `until` with time 0/null is a
    cue; `time > 0` without `until` is hands-on; `repeat` = consecutive countdowns of
    `time` (per-iteration), or hands-on `time × repeat` without `until`;
  * DSL timer step  iff  the atom carries a `~timer{}` sigil, read as structure (segments
    in sequence, `× N` repeats, `count=` iterations); `attention_level` sets occupancy
    only (none/low parallel, else hands-on); scheduled length = max(duration, timer
    total) × count, the per-iteration surplus over the sigil total reported for the "more
    minutes" line, which lands after every iteration's last ring (count × (timer + surplus));
  * available steps ordered by latest start time from the backward pass (ties: timer,
    then Prep:, then dependency-free, then node order); waves are the mise-en-place
    grouping only; one-cook simulation for the time-to-serve estimate;
  * `--done` and `--running` ids resolve their whole prerequisite chain (transitive: for
    A → B → C → D, `--done C` resolves A and B too) before availability, the backward
    pass and the simulation; a running id still needs its direct prerequisites in
    `--done`, and a running id that a `--done` id depends on is refused;
  * provenance from the row itself — "by you" only beside a matching `profile.handle`;
    the lineage line only when `lineage` is non-null; never the string "None"; a Markdown
    row with no `Fond id` line prints none (a lookup key is kept privately, never shown);
  * a running step that occupies the cook (a DSL timer atom at medium/high/full/unset
    attention, or hands-on work under way) holds back the other hands-on steps until it
    is resolved; legacy timers and none/low atoms hold nothing back;
  * `contact`, `profile.uid`, `profile.credits`, `profile.linkedAnonymousUids` and every
    `linkedFromUid` are never read.
"""

import argparse
import difflib
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

SUPPORTED_VERSIONS = (1, 2)
# The app's own counting rule (fond-export-format "Cook rows carry the app's own counting
# flags"): a cook counts when its status is one of these and its `deleted` is not true (the
# client's history list hides a cook the user removed); `migrated` rows are pre-Flutter
# cooks that carry at most `easyFollow` and count for frequency and recency only. Within a
# cook a recipe row counts when `isValid`, `userOverride` or `status == "migrated"` holds —
# see cook_recipe_counted().
COUNTED_COOK_STATUSES = ("completed", "recorded", "rated", "migrated")
ATTENTION_SHARE = {"none": 0.0, "low": 0.0, "medium": 0.5, "high": 0.8, "full": 1.0}
NOT_AN_EXPORT = (
    "This file is not a Fond data export: it has no integer `export_version`. "
    "Export my data in the Fond app (Settings > Export my data) writes "
    "fond-export-<date>.json and fond-export-<date>.md — pass one of those."
)
CANNOT_RING = "The assistant cannot ring a timer: set each countdown on a phone or kitchen timer and say when it rings."
EPS = 1e-9


class ExportError(Exception):
    """Refusals that end the command (exit 1 unless `code` says otherwise)."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class CycleDetected(ExportError):
    pass


# ---------------------------------------------------------------------------
# The vendored lint closure (scripts/fond_dsl/) — Python 3.9, imported lazily
# ---------------------------------------------------------------------------

LINT_FLOOR = (3, 9)


def _import_fond_dsl():
    """Import `scripts/fond_dsl/` beside this script, lazily, on the Python 3.9 floor.

    Only `check`, `convert` and the commands run with `--dsl` run the gate and call this;
    no command over an export does, so those keep Python 3.8 (recipe-authoring "`check`
    gates keeping and cooking"; skill-distribution "Agent Skills folder"). The package's
    `dsl.py` needs `graphlib` (3.9+). `-I` drops the script's folder from `sys.path`, so
    it is inserted first; no `__pycache__` is written into the user's skill folder. Below
    the floor the command is refused (exit 1) with one line that says every command over
    an export still works; an import failure at or above the floor is its own refusal,
    never dressed as the floor.
    """
    folder = str(Path(__file__).resolve().parent)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    sys.dont_write_bytecode = True
    version = ".".join(str(part) for part in sys.version_info[:3])
    if tuple(sys.version_info[:2]) < LINT_FLOOR:
        raise ExportError(f"Local recipe files need Python 3.9 or newer (this interpreter is {version}); "
                          "every command over an export still works", 1)
    try:
        import fond_dsl.dsl  # `graphlib` is imported here
        import fond_dsl.gate
    except ImportError as e:
        raise ExportError(f"The vendored lint (scripts/fond_dsl/) failed to import on Python {version}: {e}; "
                          "every command over an export still works", 1)
    return fond_dsl


def _import_nodes_to_dsl():
    """`scripts/nodes_to_dsl.py` beside this script — the transliteration `convert` applies
    to a nodes-only row (recipe-authoring "`convert` is a labelled, deterministic draft").
    Imported after `_import_fond_dsl`, which put the folder on `sys.path`: every caller
    runs the gate over the draft, so the floor is the same."""
    _import_fond_dsl()
    import nodes_to_dsl
    return nodes_to_dsl


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _s(value: Any) -> str:
    """Display any value without ever printing the word None."""
    if value is None:
        return "(unknown)"
    return str(value)


def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return max(0.0, f)


def _to_int(value: Any, default: int = 1) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def fmt_minutes(minutes: float) -> str:
    """0.5 → '30 seconds'; 12 → '12 min'; 1.5 → '1.5 min'; 90 → '1 hr 30 min'; 1080 → '18 hr'."""
    if minutes <= 0:
        return "0 min"
    if minutes < 1:
        return f"{int(round(minutes * 60))} seconds"
    if abs(minutes - round(minutes)) < 1e-6:
        whole = int(round(minutes))
        if whole >= 60:
            hours, rest = divmod(whole, 60)
            return f"{hours} hr" if rest == 0 else f"{hours} hr {rest} min"
        return f"{whole} min"
    return f"{minutes:g} min"


def fmt_whole(minutes: float) -> str:
    """For estimates: whole minutes, rounded up like the live client."""
    return f"{int(math.ceil(minutes - EPS))} min"


def host_of(url: Any) -> Optional[str]:
    if not isinstance(url, str):
        return None
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url.strip())
    if not m:
        return None
    host = m.group(1).lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    host = host.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", "-", s.strip())


def _humanize(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ")


BRACKET = re.compile(r"\[([^\[\]]+)\]")


def bracketed_needs(text: str) -> List[str]:
    """The `[bracketed]` phrases of a step: what the step needs, never with an invented amount."""
    out: List[str] = []
    for m in BRACKET.finditer(text or ""):
        phrase = m.group(1).strip()
        if phrase and phrase not in out:
            out.append(phrase)
    return out


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


def label_text(title: Any) -> str:
    """A row's display title: the title when it is a non-blank string, else "(untitled)" —
    a title-less row (a saved recipe that no longer exists) never prints as "None"."""
    return title if isinstance(title, str) and title.strip() else "(untitled)"


@dataclass
class Recipe:
    kind: str  # "authored" | "saved" | "local" (a recipe file read with --dsl or check)
    row: Dict[str, Any]
    id: Optional[str] = None
    handle: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    author_handle: Optional[str] = None
    has_author_key: bool = True
    source_author: Optional[str] = None
    lineage: Optional[Dict[str, Any]] = None
    ingredients: List[str] = field(default_factory=list)
    nodes: Any = None
    dsl: Optional[str] = None
    ref: Optional[str] = None
    saved_at: Optional[str] = None
    cook_count_field: int = 0
    deleted: bool = False
    md_steps: Optional[List[Dict[str, Any]]] = None
    md_legacy: bool = False
    # A lookup key for a Markdown row that carries no `Fond id` line: used for dedupe,
    # history and reference resolution only, never printed — provenance is never invented.
    key_hint: Optional[str] = None
    # A local recipe file (kind "local"): the whole file, the body after the envelope (what
    # `dsl` holds too), the envelope as the strict reader read it, where it came from, and
    # what the reader refused or warned about (reported by `check` and the --dsl gate).
    text: Optional[str] = None
    body: Optional[str] = None
    envelope: Optional[Dict[str, Any]] = None
    local_path: Optional[str] = None
    envelope_errors: List[str] = field(default_factory=list)
    envelope_warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)  # the gate's informational lines (U/V, the floor)

    @property
    def key(self) -> str:
        return self.id if self.id else (self.key_hint or f"row-{id(self)}")

    @property
    def label(self) -> str:
        return label_text(self.title)

    @property
    def origin(self) -> Optional[str]:
        """A local file's `lineage.origin` (composed | variant | transcribed), else None."""
        lineage = (self.envelope or {}).get("lineage")
        origin = lineage.get("origin") if isinstance(lineage, dict) else None
        return origin if isinstance(origin, str) else None

    @property
    def local_slug(self) -> str:
        return self.id[len("local:"):] if self.id and self.id.startswith("local:") else ""


@dataclass
class Export:
    version: int
    exported_at: Optional[str]
    profile_handle: Optional[str]
    has_profile: bool
    authored: List[Recipe]
    saved: List[Recipe]
    cooks: List[Dict[str, Any]]
    raw: Dict[str, Any]
    from_markdown: bool = False
    payload: bool = False
    warnings: List[str] = field(default_factory=list)
    # A library (`--dsl`): the local files as `authored`, the folder or file they came from,
    # and the parent export `--parent` named (its rows supply a variant's `Derived from:`
    # by-line, the cross-check and the U/V baseline).
    local: bool = False
    local_root: Optional[str] = None
    parent: Optional["Export"] = None

    @property
    def authored_by_key(self) -> Dict[str, Recipe]:
        return {r.key: r for r in self.authored}

    def content_of(self, recipe: Recipe) -> Optional[Recipe]:
        """The recipe that carries the steps: the row itself, or the authored recipe an
        `authoredRecipeRef` points to. A version-1 saved row whose id is in the authored
        set (the user's own recipe, saved) folds into that authored recipe too: its steps
        are in the export, so it is listed once, as the authored recipe, never as "saved,
        no steps" (references/export-format.md §5)."""
        by_key = self.authored_by_key
        if recipe.kind == "saved":
            if recipe.ref:
                return by_key.get(recipe.ref)
            if recipe.id and recipe.id in by_key:
                return by_key[recipe.id]
        return recipe

    def all_recipes(self) -> List[Recipe]:
        return list(self.authored) + list(self.saved)


def _ingredient_text(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("text", "original", "name"):
            if item.get(key):
                return str(item[key])
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def parse_nodes(nodes: Any) -> Tuple[List[Any], Optional[str]]:
    """`nodes` as a list, a JSON string of a list, a dict of nodes, or nothing.
    Returns (list, warning)."""
    if nodes is None:
        return [], None
    if isinstance(nodes, str):
        text = nodes.strip()
        if not text:
            return [], None
        try:
            parsed = json.loads(text)
        except ValueError:
            return [], "the `nodes` field is a string that is not JSON; treated as no steps"
        return parse_nodes(parsed)
    if isinstance(nodes, dict):
        return list(nodes.values()), None
    if isinstance(nodes, list):
        return nodes, None
    return [], f"the `nodes` field has an unexpected type ({type(nodes).__name__}); treated as no steps"


def has_steps(recipe: Optional[Recipe]) -> bool:
    if recipe is None:
        return False
    if isinstance(recipe.dsl, str) and recipe.dsl.strip():
        return True
    nodes, _ = parse_nodes(recipe.nodes)
    if nodes:
        return True
    return bool(recipe.md_steps)


def _recipe_from_row(row: Dict[str, Any], kind: str) -> Recipe:
    lineage = row.get("lineage")
    ingredients_raw = row.get("ingredients")
    ingredients = [_ingredient_text(i) for i in ingredients_raw] if isinstance(ingredients_raw, list) else []
    return Recipe(
        kind=kind,
        row=row,
        id=str(row["id"]) if row.get("id") is not None else None,
        handle=row.get("handle") if isinstance(row.get("handle"), str) else None,
        title=row.get("title") if isinstance(row.get("title"), str) else None,
        url=row.get("url") if isinstance(row.get("url"), str) and row.get("url").strip() else None,
        author_handle=row.get("authorHandle") if isinstance(row.get("authorHandle"), str) else None,
        has_author_key="authorHandle" in row,
        source_author=row.get("sourceAuthor") if isinstance(row.get("sourceAuthor"), str) and row.get("sourceAuthor").strip() else None,
        lineage=lineage if isinstance(lineage, dict) else None,
        ingredients=ingredients,
        nodes=row.get("nodes"),
        dsl=row.get("dsl") if isinstance(row.get("dsl"), str) and row.get("dsl").strip() else None,
        ref=str(row["authoredRecipeRef"]) if row.get("authoredRecipeRef") is not None else None,
        saved_at=row.get("savedAt") if isinstance(row.get("savedAt"), str) else None,
        cook_count_field=_to_int(row.get("cookCount"), 0),
        deleted=bool(row.get("deleted", False)),
    )


# ---------------------------------------------------------------------------
# Loading the JSON export
# ---------------------------------------------------------------------------


def unwrap_payload(data: Any) -> Tuple[Any, bool]:
    """The raw callable payload `{json, markdown}` → its JSON half."""
    if isinstance(data, dict) and "json" in data and set(data.keys()) <= {"json", "markdown"}:
        inner = data["json"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                raise ExportError(NOT_AN_EXPORT)
        return inner, True
    return data, False


def check_version(value: Any, warnings: List[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        else:
            raise ExportError(NOT_AN_EXPORT)
    if value > max(SUPPORTED_VERSIONS):
        warnings.append(
            f"export_version {value} is newer than this skill knows ({', '.join(str(v) for v in SUPPORTED_VERSIONS)}); "
            "reading it as version 2 — fields this version does not know are ignored."
        )
    elif value < 1:
        raise ExportError(NOT_AN_EXPORT)
    return value


def load_json_export(path: Path) -> Export:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as e:
        raise ExportError(f"Cannot read {path}: {e.strerror or e}")
    except ValueError:
        raise ExportError(f"{path.name} is not valid JSON. " + NOT_AN_EXPORT)
    data, payload = unwrap_payload(data)
    if not isinstance(data, dict):
        raise ExportError(NOT_AN_EXPORT)
    warnings: List[str] = []
    version = check_version(data.get("export_version"), warnings)
    profile = data.get("profile")
    has_profile = isinstance(profile, dict)
    # The only profile field this script ever reads is the public handle.
    profile_handle = profile.get("handle") if has_profile and isinstance(profile.get("handle"), str) else None
    authored = [_recipe_from_row(r, "authored") for r in data.get("authoredRecipes") or [] if isinstance(r, dict)]
    saved = [_recipe_from_row(r, "saved") for r in data.get("savedRecipes") or [] if isinstance(r, dict)]
    cooks = [c for c in data.get("cooks") or [] if isinstance(c, dict)]
    return Export(
        version=version,
        exported_at=data.get("exportedAt") if isinstance(data.get("exportedAt"), str) else None,
        profile_handle=profile_handle,
        has_profile=has_profile,
        authored=authored,
        saved=saved,
        cooks=cooks,
        raw=data,
        payload=payload,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Loading the Markdown export (`--md`)
# ---------------------------------------------------------------------------

_MD_VERSION = re.compile(r"export version\s+(\d+)", re.IGNORECASE)
# The header line `Exported <ts> · export version N`: the timestamp the JSON carries as
# `exportedAt` (read from the lines before the first `## ` block).
_MD_EXPORTED = re.compile(r"^Exported\s+(\S+)\s+·", re.IGNORECASE)
_MD_STEP = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_MD_AFTER = re.compile(r"\(after steps?\s+([^)]*)\)\s*$", re.IGNORECASE)
_MD_TIMER = re.compile(
    r"Timer:\s*(\d+(?:\.\d+)?)\s*min(?:\s*[×x]\s*(\d+))?\s*[—–-]+\s*done when\s*(.*)$", re.IGNORECASE)
_MD_TIMER_SEC = re.compile(
    r"Timer:\s*(\d+)\s*sec(?:onds?)?\s*[—–-]+\s*done when\s*(.*)$", re.IGNORECASE)
_MD_CUE = re.compile(r"Done when:\s*(.*)$", re.IGNORECASE)
# The shipped renderer (user_export._step_lines) brackets a step's timing: `k. <title> —
# <text> [Timer: N min[ × R] — done when <until>] (after step i)`, `[Done when: <until>]`,
# `[~N min[ × R]]`, `[~N sec]`. _MD_TIMING_OPEN finds the LAST timing-shaped opening bracket
# (an `until` may itself hold "[…]"); _MD_TIMING_BODY must then match the bracket's WHOLE
# content, so an ingredient bracket on an untimed step (`[~2 cups stock]`, `[~1 cup water]`)
# is a need that stays in the text, never a timing.
_MD_TIMING_OPEN = re.compile(r"\s\[(?=Timer:|Done when:|~\s*\d)", re.IGNORECASE)
_MD_TIMING_BODY = re.compile(
    r"(?:Timer:\s*\d+(?:\.\d+)?\s*(?:min|sec(?:onds?)?)(?:\s*[×x]\s*\d+)?\s*[—–-]+\s*done when\s.*"
    r"|Done when:\s*.*"
    r"|~\s*\d+(?:\.\d+)?\s*min(?:\s*[×x]\s*\d+)?"
    r"|~\s*\d+\s*sec(?:onds?)?)", re.IGNORECASE | re.DOTALL)
# A one-line saved row by its strict shape — `- **<title>**[ by @<handle>] — saved <ts>…` —
# the only `- **…**` line that may follow a full section in the saved block (user_export
# _saved_line); a section's own `- **Saved:** <ts>` bullet carries no " — saved " slot.
_MD_SAVED_ONELINE = re.compile(r"^-\s+\*\*.+?\*\*(?:\s+by\s+@\S+)?\s+[—–-]+\s+saved\s")
# The shipped by-line with a source author: `by <sourceAuthor> · on Fond by @<handle>` (or
# `· on Fond by (unknown)` for a null handle, user_export._by_line).
# Split at the LAST ` · on Fond by ` — the structural delimiter the renderer appends after
# the source author, which may itself contain those words: a greedy head takes everything
# before the final delimiter.
_MD_ON_FOND = re.compile(r"^(.*)\s+·\s+on Fond\s+(by\s+.*)$", re.IGNORECASE)
_MD_HANDS = re.compile(r"(?:^|\s)~\s*(\d+(?:\.\d+)?)\s*min(?:\s*[×x]\s*(\d+))?\b", re.IGNORECASE)
_MD_HANDS_SEC = re.compile(r"(?:^|\s)~\s*(\d+)\s*sec(?:onds?)?\b", re.IGNORECASE)
_MD_FOND_ID = re.compile(r"Fond id[:*\s]+`?([^\s`(]+)`?(?:\s*\(handle\s+`?([^)`\s]+)`?\))?", re.IGNORECASE)
# The one-line `authoredRecipeRef` row's tail, `… under Recipes you created (Fond id <id>)`
# (user_export._saved_line): the id of the authored recipe the row is a save of.
_MD_REF_ID = re.compile(r"\(Fond id\s+([^\s()]+)\)\s*$", re.IGNORECASE)
_MD_KV = re.compile(r"^\s*-\s*\*\*([^*]+):\*\*\s*(.*)$")
_MD_BYLINE = re.compile(r"^\s*(?:-\s*)?(?:\*\*)?by\s+(.+?)(?:\*\*)?\s*$", re.IGNORECASE)
_MD_BY_HANDLE = re.compile(r"\bby\s+(?:you\s+\()?@([A-Za-z0-9_.-]+)\)?", re.IGNORECASE)
_MD_BY_UNKNOWN = re.compile(r"\bby\s+\(unknown\)", re.IGNORECASE)
_MD_SAVED_LINE = re.compile(r"^\s*-\s*\*\*(.+?)\*\*(.*)$")
# `### <startedAt> — <mealName> (<status>)`, which may be followed by the renderer's
# " — from earlier anonymous session <uid>" suffix, which is matched but never captured
# (`linkedFromUid` is never read), and — for a cook the user removed — ending with
# " (removed from history)" (group 4; the version-2 renderer prints it after the session
# suffix, and either order is accepted). A meal name may itself contain parentheses.
_MD_COOK_HEAD = re.compile(
    r"^###\s+(\S+)\s+[—–-]+\s+(.*?)\s*\(([^()\s]+)\)"
    r"(?:\s*\(removed from history\))?"
    r"(?:\s*[—–-]+\s*from earlier anonymous session\b.*?)?"
    r"(\s*\(removed from history\))?\s*$")
_MD_COOK_REMOVED = "(removed from history)"
# A rating is "<label> <n>/5"; the app stores ratings as doubles (the review screen
# writes `starIndex + 1.0`), so the renderer prints "taste 4.0/5" as often as "taste 4/5".
_MD_RATING = re.compile(r"(easy to follow|taste|would cook again)\s+(\d+(?:\.\d+)?)/5", re.IGNORECASE)
# A cook line is `- <title> — completed <ts>|not completed[ (not counted)]; <ratings>[;
# feedback: "<text>"]` — the renderer's one form in both versions. The title is free text
# and may itself hold " — " ("Soup — Quick"), and even the slot's own words ("Soup —
# completed early; feedback: fake"), so the line is never cut at the first dash nor at the
# first "completed": every place a structural slot could start is tried, and a slot counts
# only when its timestamp is an ISO 8601 timestamp (the renderer's `isoformat()`; "early"
# is no timestamp) — or it reads "not completed" — and the rest of the line, from the slot
# to its end, is exactly the renderer's tail: " (not counted)" if present, then
# "; " + ratings (each "<label> <n>/5", comma-separated, or "no rating") if present, then
# "; feedback: \"" + anything if present. One reading cuts the line there. Two or more readings —
# a title that spells out a whole slot and tail, or a feedback that does — name two
# different titles, and the line is credited to neither (_md_cooks). Ratings and
# "(not counted)" are read from their own slots only, never from the title or feedback.
# The feedback slot (group "fb") runs to the end of the physical line without requiring
# its closing quote: the renderer writes the feedback raw, so a feedback holding a line
# break splits the cook line, and the first physical line must still parse. The lines
# after an unclosed feedback quote, up to and including the line that closes it, are
# feedback text and never cook rows — even one that starts with "- " (a feedback listing
# "- Garlic Bread") or spells out a whole cook line (_md_cooks).
_MD_ISO_TS = r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?)?(?:Z|[+-]\d{2}(?::?\d{2})?)?"
_MD_RATING_ITEM = r"(?i:easy to follow|taste|would cook again)\s+[^\s,;/]+/5"
_MD_COOK_SLOT = re.compile(
    r"\s+[—–-]+\s+(?:completed\s+(?P<ts>" + _MD_ISO_TS + r")|not completed)"
    r"(?P<nc>\s*\(not counted\))?"
    r"(?:;\s*(?P<ratings>(?i:no rating)|" + _MD_RATING_ITEM + r"(?:\s*,\s*" + _MD_RATING_ITEM + r")*))?"
    r"(?P<fb>;\s*feedback:\s*\".*)?\s*$")
_MD_WS_RUN = re.compile(r"\s+")


def _md_cook_readings(body: str) -> List[Tuple[str, Any]]:
    """Every (title, slot match) reading of a cook line's body: one per whitespace run
    where `_MD_COOK_SLOT` matches through to the end of the line."""
    readings = []
    for ws in _MD_WS_RUN.finditer(body):
        slot = _MD_COOK_SLOT.match(body, ws.start())
        if slot:
            readings.append((body[:ws.start()].strip(), slot))
    return readings


def _md_feedback_left_open(slot: Any) -> bool:
    """A cook-line reading whose feedback slot opens a quote the physical line does not
    close: the text after the opening quote does not end in `"` (a feedback that begins
    with a line break leaves the opening quote as the line's last character)."""
    fb = slot.group("fb")
    if fb is None:
        return False
    return not fb[fb.index('"') + 1:].rstrip().endswith('"')


def _md_sections(block: List[str]) -> List[List[str]]:
    """Split a block on `### ` headings, never inside a ``` fence (a DSL fence carries
    `## ` atom headers of its own)."""
    sections: List[List[str]] = []
    current: Optional[List[str]] = None
    fenced = False
    for line in block:
        if line.strip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("### "):
            if current is not None:
                sections.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        sections.append(current)
    return sections


def _md_parse_step_line(ordinal: int, body: str, legacy: bool = False) -> Dict[str, Any]:
    """One printed step line → {title, text, timer_min, repeat, until, cue, hands_min,
    hands_repeat, deps(ordinals)}. Reads the shipped bracketed timing and the older
    unbracketed " — <timing>" form; lenient about punctuation and bold markers."""
    step: Dict[str, Any] = {"ordinal": ordinal, "title": None, "text": "", "timer_min": None,
                            "repeat": 1, "until": None, "cue": None, "hands_min": None,
                            "hands_repeat": 1, "deps": []}
    rest = body
    m = _MD_AFTER.search(rest)
    if m:
        step["deps"] = [int(k) for k in re.findall(r"\d+", m.group(1))]
        rest = rest[: m.start()].rstrip(" —–-")
    # Unwrap a TRAILING bracket whose whole content is a timing into the " — <timing>" form
    # the rules below read (see _MD_TIMING_OPEN / _MD_TIMING_BODY); any other bracket stays.
    # The candidates are tried last to first: a done-when may itself hold a bracket that
    # looks like an opener (`[Timer: 12 min — done when reduced to [~2 cups]]`), whose
    # content to the line's final `]` is no timing — the enclosing bracket's is, and that
    # is the one unwrapped. An inner candidate shaped like a whole timing (`… done when
    # reduce to [Done when: glossy]]`) would pass the grammar, whose `.*` swallows the
    # enclosing `]`, so a candidate whose content has unmatched brackets is skipped for
    # the enclosing opener: only a BALANCED trailing bracket is unwrapped. Each candidate's
    # content runs to the final `]`, so only a trailing bracket ever qualifies and
    # `[~2 cups stock]` on an untimed step stays.
    if rest.rstrip().endswith("]"):
        for b in reversed(list(_MD_TIMING_OPEN.finditer(rest))):
            content = rest[b.end():].rstrip()[:-1]
            if content.count("[") != content.count("]"):
                continue
            if _MD_TIMING_BODY.fullmatch(content):
                rest = rest[: b.start()].rstrip() + " — " + content
                break
    m = _MD_TIMER.search(rest)
    if m:
        step["timer_min"] = float(m.group(1))
        step["repeat"] = int(m.group(2)) if m.group(2) else 1
        step["until"] = m.group(3).strip().rstrip(" —–-")
        rest = rest[: m.start()].rstrip(" —–-")
    else:
        m = _MD_TIMER_SEC.search(rest)
        if m:
            step["timer_min"] = int(m.group(1)) / 60.0
            step["until"] = m.group(2).strip()
            rest = rest[: m.start()].rstrip(" —–-")
        else:
            m = _MD_CUE.search(rest)
            if m:
                step["cue"] = m.group(1).strip()
                rest = rest[: m.start()].rstrip(" —–-")
            else:
                m = _MD_HANDS.search(rest)
                if m:
                    step["hands_min"] = float(m.group(1))
                    step["hands_repeat"] = int(m.group(2)) if m.group(2) else 1
                    rest = (rest[: m.start()] + rest[m.end():]).rstrip(" —–-")
                else:
                    m = _MD_HANDS_SEC.search(rest)
                    if m:
                        step["hands_min"] = int(m.group(1)) / 60.0
                        rest = (rest[: m.start()] + rest[m.end():]).rstrip(" —–-")
    rest = rest.strip()
    bold = re.match(r"^\*\*(.+?)\*\*\s*(?:[—–-]+\s*)?(.*)$", rest)
    if bold:
        step["title"] = bold.group(1).strip()
        step["text"] = bold.group(2).strip()
    elif " — " in rest:
        head, _, tail = rest.partition(" — ")
        step["title"], step["text"] = head.strip(), tail.strip()
    else:
        step["title"] = None
        step["text"] = rest
    if not step["title"]:
        if legacy:
            # A version-1 line has no title: the text stands alone (step_line prints a
            # title that equals the text once), never a truncated copy of it.
            step["title"] = step["text"] if step["text"] else f"Step {ordinal}"
        else:
            # A version-2 line with no " — ": the renderer printed a node with neither title
            # nor text as `k. (untitled step)` and a non-dict node as `k. <value>` — read as
            # text, never as a title (the JSON reader's `Step k` stands in).
            step["title"] = f"Step {ordinal}"
    return step


def _md_recipe_section(lines: List[str], kind: str, legacy: bool) -> Recipe:
    title = lines[0][4:].strip()
    row: Dict[str, Any] = {"title": title}
    recipe = Recipe(kind=kind, row=row, title=title, has_author_key=False)
    ingredients: List[str] = []
    steps: List[Dict[str, Any]] = []
    dsl_lines: Optional[List[str]] = None
    mode = None
    for line in lines[1:]:
        if dsl_lines is not None:
            if line.strip().startswith("```"):
                recipe.dsl = "\n".join(dsl_lines).strip() + "\n"
                dsl_lines = None
            else:
                dsl_lines.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            dsl_lines = []
            continue
        if stripped in ("**Ingredients**", "**Steps**", "**Recipe DSL**"):
            mode = stripped.strip("*").lower()
            continue
        kv = _MD_KV.match(line)
        if kv:
            key, value = kv.group(1).strip().lower(), kv.group(2).strip()
            if key == "handle" and value not in ("—", ""):
                recipe.handle = value
            elif key == "source" and value not in ("—", ""):
                recipe.url = value
            elif key == "fond id":
                m = _MD_FOND_ID.search(line)
                if m:
                    recipe.id = m.group(1)
                    if m.group(2):
                        recipe.handle = m.group(2)
            elif key == "lineage" and value not in ("—", ""):
                recipe.lineage = {"_line": value}
            elif key == "saved" and value not in ("—", ""):
                # Shipped: `<ts> (<reason>)` with the count on its own `Cooked:` line; the
                # older `<ts>, cooked N×` form is still read.
                recipe.saved_at = value.split(",")[0].split(" (")[0].strip()
                m = re.search(r"cooked\s+(\d+)", value)
                if m:
                    recipe.cook_count_field = int(m.group(1))
            elif key == "cooked":
                m = re.match(r"(\d+)", value)
                if m:
                    recipe.cook_count_field = int(m.group(1))
            continue
        if _MD_FOND_ID.search(line) and recipe.id is None:
            m = _MD_FOND_ID.search(line)
            recipe.id = m.group(1)
            if m.group(2):
                recipe.handle = m.group(2)
            continue
        if re.match(r"^\s*(?:-\s*)?(?:\*\*)?Lineage[:*]", line, re.IGNORECASE) and recipe.lineage is None:
            value = re.sub(r"^\s*(?:-\s*)?(?:\*\*)?Lineage[:*\s]+", "", line, flags=re.IGNORECASE).strip()
            if value:
                recipe.lineage = {"_line": value}
            continue
        if mode is None and (_MD_BYLINE.match(line) or _MD_BY_HANDLE.search(line) or _MD_BY_UNKNOWN.search(line)) \
                and not recipe.has_author_key:
            recipe.has_author_key = True
            # The shipped by-line `by <sourceAuthor> · on Fond by @<handle>`: the Fond handle is
            # read only from the part after the LAST " · on Fond by" — the delimiter the
            # renderer appends last, so a source author that itself contains those words
            # (`by Food · on Fond by @evil · on Fond by @ana`) never names the handle, and one
            # written "@cara" is never the Fond creator — and the source author is everything
            # before that delimiter; "(unknown)" after it is the renderer's null handle, never
            # a handle string.
            on_fond = _MD_ON_FOND.match(line)
            if on_fond:
                m = _MD_BY_HANDLE.search(on_fond.group(2))
                recipe.author_handle = m.group(1) if m else None
                head = re.match(r"^\s*(?:-\s*)?(?:\*\*)?by\s+(.+)$", on_fond.group(1), re.IGNORECASE)
                recipe.source_author = (head.group(1).strip() or None) if head else None
                continue
            m = _MD_BY_HANDLE.search(line)
            recipe.author_handle = m.group(1) if m else None
            src = re.match(r"^\s*(?:-\s*)?(?:\*\*)?by\s+(?!@|you\b|\(unknown\))(.+?)\s*\((?:saved to Fond by|via)\b", line, re.IGNORECASE)
            if src:
                recipe.source_author = src.group(1).strip()
            continue
        if mode == "ingredients" and stripped.startswith("- "):
            ingredients.append(stripped[2:].strip())
            continue
        if mode == "steps":
            m = _MD_STEP.match(line)
            if m:
                steps.append(_md_parse_step_line(len(steps) + 1, m.group(2), legacy))
            continue
    recipe.ingredients = ingredients
    if steps:
        recipe.md_steps = steps
        recipe.md_legacy = legacy
    return recipe


def _md_saved_line(line: str) -> Optional[Recipe]:
    m = _MD_SAVED_LINE.match(line)
    if not m:
        return None
    title, tail = m.group(1).strip(), m.group(2)
    if title in ("—", "-", ""):
        title = None  # the renderer prints "—" for a recipe whose document is gone
    row = {"title": title}
    recipe = Recipe(kind="saved", row=row, title=title, has_author_key=True)
    hm = _MD_BY_HANDLE.search(tail)
    recipe.author_handle = hm.group(1) if hm else None
    recipe.deleted = "since deleted" in tail
    um = re.search(r"https?://\S+", tail)
    if um:
        recipe.url = um.group(0).rstrip(".,;)")
    cm = re.search(r"cooked\s+(\d+)", tail)
    if cm:
        recipe.cook_count_field = int(cm.group(1))
    sm = re.search(r"saved\s+(\S+)", tail)
    if sm:
        recipe.saved_at = sm.group(1).rstrip(",")
    if re.search(r"your own recipe|see .*Recipes you created|authored", tail, re.IGNORECASE):
        idm = _MD_REF_ID.search(tail)
        if idm:
            # The shipped tail names the authored recipe by id — the row's own id too (a
            # save of your own recipe shares its document): resolved by id, never by title.
            recipe.id = recipe.ref = idm.group(1)
        else:
            recipe.ref = title  # no tail (a version-1 render): resolved by title
    return recipe


def _md_cooks(block: List[str], warnings: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    cooks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    # True while inside a feedback the renderer wrote across physical lines: from a cook
    # line whose feedback slot opened a quote it did not close on that line, through the
    # line that closes it (the renderer always ends a feedback with its closing quote).
    in_feedback = False
    for line in block:
        if in_feedback:
            # Feedback text, never a cook row or a cook heading — even a line that starts
            # with "- ", spells out a whole cook line, or is shaped like "### <timestamp> —
            # <meal> (<status>)"; the line that closes the quote is the feedback's last.
            if line.rstrip().endswith('"'):
                in_feedback = False
            continue
        head = _MD_COOK_HEAD.match(line)
        if head:
            current = {"id": None, "mealName": head.group(2), "status": head.group(3),
                       "startedAt": head.group(1), "completedAt": None,
                       "deleted": _MD_COOK_REMOVED in line, "recipes": []}
            cooks.append(current)
            continue
        if current is not None and line.strip().startswith("- "):
            body = line.strip()[2:]
            readings = _md_cook_readings(body)
            # A reading that opens a feedback quote the line does not close: the lines that
            # follow continue that feedback (also when a second reading, credited to no
            # recipe below, would read the line without one — skipping a row is never a
            # cook credited to the wrong recipe).
            in_feedback = any(_md_feedback_left_open(row) for _t, row in readings)
            if len(readings) == 1:
                title, row = readings[0]
                completed_at = row.group("ts")  # None on "not completed"
                not_counted = row.group("nc") is not None
                rating_text = row.group("ratings") or ""
            elif readings:
                # Two readings name two titles (a title or a feedback spells out a whole
                # slot and tail): the line cannot say which recipe was cooked, so it names
                # none — no title, no completion, no rating — rather than guessing. It
                # counts as a cook only when every reading counts it.
                title, completed_at, rating_text = None, None, ""
                not_counted = any(row.group("nc") is not None for _t, row in readings)
                if warnings is not None:
                    warnings.append(f"a cook line under {current['startedAt']} reads as {len(readings)} different "
                                    "recipe titles (one of them spells out the line's own ' — completed …' "
                                    "structure); that cook is credited to no recipe — the JSON export resolves it")
            else:
                # No structural slot on the line (a hand-edited row): the whole body is the
                # title, nothing in it is a completion or a rating, and the renderer's
                # "(not counted)" is still honoured wherever it stands.
                title, completed_at, not_counted, rating_text = body.strip(), None, "(not counted)" in body, ""
            ratings: Dict[str, Union[int, float]] = {}
            for label, value in _MD_RATING.findall(rating_text):
                key = {"easy to follow": "easyFollow", "taste": "taste", "would cook again": "wouldCookAgain"}[label.lower()]
                v = float(value)
                ratings[key] = int(v) if v.is_integer() else v  # "4.0" reads as 4, "4.5" stays 4.5
            # "(not counted)" is the renderer's own verdict over isValid / userOverride /
            # status == "migrated" (a version-1 renderer wrote it from isValid alone), so
            # it lands in `isValid`; the row carries no `status` or `userOverride` key and
            # the cook's own status stands in, exactly as for a version-1 JSON row.
            current["recipes"].append({
                "id": None, "title": title, "isValid": not not_counted,
                "completedAt": completed_at, "ratings": ratings, "feedback": None,
            })
    return cooks


def load_markdown_export(path: Path) -> Export:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ExportError(f"Cannot read {path}: {e.strerror or e}")
    lines = text.splitlines()
    warnings: List[str] = []
    version_line = next((ln for ln in lines[:12] if _MD_VERSION.search(ln)), None)
    if version_line is None:
        raise ExportError(NOT_AN_EXPORT)
    version = check_version(int(_MD_VERSION.search(version_line).group(1)), warnings)
    exported_at = next((m.group(1) for m in (_MD_EXPORTED.match(ln) for ln in lines[:12]
                                             if not ln.startswith("## ")) if m), None)
    # Split into the top-level blocks. The Contact block is skipped unread.
    blocks: Dict[str, List[str]] = {}
    name: Optional[str] = None
    fenced = False
    for line in lines:
        if line.strip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            name = line[3:].strip().lower()
            blocks[name] = []
        elif name is not None:
            blocks[name].append(line)
    profile_block = next((v for k, v in blocks.items() if k == "profile"), None)
    has_profile = profile_block is not None
    profile_handle = None
    if profile_block:
        for line in profile_block:
            kv = _MD_KV.match(line)
            if kv and kv.group(1).strip().lower() == "handle":
                value = kv.group(2).strip()
                profile_handle = value if value not in ("—", "") else None
                break
    legacy = version < 2
    created = next((v for k, v in blocks.items() if k.startswith("recipes you created")), [])
    saved_block = next((v for k, v in blocks.items() if k.startswith("recipes you saved")), [])
    history = next((v for k, v in blocks.items() if k.startswith("cooking history")), [])
    authored = [_md_recipe_section(sec, "authored", legacy) for sec in _md_sections(created)]
    # The shipped renderer interleaves one-line rows with full sections in the export's own
    # order (newest savedAt first), so a one-line row may follow a section: one pass in
    # document order. Before the first section any `- **…**` line is a row (the version-1
    # block is nothing else); after one, only a line of the one-line row's strict shape
    # (_MD_SAVED_ONELINE) — never a section's own `- **Saved:**` bullet — standing BETWEEN
    # sections, and it ends the section it follows. Inside a section its `**Ingredients**`
    # and `**Steps**` lists are blocks that run from their header through the list to the
    # blank line that ends it (the renderer writes a blank between the header and the first
    # item, so that one does not end it), and a ``` fence to its closing marks: a list item
    # such as `- **Sauce** — saved for garnish` is an ingredient, never a saved row.
    saved: List[Recipe] = []
    section: Optional[List[str]] = None
    seen_section, fenced = False, False
    in_list, list_started = False, False
    for line in saved_block:
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("### "):
            if section is not None:
                saved.append(_md_recipe_section(section, "saved", legacy))
            section, seen_section, in_list = [line], True, False
            continue
        if not fenced and section is not None:
            if stripped in ("**Ingredients**", "**Steps**"):
                in_list, list_started = True, False
            elif in_list and stripped:
                list_started = True
            elif in_list and list_started:
                in_list = False  # the blank line after the list's items ends the block
        if fenced or in_list or (seen_section and not _MD_SAVED_ONELINE.match(stripped)):
            if section is not None:
                section.append(line)
            continue
        rec = _md_saved_line(line)
        if rec:
            if section is not None:
                saved.append(_md_recipe_section(section, "saved", legacy))
                section = None
            saved.append(rec)
        elif section is not None:
            section.append(line)
    if section is not None:
        saved.append(_md_recipe_section(section, "saved", legacy))
    # A section with no `Fond id` line gets a lookup key only; its `id` stays None, so
    # no invented id is ever printed as provenance.
    for i, rec in enumerate(authored):
        if rec.id is None:
            rec.key_hint = f"md-authored-{i + 1}"
    # One-line saved rows that point at an authored section: a row whose tail named the
    # id (`rec.id` is set only from that tail) keeps it — `content_of` resolves it by id,
    # and a dangling one is reported as the JSON's would be. The title map is only the
    # fallback for a row without the tail: the explicit "your own recipe" row of an older
    # render, or (version 1, which has no such marker) a row whose title and author
    # handle match an authored section and the profile handle.
    by_title = {r.title: r for r in authored if r.title}
    for rec in saved:
        if rec.ref and rec.id is None:
            target = by_title.get(rec.ref)
            rec.ref = target.key if target else None
        elif (not rec.ref and rec.title in by_title and profile_handle
              and rec.author_handle == profile_handle and not has_steps(rec)):
            rec.ref = by_title[rec.title].key
    for i, rec in enumerate(saved):
        if rec.id is None:
            rec.key_hint = f"md-saved-{i + 1}"
    return Export(
        version=version,
        exported_at=exported_at,
        profile_handle=profile_handle,
        has_profile=has_profile,
        authored=authored,
        saved=saved,
        cooks=_md_cooks(history, warnings),
        raw={},
        from_markdown=True,
        warnings=warnings,
    )


def load_export(path: Path, markdown: bool = False) -> Export:
    if markdown or path.suffix.lower() in (".md", ".markdown", ".txt"):
        return load_markdown_export(path)
    return load_json_export(path)


# ---------------------------------------------------------------------------
# Local recipe files — the envelope (recipe-authoring "The envelope and its keys per
# origin", "The local id"): DSL_SPEC §1.2's legacy frontmatter block over a canonical
# body, read by the script's own strict reader. Every scalar stays a string; the shapes
# the reference reader mis-reads are refused, never guessed.
# ---------------------------------------------------------------------------

ENVELOPE_FIELDS = ("title", "author", "yield", "source_url", "attribution", "lineage")
LINEAGE_FIELDS = ("origin", "parent_id", "parent_handle", "parent_lineage", "exported_at", "credits", "made_on", "changes")
MADE_ON_EMPTY = "fill lineage.made_on with today's date (YYYY-MM-DD)"
PARENT_FIELDS = ("parent_id", "parent_handle", "parent_lineage", "exported_at", "credits")  # a variant's, never another origin's
ORIGINS = ("composed", "variant", "transcribed")
ENVELOPE_LISTS = {"attribution", "credits", "changes"}
# Keys that would make a local file look like a registry object: refused by name.
FOND_LOOKING_FIELDS = {"id", "handle", "fond_id", "fondid", "fond_handle", "uid", "fork_point", "forkpoint",
                     "parentid", "attributionhandles", "attribution_handles"}
# The must-not-publish check's account-id shape: 28 alphanumerics, not inside a longer word.
UID_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9]{28}(?![A-Za-z0-9_])")
LOCAL_SLUG = re.compile(r"^[a-z][a-z0-9-]*$")
MADE_ON_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
H_RE = re.compile(r"^[0-9a-f]{8}$")
_ENV_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s+(.*))?$")
_RENAME = re.compile(r"^rename\s+(\S+)\s*->\s*(\S+)$")
_SPLIT = re.compile(r"^split\s+(\S+)\s*->\s*(.+)$")
COPY_ENTRY = "copied from the Fond-format steps the export carries"
CONVERT_ENTRY = "converted by the assistant from the app's steps"
NOT_AN_EXPORT_LOCAL = "a local file is not an export; its provenance block is the file"
NO_PARENT_FOR_CHECK = ("check needs --parent <export> on a variant: the parent row supplies the baseline for "
                       "rules U and V and the cross-check of author, source, credits and lineage")


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


# The `---` fence as `split_dsl` and the reference `split_frontmatter` match it — kept the
# same so every reader splits a file at the same places (and `h`, over the body, agrees).
_FENCE_RE = re.compile(r"^---\s*$", re.MULTILINE)


def split_envelope(text: str) -> Tuple[Optional[str], str]:
    """(the frontmatter text, the body after it) — None when the file opens with no `---`
    block. The same split `split_dsl` and the reference `split_frontmatter` make."""
    parts = _FENCE_RE.split(text, maxsplit=2)
    if len(parts) == 3 and not parts[0].strip():
        return parts[1], parts[2].lstrip("\n")
    return None, text


def _tab_error(n: int, raw: str) -> str:
    """The reader's refusal of a line carrying a tab, by file line."""
    if "\t" in raw.lstrip():
        return f"line {n}: a tab after the indent — the envelope carries no tabs; write a space"
    return f"line {n}: a tab in the indent — indent with two spaces"


def envelope_fences(text: str) -> Tuple[int, List[str], List[str]]:
    """For a file `split_envelope` finds an envelope in: (the file line its frontmatter text
    opens on, the tab errors at the opening fence, the tab errors on the closing fence). The
    fence pattern's `\\s*` swallows a tab after either `---` and, after the opening one, the
    whitespace-only lines below it, so none of those reaches `parse_envelope`; the envelope
    carries no tab anywhere (recipe-authoring "The envelope and its keys per origin"), so each
    is an error naming its file line. What the closing match swallows after its own line is
    the body's leading blank lines, not the envelope's. The line count also keeps the
    reader's numbering right when blank lines sit above or just below the opening fence."""
    fences = list(_FENCE_RE.finditer(text))[:2]
    errors: Tuple[List[str], List[str]] = ([], [])
    for k, m in enumerate(fences):
        first = text.count("\n", 0, m.start()) + 1
        lines = m.group(0).split("\n")
        for i, raw in enumerate(lines if k == 0 else lines[:1]):
            if "\t" not in raw:
                continue
            if i == 0:  # the fence line itself
                errors[k].append(f"line {first}: a tab on the `---` fence — the envelope carries no tabs; write the "
                                 "fence as `---`")
            else:  # a whitespace-only line the opening match swallowed
                errors[k].append(_tab_error(first + i, raw))
    start = text.count("\n", 0, fences[0].end()) + 1 if fences else 1
    return start, errors[0], errors[1]


def parse_envelope(fm: str, first_line: Optional[int] = None) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """The strict reader: `key: scalar`, `key:` over a map or a list indented two spaces
    deeper, `- item` scalars; nothing else. Returns (data, errors, warnings). Refused (an
    error, never a guess): a tab, a compact list (`[a, b]`, or `- item` at the key's own
    indent), a list item or scalar carrying a colon-space inside a list (a `changes` entry
    with a colon is the one warning, "write -> not :"), a duplicated key, a map inside a
    list, a third level, a value shaped like an account id. Every scalar is a string
    (quotes removed); nothing is int-ified or read as null."""
    errors: List[str] = []
    warnings: List[str] = []
    rows: List[Tuple[int, int, str]] = []  # (line number, indent, content)
    # The text `split_envelope` hands over opens with the newline that ends the `---` line,
    # so its first element is the tail of that line — line 1 unless `first_line` (from
    # `envelope_fences`) says the fence match ended lower; a text without it starts on line 2.
    start = first_line if first_line is not None else (1 if fm.startswith("\n") else 2)
    for n, raw in enumerate(fm.split("\n"), start):
        # The envelope carries no tab anywhere — in the indent, after it (a `changes`
        # entry, a value), inside a quoted scalar, a comment — each an error naming the
        # line; the line is dropped rather than read as something it might have meant.
        # (A tab on a fence is `envelope_fences`'s: the split swallows it before this.)
        if "\t" in raw:
            errors.append(_tab_error(n, raw))
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rows.append((n, len(raw) - len(raw.lstrip(" ")), raw.strip()))

    def scalar(value: str, where: str) -> str:
        v = _unquote(value)
        if v.startswith("[") and v.endswith("]"):
            errors.append(f"{where}: compact list `{v}` — write one `- item` per line")
        if UID_RE.search(v):
            errors.append(f"{where}: a 28-character account-id-shaped value — a local file never carries a uid")
        return v

    def parse_list(i: int, indent: int, key_path: str) -> Tuple[List[str], int]:
        items: List[str] = []
        while i < len(rows) and rows[i][1] == indent and rows[i][2].startswith("- "):
            n, _ind, content = rows[i]
            item = content[2:].strip()
            where = f"{key_path} entry {len(items) + 1} (line {n})"
            if item.startswith("- "):
                errors.append(f"{where}: a list inside a list")
            elif ": " in item or item.endswith(":"):
                if key_path.endswith("changes"):
                    warnings.append(f"{where}: write -> not : (`{item}`)")
                else:
                    errors.append(f"{where}: a colon-space in a list item (`{item}`) — the reference reader "
                                  "would read it as a map; write it without the colon")
            elif ":" in item and key_path.endswith("changes"):
                warnings.append(f"{where}: write -> not : (`{item}`)")
            items.append(scalar(item, where))
            i += 1
            if i < len(rows) and rows[i][1] > indent:
                errors.append(f"{where}: nothing may be indented under a list item (line {rows[i][0]})")
                while i < len(rows) and rows[i][1] > indent:
                    i += 1
        return items, i

    def parse_map(i: int, indent: int, key_path: str, depth: int) -> Tuple[Dict[str, Any], int]:
        out: Dict[str, Any] = {}
        while i < len(rows) and rows[i][1] == indent:
            n, _ind, content = rows[i]
            m = _ENV_KEY.match(content)
            if not m or content.startswith("- "):
                errors.append(f"line {n}: expected `key: value`, got `{content}`")
                i += 1
                continue
            key, value = m.group(1), m.group(2)
            where = f"{key_path}{key}" if key_path else key
            if key in out:
                errors.append(f"line {n}: duplicated key `{where}`")
            i += 1
            if value is not None and value.strip():
                out[key] = scalar(value, f"{where} (line {n})")
                if i < len(rows) and rows[i][1] > indent:
                    errors.append(f"{where} (line {n}): a value and an indented block (line {rows[i][0]})")
                    while i < len(rows) and rows[i][1] > indent:
                        i += 1
                continue
            # `key:` with nothing after it: a block two spaces deeper, or an empty value
            if i < len(rows) and rows[i][1] > indent:
                nxt_n, nxt_indent, nxt_content = rows[i]
                if nxt_indent != indent + 2:
                    errors.append(f"{where}: indent the block under it by two spaces (line {nxt_n})")
                    while i < len(rows) and rows[i][1] > indent:
                        i += 1
                    continue
                if nxt_content.startswith("- "):
                    out[key], i = parse_list(i, nxt_indent, where)
                elif depth >= 1:
                    errors.append(f"{where}: a map inside `{key_path.rstrip('.')}` — the envelope nests one level only")
                    while i < len(rows) and rows[i][1] > indent:
                        i += 1
                else:
                    out[key], i = parse_map(i, nxt_indent, f"{where}.", depth + 1)
            elif i < len(rows) and rows[i][1] == indent and rows[i][2].startswith("- "):
                errors.append(f"{where}: compact block list — indent its `- item` lines two spaces under the key")
                while i < len(rows) and rows[i][1] == indent and rows[i][2].startswith("- "):
                    i += 1
            else:
                out[key] = ""
        return out, i

    if rows and rows[0][1] != 0:
        errors.append(f"line {rows[0][0]}: the envelope starts indented")
        return {}, errors, warnings
    data, i = parse_map(0, 0, "", 0)
    if i < len(rows):
        errors.append(f"line {rows[i][0]}: unexpected indent (`{rows[i][2]}`)")
    return data, errors, warnings


def _is_list(v: Any) -> bool:
    return isinstance(v, list)


def not_a_local_id(slug: Any) -> str:
    """The local-id refusal of recipe-authoring "The local id", one text whether it names a
    file so named (an envelope error) or an `--out` so named (`_refuse_out_name`)."""
    return (f"`{slug}` is not a local id: the file name up to its first dot must match ^[a-z][a-z0-9-]*$ "
            "(the id is local:<that name>)")


def envelope_findings(recipe: "Recipe") -> Tuple[List[str], List[str]]:
    """The envelope checks of recipe-authoring "The envelope and its keys per origin" and
    "The local id", over a parsed envelope: (errors, warnings), each naming its key."""
    errors: List[str] = list(recipe.envelope_errors)
    warnings: List[str] = list(recipe.envelope_warnings)
    env = recipe.envelope if isinstance(recipe.envelope, dict) else {}
    if recipe.envelope is None:
        errors.append("no envelope: a local recipe file opens with a `---` block (title, lineage) over the recipe")
    slug = recipe.local_slug
    if not LOCAL_SLUG.match(slug or ""):
        errors.append(not_a_local_id(slug))
    for key in env:
        if key in ENVELOPE_FIELDS:
            continue
        if key.lower() in FOND_LOOKING_FIELDS:
            errors.append(f"`{key}`: a local file never carries a Fond id")
        else:
            errors.append(f"`{key}` is not a DSL_SPEC §1.2 key (title, author, yield, source_url, attribution, lineage)")
    for key in ("title", "author", "yield", "source_url"):
        if key in env and not isinstance(env[key], str):
            errors.append(f"`{key}` must be one value, not a list or a map")
    title = env.get("title") if isinstance(env.get("title"), str) else None
    if not title:
        errors.append("`title` is required")
    elif recipe.body is not None:
        h1, _body = split_dsl(recipe.body)
        if h1 and h1 != title:
            errors.append(f"`title` (`{title}`) and the `# H1` (`{h1}`) disagree")
        elif not h1:
            errors.append(f"the body has no `# {title}` H1 before its first atom")
    def not_a_list(value: Any) -> bool:
        # a compact `[a, b]` was already refused by the reader; report the shape once
        return not _is_list(value) and not (isinstance(value, str) and value.startswith("[") and value.endswith("]"))

    if "attribution" in env and not_a_list(env["attribution"]):
        errors.append("`attribution` must be a list of `- <source>` lines")
    lineage = env.get("lineage")
    if "lineage" not in env:
        errors.append("`lineage` is required (origin, made_on, changes)")
        lineage = {}
    elif not isinstance(lineage, dict):
        errors.append("`lineage` must be a map (origin, made_on, changes, …)")
        lineage = {}
    for key in lineage:
        if key in LINEAGE_FIELDS:
            continue
        if key.lower() in FOND_LOOKING_FIELDS:
            errors.append(f"`lineage.{key}`: a local file never carries a Fond id or a fork point")
        else:
            errors.append(f"`lineage.{key}` is not a lineage key of a local file ({', '.join(LINEAGE_FIELDS)})")
    for key in ("origin", "parent_id", "parent_handle", "parent_lineage", "exported_at", "made_on"):
        if key in lineage and not isinstance(lineage[key], str):
            errors.append(f"`lineage.{key}` must be one value, not a list or a map")
    origin = lineage.get("origin") if isinstance(lineage.get("origin"), str) else None
    if not origin:
        errors.append("`lineage.origin` is required (composed | variant | transcribed)")
    elif origin not in ORIGINS:
        errors.append(f"`lineage.origin` must be composed, variant or transcribed, not `{origin}`")
    made_on = lineage.get("made_on") if isinstance(lineage.get("made_on"), str) else None
    if not made_on:
        # `convert` without `--made-on` leaves the value empty: the script reads no clock.
        errors.append(MADE_ON_EMPTY)
    elif not MADE_ON_RE.match(made_on):
        errors.append(f"`lineage.made_on` must be YYYY-MM-DD, not `{made_on}`")
    changes = lineage.get("changes")
    if "changes" not in lineage or not _is_list(changes) or not [c for c in changes if str(c).strip()]:
        errors.append("`lineage.changes` needs at least one entry (one line per edit; the first says where the body came from)")
    else:
        for k, entry in enumerate(changes, 1):
            head = str(entry).split(" ", 1)[0].lower()
            if head in ("rename", "split") and alias_of(str(entry)) is None:
                form = "rename <old> -> <new>" if head == "rename" else "split <old> -> <a>, <b>[, …]"
                warnings.append(f"lineage.changes entry {k}: `{entry}` is not understood (write `{form}`); "
                                "the player's reconcile ignores it")
    if "credits" in lineage and not_a_list(lineage["credits"]):
        errors.append("`lineage.credits` must be a list of handles (`- ana`)")
    if origin == "variant":
        if not isinstance(lineage.get("parent_id"), str) or not lineage.get("parent_id").strip():
            errors.append("`lineage.parent_id` is required on a variant (the parent row's Fond id)")
    elif origin in ORIGINS:
        for key in PARENT_FIELDS:
            if key in lineage:
                errors.append(f"`lineage.{key}` belongs to a variant; a {origin} file names no parent")
        if origin == "composed" and isinstance(env.get("source_url"), str) and env.get("source_url").strip() \
                and not env.get("attribution"):
            errors.append("a file composed from a page needs an `attribution` line beside `source_url` — the page's "
                          "named creator, or its site name when the page names none")
    return errors, warnings


def alias_of(entry: str) -> Optional[Tuple[str, str, List[str]]]:
    """A `changes` entry the player's reconcile reads: ("rename", old, [new]) or ("split",
    old, [a, b, …]); None for free text or a malformed entry (never guessed)."""
    m = _RENAME.match(entry.strip())
    if m:
        return ("rename", m.group(1), [m.group(2)]) if LOCAL_SLUG.match(m.group(1)) and LOCAL_SLUG.match(m.group(2)) else None
    m = _SPLIT.match(entry.strip())
    if m:
        children = [c.strip() for c in m.group(2).split(",") if c.strip()]
        if len(children) >= 2 and LOCAL_SLUG.match(m.group(1)) and all(LOCAL_SLUG.match(c) for c in children):
            return ("split", m.group(1), children)
    return None


def envelope_aliases(recipe: "Recipe") -> Dict[str, List[str]]:
    """old slug → new slug(s), from the file's parsed `rename`/`split` entries only."""
    out: Dict[str, List[str]] = {}
    lineage = (recipe.envelope or {}).get("lineage")
    for entry in (lineage.get("changes") if isinstance(lineage, dict) and _is_list(lineage.get("changes")) else []):
        parsed = alias_of(str(entry))
        if parsed:
            out[parsed[1]] = parsed[2]
    return out


def body_hash(text: str) -> str:
    """`h`: the first eight hex digits of SHA-256 over the body — CRLF → LF, trailing
    whitespace stripped per line, exactly one final newline — so an envelope-only edit
    leaves it unchanged and any body edit changes it."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    norm = "\n".join(ln.rstrip() for ln in lines).rstrip("\n") + "\n"
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]


def recipe_h(content: Recipe) -> str:
    """Every recipe has an `h`: a local file's body, a DSL row's `dsl` text, or for a nodes
    (or Markdown-steps) row the canonical JSON of the slim fields the graph reads — so no
    FOND1 line ever prints `h=undefined`."""
    if content.kind == "local":
        return body_hash(content.body or "")
    if content.dsl:
        return body_hash(content.dsl)
    if content.md_steps:
        slim: Any = content.md_steps
    else:
        nodes, _ = parse_nodes(content.nodes)
        slim = []
        for node in nodes:
            if not isinstance(node, dict):
                node = {"text": str(node)}
            slim.append({k: node.get(k) for k in ("id", "title", "text", "time", "until", "dependencies", "repeat") if k in node})
    canonical = json.dumps(slim, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def local_recipe_from_text(text: str, basename: str, shown_path: str) -> Recipe:
    """A `Recipe(kind="local")` from a file's text: id `local:<basename>`, the envelope as
    the strict reader read it (its refusals kept for `check`), the body as `dsl` so the
    graph is built exactly as for an export row."""
    fm, body = split_envelope(text)
    envelope: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    warnings: List[str] = []
    if fm is not None:
        first_line, opening, closing = envelope_fences(text)
        envelope, errors, warnings = parse_envelope(fm, first_line)
        errors = opening + errors + closing
    env = envelope or {}
    title = env.get("title") if isinstance(env.get("title"), str) and env.get("title").strip() else None
    if title is None:
        h1, _b = split_dsl(body)
        title = h1
    url = env.get("source_url") if isinstance(env.get("source_url"), str) and env.get("source_url").strip() else None
    return Recipe(
        kind="local", row={}, id=f"local:{basename}", handle=None, title=title, url=url,
        author_handle=None, has_author_key=False, source_author=None, lineage=None, ingredients=[],
        nodes=None, dsl=body if body.strip() else None, text=text, body=body, envelope=envelope,
        local_path=shown_path, envelope_errors=errors, envelope_warnings=warnings,
    )


def local_basename(path: Path) -> str:
    return path.name.split(".")[0]


def load_library_file(path: Union[Path, str], out_hint: Optional[str] = None) -> Recipe:
    """One recipe file, or `-` for stdin. With `--out` (the hint) the id is the OUTPUT's
    basename — the id the kept file will carry, so `check source.md --out foo.recipe.md`
    constructs, gates and reports `local:foo`, never `local:source` (recipe-authoring "The
    local id"); without it a file's id is its own name and stdin's the slug of its title. A
    file that opens with no envelope is still a Recipe whose `check` refuses it."""
    hint = local_basename(Path(out_hint)) if out_hint else ""
    if str(path) == "-":
        text = sys.stdin.read()
        if not hint:
            fm, body = split_envelope(text)
            env = parse_envelope(fm)[0] if fm is not None else {}
            title = env.get("title") if isinstance(env.get("title"), str) else (split_dsl(body)[0] or "")
            hint = slugify(title or "")
        return local_recipe_from_text(text, hint or "untitled", "- (stdin)")
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ExportError(f"Cannot read {p}: {e.strerror or e}")
    return local_recipe_from_text(text, hint or local_basename(p), str(p))


def collisions_in(recipes: List[Recipe]) -> Dict[str, List[Recipe]]:
    """id -> the files that share it, for every id two or more files carry (file order kept)."""
    groups: Dict[str, List[Recipe]] = {}
    for r in recipes:
        groups.setdefault(r.id or "", []).append(r)
    return {rid: group for rid, group in groups.items() if len(group) > 1}


_COUNT_WORDS = {2: "two", 3: "three", 4: "four"}


def collision_line(group: List[Recipe]) -> str:
    """The one line a collision prints — the library's warning, and the refusal of any
    lookup by the shared id — naming every file."""
    paths = ", ".join(str(r.local_path) for r in group)
    count = _COUNT_WORDS.get(len(group), str(len(group)))
    return (f"{count} files share the basename `{group[0].local_slug}` ({paths}) — rename all but one; "
            "local ids must be unique in a folder")


def load_library(path: Path, parent: Optional[Export] = None) -> Export:
    """A library: one file, or every envelope-bearing `.md` in a folder (non-recursive,
    sorted by basename). Files sharing a basename share an id — the collision rule
    (recipe-authoring "The local id"): the collision is named once in a warning and EVERY
    member is refused by the gate with an error naming the other file(s), so a suffix
    (`dal.md` beside `dal.recipe.md`) never decides which file `local:dal` means."""
    recipes: List[Recipe] = []
    warnings: List[str] = []
    if str(path) == "-":
        recipes.append(load_library_file("-"))
    elif path.is_dir():
        for p in sorted(path.iterdir(), key=lambda q: q.name):
            if not p.is_file() or p.suffix.lower() != ".md":
                continue
            try:
                head = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if split_envelope(head)[0] is None:
                continue
            recipes.append(local_recipe_from_text(head, local_basename(p), str(p)))
        if not recipes:
            raise ExportError(f"{path} holds no recipe file (a `.md` that opens with a `---` envelope).")
    else:
        recipes.append(load_library_file(path))
    for group in collisions_in(recipes).values():
        warnings.append(collision_line(group))
        for r in group:
            others = ", ".join(str(o.local_path) for o in group if o is not r)
            r.envelope_errors.append(f"basename `{r.local_slug}` is also the basename of {others}; rename all but one — "
                                     "local ids must be unique in a folder")
    return Export(version=parent.version if parent else 0, exported_at=None, profile_handle=None, has_profile=False,
                  authored=recipes, saved=[], cooks=[], raw={}, warnings=warnings, local=True, local_root=str(path),
                  parent=parent)


def masked_view(export: Export) -> Export:
    """The export as after `strip`: no profile, so `byline()` never prints "you (@h)" — a
    version-1 row keeps the handle `strip` would have stamped on it. For lines that go into
    a file or a page (a variant's `Derived from:`, the player payload)."""
    def stamp(r: Recipe) -> Recipe:
        if r.has_author_key:
            return r
        return replace(r, author_handle=export.profile_handle if export.has_profile else None, has_author_key=True)
    return replace(export, profile_handle=None, has_profile=False,
                   authored=[stamp(r) for r in export.authored], saved=[stamp(r) for r in export.saved])


def masked_parent_row(recipe: Recipe, export: Export) -> Tuple[Optional[Recipe], Optional[Export]]:
    """A variant's parent row AND the export it is read from, both as after `strip`: the
    row is looked up in `masked_view(export.parent)`, never in the original, so a
    version-1 authored row (no `authorHandle` key) carries the handle `strip` stamps on
    it and `byline()` prints "by @ana" — not "by (unknown)" — and never "by you"."""
    if export.parent is None:
        return None, None
    masked = masked_view(export.parent)
    return parent_row_of(recipe, masked), masked


def parent_row_of(recipe: Recipe, parent: Optional[Export]) -> Optional[Recipe]:
    """The parent export's row a variant names by `lineage.parent_id` (exact id), as the
    export presents it (a saved copy of the user's own recipe is the authored row)."""
    lineage = (recipe.envelope or {}).get("lineage")
    pid = lineage.get("parent_id") if isinstance(lineage, dict) else None
    if parent is None or not isinstance(pid, str) or not pid:
        return None
    for r in parent.all_recipes():
        if r.id == pid:
            c = parent.content_of(r)
            return c if (c is not None and c is not r and c.kind == "authored") else r
    return None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def effective_author(recipe: Recipe, export: Export) -> Optional[str]:
    """The row's own `authorHandle`; a version-1 authored row (no such key) takes
    `profile.handle` when `profile` is present."""
    if recipe.has_author_key:
        return recipe.author_handle
    return export.profile_handle if export.has_profile else None


def author_text(recipe: Recipe, export: Export) -> str:
    handle = effective_author(recipe, export)
    if handle is None or not str(handle).strip():
        return "(unknown)"
    # "you" only beside a matching profile.handle, never once profile is gone.
    if export.has_profile and export.profile_handle is not None and export.profile_handle == handle:
        return f"you (@{handle})"
    return f"@{handle}"


def _attribution_lines(recipe: Recipe) -> List[str]:
    value = (recipe.envelope or {}).get("attribution")
    return [str(v) for v in value if str(v).strip()] if isinstance(value, list) else []


def parent_head(recipe: Recipe, export: Export) -> str:
    """A variant's parent by-line head — "by @cara", "by Ana (saved to Fond by @blog.example)",
    "by (unknown)" — exactly as `byline()` prints it for the parent row (the profile masked,
    so never "by you"); from the file's own `author`/`attribution` when the row is not at
    hand, through the same function on a stand-in row."""
    row, masked = masked_parent_row(recipe, export)
    if row is not None and masked is not None:
        return byline(row, masked).split(" · ")[0]
    env = recipe.envelope or {}
    author = env.get("author") if isinstance(env.get("author"), str) else None
    handle = author[1:] if author and author.startswith("@") else None
    source = next((a[len("source "):].strip() for a in _attribution_lines(recipe) if a.startswith("source ")), None)
    stand_in = Recipe(kind="authored", row={}, author_handle=handle or None, has_author_key=True, source_author=source)
    return byline(stand_in, Export(0, None, None, False, [], [], [], {})).split(" · ")[0]


def local_byline(recipe: Recipe, export: Export) -> str:
    """The origin line of a local file, after its title (recipe-authoring "Composed",
    "Variant", "Transcribed"): never a Fond id, handle or "by @" of its own."""
    env = recipe.envelope or {}
    lineage = env.get("lineage") if isinstance(env.get("lineage"), dict) else {}
    origin = recipe.origin
    attribution = _attribution_lines(recipe)
    if origin == "variant":
        row, _masked = masked_parent_row(recipe, export)
        parent_title = row.label if row is not None else _s(lineage.get("parent_id"))
        tail = f"local variant of {parent_title} {parent_head(recipe, export)}"
    elif origin == "transcribed":
        tail = "transcribed by the assistant" + (f" from {', '.join(attribution)}" if attribution else "")
    elif origin == "composed":
        host = host_of(recipe.url)
        tail = "composed by the assistant" + (f" · from {host}, credited to {', '.join(attribution)}" if host and attribution else "")
    else:
        tail = "local file"
    return f"{tail} · {recipe.id}"


def byline(recipe: Recipe, export: Export) -> str:
    if recipe.kind == "local":
        return local_byline(recipe, export)
    author = author_text(recipe, export)
    if recipe.source_author:
        head = f"by {recipe.source_author} (saved to Fond by {author})"
    else:
        head = f"by {author}"
    parts = [head]
    host = host_of(recipe.url)
    if host:
        parts.append(f"from {host}")
    if recipe.handle:
        parts.append(f"Fond handle {recipe.handle}")
    elif recipe.id:
        parts.append(f"Fond id {recipe.id}")
    return " · ".join(parts)


def lineage_line(lineage: Optional[Dict[str, Any]]) -> Optional[str]:
    """'forked from <parentId>[ at <forkPoint>]; credits @a, @b' — only when lineage is
    non-null; a null handle is '(unknown)'; the string 'None' never appears."""
    if not isinstance(lineage, dict):
        return None
    if "_line" in lineage:  # echoed verbatim from a Markdown export
        return str(lineage["_line"])
    parent = lineage.get("parentId")
    text = f"forked from {_s(parent)}"
    if lineage.get("forkPoint") is not None:
        text += f" at {lineage['forkPoint']}"
    handles = lineage.get("attributionHandles")
    if isinstance(handles, list) and handles:
        credits = ", ".join(f"@{h}" if isinstance(h, str) and h else "(unknown)" for h in handles)
        text += f"; credits {credits}"
    return text


def provenance_fields(recipe: Recipe, export: Export) -> Dict[str, Any]:
    """The provenance every --json recipe row carries: `byline` as `byline()` renders it
    and `lineage` as the one lineage line — null when the row's `lineage` is null."""
    return {"byline": byline(recipe, export), "lineage": lineage_line(recipe.lineage)}


def row_lines(entry: Dict[str, Any], tail: str = "", prefix: str = "  - ") -> List[str]:
    """Render one presented recipe from its --json entry: "<prefix><title> — <by-line><tail>"
    and, only when the entry's `lineage` is non-null, a "Lineage:" line indented under it.
    Every command that presents a recipe row — `list` (cookable and uncookable rows alike),
    `missing`, `history`, `cook-again`, `scale` and the several-match answer — renders it
    through this, from the same fields its JSON carries, so the text can never drop a by-line
    or a lineage line the JSON has and the surfaces cannot drift (cook-playback, "Provenance
    on every presentation" and "by-line travels"). A null title prints as "(untitled)"."""
    lines = [f"{prefix}{label_text(entry.get('title'))} — {entry['byline']}{tail}"]
    if entry.get("lineage"):
        lines.append(f"{' ' * len(prefix)}  Lineage: {entry['lineage']}")
    return lines


def local_provenance_block(recipe: Recipe, export: Export) -> List[str]:
    """`show`, the opening turn and the player's mise screen: the origin line, then one line
    each and only when present — Local file, Source, Attribution, a variant's Derived from
    (`Fond id <pid>[ (handle <h>)] — <the parent's by-line>` through `byline()` with the
    profile masked, else exactly `Fond id <pid> (not in this export)`), Lineage (parent),
    Credits, Exported — and the Changes block, its first entry
    never dropped. "Fond id" names the parent only; "fork" only inside the echoed line."""
    env = recipe.envelope or {}
    lineage = env.get("lineage") if isinstance(env.get("lineage"), dict) else {}
    lines = [f"{recipe.label} — {byline(recipe, export)}"]
    lines.append(f"  Local file: {recipe.local_path}")
    if recipe.url:
        lines.append(f"  Source: {recipe.url}")
    attribution = _attribution_lines(recipe)
    if attribution:
        lines.append(f"  Attribution: {'; '.join(attribution)}")
    if recipe.origin == "variant":
        pid = lineage.get("parent_id")
        if isinstance(pid, str) and pid:
            row, masked = masked_parent_row(recipe, export)
            if row is not None and masked is not None:
                handle = lineage.get("parent_handle")
                shown = f" (handle {handle})" if isinstance(handle, str) and handle else ""
                lines.append(f"  Derived from: Fond id {pid}{shown} — {byline(row, masked)}")
            else:
                # The spec's exact form from the file alone: no handle, no by-line.
                lines.append(f"  Derived from: Fond id {pid} (not in this export)")
        parent_lineage = lineage.get("parent_lineage")
        if isinstance(parent_lineage, str) and parent_lineage:
            lines.append(f"  Lineage (parent): {parent_lineage}")
        credits = lineage.get("credits")
        if isinstance(credits, list) and credits:
            lines.append("  Credits: " + ", ".join(c if c == "(unknown)" else f"@{c}" for c in (str(x) for x in credits)))
        exported_at = lineage.get("exported_at")
        if isinstance(exported_at, str) and exported_at:
            lines.append(f"  Exported: {exported_at}")
    changes = lineage.get("changes")
    if isinstance(changes, list) and changes:
        lines.append("  Changes:")
        lines += [f"    - {c}" for c in changes]
    return lines


def provenance_block(recipe: Recipe, export: Export, content: Optional[Recipe]) -> List[str]:
    if recipe.kind == "local":
        return local_provenance_block(recipe, export)
    lines = [f"{recipe.label} — {byline(recipe, export)}"]
    if recipe.id:
        lines.append(f"  Fond id: {recipe.id}")
    else:
        lines.append("  Fond id: — (not in the Markdown)" if export.from_markdown else "  Fond id: — (not in the export)")
    if recipe.handle:
        lines.append(f"  Fond handle: {recipe.handle}")
    lines.append(f"  Source: {recipe.url if recipe.url else '— (no url in the export)'}")
    if recipe.source_author:
        lines.append(f"  Source author: {recipe.source_author}")
    ll = lineage_line(recipe.lineage)
    if ll:
        lines.append(f"  Lineage: {ll}")
    if recipe.kind == "saved":
        extra = []
        if recipe.saved_at:
            extra.append(f"saved {recipe.saved_at}")
        if recipe.cook_count_field:
            extra.append(f"cooked {recipe.cook_count_field}× (app counter)")
        if extra:
            lines.append("  " + ", ".join(extra))
    if content is not None and content is not recipe:
        lines.append(f"  Steps: your own recipe {content.label}" + (f" (Fond id {content.id})" if content.id else ""))
    return lines


# ---------------------------------------------------------------------------
# DSL parsing — a stdlib re-implementation of the small subset the cook needs
# (DSL_SPEC §1.3–§1.5, §2.1, §2.4, §3.4, §3.7). Never imports the service's own modules.
# ---------------------------------------------------------------------------

HEADER = re.compile(r"^##\s+(.+?)(?:\s*\[(.*?)\])?\s*$")
TIMER = re.compile(r"~([A-Za-z_][A-Za-z0-9_-]*)?\{([^}]*)\}")
ING_DEF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\{([^}]*)\}")
ING_REF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*)")
ING_PART_DEF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\[([A-Za-z0-9_-]+)\]\{([^}]*)\}")
ING_PART_REF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\[([A-Za-z0-9_-]+)\](?!\{)")
EQ_DEF = re.compile(r"#([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\{([^}]*)\}")
EQ_REF = re.compile(r"#([A-Za-z][A-Za-z0-9_-]*)")
STEP_REF = re.compile(r"\^\{([^}]+)\}")
_PREP_SLOT = re.compile(
    r"(@[A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*(?:\[[^\]]*\])?\{)([^{}]*)(\})\(([^()]*)\)")
# One timer segment: lo[-hi]%unit [× N]  (range floor; ascii x accepted for ×)
_SEGMENT = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?(?:\s*%\s*([A-Za-z]+))?(?:\s*(?:×|(?<![A-Za-z0-9])[xX])\s*(\d+))?")


def absorb_prep_slot(text: str) -> str:
    def _sub(m):
        head, phrase, close, prep = m.group(1), m.group(2).rstrip(), m.group(3), m.group(4).strip()
        if not prep:
            return f"{head}{phrase}{close}"
        return f"{head}{phrase + ', ' + prep if phrase else prep}{close}"
    return _PREP_SLOT.sub(_sub, text)


def _unit_minutes(value: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("h"):
        return value * 60
    if u.startswith("s"):
        return value / 60
    if u.startswith("d"):
        return value * 1440
    return value


def _unit_word(unit: str) -> str:
    u = unit.lower()
    if u.startswith("h"):
        return "hr"
    if u.startswith("s"):
        return "sec"
    if u.startswith("d"):
        return "day"
    return "min"


def parse_timer_body(body: str) -> List[Tuple[float, str, int]]:
    """`5%min, 10%min` → [(5, '5 min', 1), (10, '10 min', 1)]; `2-3%min × 2` →
    [(2, '2-3 min', 2)]. Minutes are the range floor (the conservative convention)."""
    out: List[Tuple[float, str, int]] = []
    for seg in body.split(","):
        if not seg.strip():
            continue
        m = _SEGMENT.search(seg)
        if not m:
            continue
        lo = float(m.group(1))
        hi = m.group(2)
        unit = m.group(3) or "min"
        rep = max(1, int(m.group(4))) if m.group(4) else 1
        label = f"{lo:g}" + (f"-{float(hi):g}" if hi else "") + f" {_unit_word(unit)}"
        out.append((_unit_minutes(lo, unit), label, rep))
    return out


def render_timer_human(body: str) -> str:
    """`5%min, 10%min` → '5 minutes, then 10 minutes'; `2-3%min × 2` → '2 to 3 minutes × 2'."""
    parts = []
    for minutes, label, rep in parse_timer_body(body):
        qty, _, unit = label.partition(" ")
        words = {"min": "minutes", "hr": "hours", "sec": "seconds", "day": "days"}.get(unit, unit)
        if "-" in qty:
            lo, hi = qty.split("-")
            text = f"{lo} to {hi} {words}"
        else:
            text = f"{qty} {words[:-1] if qty == '1' else words}"
        if rep > 1:
            text += f" × {rep}"
        parts.append(text)
    return ", then ".join(parts) if parts else body.strip()


_SIGIL_NOISE_NAMES = {"timer", "time", "t", "x"}


def timer_in_prose(name: Optional[str], body: str, surrounding: str) -> str:
    """A sigil in prose → its human timing, keeping the sigil's name when the sentence does
    not already say it: `~per-side{2-3%min × 2}` → "2 to 3 minutes per side × 2", but
    `~toast{2%min}` in "Toast the cumin …" → "2 minutes"."""
    human = render_timer_human(body)
    word = _humanize(name or "").strip().lower()
    if len(word) < 3 or word in _SIGIL_NOISE_NAMES:
        return human
    if re.search(r"(?<![A-Za-z])" + re.escape(word), TIMER.sub(" ", surrounding), re.IGNORECASE):
        return human
    head, sep, rep = human.rpartition(" × ")
    return f"{head} {word}{sep}{rep}" if sep else f"{human} {word}"


def render_prose(prose: str) -> str:
    """DSL prose → plain text with `[bracketed]` ingredient phrases (the legacy node
    convention the playback uses for per-step needs)."""
    base = absorb_prep_slot(prose)
    text = TIMER.sub(lambda m: timer_in_prose(m.group(1), m.group(2) or "", base), base)

    def part_def(m):
        slug, qty = _humanize(m.group(1)), m.group(3).strip()
        if not qty:
            return f"[{slug}]"
        stem = slug.split()[-1].lower().rstrip("s")[:5]
        return f"[{qty}]" if stem and stem in qty.lower() else f"[{qty} {slug}]"

    text = ING_PART_DEF.sub(part_def, text)
    text = ING_PART_REF.sub(lambda m: f"[{_humanize(m.group(1))}]", text)
    text = ING_DEF.sub(lambda m: f"[{m.group(2).strip() or _humanize(m.group(1))}]", text)
    text = EQ_DEF.sub(lambda m: _humanize(m.group(1)), text)
    text = ING_REF.sub(lambda m: f"[{_humanize(m.group(1))}]", text)
    text = EQ_REF.sub(lambda m: _humanize(m.group(1)), text)
    text = STEP_REF.sub(lambda m: _humanize(m.group(1).strip()), text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_meta(meta: Optional[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in re.finditer(r"(\w+)=(\[[^\]]*\]|\S+)", meta or ""):
        out[m.group(1)] = m.group(2)
    return out


def parse_depends_on(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if not isinstance(value, str):
        return []
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        return [d.strip() for d in v[1:-1].split(",") if d.strip()]
    return [v] if v else []


def split_dsl(text: str) -> Tuple[Optional[str], str]:
    """Optional legacy `---` frontmatter is skipped; the title is the leading `# H1`."""
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    fm_title = None
    if len(parts) == 3:
        tm = re.search(r"^\s*title:\s*(.+?)\s*$", parts[1], re.MULTILINE)
        if tm:
            fm_title = tm.group(1).strip().strip("\"'")
        body = parts[2]
    else:
        body = text
    first_atom = re.search(r"^##\s+", body, re.MULTILINE)
    head = body[: first_atom.start()] if first_atom else body
    h1 = re.search(r"^\s*#\s+(.+?)\s*$", head, re.MULTILINE)
    return (fm_title or (h1.group(1).strip() if h1 else None)), body


def parse_atoms(body: str) -> List[Dict[str, Any]]:
    atoms: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for line in body.split("\n"):
        m = HEADER.match(line)
        if m:
            if current is not None:
                current["prose"] = current["prose"].strip()
                atoms.append(current)
            current = {"title": m.group(1).strip(), "meta": parse_meta(m.group(2)), "prose": ""}
        elif current is not None:
            current["prose"] += line + "\n"
    if current is not None:
        current["prose"] = current["prose"].strip()
        atoms.append(current)
    return atoms


def attention_share(meta: Dict[str, str]) -> Tuple[Optional[str], float]:
    """(level word or None, bandwidth share). Unset → 1.0 (DSL_SPEC §6 rule S)."""
    level = meta.get("attention_level")
    if level is not None:
        word = str(level).strip().lower()
        if word in ATTENTION_SHARE:
            return word, ATTENTION_SHARE[word]
    raw = meta.get("attention")
    if raw is not None:
        try:
            return None, max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    return None, 1.0


# ---------------------------------------------------------------------------
# Steps and the graph
# ---------------------------------------------------------------------------


@dataclass
class Step:
    id: str
    ordinal: int
    title: str
    text: str
    deps: List[str]
    kind: str  # timer | hands-on | watch | cue | instant
    occupies: bool
    scheduled: float
    countdowns: List[Tuple[float, str]] = field(default_factory=list)  # one iteration
    count: int = 1  # DSL count= or legacy repeat
    timer_total: float = 0.0  # one iteration
    surplus: float = 0.0  # DSL: duration − sigil total, per iteration, when positive
    done_when: Optional[str] = None  # legacy `until` as exported
    needs: List[str] = field(default_factory=list)
    prep: bool = False
    source: str = "nodes"
    attention: Optional[str] = None
    duration: float = 0.0
    time: Optional[float] = None
    structure: str = ""  # printed timer structure, e.g. "5 min, then 10 min"

    @property
    def is_timer(self) -> bool:
        return self.kind == "timer"

    @property
    def spoken_done_when(self) -> Optional[str]:
        """`until` with the projection's trailing '(×N)' dropped — the count is spoken."""
        if self.done_when is None:
            return None
        if self.count > 1:
            return re.sub(r"\s*\(\s*[×x]\s*\d+\s*\)\s*$", "", self.done_when).strip() or self.done_when
        return self.done_when


@dataclass
class Graph:
    title: str
    steps: List[Step]
    source: str  # dsl | nodes | md-steps | md-list
    ingredients: List[str]
    warnings: List[str] = field(default_factory=list)

    @property
    def by_id(self) -> Dict[str, Step]:
        return {s.id: s for s in self.steps}


def _timer_structure(countdowns: List[Tuple[float, str]], count: int, segments: List[Tuple[float, str, int]]) -> str:
    """Printed structure of a sigiled atom: '5 min, then 10 min'; '2 min × 2'; '3 min × 3'."""
    parts = []
    for minutes, label, rep in segments:
        piece = fmt_minutes(minutes)
        qty = label.split(" ")[0]
        if "-" in qty:
            piece += f" ({label} at the low bound)"
        if rep > 1:
            piece += f" × {rep}"
        parts.append(piece)
    text = ", then ".join(parts)
    if count > 1:
        if len(segments) == 1 and segments[0][2] == 1:
            text += f" × {count}"
        else:
            text += f", × {count} iterations"
    return text


def steps_from_dsl(text: str) -> Tuple[Optional[str], List[Step], List[str], List[str]]:
    """Atoms → steps. Notes never schedule; derived atoms do (they are prep work)."""
    title, body = split_dsl(text)
    atoms = parse_atoms(body)
    warnings: List[str] = []
    ingredients: List[str] = []
    for atom in atoms:
        for m in ING_DEF.finditer(absorb_prep_slot(atom["prose"])):
            phrase = m.group(2).strip()
            if phrase:
                ingredients.append(phrase)
    real = [a for a in atoms if a["meta"].get("type") != "note"]
    note_ids = {slugify(a["title"]) for a in atoms if a["meta"].get("type") == "note"}
    ids: List[str] = []
    for atom in real:
        sid = slugify(atom["title"]) or f"atom-{len(ids) + 1}"
        base, n = sid, 2
        while sid in ids:
            sid = f"{base}-{n}"
            n += 1
        if sid != base:
            warnings.append(f"two atoms slugify to '{base}'; the later one is read as '{sid}'")
        ids.append(sid)
    known = set(ids)
    steps: List[Step] = []
    for ordinal, (atom, sid) in enumerate(zip(real, ids), 1):
        meta = atom["meta"]
        prose = atom["prose"]
        count = max(1, _to_int(meta.get("count", meta.get("iteration")), 1))
        duration_raw = meta.get("duration", meta.get("active"))
        duration = _to_float(duration_raw) or 0.0
        level, share = attention_share(meta)
        occupies = share > 0.0
        deps = []
        for d in parse_depends_on(meta.get("depends_on")):
            nd = d.replace("_", "-")
            if nd in note_ids and nd not in known:
                continue
            if nd in known:
                # A self-reference is kept: it is a one-step cycle for find_cycle to refuse.
                if nd not in deps:
                    deps.append(nd)
            else:
                warnings.append(f"'{atom['title']}' depends on '{d}', which is not an atom of this recipe; ignored")
        segments: List[Tuple[float, str, int]] = []
        for m in TIMER.finditer(prose):
            segments.extend(parse_timer_body(m.group(2) or ""))
        countdowns: List[Tuple[float, str]] = []
        for minutes, label, rep in segments:
            countdowns.extend([(minutes, label)] * rep)
        timer_total = sum(m for m, _ in countdowns)
        is_timer = bool(countdowns)
        scheduled = max(duration, timer_total) * count
        surplus = duration - timer_total if is_timer and duration > timer_total + EPS else 0.0
        if is_timer:
            kind = "timer"
        elif scheduled <= 0:
            kind = "instant"
        elif occupies:
            kind = "hands-on"
        else:
            kind = "watch"
        text_out = render_prose(prose)
        steps.append(Step(
            id=sid, ordinal=ordinal, title=atom["title"], text=text_out, deps=deps, kind=kind,
            occupies=occupies, scheduled=scheduled, countdowns=countdowns, count=count,
            timer_total=timer_total, surplus=surplus, done_when=None,
            needs=bracketed_needs(text_out), prep=atom["title"].lower().startswith("prep:"),
            source="dsl", attention=level if level else ("unset" if meta.get("attention") is None else "numeric"),
            duration=duration, structure=_timer_structure(countdowns, count, segments) if is_timer else "",
        ))
    return title, steps, ingredients, warnings


def _legacy_step(ordinal: int, sid: str, title: str, text: str, deps: List[str],
                 time: Optional[float], until: Optional[str], repeat: int, source: str) -> Step:
    per = time or 0.0
    is_timer = until is not None and per > 0
    scheduled = per * repeat
    if is_timer:
        kind = "timer"
    elif per > 0:
        kind = "hands-on"
    elif until is not None:
        kind = "cue"
    else:
        kind = "instant"
    countdowns = [(per, fmt_minutes(per))] * repeat if is_timer else []
    structure = ""
    if is_timer:
        structure = fmt_minutes(per) + (f" × {repeat}" if repeat > 1 else "")
    return Step(
        id=sid, ordinal=ordinal, title=title, text=text, deps=deps, kind=kind,
        occupies=(kind == "hands-on"), scheduled=scheduled, countdowns=countdowns, count=repeat,
        timer_total=per if is_timer else 0.0, surplus=0.0, done_when=until,
        needs=bracketed_needs(text), prep=title.lower().startswith("prep:"), source=source,
        time=time, structure=structure,
    )


def steps_from_nodes(nodes: List[Any]) -> Tuple[List[Step], List[str]]:
    warnings: List[str] = []
    prepared = []
    ids: List[str] = []
    for pos, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            node = {"text": str(node)}
        raw_id = node.get("id")
        if raw_id is None or str(raw_id).strip() == "":
            sid = str(pos)
            warnings.append(f"node {pos} has no id; using its position ({pos})")
        else:
            sid = str(raw_id).strip()
            if re.fullmatch(r"\d+\.0", sid):
                sid = sid[:-2]
        base, n = sid, 2
        while sid in ids:
            sid = f"{base}-{n}"
            n += 1
        ids.append(sid)
        prepared.append((pos, sid, node))
    known = set(ids)
    steps: List[Step] = []
    for pos, sid, node in prepared:
        title = node.get("title")
        title = str(title).strip() if isinstance(title, str) and title.strip() else f"Step {pos}"
        text = node.get("text")
        text = str(text).strip() if isinstance(text, str) else ""
        raw_deps = node.get("dependencies")
        if isinstance(raw_deps, str):
            try:
                raw_deps = json.loads(raw_deps)
            except ValueError:
                raw_deps = [d.strip() for d in raw_deps.split(",") if d.strip()]
        if not isinstance(raw_deps, list):
            raw_deps = []
        deps: List[str] = []
        for d in raw_deps:
            ds = str(d).strip()
            if re.fullmatch(r"\d+\.0", ds):
                ds = ds[:-2]
            if ds in known:
                # A self-reference is kept (it is a one-step cycle for find_cycle to refuse);
                # the warning below is only for ids no node carries.
                if ds not in deps:
                    deps.append(ds)
            else:
                warnings.append(f"'{title}' depends on id {ds!r}, which no node carries; ignored")
        until = node.get("until")
        until = until.strip() if isinstance(until, str) and until.strip() else None
        repeat = max(1, _to_int(node.get("repeat"), 1)) if node.get("repeat") is not None else 1
        steps.append(_legacy_step(pos, sid, title, text, deps, _to_float(node.get("time")), until, repeat, "nodes"))
    return steps, warnings


def steps_from_markdown(md_steps: List[Dict[str, Any]], legacy: bool) -> List[Step]:
    """Enriched Markdown step lines, or a legacy numbered list (Prep: first, serial)."""
    if legacy:
        ordered = [s for s in md_steps if (s["title"] or "").lower().startswith("prep:")] + \
                  [s for s in md_steps if not (s["title"] or "").lower().startswith("prep:")]
        steps = []
        prev: Optional[str] = None
        for pos, s in enumerate(ordered, 1):
            sid = str(s["ordinal"])
            step = _legacy_step(pos, sid, s["title"], s["text"], [prev] if prev else [], None, None, 1, "md-list")
            steps.append(step)
            prev = sid
        return steps
    steps = []
    for s in md_steps:
        sid = str(s["ordinal"])
        deps = [str(k) for k in s["deps"] if 1 <= k <= len(md_steps)]  # a self-reference stays: find_cycle refuses it
        if s["timer_min"] is not None:
            step = _legacy_step(s["ordinal"], sid, s["title"], s["text"], deps, s["timer_min"], s["until"], s["repeat"], "md-steps")
        elif s["cue"] is not None:
            step = _legacy_step(s["ordinal"], sid, s["title"], s["text"], deps, None, s["cue"], 1, "md-steps")
        elif s["hands_min"] is not None:
            step = _legacy_step(s["ordinal"], sid, s["title"], s["text"], deps, s["hands_min"], None, s["hands_repeat"], "md-steps")
        else:
            step = _legacy_step(s["ordinal"], sid, s["title"], s["text"], deps, None, None, 1, "md-steps")
        steps.append(step)
    return steps


def find_cycle(steps: List[Step]) -> Optional[List[str]]:
    by_id = {s.id: s for s in steps}
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {s.id: WHITE for s in steps}
    stack: List[str] = []

    def visit(sid: str) -> Optional[List[str]]:
        colour[sid] = GREY
        stack.append(sid)
        for d in by_id[sid].deps:
            if colour.get(d) == GREY:
                return stack[stack.index(d):] + [d]
            if colour.get(d) == WHITE:
                found = visit(d)
                if found:
                    return found
        stack.pop()
        colour[sid] = BLACK
        return None

    for s in steps:
        if colour[s.id] == WHITE:
            found = visit(s.id)
            if found:
                return found
    return None


def build_graph(recipe: Recipe) -> Graph:
    warnings: List[str] = []
    ingredients = list(recipe.ingredients)
    if recipe.dsl:
        title, steps, dsl_ingredients, w = steps_from_dsl(recipe.dsl)
        warnings += w
        source = "dsl"
        if not ingredients:
            ingredients = dsl_ingredients
        nodes, _ = parse_nodes(recipe.nodes)
        if nodes:
            warnings.append("this recipe carries both DSL and legacy nodes; the DSL wins and the nodes are ignored")
    elif recipe.md_steps:
        steps = steps_from_markdown(recipe.md_steps, recipe.md_legacy)
        source = "md-list" if recipe.md_legacy else "md-steps"
    else:
        nodes, w = parse_nodes(recipe.nodes)
        if w:
            warnings.append(w)
        if not nodes:
            raise ExportError(f"{recipe.label} has no steps in this export.")
        steps, w2 = steps_from_nodes(nodes)
        warnings += w2
        source = "nodes"
    if not steps:
        raise ExportError(f"{recipe.label} has no steps in this export.")
    cycle = find_cycle(steps)
    if cycle:
        by_id = {s.id: s for s in steps}
        if len(cycle) == 2 and cycle[0] == cycle[1]:
            # find_cycle reports a self-edge as [id, id]: one step that depends on itself.
            s = by_id[cycle[0]]
            loop = f"step {s.ordinal} ({s.title}, id {s.id}) depends on itself"
        else:
            chain = " → ".join(f"step {by_id[c].ordinal} ({by_id[c].title}, id {c})" for c in cycle)
            loop = f"its steps depend on each other in a loop — {chain}"
        raise CycleDetected(
            f"Cannot plan {recipe.label}: {loop}. "
            "No step can be offered until the export's dependencies are fixed."
        )
    return Graph(title=recipe.label, steps=steps, source=source, ingredients=ingredients, warnings=warnings)


# ---------------------------------------------------------------------------
# Ordering, waves, the backward pass and the one-cook simulation
# ---------------------------------------------------------------------------


def topo_order(steps: List[Step]) -> List[Step]:
    by_id = {s.id: s for s in steps}
    seen: set = set()
    out: List[Step] = []

    def visit(s: Step) -> None:
        if s.id in seen:
            return
        seen.add(s.id)
        for d in s.deps:
            if d in by_id:
                visit(by_id[d])
        out.append(s)

    for s in steps:
        visit(s)
    return out


def waves(graph: Graph) -> List[List[Step]]:
    """Dependency depth, the mise-en-place grouping only: wave 1 has no dependencies."""
    depth: Dict[str, int] = {}
    for s in topo_order(graph.steps):
        depth[s.id] = 1 + max((depth[d] for d in s.deps), default=-1) if s.deps else 0
    out: List[List[Step]] = []
    for s in graph.steps:
        while len(out) <= depth[s.id]:
            out.append([])
        out[depth[s.id]].append(s)
    for wave in out:
        wave.sort(key=lambda s: (0 if s.prep else 1, s.ordinal))
    return out


def effective_minutes(step: Step, running: Dict[str, float]) -> float:
    """A running step contributes only the whole minutes left on it."""
    return float(running[step.id]) if step.id in running else step.scheduled


def latest_start(graph: Graph, done: set, running: Dict[str, float]) -> Dict[str, float]:
    """The live client's backward pass (cooking_step.dart _calculateCriticalPath):
    total = Σ remaining minutes; a sink's LST = total − its minutes; otherwise the
    minimum LST of its unresolved dependents − its minutes."""
    unresolved = [s for s in graph.steps if s.id not in done]
    total = sum(effective_minutes(s, running) for s in unresolved)
    dependents: Dict[str, List[Step]] = {s.id: [] for s in graph.steps}
    for s in unresolved:
        for d in s.deps:
            if d in dependents:
                dependents[d].append(s)
    lst: Dict[str, float] = {}
    for s in reversed(topo_order(graph.steps)):
        if s.id in done:
            continue
        mins = effective_minutes(s, running)
        deps_lst = [lst[t.id] for t in dependents[s.id] if t.id in lst]
        lst[s.id] = (min(deps_lst) if deps_lst else total) - mins
    return lst


def order_key(step: Step, lst: Dict[str, float]):
    """Latest start time first; ties: timer, then Prep:, then dependency-free, then node order."""
    return (lst.get(step.id, float("inf")), 0 if step.is_timer else 1, 0 if step.prep else 1,
            0 if not step.deps else 1, step.ordinal)


def available_steps(graph: Graph, done: set, running: Dict[str, float], lst: Dict[str, float]) -> List[Step]:
    avail = [s for s in graph.steps if s.id not in done and s.id not in running
             and all(d in done for d in s.deps)]
    return sorted(avail, key=lambda s: order_key(s, lst))


def simulate(graph: Graph, done: set, running: Dict[str, float], lst: Dict[str, float]) -> float:
    """One cook: zero-time steps resolve instantly; non-occupying steps (legacy timers,
    DSL none/low atoms) run in parallel; at most one hands-on step at a time, chosen by
    earliest latest start. Running steps are already in progress at minute 0 with their
    remainder. Mirrors cooking_step.dart computeRemainingTime."""
    resolved = set(done)
    timers: Dict[str, float] = {}
    active: Dict[str, float] = {}
    for sid, rem in running.items():
        step = graph.by_id[sid]
        if rem <= 0:
            resolved.add(sid)
        elif step.occupies:
            active[sid] = float(rem)
        else:
            timers[sid] = float(rem)
    pending = [s for s in graph.steps if s.id not in resolved and s.id not in running]
    t = 0.0
    guard = 0
    while pending or timers or active:
        guard += 1
        if guard > 100000:
            break
        # Start everything that can start at this instant, whether or not hands-on work
        # is under way: zero-time steps resolve at once (and may unlock more), every
        # non-occupying step (a legacy timer, a none/low atom) starts the moment its
        # dependencies are resolved, and one occupying step is picked only while no
        # occupying step is active — the one-hands-on rule holds back hands-on work only.
        while True:
            avail = [s for s in pending if all(d in resolved for d in s.deps)]
            instant = [s for s in avail if effective_minutes(s, running) <= 0]
            if not instant:
                break
            for s in instant:
                resolved.add(s.id)
                pending.remove(s)
        for s in [s for s in avail if not s.occupies]:
            timers[s.id] = t + s.scheduled
            pending.remove(s)
        if not active:
            cands = [s for s in avail if s.occupies]
            if cands:
                pick = min(cands, key=lambda s: order_key(s, lst))
                active[pick.id] = t + pick.scheduled
                pending.remove(pick)
        if not active and not timers:
            break  # nothing under way and nothing startable: unreachable in a DAG
        t = min(list(active.values()) + list(timers.values()))
        for sid in [k for k, v in active.items() if v <= t + EPS]:
            del active[sid]
            resolved.add(sid)
        for sid in [k for k, v in timers.items() if v <= t + EPS]:
            del timers[sid]
            resolved.add(sid)
    return t


# ---------------------------------------------------------------------------
# Rendering steps
# ---------------------------------------------------------------------------


def timing_text(step: Step, spoken: bool = True) -> str:
    """The step's timing: Timer / Done when / ~N min / watch — per the timer rule."""
    if step.kind == "timer":
        if step.source == "dsl":
            text = f"Timer: {step.structure}"
            n = len(step.countdowns) * step.count
            if n > 1:
                text += f" ({n} countdowns, one at a time)"
            if step.surplus > EPS:
                # The surplus is per iteration (cook-playback: "N = duration − sigil total,
                # both per-iteration figures"), so with count > 1 it lands after EVERY
                # iteration's last ring and the step is count × (timer total + surplus).
                more = f"about {fmt_minutes(step.surplus)} more on this step"
                if step.count > 1:
                    when = "after each ring" if len(step.countdowns) == 1 else "after each iteration's last ring"
                    text += (f" — {when} {more} (duration {fmt_minutes(step.duration)} per iteration; "
                             f"{fmt_minutes(step.scheduled)} in all)")
                else:
                    text += f" — after the last ring {more} (duration {fmt_minutes(step.duration)})"
            return text
        cue = step.spoken_done_when if spoken else step.done_when
        text = f"Timer: {step.structure}"
        if step.count > 1:
            text += f" ({step.count} countdowns, one at a time)"
        return text + f" — done when {cue}"
    if step.kind == "cue":
        return f"Done when: {step.done_when}"
    if step.kind == "hands-on":
        if step.source == "dsl":
            return f"~{fmt_minutes(step.scheduled)} hands-on"
        per = step.time or 0.0
        text = f"~{fmt_minutes(per)}"
        if step.count > 1:
            text += f" × {step.count} (about {fmt_minutes(step.scheduled)} in all)"
        text += " hands-on"
        return text
    if step.kind == "watch":
        # A sigil-less none/low atom: read as written, "about N min" at most — no countdown,
        # no clock time, no watching instruction, nothing proposed (cook-playback, "Timer
        # steps are exactly the `until` steps (nodes) and the `~timer{}` atoms (DSL)").
        return f"about {fmt_minutes(step.scheduled)} — no timer, no clock time; does not occupy you"
    return ""


def timed_nodes(content: Recipe) -> List[Dict[str, Any]]:
    """The app's own timer steps of a row, read beside its DSL: every `nodes[]` entry with
    `until` set and `time > 0` (the legacy timer rule), as {title, minutes, repeat} in node
    order, `minutes` per iteration. On `--md` the section's parsed step list stands in for
    `nodes[]`: a `Timer:` step line is such a step."""
    out: List[Dict[str, Any]] = []
    nodes, _ = parse_nodes(content.nodes)
    for pos, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            continue
        until = node.get("until")
        minutes = _to_float(node.get("time")) or 0.0
        if isinstance(until, str) and until.strip() and minutes > 0:
            title = node.get("title")
            title = str(title).strip() if isinstance(title, str) and title.strip() else f"Step {pos}"
            repeat = max(1, _to_int(node.get("repeat"), 1)) if node.get("repeat") is not None else 1
            out.append({"title": title, "minutes": minutes, "repeat": repeat})
    for s in content.md_steps or []:
        if s.get("timer_min") is not None and s["timer_min"] > 0:
            out.append({"title": s["title"], "minutes": float(s["timer_min"]), "repeat": max(1, _to_int(s.get("repeat"), 1))})
    return out


def timers_notice(content: Recipe, graph: Graph) -> Optional[Dict[str, Any]]:
    """The notice of cook-playback "Timerless DSL: cooked as written, one question before the
    first step": present if and only if the recipe is cooked from its `dsl`, that DSL carries
    zero `~timer{}` sigils (TIMER finds none) and the row's app steps carry at least one
    timer step — the two conditions decide, never the export version. It states the facts
    for the assistant's one question; the DSL is still cooked as written: no fallback to the
    nodes, no sigil inferred, no countdown, no clock time."""
    if graph.source != "dsl" or not content.dsl or TIMER.search(content.dsl):
        return None
    steps = timed_nodes(content)
    if not steps:
        return None
    return {"dsl": 0, "nodes": len(steps), "steps": steps}


def timers_notice_line(notice: Dict[str, Any]) -> str:
    """`Note: the Fond-format steps carry no timers; the app's steps for this recipe had N
    (<title> <time> min[ × R], …)` — the spec's wording; R only when the node repeats."""
    parts = []
    for s in notice["steps"]:
        part = f"{s['title']} {s['minutes']:g} min"
        if s["repeat"] > 1:
            part += f" × {s['repeat']}"
        parts.append(part)
    return (f"Note: the Fond-format steps carry no timers; the app's steps for this recipe had "
            f"{notice['nodes']} ({', '.join(parts)})")


def short_title(step: Step) -> str:
    """The title for a one-line mention. A step whose title is its whole text (a version-1
    Markdown line) is cut at its first clause, on a word boundary, never mid-word."""
    if step.title != step.text:
        return step.title
    m = re.match(r"^(.{3,}?[^\s,;:.])[,;:.](?:\s|$)", step.text)
    head = m.group(1) if m else step.text
    if len(head) > 72:
        head = head[:72].rsplit(" ", 1)[0] + "…"
    return head


def dep_ordinals(step: Step, graph: Graph) -> str:
    """'(after step k, …)' where k is the printed ordinal of the dependency."""
    by_id = graph.by_id
    ks = [str(by_id[d].ordinal) for d in step.deps if d in by_id]
    return f"(after step {', '.join(ks)})" if ks else ""


def step_line(step: Step, graph: Graph, spoken: bool = True) -> str:
    parts = [f"{step.title}"]
    if step.text and step.text != step.title:
        parts.append(step.text)
    timing = timing_text(step, spoken)
    if timing:
        parts.append(timing)
    after = dep_ordinals(step, graph)
    line = " — ".join(parts)
    if after:
        line += f" {after}"
    return line


def step_json(step: Step, graph: Graph, lst: Dict[str, float], done: set, running: Dict[str, float],
              held: Optional[set] = None) -> Dict[str, Any]:
    held = held or set()
    return {
        "id": step.id, "ordinal": step.ordinal, "title": step.title, "text": step.text,
        "kind": step.kind, "occupies": step.occupies, "scheduled": step.scheduled,
        "countdowns": [[m, label] for m, label in step.countdowns], "count": step.count,
        "timer_total": step.timer_total, "surplus": step.surplus, "structure": step.structure,
        "done_when": step.spoken_done_when, "done_when_raw": step.done_when,
        "needs": step.needs, "prep": step.prep,
        "deps": list(step.deps), "after": [graph.by_id[d].ordinal for d in step.deps if d in graph.by_id],
        "latest_start": lst.get(step.id), "attention": step.attention, "duration": step.duration,
        "time": step.time, "timing": timing_text(step),
        "state": "done" if step.id in done else "running" if step.id in running
        else "held" if step.id in held
        else "available" if all(d in done for d in step.deps) else "locked",
        "remaining": running.get(step.id),
    }


# ---------------------------------------------------------------------------
# Title lookup
# ---------------------------------------------------------------------------


# The marks `_norm` folds away: the accents a precomposed Latin, Greek or Cyrillic letter
# decomposes into (Combining Diacritical Marks and their extensions), Hebrew points and
# Arabic harakat — each written or left out, so "Crème" is typed "creme" and "שָׁלוֹם" "שלום".
# Every other mark spells the word and stays in the key: Kana voicing (パ ≠ ハ), Indic
# vowel signs and the virama (दिन ≠ दीन), Thai vowels and tones (ข้าว ≠ ข่าว ≠ ขาว).
_FOLDED_MARKS = ((0x0300, 0x036F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF), (0x20D0, 0x20FF), (0xFE20, 0xFE2F),
                 (0x0591, 0x05C7), (0x0610, 0x061A), (0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06ED))
# Latin letters NFKD leaves whole, folded to the spelling people type without them, so a
# short title ("Œuf") is still found by "oeuf" rather than falling under the fuzzy cutoff.
_LATIN_FOLD = {"ø": "o", "œ": "oe", "æ": "ae", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i", "ħ": "h"}
# Variation selectors are marks that pick a glyph (the emoji presentation of ❤️), not letters.
_VARIATION_SELECTORS = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))


def _in_ranges(c: str, ranges: Tuple[Tuple[int, int], ...]) -> bool:
    o = ord(c)
    return any(lo <= o <= hi for lo, hi in ranges)


def _norm(s: str) -> str:
    """Lookup key for a title (and for the title a cook row carries): case-folded, the
    Latin/Greek/Cyrillic accents and Hebrew/Arabic points folded away, every other mark
    kept with its word, every letter or digit of any script kept, punctuation and runs of
    whitespace collapsed to one space. "Crème brûlée" and "creme brulee" share a key;
    "汤" and "面" keep their own, and so do "パン" and "ハン", "दिन" and "दीन". A title or
    query that folds to nothing (punctuation only) gets the empty key, and every caller
    treats an empty key as "no match" — two unrelated titles never meet on "". The key is
    NFC-composed, so the fuzzy pass scores a voiced kana or a Hangul syllable as one
    character, not as a base plus a mark it half-matches."""
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not (unicodedata.combining(c) and _in_ranges(c, _FOLDED_MARKS)))
    s = "".join(_LATIN_FOLD.get(c, c) for c in s)

    def keep(c: str) -> bool:
        return c.isalnum() or (unicodedata.category(c) in ("Mn", "Mc") and not _in_ranges(c, _VARIATION_SELECTORS))

    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", "".join(c if keep(c) else " " for c in s)).strip())


def find_recipe(export: Export, query: str) -> Recipe:
    """Exact id/handle/title first, then substring, then fuzzy; several → ask."""
    q = query.strip()
    if not q:
        raise ExportError("Give a recipe title (or its Fond id or handle).", code=2)
    rows = export.all_recipes()
    for r in rows:
        if (r.id and r.id == q) or (r.handle and r.handle == q):
            return _refuse_collided(export, r)
    nq = _norm(q)
    # An empty key — a query of punctuation only, or a title that folds to nothing — matches
    # no row on any pass: exact, substring and fuzzy all need a non-empty key on both sides.
    # The one exception is the title's own spelling (whitespace-trimmed): "???" reaches
    # the recipe titled "???" instead of a hint that lists the very title typed.
    exact = [r for r in rows if r.title and ((nq and _norm(r.title) == nq) or r.title.strip() == q)]
    if not exact:
        exact = [r for r in rows if r.title and nq and nq in _norm(r.title)]
    if not exact and nq:
        # normalized title → every row carrying it, so two creators' recipes that share a
        # title both survive the fuzzy pass and reach the "which one?" answer below rather
        # than whichever came last winning silently (cook-playback, "ambiguous title").
        titles: Dict[str, List[Recipe]] = {}
        for r in rows:
            key = _norm(r.title) if r.title else ""
            if key:
                titles.setdefault(key, []).append(r)
        # difflib scores a key character by character, so a short key — three ideographs, one
        # short Latin word — clears 0.6 with a third of it wrong (红烧鱼 vs 红烧肉: 0.67, and a
        # lone candidate would be presented silently); a short key must come closer.
        cutoff = 0.6 if len(nq) >= 6 else 0.8
        close = difflib.get_close_matches(nq, list(titles.keys()), n=5, cutoff=cutoff)
        exact = [r for c in close for r in titles[c]]
    exact = _dedupe_refs(export, exact)
    if len(exact) == 1:
        return _refuse_collided(export, exact[0])
    if export.local and len(exact) > 1 and len({r.id for r in exact}) == 1:
        # Every candidate is one collided local id (the files share a title as well as a
        # basename): "which one?" would point at the very id that cannot answer.
        return _refuse_collided(export, exact[0])
    if not exact:
        names = ", ".join(f"'{r.label}'" for r in _dedupe_refs(export, rows)[:12] if r.title)
        raise ExportError(f"No recipe in this export matches '{query}'. Titles here: {names}", code=2)
    lines = [f"Several recipes match '{query}' — which one?"]
    for r in exact:
        # Through the one row renderer, so each candidate carries its by-line (which already
        # holds the handle, or the id when there is no handle) and its lineage line.
        lines += row_lines({"title": r.label, **provenance_fields(r, export)},
                           f" (Fond id {r.id})" if r.id and r.handle else "")
    lines.append("Say the title, or pass the Fond id or handle.")
    raise ExportError("\n".join(lines), code=2)


def _refuse_collided(export: Export, recipe: Recipe) -> Recipe:
    """A local id two or more files share names none of them (recipe-authoring "The local
    id", the collision rule): the lookup refuses with the one line naming the files, exit 1,
    rather than handing back whichever file sorted first. An export row passes through."""
    if export.local:
        group = [r for r in export.authored if r.id == recipe.id]
        if len(group) > 1:
            raise ExportError(collision_line(group), code=1)
    return recipe


def _dedupe_refs(export: Export, rows: List[Recipe]) -> List[Recipe]:
    """A saved copy of the user's own recipe and the authored row are one recipe."""
    out: List[Recipe] = []
    seen_content = set()
    for r in rows:
        c = export.content_of(r)
        key = id(c) if c is not None else id(r)
        if key in seen_content:
            continue
        seen_content.add(key)
        out.append(c if (c is not None and c is not r and c.kind == "authored") else r)
    return out


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def cook_counts(cook: Dict[str, Any]) -> bool:
    """A cook counts when its status is in the app's set and it was not removed from
    history (`deleted`, a version-2 flag; absent on a version-1 row means not removed)."""
    return cook.get("status") in COUNTED_COOK_STATUSES and not bool(cook.get("deleted", False))


def cook_recipe_counted(cr: Dict[str, Any], cook: Dict[str, Any]) -> bool:
    """The app's own rule for a recipe within a cook: `isValid`, or `userOverride` (an
    invalid cook the user marked as cooked), or the row's `status` is `migrated` (a
    pre-Flutter cook whose isValid came from a heuristic). A version-1 row has neither
    `status` nor `userOverride`: the cook's own `status: "migrated"` stands in for the
    recipe's (the migration wrote both) and `userOverride` is taken as false."""
    if bool(cr.get("isValid")):
        return True
    if bool(cr.get("userOverride", False)):
        return True
    status = cr["status"] if "status" in cr else cook.get("status")
    return status == "migrated"


# A cook row with no `id` is attributed by title. Every Markdown cook line is such a row:
# the renderer prints "- <title> — completed …; <ratings>" and nothing else, so when two
# recipes in the export share a title the Markdown cannot say which one was cooked. Such
# rows are kept under this prefix and credited to neither (ambiguous_cooks).
AMBIGUOUS_PREFIX = "ambiguous:"
# The counted_cooks key for a counted row that names no recipe at all — no id and no
# title: a Markdown cook line that reads as two titles (_md_cooks). Never a "title:" key,
# so a recipe actually titled "None" is never confused with it.
UNCREDITED_BUCKET = "uncredited:"


def title_candidates(export: Export) -> Dict[str, List[str]]:
    """normalized title → the distinct content keys carrying it. A saved copy of the
    user's own recipe folds into the authored row (one key), so it is never a collision."""
    out: Dict[str, List[str]] = {}
    for r in export.all_recipes():
        c = export.content_of(r) or r
        key = _norm(r.title) if r.title else ""
        if key:  # a title that folds to nothing is never the one a cook line names
            keys = out.setdefault(key, [])
            if c.key not in keys:
                keys.append(c.key)
    return out


def counted_cooks(export: Export) -> Dict[str, List[Dict[str, Any]]]:
    """content id → counted cook entries [{cook, recipe}]: cooks that count (status in the
    app's set, not removed from history) and, within them, the recipe rows that count
    (cook_recipe_counted). A row with no `id` (every Markdown cook line) resolves by
    normalized title only when exactly one recipe in the export carries that title; when
    two or more do, the row lands under AMBIGUOUS_PREFIX + title and is attributed to
    neither — a cook, a rating and a by-line are never handed to the wrong creator. A
    title no recipe carries lands under "title:<title>"; a row with neither id nor title
    (a Markdown line that reads as two titles) under UNCREDITED_BUCKET."""
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    candidates = title_candidates(export)
    for cook in export.cooks:
        if not cook_counts(cook):
            continue
        for cr in cook.get("recipes") or []:
            if not isinstance(cr, dict) or not cook_recipe_counted(cr, cook):
                continue
            rid = str(cr["id"]) if cr.get("id") is not None else None
            if rid is None and isinstance(cr.get("title"), str):
                key = _norm(cr["title"])
                keys = candidates.get(key, []) if key else []  # an empty key names no recipe
                if len(keys) == 1:
                    rid = keys[0]
                elif len(keys) > 1:
                    rid = AMBIGUOUS_PREFIX + key
            if rid is None:
                rid = f"title:{cr['title']}" if isinstance(cr.get("title"), str) else UNCREDITED_BUCKET
            by_id.setdefault(rid, []).append({"cook": cook, "recipe": cr})
    return by_id


def ambiguous_cooks(export: Export, counted: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """[{title, times, recipes: [Recipe]}] — one group per title that two or more recipes
    share and that has counted cook rows the export cannot attribute. Empty whenever every
    cook row carries an id (a JSON export). `recipes` are the presented rows (a saved copy
    of an own recipe shows as the authored row), in export order."""
    presented = _dedupe_refs(export, export.all_recipes())
    groups: List[Dict[str, Any]] = []
    for rid, entries in counted.items():
        if not rid.startswith(AMBIGUOUS_PREFIX):
            continue
        norm = rid[len(AMBIGUOUS_PREFIX):]
        recipes = [r for r in presented if r.title and _norm(r.title) == norm]
        title = next((e["recipe"].get("title") for e in entries if isinstance(e["recipe"].get("title"), str)), None)
        groups.append({"title": title or (recipes[0].label if recipes else "(untitled)"),
                       "times": len(entries), "recipes": recipes})
    return groups


def ambiguous_keys(export: Export, groups: List[Dict[str, Any]]) -> Set[str]:
    """The content keys of every recipe in an ambiguous_cooks group."""
    return {(export.content_of(r) or r).key for g in groups for r in g["recipes"]}


def _ambiguous_note(export: Export, group: Dict[str, Any]) -> str:
    why = ("from a Markdown export (its cook lines carry the title only); use the JSON" if export.from_markdown
           else "(these cook rows carry no Fond id)")
    return f"{len(group['recipes'])} recipes named {group['title']} — {group['times']} counted cook(s) cannot be attributed {why}"


def _candidate_rows(export: Export, group: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"id": r.id, "title": r.label, **provenance_fields(r, export)} for r in group["recipes"]]


def _candidate_lines(export: Export, group: Dict[str, Any], indent: str = "      ") -> List[str]:
    lines: List[str] = []
    for r in group["recipes"]:
        lines += row_lines({"title": r.label, **provenance_fields(r, export)},
                           f" (Fond id {r.id})" if r.id and r.handle else "", prefix=f"{indent}could be: ")
    return lines


def cook_when(entry: Dict[str, Any]) -> str:
    """A counted cook entry's date: the cook's `startedAt`, else its `completedAt` ("" when
    neither) — the one date `history`, `cook-again` and the verdict all compare."""
    return entry["cook"].get("startedAt") or entry["cook"].get("completedAt") or ""


def last_cooked(entries: List[Dict[str, Any]]) -> str:
    """The newest counted cook's date ("" when none carries one): "last cooked", which need
    not be the cook a rating came from (latest_rated)."""
    return max((cook_when(e) for e in entries), default="")


def latest_rated(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The ONE counted cook entry every rating summary reads (export-format §6): the latest
    that rated taste or would-cook-again. Its taste, wouldCookAgain and date travel together,
    never the best of each across cooks, so an old 5/5 never outlives a newer 1/5. A row
    carrying only `easyFollow` (what a migrated cook has at most) counts for frequency and
    recency, never as a rating."""
    rated = [e for e in entries if isinstance(e["recipe"].get("ratings"), dict)
             and any(e["recipe"]["ratings"].get(k) is not None for k in ("taste", "wouldCookAgain"))]
    if not rated:
        return None
    return max(rated, key=lambda e: (cook_when(e), e["recipe"].get("completedAt") or ""))


def verdict(entries: List[Dict[str, Any]]) -> Tuple[Optional[str], bool, Optional[Dict[str, Any]]]:
    """(hit|miss|ok|None, would cook again, the ratings used) from latest_rated's one cook."""
    rated = latest_rated(entries)
    if rated is None:
        return None, False, None
    ratings = rated["recipe"]["ratings"]
    taste = _to_float(ratings.get("taste"))
    again = _to_float(ratings.get("wouldCookAgain"))
    word = None
    if taste is not None:
        word = "hit" if taste >= 4 else "miss" if taste <= 2 else "ok"
    return word, bool(again is not None and again >= 4), ratings


def history_count(export: Export, recipe: Recipe, counted: Dict[str, List[Dict[str, Any]]]) -> int:
    c = export.content_of(recipe) or recipe
    n = len(counted.get(c.key, []))
    if recipe is not c and recipe.key != c.key:
        n += len(counted.get(recipe.key, []))
    return n


def _cook_row_is(cr: Dict[str, Any], recipe: Recipe) -> bool:
    """A cook's recipe row names this recipe: by id when both carry one, else by title
    (the Markdown history carries titles only)."""
    if cr.get("id") is not None and recipe.id:
        return str(cr["id"]) == recipe.id
    if not (cr.get("title") and recipe.title):
        return False
    key = _norm(str(cr["title"]))
    return bool(key) and key == _norm(recipe.title)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cook_count(export: Export, recipe: Recipe, counted: Dict[str, List[Dict[str, Any]]]) -> int:
    return max(history_count(export, recipe, counted), recipe.cook_count_field)


def partition(export: Export) -> Tuple[List[Recipe], List[Recipe]]:
    """(cookable, missing). Saved copies of the user's own recipes fold into the authored row."""
    cookable: List[Recipe] = []
    missing: List[Recipe] = []
    seen = set()
    for r in export.all_recipes():
        c = export.content_of(r)
        if c is not None and has_steps(c):
            if c is not r and c.kind == "authored":
                continue  # listed once, as the authored recipe
            if id(c) in seen:
                continue
            seen.add(id(c))
            cookable.append(r)
        else:
            missing.append(r)
    return cookable, missing


DEFAULT_MISSING_REASON = "saved, no steps in this export"


def _reason_suffix(reason: str) -> str:
    """' (recipe since deleted)' and the like; nothing for a reason the sentence already
    says ("… has no steps in this export")."""
    return "" if reason in (DEFAULT_MISSING_REASON, "no steps in this export") else f" ({reason})"


def missing_reason(recipe: Recipe, export: Export) -> str:
    if recipe.deleted:
        return "recipe since deleted"
    if recipe.ref and export.content_of(recipe) is None:
        return "points at one of your recipes that is not in this export"
    if recipe.title is None and recipe.kind == "saved":
        return "recipe no longer exists"
    if recipe.kind == "authored":
        return "no steps in this export"
    return DEFAULT_MISSING_REASON


def cmd_list(export: Export, as_json: bool) -> Dict[str, Any]:
    counted = counted_cooks(export)
    unattributed = ambiguous_keys(export, ambiguous_cooks(export, counted))
    cookable, missing = partition(export)
    out = {"export_version": export.version, "exported_at": export.exported_at,
           "cookable": [], "missing": [], "warnings": export.warnings}
    lines = [f"Fond export, version {export.version}" + (f", exported {export.exported_at}" if export.exported_at else "")
             + f" — {len(cookable)} recipe(s) you can cook, {len(missing)} saved without steps."]
    lines.append("")
    lines.append(f"Cookable ({len(cookable)}):")
    for r in cookable:
        c = export.content_of(r) or r
        n = _cook_count(export, r, counted)
        src = "DSL" if c.dsl else "steps"
        # A recipe sharing its title with another: the Markdown cook lines cannot say which
        # was cooked, so "not cooked yet" would be a guess (a saved row's own "cooked N×"
        # figure is the renderer's and stands).
        unsure = c.key in unattributed and n == 0
        entry = {"id": r.id, "content_id": c.id, "title": r.label, **provenance_fields(r, export),
                 "cooked": None if unsure else n, "source": src, "kind": r.kind}
        out["cookable"].append(entry)
        tail = (" — cooks not attributable (another recipe here shares this title; use the JSON)" if unsure
                else f" — cooked {n}×" if n else " — not cooked yet")
        lines += row_lines(entry, f" — {src}{tail}")
    if not cookable:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Saved, no steps in this export ({len(missing)}):")
    for r in missing:
        reason = missing_reason(r, export)
        # The same renderer as the cookable rows: a saved row whose steps the export's size
        # tier removed (`nodes` null) keeps its `lineage`, and that line must travel here too.
        entry = {"id": r.id, "title": r.title, **provenance_fields(r, export), "reason": reason}
        out["missing"].append(entry)
        lines += row_lines(entry, f" — {reason}")
    if not missing:
        lines.append("  (none)")
    for w in export.warnings:
        lines.append(f"Note: {w}")
    out["text"] = "\n".join(lines)
    return out


def cmd_missing(export: Export, as_json: bool) -> Dict[str, Any]:
    _cookable, missing = partition(export)
    lines = [f"Saved, no steps in this export ({len(missing)}):"]
    rows = []
    for r in missing:
        reason = missing_reason(r, export)
        entry = {"id": r.id, "title": r.title, "author": effective_author(r, export),
                 **provenance_fields(r, export), "url": r.url, "reason": reason}
        rows.append(entry)
        lines += row_lines(entry, f" — {reason}")
    if not missing:
        lines.append("  (none — every recipe in this export has steps)")
    return {"missing": rows, "text": "\n".join(lines)}


def _ingredient_lines(ingredients: List[str]) -> List[str]:
    if not ingredients:
        return ["  (no ingredient list in the export)"]
    return [f"  - {i}" for i in ingredients]


def cmd_show(export: Export, query: str, as_json: bool) -> Dict[str, Any]:
    recipe = find_recipe(export, query)
    content = export.content_of(recipe)
    lines = provenance_block(recipe, export, content)
    out: Dict[str, Any] = {"id": recipe.id, "handle": recipe.handle, "title": recipe.label, "url": recipe.url,
                           "author": effective_author(recipe, export), "byline": byline(recipe, export),
                           "sourceAuthor": recipe.source_author, "lineage": lineage_line(recipe.lineage),
                           "lineage_raw": recipe.lineage if recipe.lineage and "_line" not in recipe.lineage else None,
                           "cookable": has_steps(content), "ingredients": [], "steps": [], "dsl": None,
                           "warnings": []}
    if content is None or not has_steps(content):
        why = _reason_suffix(missing_reason(recipe, export))
        lines.append("")
        # The same branch as `plan`: only a row that carries a url is said to have one.
        where = (f"The original is at {recipe.url} — shown, never fetched unasked." if recipe.url
                 else "The export carries no source url for it.")
        lines.append(f"This recipe has no steps in this export{why}; it belonged to "
                     f"{author_text(recipe, export)}. {where}")
        out["text"] = "\n".join(lines)
        return out
    graph = build_graph(content)
    h = recipe_h(content)
    out["ingredients"] = graph.ingredients
    out["source"] = graph.source
    out["h"] = h
    out["warnings"] = graph.warnings
    if content.kind == "local":
        out["origin"] = content.origin
        lines += [f"  {note_line(n)}" for n in content.notes]
    lines.append("")
    lines.append(f"Ingredients ({len(graph.ingredients)}):")
    lines += _ingredient_lines(graph.ingredients)
    lines.append("")
    origin = ("the local file" if content.kind == "local" else "the DSL" if graph.source == "dsl"
              else "the exported step list")
    lines.append(f"Steps ({len(graph.steps)}, from {origin}, h={h}):")
    for s in graph.steps:
        lines.append(f"  {s.ordinal}. {step_line(s, graph, spoken=False)}")
        out["steps"].append({"ordinal": s.ordinal, "id": s.id, "title": s.title, "text": s.text,
                             "timing": timing_text(s, spoken=False), "after": [graph.by_id[d].ordinal for d in s.deps],
                             "kind": s.kind, "line": step_line(s, graph, spoken=False)})
    notice = timers_notice(content, graph)
    if notice:
        out["timers_notice"] = notice
        lines.append(timers_notice_line(notice))
    if content.dsl:
        out["dsl"] = content.dsl
        lines += ["", "Recipe DSL:", "```", content.dsl.rstrip(), "```"]
    for w in graph.warnings:
        lines.append(f"Note: {w}")
    out["text"] = "\n".join(lines)
    return out


def parse_done(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def parse_running(value: Optional[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not value:
        return out
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ExportError(f"--running expects <id>=<minutes-left>, got '{pair}'.", code=2)
        sid, _, mins = pair.partition("=")
        sid = sid.strip()
        try:
            n = int(mins.strip())
        except ValueError:
            raise ExportError(f"--running {pair}: minutes-left must be a whole number ≥ 0 "
                              "(pass 1 for a sub-minute remainder until it rings, then 0).", code=2)
        if n < 0:
            raise ExportError(f"--running {pair}: minutes-left must be ≥ 0.", code=2)
        out[sid] = n
    return out


def validate_state(graph: Graph, done: List[str], running: Dict[str, int]) -> None:
    by_id = graph.by_id
    ids = [s.id for s in graph.steps]
    listing = "This recipe's step ids: " + ", ".join(ids) + "."
    for sid in done:
        if sid not in by_id:
            raise ExportError(f"Unknown step id '{sid}' in --done. {listing}", code=2)
    for sid in running:
        if sid not in by_id:
            raise ExportError(f"Unknown step id '{sid}' in --running. {listing}", code=2)
        if sid in done:
            raise ExportError(f"Step '{sid}' is in both --done and --running; a running step is not resolved. {listing}", code=2)
    # A --done id resolves its whole prerequisite chain (implied_done), so a running id
    # inside that chain is the same contradiction as an id given to both flags. Checked
    # before the direct-prerequisite rule so an inconsistent state is named in one round
    # trip, not after the model has added the prerequisite that rule asked for.
    chains = {d: prerequisites(graph, d) for d in done}
    for sid in running:
        implied_by = [d for d in done if sid in chains[d]]
        if implied_by:
            raise ExportError(
                f"Step '{sid}' cannot be running: {', '.join(repr(d) for d in implied_by)} in --done depends on it "
                f"(directly or through other steps), so it would already be resolved. {listing}", code=2)
    for sid in running:
        missing_deps = [d for d in by_id[sid].deps if d not in done]
        if missing_deps:
            raise ExportError(
                f"Step '{sid}' cannot be running: it depends on {', '.join(repr(d) for d in missing_deps)}, "
                f"not in --done. {listing}", code=2)


def prerequisites(graph: Graph, sid: str) -> Set[str]:
    """Every step `sid` depends on, directly or through other steps (the transitive
    closure over `deps`; a cycle is refused by build_graph, so the walk ends)."""
    by_id = graph.by_id  # an uncached property: bind it once per walk
    seen: Set[str] = set()
    stack = list(by_id[sid].deps)
    while stack:
        d = stack.pop()
        if d in seen or d not in by_id:
            continue
        seen.add(d)
        stack.extend(by_id[d].deps)
    return seen


def implied_done(graph: Graph, done: List[str], running: Dict[str, int]) -> Set[str]:
    """The resolved set: every --done id plus the whole prerequisite chain of every
    --done and --running id — a step is resolved or under way only once everything it
    depends on, at any depth, is resolved (for A → B → C → D, `--done C` resolves A and
    B too, so only D is offered and counted). Computed before availability, the backward
    pass and the simulation; a partial list still estimates."""
    resolved: Set[str] = set(done)
    for sid in list(done) + list(running):
        resolved |= prerequisites(graph, sid)
    return resolved


def _occupier_text(occupiers: List[Step]) -> str:
    return " and ".join(f"step {s.ordinal} ({short_title(s)}, id {s.id})" for s in occupiers)


def check_h_stamp(content: Recipe, h_arg: Optional[str]) -> str:
    """`--h <8hex>` from a pasted FOND1 line: a stale stamp is refused before anything is
    estimated (recipe-authoring "The FOND1 line carries `h=`…"); absent, an older line
    replays as before. Returns the recipe's current `h`."""
    h = recipe_h(content)
    if h_arg is None:
        return h
    given = h_arg
    if not H_RE.fullmatch(given):
        raise ExportError("--h expects the eight hex digits after `h=` in the FOND1 line.", code=2)
    if given != h:
        raise ExportError(f"that line is for h={given}; the recipe is now h={h} — paste the line from the updated "
                          "player, or tell me which steps are done", code=1)
    return h


def cmd_plan(export: Export, query: str, done_arg: Optional[str], running_arg: Optional[str], as_json: bool,
             h_arg: Optional[str] = None) -> Dict[str, Any]:
    recipe = find_recipe(export, query)
    content = export.content_of(recipe)
    if content is None or not has_steps(content):
        # cook-playback "Saved recipes without steps": by-line, Fond id and url (the
        # provenance block), the original's address, nothing to convert, and no offer —
        # a composed file from that url is a user-asked act (recipe-authoring "Composed"),
        # never proposed here.
        why = _reason_suffix(missing_reason(recipe, export))
        where = (f"The original is at {recipe.url} — opened only if you ask." if recipe.url
                 else "The export carries no source url for it.")
        text = "\n".join(provenance_block(recipe, export, content) + [
            "",
            f"{recipe.label} has no steps in this export{why}; it belonged to {author_text(recipe, export)}. "
            f"{where} Nothing to convert, and no steps are written from memory."])
        raise ExportError(text)
    graph = build_graph(content)
    h = check_h_stamp(content, h_arg)
    done_ids = parse_done(done_arg)
    running = parse_running(running_arg)
    validate_state(graph, done_ids, running)
    done = implied_done(graph, done_ids, running)
    implied = sorted(done - set(done_ids), key=lambda d: graph.by_id[d].ordinal)
    lst = latest_start(graph, done, running)
    avail = available_steps(graph, done, running, lst)
    locked = sorted([s for s in graph.steps if s.id not in done and s.id not in running and s not in avail],
                    key=lambda s: order_key(s, lst))
    # A running step that occupies the cook (a DSL timer atom at medium/high/full/unset
    # attention, or hands-on work under way) holds back every other hands-on step until
    # it is resolved; legacy timers and none/low atoms hold nothing back. The simulation
    # already models this; the offered list must too.
    occupiers = [graph.by_id[sid] for sid in running if graph.by_id[sid].occupies]
    held = [s for s in avail if occupiers and s.occupies]
    offerable = [s for s in avail if s not in held]
    held_ids = {s.id for s in held}
    estimate = simulate(graph, done, running, lst)
    whole = int(math.ceil(estimate - EPS))

    lines = provenance_block(recipe, export, content)
    src = {"dsl": "DSL (legacy nodes ignored)", "nodes": "legacy steps", "md-steps": "the Markdown step list",
           "md-list": "a version-1 Markdown list (no timers, serial; the .json gives timers and parallel steps)"}[graph.source]
    if content.kind == "local":
        src = "a local file"
    lines.append(f"  Steps from: {src} (h={h})")
    lines += [f"  {note_line(n)}" for n in content.notes]
    notice = timers_notice(content, graph)
    if notice:
        lines.append(timers_notice_line(notice))
    lines.append("")
    lines.append(f"Ingredients ({len(graph.ingredients)}):")
    lines += _ingredient_lines(graph.ingredients)
    lines.append("")
    all_waves = waves(graph)
    if not done and not running:
        lines.append("Mise en place — wave 1, nothing to wait for (Prep: steps first):")
        for s in all_waves[0]:
            lines.append(f"  {s.ordinal}. (id {s.id}) {step_line(s, graph)}")
            if s.needs:
                lines.append(f"       needs: {', '.join(s.needs)}")
        if len(all_waves) > 1:
            lines.append("Later waves (grouping only — the order below is what counts):")
            for k, wave in enumerate(all_waves[1:], 2):
                lines.append(f"  wave {k}: " + "; ".join(f"{s.ordinal}. {short_title(s)} (id {s.id})" for s in wave))
        lines.append("")
    else:
        if done_ids:
            lines.append("Resolved: " + ", ".join(f"{graph.by_id[d].ordinal}. {short_title(graph.by_id[d])} (id {d})" for d in done_ids))
        if implied:
            lines.append("Resolved by implication (everything a resolved or running step depends on): "
                         + ", ".join(f"{graph.by_id[d].ordinal}. {short_title(graph.by_id[d])} (id {d})" for d in implied))
        if running:
            lines.append("Running (already in progress at minute 0):")
            for sid, rem in running.items():
                s = graph.by_id[sid]
                state = "has rung / run out — unresolved until you say it is done" if rem <= 0 else f"{rem} min left"
                occ = " — occupies you until it is done" if s.occupies else " — does not occupy you"
                lines.append(f"  {s.ordinal}. {short_title(s)} (id {sid}) — {state}{occ}")
        lines.append("")
    lines.append("Available now, in the app's order (earliest latest-start first):")
    if offerable:
        for n, s in enumerate(offerable, 1):
            lines.append(f"  {n}) step {s.ordinal} (id {s.id}) {step_line(s, graph)}")
            if s.needs:
                lines.append(f"       needs: {', '.join(s.needs)}")
    elif held:
        lines.append(f"  (nothing you can start — {_occupier_text(occupiers)} occupies you until it is done)")
    elif running:
        lines.append("  (nothing — every unresolved step waits on something that is still running)")
    else:
        lines.append("  (nothing — every step is resolved)")
    if held:
        verb = "is done — it occupies you" if len(occupiers) == 1 else "are done — they occupy you"
        lines.append(f"Held until {_occupier_text(occupiers)} {verb} (no other hands-on step until then):")
        for s in held:
            lines.append(f"  step {s.ordinal} (id {s.id}) {step_line(s, graph)}")
            if s.needs:
                lines.append(f"       needs: {', '.join(s.needs)}")
    if locked:
        lines.append("Locked (waiting on other steps):")
        for s in locked:
            lines.append(f"  step {s.ordinal} (id {s.id}) {step_line(s, graph)}")
            if s.needs:
                lines.append(f"       needs: {', '.join(s.needs)}")
    lines.append("")
    remaining = [s for s in graph.steps if s.id not in done]
    if not remaining:
        lines.append("Every step is resolved — the recipe is done.")
    elif done or running:
        lines.append(f"Estimated time to go: about {whole} min (an estimate, not a promise; "
                     "running steps count their minutes left only).")
    else:
        lines.append(f"Estimated time to serve: about {whole} min (one cook; timers and walk-away steps "
                     "overlap hands-on work; an estimate, not a promise).")
    lines.append(CANNOT_RING)
    for w in graph.warnings:
        lines.append(f"Note: {w}")
    for w in export.warnings:
        lines.append(f"Note: {w}")
    out = {
        "id": recipe.id, "title": recipe.label, "byline": byline(recipe, export),
        "lineage": lineage_line(recipe.lineage), "url": recipe.url, "source": graph.source, "h": h,
        "ingredients": graph.ingredients,
        "waves": [[s.id for s in wave] for wave in all_waves],
        "steps": [step_json(s, graph, lst, done, running, held_ids) for s in graph.steps],
        "available": [s.id for s in offerable], "held": [s.id for s in held],
        "held_by": [s.id for s in occupiers] if held else [], "locked": [s.id for s in locked],
        "done": sorted(done, key=lambda d: graph.by_id[d].ordinal), "implied_done": implied, "running": running,
        "estimate_minutes": whole, "estimate_exact": estimate, "warnings": graph.warnings + export.warnings,
        "text": "\n".join(lines),
    }
    if notice:
        out["timers_notice"] = notice
    return out


def cmd_history(export: Export, query: Optional[str], as_json: bool) -> Dict[str, Any]:
    counted = counted_cooks(export)
    ambiguous = ambiguous_cooks(export, counted)
    unattributed = ambiguous_keys(export, ambiguous)
    cookable, _missing = partition(export)
    cookable_keys = {(export.content_of(r) or r).key for r in cookable}
    rows = []
    for r in _dedupe_refs(export, export.all_recipes()):
        c = export.content_of(r) or r
        entries = counted.get(c.key, [])
        if not entries:
            continue
        word, again, ratings = verdict(entries)
        rated = latest_rated(entries)
        last = last_cooked(entries)
        rows.append({"id": c.id, "title": r.label, **provenance_fields(r, export), "times": len(entries),
                     "last": last or None, "verdict": word, "would_cook_again": again, "ratings": ratings,
                     "rated_at": (cook_when(rated) or None) if rated else None,
                     "cookable": c.key in cookable_keys})
    rows.sort(key=lambda row: (row["times"], row["last"] or ""), reverse=True)
    if query:
        recipe = find_recipe(export, query)
        c = export.content_of(recipe) or recipe
        if c.key in unattributed:
            # The title is shared: the cooks under it belong to one of several recipes and
            # the export cannot say which — say so, name every candidate, attribute it to none.
            group = next(g for g in ambiguous if c.key in ambiguous_keys(export, [g]))
            head = {"id": c.id, "title": recipe.label, **provenance_fields(recipe, export)}
            lines = row_lines(head, prefix="") + [_ambiguous_note(export, group)]
            lines += _candidate_lines(export, group, indent="  ")
            return {**head, "times": None, "not_counted": None, "verdict": None,
                    "would_cook_again": False, "ratings": None, "rated_at": None, "last": None, "ambiguous": True,
                    "unattributed_cooks": group["times"], "candidates": _candidate_rows(export, group),
                    "text": "\n".join(lines)}
        entries = counted.get(c.key, [])
        total = [cook for cook in export.cooks if any(_cook_row_is(cr, c) for cr in cook.get("recipes") or [] if isinstance(cr, dict))]
        not_counted = len(total) - len(entries)
        word, again, ratings = verdict(entries)
        rated = latest_rated(entries)
        rated_at = (cook_when(rated) or None) if rated else None
        last = last_cooked(entries)
        head = {"id": c.id, "title": recipe.label, **provenance_fields(recipe, export)}
        lines = row_lines(head, prefix="") + [
                 f"Cooked {len(entries)} time(s) that count (status completed/recorded/rated/migrated, not removed from history, recipe counted)"
                 + (f"; {not_counted} other cook(s) not counted (aborted, removed from history, or not counted in the app)" if not_counted > 0 else "") + "."]
        if entries:
            lines.append(f"Last cooked: {last or '(no date)'}.")
        if ratings:
            # The verdict is one cook's (latest_rated); name that cook when it is not the last.
            when = f", from the cook of {rated_at}" if rated_at and rated_at != last else ""
            # "4/5" whether the export stored 4 or 4.0 (the app writes doubles), as cook-again prints it.
            taste = _to_float(ratings.get("taste"))
            taste_text = _s(None) if taste is None else f"{taste:g}"
            lines.append(f"Verdict: {word or 'rated'} (taste {taste_text}/5"
                         + (", would cook again" if again else "") + f"){when}.")
        else:
            lines.append("No verdict: no taste or would-cook-again rating recorded (a migrated cook carries at most easy-to-follow).")
        return {**head, "times": len(entries), "not_counted": max(0, not_counted),
                "verdict": word, "would_cook_again": again, "ratings": ratings, "rated_at": rated_at,
                "last": last or None, "ambiguous": False,
                "text": "\n".join(lines)}
    # A cook counts once however many recipes it held; a recipe cook is one counted
    # recipe within a counted cook (the figure each row shows). Cooks under a title two
    # recipes share are counted but attributed to neither (counted_cooks).
    cooks_n = len({id(e["cook"]) for entries in counted.values() for e in entries})
    recipe_cooks = sum(r["times"] for r in rows)
    unattributed_n = sum(g["times"] for g in ambiguous)
    uncredited_n = len(counted.get(UNCREDITED_BUCKET, []))
    why = ("their Markdown line reads as two titles — the JSON export resolves them" if export.from_markdown
           else "these cook rows carry neither a Fond id nor a title")
    lines = [f"Cooking history from this export ({cooks_n} counted cook(s), {recipe_cooks} recipe cook(s), "
             f"across {len(rows)} recipe(s)"
             + (f"; {unattributed_n} recipe cook(s) not attributable, see below" if unattributed_n else "")
             + (f"; {uncredited_n} recipe cook(s) credited to no recipe ({why})" if uncredited_n else "") + "):"]
    for row in rows:
        v = f" — {row['verdict']}" if row["verdict"] else ""
        a = ", would cook again" if row["would_cook_again"] else ""
        # The verdict is one cook's (latest_rated): name that cook when it is not the last.
        w = f" (rated {row['rated_at']})" if (v or a) and row["rated_at"] and row["rated_at"] != row["last"] else ""
        ck = "" if row["cookable"] else " — not cookable from this export"
        lines += row_lines(row, f" — cooked {row['times']}× — last {row['last'] or '(no date)'}{v}{a}{w}{ck}")
    if not cooks_n:
        lines.append("  (no counted cooks)")
    elif not rows and not ambiguous and not uncredited_n:
        lines.append("  (no counted cook names a recipe in this export)")
    for g in ambiguous:
        lines.append(f"  - {_ambiguous_note(export, g)}")
        lines += _candidate_lines(export, g)
    return {"rows": rows,
            "ambiguous": [{"title": g["title"], "times": g["times"], "candidates": _candidate_rows(export, g)} for g in ambiguous],
            "uncredited_cooks": uncredited_n,
            "text": "\n".join(lines)}


def _rating_text(fields: List[Tuple[str, Optional[float]]]) -> str:
    """One cook's ratings (latest_rated) as "would cook again 4/5, taste 4/5", from (label,
    value) pairs; a field that cook left blank is left out — never printed as 0/5, never
    borrowed from another cook."""
    shown = [f"{label} {value:g}/5" for label, value in fields if value is not None]
    return ", ".join(shown) if shown else "no rating"


def cmd_cook_again(export: Export, as_json: bool) -> Dict[str, Any]:
    counted = counted_cooks(export)
    ambiguous = ambiguous_cooks(export, counted)
    cookable, _missing = partition(export)
    cookable_keys = {(export.content_of(r) or r).key for r in cookable}

    suggestions, aside = [], []
    for r in _dedupe_refs(export, export.all_recipes()):
        c = export.content_of(r) or r
        entries = counted.get(c.key, [])
        if not entries:
            continue
        # One cook's ratings, together (latest_rated) — never the best of each across cooks,
        # so an old 5/5 cook followed by a newer 1/5 cook ranks and reads as 1/5.
        rated = latest_rated(entries)
        ratings = rated["recipe"]["ratings"] if rated else {}
        row = {"id": c.id, "title": r.label, **provenance_fields(r, export), "times": len(entries),
               "would_cook_again": _to_float(ratings.get("wouldCookAgain")), "taste": _to_float(ratings.get("taste")),
               "rated_at": (cook_when(rated) or None) if rated else None, "last": last_cooked(entries) or None}
        (suggestions if c.key in cookable_keys else aside).append(row)
    suggestions.sort(key=lambda row: (row["would_cook_again"] or 0.0, row["taste"] or 0.0, row["last"] or ""), reverse=True)
    aside = [row for row in aside if (row["taste"] or 0.0) >= 4 or (row["would_cook_again"] or 0.0) >= 4]
    lines = ["Cook again (cookable from this export, by rating then recency):"]
    for row in suggestions:
        rating = _rating_text([("would cook again", row["would_cook_again"]), ("taste", row["taste"])])
        when = f" (rated {row['rated_at']})" if row["rated_at"] and row["rated_at"] != row["last"] else ""
        lines += row_lines(row, f" — {rating}{when} — cooked {row['times']}×, last {row['last'] or '(no date)'}")
    if not suggestions:
        lines.append("  (nothing cooked yet that is cookable from this export)")
    if aside:
        lines.append("Rated highly, but not cookable from this export:")
        for row in aside:
            when = f" (rated {row['rated_at']})" if row["rated_at"] and row["rated_at"] != row["last"] else ""
            rating = _rating_text([("taste", row["taste"]), ("would cook again", row["would_cook_again"])])
            lines += row_lines(row, f" — {rating}{when}")
    # Cooks under a title two recipes share were attributed to neither (counted_cooks), so
    # their ratings ranked nothing above; say what was cooked and why nothing is suggested.
    if ambiguous:
        lines.append("Cooked, but not attributable to one recipe:")
        for g in ambiguous:
            lines.append(f"  - {_ambiguous_note(export, g)}")
            lines += _candidate_lines(export, g)
    unattributable = [{"title": g["title"], "times": g["times"], "candidates": _candidate_rows(export, g)} for g in ambiguous]
    return {"suggestions": suggestions, "not_cookable": aside, "unattributable": unattributable, "text": "\n".join(lines)}


# --- scaling: a labelled variant, never the original ---------------------------------

_FRACTION_CHARS = {"¼": Fraction(1, 4), "½": Fraction(1, 2), "¾": Fraction(3, 4), "⅓": Fraction(1, 3),
                   "⅔": Fraction(2, 3), "⅛": Fraction(1, 8), "⅜": Fraction(3, 8), "⅝": Fraction(5, 8), "⅞": Fraction(7, 8)}
_QTY_TOKEN = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?(?:\s*[¼½¾⅓⅔⅛⅜⅝⅞])?|[¼½¾⅓⅔⅛⅜⅝⅞])"
_LEADING_QTY = re.compile(rf"^\s*({_QTY_TOKEN})(?:\s*(?:-|–|to)\s*({_QTY_TOKEN}))?")


def _parse_qty(token: str) -> Fraction:
    token = token.strip().replace(",", ".")
    total = Fraction(0)
    for part in token.split():
        if part in _FRACTION_CHARS:
            total += _FRACTION_CHARS[part]
        elif "/" in part:
            num, den = part.split("/")
            total += Fraction(int(num), int(den))
        elif part[-1] in _FRACTION_CHARS:
            total += Fraction(part[:-1]) + _FRACTION_CHARS[part[-1]]
        else:
            total += Fraction(part)
    return total


def _fmt_qty(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    approx = value.limit_denominator(8)
    if abs(float(approx) - float(value)) > 0.01 or approx.denominator > 8:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    whole, rem = divmod(approx.numerator, approx.denominator)
    frac = f"{rem}/{approx.denominator}"
    return f"{whole} {frac}" if whole else frac


def scale_line(line: str, factor: Fraction) -> Tuple[str, bool]:
    m = _LEADING_QTY.match(line)
    if not m:
        return line, False
    lo = _fmt_qty(_parse_qty(m.group(1)) * factor)
    text = lo
    if m.group(2):
        text += f"-{_fmt_qty(_parse_qty(m.group(2)) * factor)}"
    return text + line[m.end():], True


def yield_servings(recipe: Recipe) -> Optional[Fraction]:
    """A local file's `yield` when it states a number of servings ("4 servings", "serves
    6", "4-6 servings" — the low bound); None otherwise, and `scale` asks."""
    value = (recipe.envelope or {}).get("yield")
    if not isinstance(value, str):
        return None
    m = re.search(r"\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?", value)
    if not m:
        return None
    try:
        return _parse_qty(m.group(0).replace(" ", ""))
    except (ValueError, ZeroDivisionError):
        return None


def cmd_scale(export: Export, query: str, factor: Optional[str], base: Optional[str], target: Optional[str], as_json: bool) -> Dict[str, Any]:
    recipe = find_recipe(export, query)
    content = export.content_of(recipe)
    if content is None or not has_steps(content):
        raise ExportError(f"{recipe.label} has no steps in this export; nothing to scale.")
    stated = yield_servings(content) if content.kind == "local" else None
    if factor:
        try:
            f = Fraction(factor)
        except (ValueError, ZeroDivisionError):
            raise ExportError("--factor must be a number such as 1.5 or 3/2.", code=2)
    elif (base or stated) and target:
        try:
            f = Fraction(target) / (Fraction(base) if base else stated)
        except (ValueError, ZeroDivisionError):
            raise ExportError("--from and --to must be positive numbers of servings.", code=2)
    elif content.kind == "local":
        raise ExportError("The file's `yield` states no number of servings. Ask how many the recipe serves as written, "
                          "then pass --from <servings as written> --to <servings wanted> (or --factor).", code=2)
    else:
        raise ExportError("The export carries no yield. Ask how many the recipe serves as written, then pass "
                          "--from <servings as written> --to <servings wanted> (or --factor).", code=2)
    if f <= 0:
        raise ExportError("The scale factor must be positive.", code=2)
    label = f"×{float(f):g} variant"
    graph = build_graph(content)
    # The variant's head is the recipe's own presentation — by-line and, when non-null, the
    # lineage line — exactly as `show` and `history "<title>"` head theirs.
    head = {"id": recipe.id, "title": recipe.label, **provenance_fields(recipe, export)}
    # The unscaled text is "the original" for an export row and "the file" for a local
    # file: "original" is on the never-list for a local file's own identity
    # (recipe-authoring "The local id; no Fond id, handle or lineage is minted").
    whole = "the file" if content.kind == "local" else "the original"
    lines = row_lines(head, f" — {label} ({whole} is unchanged; ask for it any time)", prefix="")
    lines.append("")
    lines.append(f"Ingredients, {label}:")
    scaled = []
    for ing in graph.ingredients:
        new, changed = scale_line(ing, f)
        scaled.append({"original": ing, "scaled": new if changed else None})
        lines.append(f"  - {new}" if changed else f"  - {ing} (no amount stated — not scaled)")
    lines.append("")
    lines.append(f"Steps, {label} (text as written; bracketed amounts inside step text are {whole}'s):")
    for s in graph.steps:
        lines.append(f"  {s.ordinal}. [{label}] {step_line(s, graph)}")
    lines.append("")
    lines.append("Caveat: salt, leavening, pan sizes and cooking times do not scale linearly — taste, "
                 "and keep the timers as the recipe states them.")
    return {**head, "factor": float(f), "label": label, "ingredients": scaled, "text": "\n".join(lines)}


# --- strip ----------------------------------------------------------------------------


def strip_export(data: Dict[str, Any]) -> Dict[str, Any]:
    """A recipes-only copy: no contact, no profile, linkedFromUid nulled on every record;
    id/handle/url/authorHandle/sourceAuthor/lineage untouched. A version-1 input first
    gets profile.handle stamped onto each authored row as authorHandle."""
    out = json.loads(json.dumps(data))  # deep copy, JSON-native
    profile = out.get("profile")
    handle = profile.get("handle") if isinstance(profile, dict) and isinstance(profile.get("handle"), str) else None
    for row in out.get("authoredRecipes") or []:
        if isinstance(row, dict) and "authorHandle" not in row:
            row["authorHandle"] = handle
    out.pop("contact", None)
    out.pop("profile", None)
    for key in ("authoredRecipes", "savedRecipes", "cooks"):
        for row in out.get(key) or []:
            if isinstance(row, dict):
                row["linkedFromUid"] = None
    return out


PLAYER_MARKER = re.compile(r"^<!-- fond-player built by fond_export\.py h=[0-9a-f]{8} id=(\S+) -->$")


def _marker_id(line: str) -> Optional[str]:
    """The `id=` of a player marker line — the recipe id, or a collection id (`export:…`,
    `library:…`; `collection_id`) for a whole-export or whole-folder page — or None when
    the line is not the marker."""
    m = PLAYER_MARKER.match(line.rstrip("\r\n"))
    return m.group(1) if m else None


def _refuse_existing(path: Path, text: str = "") -> None:
    """The write rule's refusal, exit 1, on its own so a command can refuse an existing
    path before the work that precedes its write (`convert` refuses before it builds the
    draft or runs the gate). The one exception is the player's OWN page (design decision
    5): a page may replace a file whose first line is the marker with the same `id=` —
    any `h=`, so an edited recipe rebuilds in place. A marked page for another id (a
    different recipe, another export's or folder's page, or a whole-export page against
    a recipe's) is refused naming both ids; a file that does not open with the marker is
    refused as any other file."""
    if not path.exists():
        return
    new_id = _marker_id(text.split("\n", 1)[0]) if text else None
    if new_id is not None:
        try:
            with open(path, encoding="utf-8") as fh:
                old_id = _marker_id(fh.readline())
        except OSError:
            old_id = None
        if old_id == new_id:
            return
        if old_id is not None:
            raise ExportError(f"`{path}` is the player page for {old_id}, not {new_id}; pass --out <another path>",
                              code=1)
    raise ExportError(f"`{path}` exists; pass --out <other> or edit that file", code=1)


def _write_new(path: Path, text: str) -> None:
    """The one writer (recipe-authoring "Written only to a file the user asks for"): every
    file goes to a NEW path — an existing one is refused by `_refuse_existing`, exit 1 —
    except the player's own marked page, rebuilt in place. `strip`, `check --out`,
    `convert --out` and `player --out` all write through here."""
    _refuse_existing(path, text)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as e:
        raise ExportError(f"Cannot write {path}: {e.strerror or e}")


def _refuse_out_name(target: Path) -> None:
    """`--out`'s own basename must be a local id before a recipe file is written to it
    (recipe-authoring "The local id"): a clean `good.md` written as `BAD NAME.md` would fail,
    as that file, the rule it just passed. The shape named, exit 1, nothing read or written.
    `check --out` and `convert --out` — the two recipe-file writers — call this first."""
    slug = local_basename(target)
    if not LOCAL_SLUG.match(slug):
        raise ExportError(f"{not_a_local_id(slug)}; pass --out <another name>", code=1)


def _refuse_sibling_id(target: Path) -> None:
    """The collision rule at the write boundary (recipe-authoring "The local id": two files
    cannot share a basename in one folder). A recipe file is never written beside one that
    already resolves to its id — a `.md` in the output folder that the library reader reads
    (it opens with a `---` envelope) whose name up to its first dot is the output's: `foo.md`
    beside the `foo.recipe.md` about to be written, both `local:foo`. Refused with the
    library's own collision line naming the files, exit 1, nothing written, so the file the
    skill writes never trips the rule `--dsl list` would then report. The output path itself
    is `_refuse_existing`'s; a same-named file in another folder is no sibling. `check --out`
    and `convert --out` call this after `_refuse_out_name`."""
    slug = local_basename(target)
    try:
        entries = sorted(target.parent.iterdir(), key=lambda q: q.name)
    except OSError:
        return  # no such folder: the write itself reports it
    group: List[Recipe] = []
    for p in entries:
        if p.name == target.name or not p.is_file() or p.suffix.lower() != ".md" or local_basename(p) != slug:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if split_envelope(text)[0] is not None:
            group.append(local_recipe_from_text(text, slug, str(p)))
    if group:
        group.append(local_recipe_from_text("", slug, str(target)))  # the file that would join them
        raise ExportError(f"{collision_line(group)}; pass --out <another name>", code=1)


def cmd_strip(export: Export, path: Path, out_path: Optional[str]) -> Dict[str, Any]:
    if export.local:
        # A local file is read with --dsl; it carries no contact block and no profile.
        return {"path": None, "text": NOT_AN_EXPORT_LOCAL}
    if export.from_markdown:
        raise ExportError("strip works on the .json export. For the .md, delete the block from the line "
                          "'## Contact' down to the next '##' heading in a text editor.", code=2)
    stripped = strip_export(export.raw)
    target = Path(out_path) if out_path else path.with_name(f"{path.stem}-stripped.json")
    if target.resolve() == path.resolve():
        raise ExportError("strip will not overwrite the original export; pass --out <another path>.", code=2)
    _write_new(target, json.dumps(stripped, ensure_ascii=False, indent=2) + "\n")
    note = " (the markdown half of the callable payload was dropped: it carries the Contact block)" if export.payload else ""
    return {"path": str(target), "text": f"Wrote {target}{note} — no contact, no profile, linkedFromUid nulled; "
                                         "id, handle, url, authorHandle, sourceAuthor and lineage kept."}


# ---------------------------------------------------------------------------
# Local recipe files: the gate, `check`, `convert`, `--dsl list`
# ---------------------------------------------------------------------------


def nodes_of(content: Recipe) -> List[Any]:
    """A row's legacy steps as node dicts: its `nodes[]`, or — on `--md` — the section's
    parsed step lines in the graph's own reading (so a transliteration of a Markdown row
    plays as the Markdown did)."""
    nodes, _ = parse_nodes(content.nodes)
    if nodes:
        return nodes
    if content.md_steps:
        return [{"id": s.id, "title": s.title, "text": s.text, "time": s.time, "until": s.done_when,
                 "dependencies": list(s.deps), "repeat": s.count}
                for s in steps_from_markdown(content.md_steps, content.md_legacy)]
    return []


def canonical_defs(body: str) -> int:
    """Distinct canonical `@slug{…}` definitions — the registry's ingredient floor reads
    the same count (printed for a local file, never gated)."""
    slugs = set()
    for atom in parse_atoms(split_dsl(body)[1]):
        for m in ING_DEF.finditer(atom["prose"]):
            slugs.add(m.group(1).strip())
    return len(slugs)


def transliterated(content: Recipe) -> Tuple[str, List[str]]:
    """`convert`'s deterministic draft body for a row: the row's `dsl` verbatim (one final
    newline), or the nodes transliterated in the one lint- and gate-clean mode."""
    if content.dsl:
        body = content.dsl
        return (body if body.endswith("\n") else body + "\n"), []
    n2d = _import_nodes_to_dsl()
    return n2d.transliterate(nodes_of(content), content.ingredients, content.label,
                             repeat_mode="auto", hands_on_attention="full")


def baseline_of(content: Recipe, fond_dsl: Any) -> Dict[str, Any]:
    """The parent row's own findings — its `dsl` body linted, or for a nodes-only row the
    `convert` output linted — the U/V baseline a variant inherits."""
    body, _losses = transliterated(content)
    return fond_dsl.dsl.lint_dsl(body)


def parent_mismatches(recipe: Recipe, row: Recipe, parent: Export) -> List[str]:
    """`--parent`'s cross-check: the envelope's copied fields against the row — each
    mismatch named with the key and the row's value (exact equality for `credits`, order
    included; "no `credits` key" against a null `lineage`)."""
    env = recipe.envelope or {}
    lineage = env.get("lineage") if isinstance(env.get("lineage"), dict) else {}
    out: List[str] = []

    def expect(key: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            shown = "absent" if actual is None else repr(actual)
            want = "absent" if wanted is None else repr(wanted)
            out.append(f"`{key}` is {shown}; the row carries {want}")

    expect("lineage.parent_handle", lineage.get("parent_handle"), row.handle)
    author = effective_author(row, parent)
    expect("author", env.get("author"), f"@{author}" if author else "(unknown)")
    expect("source_url", env.get("source_url"), row.url)
    expect("attribution", env.get("attribution"), [f"source {row.source_author}"] if row.source_author else None)
    expect("lineage.parent_lineage", lineage.get("parent_lineage"), lineage_line(row.lineage))
    expect("lineage.exported_at", lineage.get("exported_at"), parent.exported_at)
    wanted_credits = credits_of(row) if row.lineage is not None else None
    if row.lineage is None:
        if "credits" in lineage:
            out.append("`lineage.credits` is present; the row's `lineage` is null, so no credits key belongs here")
    else:
        expect("lineage.credits", lineage.get("credits"), wanted_credits or None)
    return out


def credits_of(row: Recipe) -> List[str]:
    """The row's `attributionHandles` verbatim — order kept, nothing added, a null position
    as "(unknown)"; from the echoed `credits @a, @b` tail of a Markdown row's line."""
    if not isinstance(row.lineage, dict):
        return []
    if "_line" in row.lineage:
        m = re.search(r";\s*credits\s+(.+)$", str(row.lineage["_line"]))
        return [h[1:] if h.startswith("@") else h for h in (p.strip() for p in m.group(1).split(",")) if h] if m else []
    handles = row.lineage.get("attributionHandles")
    return [h if isinstance(h, str) and h else "(unknown)" for h in handles] if isinstance(handles, list) else []


def plays_as(recipe: Recipe) -> Tuple[List[str], Dict[str, Any]]:
    """What the file will do under the sigil-only reader — each atom's kind and timing as
    `plan` prints it, the mise-en-place wave and the estimate — so the assistant sees its
    draft before the user does. Raises ExportError when no graph can be built."""
    graph = build_graph(recipe)
    lst = latest_start(graph, set(), {})
    all_waves = waves(graph)
    estimate = simulate(graph, set(), {}, lst)
    lines = ["Plays as:"]
    steps = []
    for s in graph.steps:
        timing = timing_text(s) or "instant"
        lines.append(f"  {s.ordinal}. {s.title} — {timing}")
        steps.append({"id": s.id, "ordinal": s.ordinal, "title": s.title, "kind": s.kind, "occupies": s.occupies,
                      "scheduled": s.scheduled, "count": s.count, "timer_total": s.timer_total,
                      "countdowns": [[m, label] for m, label in s.countdowns], "timing": timing})
    lines.append("  Mise en place (wave 1): " + ", ".join(f"{s.ordinal}. {short_title(s)}" for s in all_waves[0]))
    lines.append(f"  Estimated time to serve: about {fmt_whole(estimate)}")
    for w in graph.warnings:
        lines.append(f"  Note: {w}")
    return lines, {"steps": steps, "wave1": [s.id for s in all_waves[0]], "estimate_minutes": int(math.ceil(estimate - EPS)),
                   "warnings": graph.warnings}


def local_gate(recipe: Recipe, parent: Optional[Export], *, write_boundary: bool) -> Dict[str, Any]:
    """The gate of recipe-authoring "`check` gates keeping and cooking": the envelope checks,
    the `--parent` cross-check, the vendored `lint_dsl` under `gate.py`'s bar (errors + the
    thirteen gated rules; U and V inherited from the parent row's baseline on a variant;
    the ingredient floor a note) and the "plays as" preview. At the write boundary
    (`check`, `convert --out`) a variant REQUIRES the parent (exit 2); the read commands
    print U and V as not gated without it and proceed."""
    fond_dsl = _import_fond_dsl()
    findings: List[Dict[str, Any]] = []

    def add(rule: str, message: str) -> None:
        findings.append({"rule": rule, "step": None, "kind": "error", "message": message, "gated": True,
                         "line": fond_dsl.gate.issue_line("error", rule, None, message)})

    env_errors, warnings = envelope_findings(recipe)
    for message in env_errors:
        add("envelope", message)
    if recipe.envelope_errors:
        # The strict reader refused the envelope's shape. The vendored lint would run the
        # whole file through the reference `parse_yaml`, which raises on exactly these
        # shapes (a map under a list item), so the gate ends here: exit 1 with the
        # reader's errors printed, no lint, no "plays as", no traceback.
        return {"ok": False, "findings": findings, "gated_lines": [str(f["line"]) for f in findings],
                "notes": [], "warnings": warnings, "not_gated": [], "plays_as": {}, "plays_lines": [],
                "h": recipe_h(recipe)}
    notes: List[str] = []
    baseline: Any = None
    if recipe.origin == "variant":
        if parent is None:
            if write_boundary:
                raise ExportError(NO_PARENT_FOR_CHECK, code=2)
        else:
            row = parent_row_of(recipe, parent)
            pid = (recipe.envelope or {}).get("lineage", {}).get("parent_id")
            if row is None:
                message = f"`lineage.parent_id` {pid!r} names no recipe in the --parent export"
                if write_boundary:
                    add("parent", message)
                else:
                    notes.append(f"{message}; rules U and V are not gated")
            else:
                for message in parent_mismatches(recipe, row, parent):
                    add("parent", message)
                baseline = baseline_of(parent.content_of(row) or row, fond_dsl)
    lint = fond_dsl.dsl.lint_dsl(recipe.text or "")
    findings += fond_dsl.gate.gate_findings(lint, canonical_defs(recipe.body or ""), recipe.origin, baseline)
    plays_lines: List[str] = []
    plays: Dict[str, Any] = {}
    try:
        plays_lines, plays = plays_as(recipe)
    except ExportError as e:
        add("graph", str(e))
    gated = [f for f in findings if f["gated"]]
    notes += [str(f["line"]) for f in findings if f["kind"] == "note"]
    not_gated = [str(f["line"]) for f in findings if not f["gated"] and f["kind"] != "note"]
    return {"ok": not gated, "findings": findings, "gated_lines": [str(f["line"]) for f in gated],
            "notes": notes, "warnings": warnings, "not_gated": not_gated,
            "plays_as": plays, "plays_lines": plays_lines, "h": recipe_h(recipe)}


def note_line(n: str) -> str:
    """A gate note as one printed line. `gate.issue_line` already heads the lint's notes
    with their register (`note [U]: …`, `note: only 2 canonical …`); only a bare message
    (the `--parent` cross-check's) gets the head, so no line ever reads `note: note …`."""
    return n if n.startswith(("note:", "note [")) else f"note: {n}"


def gate_lines(recipe: Recipe, result: Dict[str, Any]) -> List[str]:
    lines = list(result["gated_lines"])
    lines += [note_line(n) for n in result["notes"]]
    lines += [f"warning: {w}" for w in result["warnings"]]
    if result["not_gated"]:
        lines.append("Not gated:")
        lines += [f"  {s}" for s in result["not_gated"]]
    lines += result["plays_lines"]
    lines.append(f"h={result['h']}")
    return lines


def refuse_unless_clean(recipe: Recipe, export: Export) -> None:
    """The read commands' gate (`--dsl show|plan|scale`): a file with findings is refused
    with them — nothing with findings is cooked; a clean file keeps its notes for the turn."""
    result = local_gate(recipe, export.parent, write_boundary=False)
    if not result["ok"]:
        raise ExportError("\n".join([f"{recipe.label} — {recipe.id}: {len(result['gated_lines'])} finding(s) block it; "
                                     "nothing with findings is cooked. Fix the file and run check."]
                                    + result["gated_lines"]), code=1)
    recipe.notes = result["notes"] + result["warnings"]


def cmd_check(file_arg: str, parent_path: Optional[str], out_path: Optional[str], as_json: bool) -> Dict[str, Any]:
    if out_path:
        # The output's basename is the id the kept file will carry: it must be a local id, no
        # recipe file in that folder may already resolve to it, and the recipe is constructed,
        # gated and reported under it (file input or stdin alike).
        _refuse_out_name(Path(out_path))
        _refuse_sibling_id(Path(out_path))
    parent = load_export(Path(parent_path)) if parent_path else None
    recipe = load_library_file(file_arg, out_hint=out_path)
    result = local_gate(recipe, parent, write_boundary=True)
    n = len(result["gated_lines"])
    lines = [f"check: {recipe.local_path} — {recipe.id}" + (f" ({recipe.origin})" if recipe.origin else "")]
    lines += gate_lines(recipe, result)
    written = None
    if result["ok"]:
        lines.append(f"Passes: nothing blocks {recipe.id}.")
        if out_path:
            _write_new(Path(out_path), recipe.text or "")
            written = out_path
            lines.append(f"Wrote {out_path}")
    else:
        lines.append(f"{n} finding(s) block {recipe.id}; nothing with a gated finding is written, kept or cooked.")
        if out_path:
            lines.append(f"Nothing written to {out_path}: fix the findings in the draft and run check again.")
    return {"ok": result["ok"], "id": recipe.id, "origin": recipe.origin, "path": recipe.local_path,
            "findings": [{k: f[k] for k in ("rule", "step", "kind", "message", "gated")} for f in result["findings"]],
            "notes": result["notes"], "warnings": result["warnings"], "plays_as": result["plays_as"], "h": result["h"],
            "written": written, "text": "\n".join(lines), "exit": 0 if result["ok"] else 1}


def _env_scalar(value: str) -> str:
    """A scalar the strict reader reads back as itself, never rewritten: quoted when its
    first character is one YAML would read as an indicator (`@cara`, `"Best" Soup`) or when
    it has outer whitespace, in an outer quote the value does not contain — double, or
    single when the value carries a `"`. A value carrying both kinds goes in single quotes
    unchanged: the strict reader's `_unquote` and the reference `_parse_scalar` each strip
    one matching outer pair and read nothing inside, so `'"It's" hot'` reads back exactly."""
    if value == "" or value[0] in "@\"'#[{&*!|>%`" or value != value.strip():
        quote = "'" if '"' in value else '"'
        return quote + value + quote
    return value


def render_envelope(env: Dict[str, Any]) -> str:
    """The envelope block in the canonical key order, lists one `- item` per line."""
    lines = ["---"]

    def emit(key: str, value: Any, indent: str) -> None:
        if isinstance(value, list):
            lines.append(f"{indent}{key}:")
            lines.extend(f"{indent}  - {_env_scalar(str(v))}" for v in value)
        elif isinstance(value, dict):
            lines.append(f"{indent}{key}:")
            for k in LINEAGE_FIELDS:
                if k in value:
                    emit(k, value[k], indent + "  ")
        elif str(value) == "":
            lines.append(f"{indent}{key}:")  # an empty value, read back as "" — `made_on:` awaiting a date
        else:
            lines.append(f"{indent}{key}: {_env_scalar(str(value))}")

    for key in ENVELOPE_FIELDS:
        if key in env and env[key] is not None:
            emit(key, env[key], "")
    lines.append("---")
    return "\n".join(lines) + "\n"


def variant_envelope(recipe: Recipe, content: Recipe, export: Export, made_on: str, first_change: str) -> Dict[str, Any]:
    """The envelope of a variant, copied from the row by the script, never typed:
    `author` the row's by-line author, `source_url` its `url`, `attribution` its
    `sourceAuthor`, `lineage` the origin, the row's id and handle, its lineage line
    verbatim and its `attributionHandles` verbatim (only when its `lineage` is non-null),
    the export's `exportedAt`, the date the assistant gave, and the first `changes` entry."""
    author = effective_author(recipe, export)
    env: Dict[str, Any] = {"title": recipe.label, "author": f"@{author}" if author else "(unknown)"}
    servings = content.row.get("servings") if isinstance(content.row, dict) else None
    if servings is not None and str(servings).strip():
        env["yield"] = f"{servings} servings" if re.fullmatch(r"\d+(?:\.\d+)?", str(servings).strip()) else str(servings)
    if recipe.url:
        env["source_url"] = recipe.url
    if recipe.source_author:
        env["attribution"] = [f"source {recipe.source_author}"]
    lineage: Dict[str, Any] = {"origin": "variant", "parent_id": recipe.id}
    if recipe.handle:
        lineage["parent_handle"] = recipe.handle
    ll = lineage_line(recipe.lineage)
    if ll:
        lineage["parent_lineage"] = ll
    if export.exported_at:
        lineage["exported_at"] = export.exported_at
    if recipe.lineage is not None:
        credits = credits_of(recipe)
        if credits:
            lineage["credits"] = credits
    lineage["made_on"] = made_on
    lineage["changes"] = [first_change]
    env["lineage"] = lineage
    return env


def cmd_convert(export: Export, query: str, out_path: Optional[str], made_on: Optional[str], as_json: bool) -> Dict[str, Any]:
    """`convert "<title>" [--made-on YYYY-MM-DD]`: the row's `dsl` verbatim, or the nodes
    transliterated, under an envelope filled from the row; the gate runs before any write
    with the row itself as the U/V baseline; `--out -` prints only; the default path is
    `<slug>.recipe.md` in the working directory, never an existing one nor one beside a
    recipe file that already resolves to its id (`_refuse_sibling_id`). `--made-on` is
    optional (the script reads no clock): without it the draft carries `made_on:` with an
    empty value, which the gate reports as the one thing left to fill in, so `--out` then
    writes nothing and the date reaches the file through `check - --out`."""
    recipe = find_recipe(export, query)
    content = export.content_of(recipe)
    if content is None or not has_steps(content):
        raise ExportError(f"{recipe.label} has no steps in this export; nothing to convert.")
    if not recipe.id:
        raise ExportError(f"{recipe.label} carries no Fond id in this Markdown export, so a variant cannot name its "
                          "parent; convert from the .json export.")
    slug = slugify(recipe.label) or "recipe"
    target = None if out_path == "-" else Path(out_path) if out_path else Path(f"{slug}.recipe.md")
    if target is not None:
        _refuse_out_name(target)  # the three refusals (exit 1) precede everything but the row lookup
        _refuse_existing(target)
        _refuse_sibling_id(target)
    made_on = (made_on or "").strip()
    if made_on and not MADE_ON_RE.match(made_on):
        raise ExportError(f"--made-on must be YYYY-MM-DD, not `{made_on}` (today's date from the conversation; "
                          "the script reads no clock).", code=2)
    body, losses = transliterated(content)
    first = COPY_ENTRY if content.dsl else CONVERT_ENTRY
    env = variant_envelope(recipe, content, export, made_on, first)
    draft = render_envelope(env) + body
    local = local_recipe_from_text(draft, local_basename(target) if target else slug, str(target) if target else "- (draft)")
    result = local_gate(local, export, write_boundary=True)
    lines = [draft.rstrip("\n"), ""]
    if losses:
        lines.append("Converted with these losses:")
        lines += [f"  - {x}" for x in losses]
    # The envelope's own findings (an empty `made_on`) are the draft's, never inherited.
    own = [str(f["line"]) for f in result["findings"] if f["gated"] and f["rule"] == "envelope"]
    inherited = [x for x in result["gated_lines"] if x not in own]
    if own:
        lines.append("Findings:")
        lines += [f"  {x}" for x in own]
    if inherited:
        lines.append("Inherited findings:" if content.dsl else "Findings:")
        lines += [f"  {x}" for x in inherited]
    lines += [f"  {note_line(n)}" for n in result["notes"]]
    lines += [f"  warning: {w}" for w in result["warnings"]]
    written = None
    if target is None:
        lines.append(f"Draft only (--out -): nothing written. h={result['h']}")
    elif result["ok"]:
        _write_new(target, draft)
        written = str(target)
        lines.append(f"Wrote {target} — a local variant of {recipe.label}; it passes check. h={result['h']}")
    else:
        lines.append(f"Nothing written to {target}: {len(result['gated_lines'])} finding(s) block the draft. Fix them in "
                     f"the draft above and persist it with `check - --parent <export> --out {target}`.")
    return {"id": local.id, "title": recipe.label, "parent_id": recipe.id, "draft": draft, "body": body, "losses": losses,
            "findings": [{k: f[k] for k in ("rule", "step", "kind", "message", "gated")} for f in result["findings"]],
            "notes": result["notes"], "warnings": result["warnings"], "h": result["h"], "ok": result["ok"],
            "written": written, "text": "\n".join(lines), "exit": 0 if result["ok"] else 1}


def cmd_dsl_list(export: Export, as_json: bool) -> Dict[str, Any]:
    """`<file|folder> --dsl list`: each file's origin line with `local:<slug>`, "(does not
    pass check)" after a failing row, duplicate basenames named."""
    rows = []
    lines = [f"Library {export.local_root} — {len(export.authored)} recipe file(s):"]
    for r in export.authored:
        result = local_gate(r, export.parent, write_boundary=False)
        entry = {"id": r.id, "title": r.label, **provenance_fields(r, export), "origin": r.origin, "path": r.local_path,
                 "ok": result["ok"], "h": result["h"], "findings": len(result["gated_lines"])}
        rows.append(entry)
        lines += row_lines(entry, "" if result["ok"] else " (does not pass check)")
    for w in export.warnings:
        lines.append(f"Note: {w}")
    return {"root": export.local_root, "recipes": rows, "warnings": export.warnings, "text": "\n".join(lines)}


# ---------------------------------------------------------------------------
# The player: one self-contained page from scripts/player.template.html
# ---------------------------------------------------------------------------

PLAYER_TEMPLATE = "player.template.html"
PAYLOAD_PLACEHOLDER = "__FOND_PAYLOAD__"
PLAYER_SCHEMA = "fond-player/1"
# The payload JSON sits inside the page's <script> element, so every character that could
# close that element, open a comment or end a string literal is written as a \uXXXX escape
# (recipe-authoring "The player"): a title, a step's text, a URL or an author label from
# the export or a local file can never break out of the payload. json.dumps escapes the
# control characters already; these five it leaves alone.
_HTML_SAFE = {ord("<"): "\\u003c", ord(">"): "\\u003e", ord("&"): "\\u0026", 0x2028: "\\u2028", 0x2029: "\\u2029"}


def html_safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).translate(_HTML_SAFE)


def phases_of(step: Step) -> Tuple[List[Dict[str, Any]], int]:
    """The countdown phases a running step steps through, normalised per source: a DSL
    atom's countdowns are one iteration (its segments, `× N` already expanded) repeated
    `count=` times; a legacy row's countdowns arrive already expanded × repeat, so one of
    them repeated `repeat` times. Returns (phases, phases per iteration)."""
    if step.kind != "timer" or not step.countdowns:
        return [], 0
    one_iter = list(step.countdowns) if step.source == "dsl" else step.countdowns[:1]
    phases = []
    for it in range(1, step.count + 1):
        for seg, (minutes, label) in enumerate(one_iter, 1):
            phases.append({"min": minutes, "label": label, "iter": it, "iters": step.count, "seg": seg, "segs": len(one_iter)})
    return phases, len(one_iter)


def player_row(view: Export, recipe: Recipe) -> Dict[str, Any]:
    """One payload row, built with the script's own functions — `cmd_plan`, `build_graph`,
    `latest_start`, `order_key`, `timing_text` — never a second derivation, so the page's
    engine agrees with `plan` by construction. `view` is the export with the profile
    masked (as after `strip`), so the "you (@h)" by-line never reaches the page; the
    provenance lines are exactly what `show` prints."""
    content = view.content_of(recipe) or recipe
    plan = cmd_plan(view, recipe.id, None, None, True)
    graph = build_graph(content)
    lst0 = latest_start(graph, set(), {})
    ranked = sorted(graph.steps, key=lambda s: order_key(s, lst0))
    rank = {s.id: i for i, s in enumerate(ranked)}
    steps = []
    for s in graph.steps:
        phases, segs = phases_of(s)
        steps.append({
            "id": s.id, "ordinal": s.ordinal, "title": s.title, "text": s.text, "kind": s.kind,
            "occupies": s.occupies, "scheduled": s.scheduled, "deps": list(s.deps), "rank": rank[s.id],
            "prep": s.prep, "needs": s.needs, "done_when": s.spoken_done_when,
            "phases": phases, "segs": segs, "iters": s.count if s.kind == "timer" else 1,
            "timer_total": s.timer_total, "surplus": s.surplus, "structure": s.structure,
            "timing": timing_text(s), "source": s.source,
        })
    local = content.kind == "local"
    lineage = (content.envelope or {}).get("lineage") if local else None
    lineage = lineage if isinstance(lineage, dict) else {}
    if local:
        credits = [str(c) for c in lineage.get("credits")] if _is_list(lineage.get("credits")) else []
        changes = [str(c) for c in lineage.get("changes")] if _is_list(lineage.get("changes")) else []
    else:
        credits = credits_of(recipe) if recipe.lineage is not None else []
        changes = []
    return {
        "id": recipe.id, "title": recipe.label, "h": plan["h"],
        "source": "local" if local else plan["source"], "origin": content.origin if local else None,
        "byline": byline(recipe, view), "lineage": lineage_line(recipe.lineage), "url": recipe.url,
        "provenance_lines": provenance_block(recipe, view, content),
        "credits": credits, "changes": changes, "aliases": envelope_aliases(content) if local else {},
        "ingredients": plan["ingredients"], "wave1": plan["waves"][0], "estimate_minutes": plan["estimate_minutes"],
        "steps": steps,
    }


def player_rows(export: Export, recipes: List[Recipe]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """The payload rows for the given recipes, over the export with its profile masked; a
    Markdown row that carries no Fond id is skipped and named (the page keys its state on
    the id — build from the .json export)."""
    view = export if export.local else masked_view(export)
    originals = export.all_recipes()
    masked = view.all_recipes()
    rows: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for recipe in recipes:
        idx = next((i for i, r in enumerate(originals) if r is recipe), None)
        r = masked[idx] if idx is not None else recipe
        if not r.id:
            skipped.append(f"{r.label} carries no Fond id in this Markdown export, and the page keys its progress on the id; "
                           "build the player from the .json export")
            continue
        rows.append(player_row(view, r))
    return rows, skipped


def collection_id(export: Export, rows: List[Dict[str, Any]]) -> str:
    """The marker id of a multi-recipe page: a stable identity of the COLLECTION, so one
    export's or folder's page never replaces another's at the same path (the own-page
    rule, recipe-authoring "Written only to a file the user asks for"). A whole export is
    `export:<exportedAt>` — the header timestamp, a space no recipe id of the FOND1 line
    uses (the page's FOND1 `rid` stays the recipe's own id) — or, when the header has
    none, `export:<8hex>`, the first eight hex digits of SHA-256 over the sorted row ids;
    a folder is `library:<8hex>`, that hash over its sorted `local:` ids. The same export
    or the same set of files rebuilds its page in place under any `h=`."""
    ids_hash = body_hash("\n".join(sorted(str(r["id"]) for r in rows)))
    if export.local:
        return f"library:{ids_hash}"
    return f"export:{export.exported_at}" if export.exported_at else f"export:{ids_hash}"


def player_marker(rows: List[Dict[str, Any]], collection: str) -> Tuple[str, str]:
    """The marker's `h` and `id`: one recipe's own; for a whole export or folder, the
    collection id and the hash of every row's `<id> <h>` line. The id is kept to
    characters that cannot end the comment or the marker line."""
    if len(rows) == 1:
        rid, h = str(rows[0]["id"]), str(rows[0]["h"])
    else:
        rid, h = collection, body_hash("\n".join(f"{r['id']} {r['h']}" for r in rows))
    return h, re.sub(r"[^A-Za-z0-9_:.+-]", "-", rid)


def build_player_page(rows: List[Dict[str, Any]], collection: str) -> Tuple[str, str, str]:
    """The page: the template beside this script with its first line's marker filled in and
    the payload embedded HTML-safe on the one `const DATA` line; `collection` is the marker
    id a multi-recipe page carries (`collection_id`). Returns (page, h, id)."""
    template_path = Path(__file__).resolve().parent / PLAYER_TEMPLATE
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ExportError(f"Cannot read {template_path}: {e.strerror or e} — the player template ships beside the script.")
    first, rest = template.split("\n", 1)
    if rest.count(PAYLOAD_PLACEHOLDER) != 1 or "h=__FOND_H__" not in first:
        raise ExportError(f"{template_path.name} is damaged: the marker placeholder must be its first line and the payload "
                          "placeholder must appear exactly once.")
    h, rid = player_marker(rows, collection)
    marker = f"<!-- fond-player built by fond_export.py h={h} id={rid} -->"
    payload = html_safe_json({"schema": PLAYER_SCHEMA, "recipes": rows})
    return marker + "\n" + rest.replace(PAYLOAD_PLACEHOLDER, payload, 1), h, rid


def player_default_path(path: Path, chosen: List[Recipe], library: bool) -> Optional[Path]:
    """`<slug>.player.html` beside the export or the recipe file; `fond-player.html` beside
    a whole export or inside a folder; None for stdin (then `--out` is required)."""
    if str(path) == "-":
        return None
    if library:
        if len(chosen) == 1:
            r = chosen[0]
            folder = path if path.is_dir() else Path(r.local_path or path).parent
            return folder / f"{r.local_slug or slugify(r.label) or 'recipe'}.player.html"
        return path / "fond-player.html"
    if len(chosen) == 1:
        return path.with_name(f"{slugify(chosen[0].label) or 'recipe'}.player.html")
    return path.with_name("fond-player.html")


def cmd_player(export: Export, recipes: List[Recipe], out_path: Optional[str], default_path: Optional[Path],
               as_json: bool) -> Dict[str, Any]:
    """`player`: the page for one recipe or every cookable one, written through `_write_new`
    (a new path, or the player's own marked page rebuilt in place — decision 5); `--out -`
    prints the page, which is how the claude.ai artifact is published and republished."""
    rows, skipped = player_rows(export, recipes)
    if not rows:
        raise ExportError("nothing to play: " + ("; ".join(skipped) if skipped else "no cookable recipe"))
    page, h, rid = build_player_page(rows, collection_id(export, rows))
    base = {"id": rid, "h": h, "recipes": [r["id"] for r in rows], "payload": {"schema": PLAYER_SCHEMA, "recipes": rows},
            "page": page, "skipped": skipped}
    if out_path == "-":
        for s in skipped:
            print(f"Note: {s}", file=sys.stderr)  # the page alone goes to stdout
        return {**base, "path": None, "text": page.rstrip("\n")}
    target = Path(out_path) if out_path else default_path
    if target is None:
        raise ExportError("player over stdin needs --out <path> (or --out - to print the page).", code=2)
    _write_new(target, page)
    what = f"{rows[0]['title']} ({rid})" if len(rows) == 1 else f"{len(rows)} recipes ({rid})"
    lines = [f"Wrote {target} — the player page for {what}; marker h={h}. Open it in a browser; after an edit, run the "
             "same command again and this page is rebuilt in place."]
    lines += [f"Note: {s}" for s in skipped]
    return {**base, "path": str(target), "text": "\n".join(lines)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMANDS = ("list", "show", "plan", "missing", "strip", "history", "cook-again", "scale", "check", "convert", "player")
DSL_COMMANDS = ("list", "show", "plan", "scale", "strip", "player")


def h_stamp_arg(value: str) -> str:
    """The argparse type of `--h`: the stamp exactly as the FOND1 line carries it — eight hex
    digits, 0-9 and a-f (recipe-authoring "The FOND1 line carries `h=`") — or the parser
    exits 2 naming the value. Nothing is trimmed or case-folded into a stamp, so a malformed
    one (`garbage`, seven or nine digits, upper case) is refused rather than read as stale
    or as absent, the same as the page's paste box."""
    if not H_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"takes the eight hex digits (0-9, a-f) after `h=` in the FOND1 line, "
                                         f"not {value!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fond_export.py", description="Cook from a Fond data export, offline.",
                                epilog=__doc__.split("Semantics")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="fond-export-<date>.json (or the .md with --md); a recipe file, a folder or - (stdin) "
                                "with --dsl or check")
    p.add_argument("command", choices=COMMANDS)
    p.add_argument("title", nargs="*", help="recipe title, Fond id or handle (show, plan, history, scale, convert)")
    p.add_argument("--md", action="store_true", help="read the Markdown export instead of the JSON")
    p.add_argument("--dsl", action="store_true", help="read a local recipe file or a library folder instead of an export")
    p.add_argument("--parent", default=None, help="the export a variant derives from (check: required on a variant; "
                                                  "--dsl: optional, gates edits and fills `Derived from:`)")
    p.add_argument("--done", default=None, help="comma-separated resolved step ids (plan)")
    p.add_argument("--running", default=None, help="<id>=<minutes-left>[,…] for steps under way (plan)")
    p.add_argument("--h", dest="h_stamp", default=None, type=h_stamp_arg,
                   help="the h=<8hex> of a pasted FOND1 line (plan); a stale one is refused, a malformed one exits 2")
    p.add_argument("--json", action="store_true", help="print the answer as JSON")
    p.add_argument("--out", default=None, help="output path (strip, check, convert, player); `-` prints the convert draft "
                                               "or the player page to stdout")
    p.add_argument("--made-on", dest="made_on", default=None,
                   help="YYYY-MM-DD, today's date from the conversation (convert; optional — without it the draft's "
                        "made_on is empty and check asks for it)")
    p.add_argument("--factor", default=None, help="scale factor, e.g. 1.5 (scale)")
    p.add_argument("--from", dest="base", default=None, help="servings as written (scale)")
    p.add_argument("--to", dest="target", default=None, help="servings wanted (scale)")
    return p


def run(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = Path(args.file)
    query = " ".join(args.title).strip()
    try:
        if args.command == "check":
            result = cmd_check(args.file, args.parent, args.out, args.json)
        elif args.dsl:
            if args.command in ("history", "cook-again"):
                raise ExportError("a local file carries no cook history; `history` and `cook-again` read the export only.", code=2)
            if args.command not in DSL_COMMANDS:
                raise ExportError(f"`{args.command}` reads an export; a local file takes --dsl list | show | plan | scale "
                                  "(or `check`).", code=2)
            parent = load_export(Path(args.parent)) if args.parent else None
            export = load_library(path, parent)
            for w in export.warnings:
                print(f"Warning: {w}", file=sys.stderr)
            if args.command == "strip":
                result = cmd_strip(export, path, args.out)
            elif args.command == "list":
                result = cmd_dsl_list(export, args.json)
            elif args.command == "player":
                # One file by title (or the only file), or every file in a folder — each
                # through the gate first: nothing with findings is cooked.
                chosen = [find_recipe(export, query)] if query else list(export.authored)
                for r in chosen:
                    refuse_unless_clean(r, export)
                result = cmd_player(export, chosen, args.out, player_default_path(path, chosen, library=True), args.json)
            else:
                if not query and len(export.authored) == 1:
                    query = export.authored[0].id
                recipe = find_recipe(export, query)
                refuse_unless_clean(recipe, export)  # the gate runs first: nothing with findings is cooked
                if args.command == "show":
                    result = cmd_show(export, recipe.id, args.json)
                elif args.command == "plan":
                    result = cmd_plan(export, recipe.id, args.done, args.running, args.json, args.h_stamp)
                else:  # scale
                    result = cmd_scale(export, recipe.id, args.factor, args.base, args.target, args.json)
        else:
            export = load_export(path, markdown=args.md)
            for w in export.warnings:
                print(f"Warning: {w}", file=sys.stderr)
            if args.command == "list":
                result = cmd_list(export, args.json)
            elif args.command == "missing":
                result = cmd_missing(export, args.json)
            elif args.command == "show":
                result = cmd_show(export, query, args.json)
            elif args.command == "plan":
                result = cmd_plan(export, query, args.done, args.running, args.json, args.h_stamp)
            elif args.command == "history":
                result = cmd_history(export, query or None, args.json)
            elif args.command == "cook-again":
                result = cmd_cook_again(export, args.json)
            elif args.command == "scale":
                result = cmd_scale(export, query, args.factor, args.base, args.target, args.json)
            elif args.command == "convert":
                if args.base is not None or args.target is not None or args.factor is not None:
                    # One verb (recipe-authoring "Variant"): the body is the row's Fond-format
                    # steps when the export carries them, else the app's steps transliterated.
                    raise ExportError("convert takes no --from, --to or --factor: the body is the Fond-format steps the "
                                      "export carries, or for a nodes-only row the app's steps transliterated — the "
                                      "first `changes` entry says which (scale a recipe with `scale`).", code=2)
                result = cmd_convert(export, query, args.out, args.made_on, args.json)
            elif args.command == "player":
                chosen = [find_recipe(export, query)] if query else partition(export)[0]
                result = cmd_player(export, chosen, args.out, player_default_path(path, chosen, library=False), args.json)
            else:  # strip
                result = cmd_strip(export, path, args.out)
    except ExportError as e:
        if args.json:
            print(json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False, indent=2))
        else:
            print(str(e))
        return e.code
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(result["text"])
    return int(result.get("exit", 0)) if isinstance(result, dict) else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
