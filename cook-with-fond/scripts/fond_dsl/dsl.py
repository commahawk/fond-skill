# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""Fond DSL parsing and linting — pure-Python port for the MCP.

Mirrors the reference implementation's `render_classic.py` + `lint.py` mechanical rules.
Rule D (partition qty sum) is skipped here — it requires `pint` and full unit
arithmetic; the canonical implementation lives in reference/qty.py. The other
rules give 80% of the value with zero dependencies.

Spec reference: DSL_SPEC.md at the repo root (canonical)
"""

import re
import unicodedata
from graphlib import CycleError, TopologicalSorter
from typing import Dict, List, Optional, Set, Tuple

# The authoring card moved to services.authoring_guidance (Phase 6: ONE guidance
# source for MCP tool descriptions AND conversion prompts). Re-exported here for
# backward compatibility; import from authoring_guidance in new code.
from fond_dsl.authoring_guidance import AUTHORING_CARD_V1  # noqa: F401

# --------------------------------------------------------------------------
# Regex patterns — copied verbatim from render_classic.py
# --------------------------------------------------------------------------

ING_DEF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\{([^}]*)\}")
ING_REF = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*)")
ING_PART_DEF = re.compile(
    r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\[([A-Za-z0-9_-]+)\]\{([^}]*)\}"
)
ING_PART_REF = re.compile(
    r"@([A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*)\[([A-Za-z0-9_-]+)\](?!\{)"
)
STEP_REF = re.compile(r"\^\{([^}]+)\}")
TIMER = re.compile(r"~([A-Za-z_][A-Za-z0-9_-]*)?\{([^}]*)\}")
HEADER = re.compile(r"^##\s+(.+?)(?:\s*\[(.*?)\])?\s*$")

_TIMER_SEGMENT = re.compile(r"^\s*\d+(?:-\d+)?\s*%\w+\s*(?:×\s*\d+)?\s*$")

# Parsed timer segment for minute totals (rule AA + the scheduler's back-compat
# duration floor): lo[-hi]%unit [× N]. Low bound of ranges — conservative.
_TIMER_SEGMENT_VALUE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*%(\w+)(?:\s*×\s*(\d+))?"
)


def atom_count(meta) -> int:
    """The atom's iteration multiplier: `count=` (canonical, DSL_SPEC §1.4) with
    `iteration=` honored as the deprecated alias (`count` wins if both) — the
    intent-audit found the alias parsed and then silently IGNORED, dropping an
    authored multiplier from the schedule. Rule AB nudges the rename."""
    for key in ("count", "iteration"):
        v = meta.get(key)
        if v is not None:
            try:
                return max(1, int(str(v).strip()))
            except (TypeError, ValueError):
                continue
    return 1


def atom_duration_raw(meta) -> object:
    """The atom's authored wall-clock duration: `duration=` (canonical, DSL_SPEC
    §1.4) with `active=` as the legacy alias — `duration` wins if both are set.
    Returns the raw value (callers parse); None when neither key is present."""
    v = meta.get("duration")
    return v if v is not None else meta.get("active")


def timer_total_minutes(prose: str) -> int:
    """Sum of all ~timer sigil minutes in `prose` — low bound of ranges,
    honoring `× N` repeats. Units: h*/d* scale up, s* scales down, anything
    else (min, minutes, unknown) reads as minutes."""
    total = 0.0
    for m in TIMER.finditer(prose):
        for seg in _TIMER_SEGMENT_VALUE.finditer(m.group(2) or ""):
            lo = float(seg.group(1))
            unit = seg.group(3).lower()
            repeat = int(seg.group(4)) if seg.group(4) else 1
            if unit.startswith("h"):
                mins = lo * 60
            elif unit.startswith("s"):
                mins = lo / 60
            elif unit.startswith("d"):
                mins = lo * 1440
            else:
                mins = lo
            total += mins * repeat
    return int(round(total))
# Rule T — a stated duration in plain prose ("about 17 minutes", "3-4 min",
# "1 hour"). Digit-anchored on purpose: "a few minutes" is too vague to model,
# and unit words keep "1-inch pieces" out.
_PROSE_DURATION = re.compile(
    r"\b(?:about\s+|approximately\s+)?\d+(?:\s*(?:-|–|—|\bto\b)\s*\d+)?\s*(?:more\s+)?(?:minutes?|mins?|hours?|hrs?)\b",
    re.IGNORECASE,
)
_VALID_ATTENTION_LEVELS = {"none", "low", "medium", "high", "full"}
# Rule O — kebab-case identifier shape, with snake_case accepted as deprecated.
_KEBAB = re.compile(r"^[a-z][a-z0-9-]*$")
_KEBAB_OR_SNAKE = re.compile(r"^[a-z][a-z0-9_-]*$")


def normalize_slug(value: str) -> str:
    """Map snake_case → kebab-case. Leaves already-kebab unchanged."""
    return value.replace("_", "-")


# A def phrase's trailing PURPOSE clause ("water for sprinkling on the surface
# of the naan") is data for the list, noise for step text — display renders
# trim it (kitchen-found 2026-07-15: verbose Needs lines + bold step text).
_PURPOSE_TAIL = re.compile(r"\s+(?:for|to)\s+\w+ing\b.*$", re.IGNORECASE)


def strip_purpose_clause(phrase: str) -> str:
    """Drop a trailing gerund purpose clause from a def phrase for DISPLAY —
    'water for sprinkling on the surface of the naan' → 'water'. Gerund-only
    on purpose: ', to taste' and 'for the pan' stay. Never splits inside a
    parenthetical (the head must keep balanced parens)."""
    p = (phrase or "").strip()
    m = _PURPOSE_TAIL.search(p)
    if not m or m.start() == 0:
        return p
    head = p[: m.start()].strip().rstrip(",")
    if not head or not any(c.isalpha() for c in head) or head.count("(") != head.count(")"):
        return p
    return head


# The explicit prep slot (DSL_SPEC §2.1.1): `@slug{X}(Y)`. Absorbing it folds the
# prep into the inline `@slug{X, Y}` form so downstream passes that already handle
# inline prep (Classic render's list projection; the cook prep-lift) need no new
# machinery — the slot becomes a TRAILING clause, which the lift materializes
# unconditionally (leading-participle products stay gated). Parens INSIDE the braces
# are literal; only the `(…)` immediately after `}` is the slot.
_PREP_SLOT_RE = re.compile(
    r"(@[A-Za-z][A-Za-z0-9_-]*(?:\s[A-Za-z][A-Za-z0-9_-]*)*(?:\[[^\]]*\])?\{)"  # @slug[part]{
    r"([^{}]*)"  # phrase
    r"(\})"      # }
    r"\(([^()]*)\)"  # (prep)
)


def absorb_prep_slot(text: str) -> str:
    """Fold `@slug{X}(Y)` → `@slug{X, Y}` (idempotent; a no-op on un-slotted text)."""
    def _sub(m):
        head, phrase, close, prep = m.group(1), m.group(2).rstrip(), m.group(3), m.group(4).strip()
        if not prep:
            return f"{head}{phrase}{close}"
        joined = f"{phrase}, {prep}" if phrase else prep
        return f"{head}{joined}{close}"

    return _PREP_SLOT_RE.sub(_sub, text)


def check_slug_shape(value: str) -> Tuple[str, str]:
    """Return (severity, message). severity ∈ {'clean', 'warn', 'error'}."""
    if _KEBAB.match(value):
        return "clean", ""
    if _KEBAB_OR_SNAKE.match(value):
        return ("warn", f"{value!r} uses snake_case — kebab-case is canonical (use {normalize_slug(value)!r})")
    if value and value[0].isupper():
        return ("error", f"{value!r} starts with uppercase — slug ids must be lowercase kebab. "
                         "If you wrote `phase=Cook Rice`, the parser truncated at whitespace; use `phase=cook-rice`.")
    return ("error", f"{value!r} is not a valid slug — must match [a-z][a-z0-9-]*")
# Rule N — CookLang qty%unit shorthand pattern. If a canonical or partition
# bracket contains ONLY this pattern (no prose), it's the wrong format.
# Allows "1 cup 1% milk" or "2 lbs 85% lean beef" (% inside prose) but catches
# bare "2%lbs" / "4%tbsp" / "1/4%cup".
_COOKLANG_SHORTHAND = re.compile(r"^\s*\d+(?:[\s./]\d+)?\s*%\w+\s*$")
# Legacy v0 metadata field names — `t=5 a=0.7 w=10 out=foo` — were superseded
# by `active=5 attention_level=high hold=10 produces=foo phase=…` in v1. Steps
# using legacy fields don't schedule properly (no phase, no proper bandwidth
# model) and silently pass A–K. Rule L catches them.
_LEGACY_FIELDS = {"out", "t", "a", "w"}


# --------------------------------------------------------------------------
# Parsing helpers — minimal YAML + step parser
# --------------------------------------------------------------------------

def _parse_scalar(v: str):
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v in ("null", "~", ""):
        return None
    if v.startswith("[") and v.endswith("]"):
        return [p.strip().strip("\"'") for p in v[1:-1].split(",") if p.strip()]
    if v.isdigit():
        return int(v)
    return v


def parse_yaml(text: str) -> dict:
    """Minimal YAML subset sufficient for our frontmatter."""
    result: dict = {}
    stack: list = [(0, result)]
    lines = [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        while stack and indent < stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if stripped.startswith("- "):
            item_body = stripped[2:]
            if ":" in item_body:
                k, _, v = item_body.partition(":")
                item: dict = {k.strip(): _parse_scalar(v)}
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    nxt_indent = len(nxt) - len(nxt.lstrip())
                    if nxt_indent > indent and not nxt.lstrip().startswith("- "):
                        k2, _, v2 = nxt.lstrip().partition(":")
                        item[k2.strip()] = _parse_scalar(v2)
                        j += 1
                    else:
                        break
                if isinstance(parent, list):
                    parent.append(item)
                i = j
                continue
            else:
                if isinstance(parent, list):
                    parent.append(_parse_scalar(item_body))
                i += 1
                continue
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if not v:
                if i + 1 < len(lines) and lines[i + 1].lstrip().startswith("- "):
                    new_list: list = []
                    parent[k] = new_list
                    stack.append((indent + 2, new_list))
                else:
                    new_map: dict = {}
                    parent[k] = new_map
                    stack.append((indent + 2, new_map))
            else:
                parent[k] = _parse_scalar(v)
        i += 1
    return result


def split_frontmatter(text: str) -> Tuple[dict, str]:
    """Frontmatter is now OPTIONAL. The canonical document shape is:

        # Recipe Title
        ## Atom 1 [phase=X section=Y …]
        prose…

    If a YAML frontmatter block is present (legacy / hand-authored), it parses
    normally and contributes title/sections/phases. Otherwise we extract the
    title from the leading `# H1` line if there is one. Sections and phases
    are inferred from atom metadata downstream."""
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) == 3:
        fm = parse_yaml(parts[1]) or {}
        body = parts[2].lstrip("\n")
    else:
        fm = {}
        body = text

    # Promote a leading `# H1` line to fm['title'] if frontmatter didn't carry one.
    # Only the H1 BEFORE the first `## …` atom header counts as the title.
    if "title" not in fm:
        first_atom = re.search(r"^##\s+", body, re.MULTILINE)
        head = body[: first_atom.start()] if first_atom else body
        title_match = re.search(r"^\s*#\s+(.+?)\s*$", head, re.MULTILINE)
        if title_match:
            fm["title"] = title_match.group(1).strip()
    return fm, body


def parse_meta(meta_str: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if not meta_str:
        return meta
    for m in re.finditer(r"(\w+)=(\[[^\]]*\]|\S+)", meta_str):
        meta[m.group(1)] = m.group(2)
    return meta


def parse_steps(body: str) -> List[Dict]:
    steps: List[Dict] = []
    current: Optional[Dict] = None
    for line in body.split("\n"):
        m = HEADER.match(line)
        if m:
            if current is not None:
                current["prose"] = current["prose"].strip()
                steps.append(current)
            current = {"title": m.group(1).strip(), "meta": parse_meta(m.group(2) or ""), "prose": ""}
        elif current is not None:
            current["prose"] += line + "\n"
    if current is not None:
        current["prose"] = current["prose"].strip()
        steps.append(current)
    return steps


def is_derived(step: Dict) -> bool:
    return step["meta"].get("derived") in ("true", True)


def is_note(step: Dict) -> bool:
    return step["meta"].get("type") == "note"


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def parse_depends_on(value) -> List[str]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    if value.startswith("[") and value.endswith("]"):
        return [d.strip() for d in value[1:-1].split(",") if d.strip()]
    return [value.strip()] if value.strip() else []


def dag_health(dsl_text: str) -> dict:
    """Structural health of the step DAG — the single-sink invariant.

    A recipe's dependency graph should converge to ONE terminal step (plate/
    serve), so `sinks` (steps nothing depends on) and `components` (weakly
    connected subgraphs) are the flattening signals: a conversion that drops an
    ordering edge strands a branch as an extra sink/component, while a correct
    parallel DAG (two branches merging at the finish step) stays single-sink.
    Raw edge counts can't tell those apart — a fully serial chain maximizes
    edges, so counting rewards exactly the wrong shape.

    Returns {"steps": int, "edges": int, "sinks": [step-ids], "components": int}
    over the non-derived, non-note atoms — sinks stay named so correctives can
    point at the orphaned branch. Edges to unknown ids (rule A's domain) are
    ignored. A recipe that fails to parse reports empty across the board.
    """
    try:
        steps = [
            s for s in parse_steps(split_frontmatter(dsl_text)[1])
            if not is_derived(s) and not is_note(s)
        ]
    except Exception:  # noqa: BLE001
        return {"steps": 0, "edges": 0, "sinks": [], "components": 0}
    ids = [slugify(s["title"]) for s in steps]
    known = set(ids)
    edges = [
        (dep, sid)
        for s, sid in zip(steps, ids)
        for dep in parse_depends_on(s["meta"].get("depends_on", ""))
        if dep in known and dep != sid
    ]
    has_dependent = {dep for dep, _ in edges}
    parent = {i: i for i in ids}

    def _find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for dep, sid in edges:
        parent[_find(dep)] = _find(sid)
    return {
        "steps": len(ids),
        "edges": len(edges),
        "sinks": [i for i in ids if i not in has_dependent],
        "components": len({_find(i) for i in ids}),
    }


# --------------------------------------------------------------------------
# Shared ingredient-phrase helper — the SHORT "second-mention" form of a phrase.
# A first mention (a canonical @def) reads the full phrase; every later mention
# reads this stripped short form ("1 large yellow onion" → "yellow onion").
# Shared by prep-lift (prepped-reference short form) and the legacy ref renderer
# (V5-2: subsequent refs render unbracketed short form). Lives here in the base
# module so both consumers import it without a services.cook ↔ dsl_to_legacy cycle.
# --------------------------------------------------------------------------

FRACTION_CHARS = "¼-¾⅐-⅞"  # ¼-¾ and the vulgar-fraction block
# Leading tokens stripped for the short form: quantities, measurement units, and
# size adjectives. Colours / food-name words (green onion) are NOT stripped.
_SIZE_ADJ = {"large", "medium", "small", "big", "jumbo", "mini", "extra-large", "x-large"}
_UNITS = {
    "cup", "cups", "tablespoon", "tablespoons", "tbsp", "tbsps", "teaspoon",
    "teaspoons", "tsp", "tsps", "ounce", "ounces", "oz", "pound", "pounds", "lb",
    "lbs", "gram", "grams", "g", "kilogram", "kilograms", "kg", "ml",
    "milliliter", "milliliters", "liter", "liters", "l", "pint", "pints",
    "quart", "quarts", "gallon", "gallons", "stick", "sticks", "can", "cans",
    "package", "packages", "pkg", "jar", "jars", "bunch", "bunches", "sprig",
    "clove", "cloves",
    "sprigs", "head", "heads", "pinch", "pinches", "dash", "dashes", "handful",
    "handfuls", "piece", "pieces", "slice", "slices",
    # multilingual measure words (keep-source-language ruling 2026-07-13)
    "el", "esslöffel", "tl", "teelöffel", "tasse", "tassen", "gramm",
    "cda", "cdta", "taza", "tazas", "cucchiaio", "cucchiai", "cucchiaino",
    "cucchiaini", "tazza", "tazze", "eetlepel", "eetlepels", "theelepel",
    "theelepels",
}
# "plus" chains a second quantity ("1/2 cup plus 2 tbsp lemon juice") — the
# stripper must walk through it to the noun, else partition renders duplicate
# the tail ("2 1/2 tbsp plus 2 1/2 tbsp lemon juice").
_LEAD_FILLER = {"a", "an", "of", "to", "x", "×", "-", "–", "plus"}

# Rules AC/AD/AE tables (list-integrity checks, promoted from the conversion
# fidelity battery F6/F7/F8 — see DSL_SPEC §6).
_NOUNLESS_STOP = frozenset(
    {"divided", "optional", "plus", "more", "about", "approximately", "to",
     "taste", "or", "and", "of", "the", "each", "extra", "needed", "desired"}
)
_NON_FOOD_PHRASE = re.compile(
    r"\b(parchment|aluminum foil|tin foil|cheesecloth|toothpicks?|skewers?|"
    r"twine|plastic wrap|cling film|paper towels?|muffin liners?|cupcake liners?|"
    r"canning jars?|mason jars?|loaf tins?|cake tins?|springform)\b",
    re.IGNORECASE,
)
_NON_FOOD_HEADS = frozenset(
    {"jar", "jars", "tin", "tins", "liner", "liners", "ramekin", "ramekins",
     "foil", "cheesecloth", "twine", "skewer", "skewers", "toothpick",
     "toothpicks", "springform"}
)
_PANTRY_PROSE = re.compile(r"\b(cooking spray|non-?stick spray|baking spray)\b", re.IGNORECASE)
_QUANTITY = re.compile(rf"^[0-9{FRACTION_CHARS}][0-9{FRACTION_CHARS}/.\-–]*$")


def short_noun(base: str) -> str:
    """Strip a leading run of quantity / unit / size tokens off the base phrase,
    keeping the food noun ("2 large carrots" → "carrots"). Falls back to the whole
    base if stripping would empty it."""
    toks = base.split()
    i = 0
    while i < len(toks):
        t = toks[i].lower().strip(",.")
        if _QUANTITY.match(t) or t in _UNITS or t in _SIZE_ADJ or t in _LEAD_FILLER:
            i += 1
        else:
            break
    rest = toks[i:]
    return " ".join(rest) if rest else base


# --------------------------------------------------------------------------
# Lint — mechanical rules (A, B, C, E, F, G, H, I, J, K). Rule D skipped
# because qty.py + pint aren't available in this venv.
# --------------------------------------------------------------------------

def lint_dsl(dsl_text: str) -> dict:
    """Run mechanical lint rules against a DSL string.

    Returns:
        {
          "errors":      [ {rule, step, message} ],
          "warnings":    [ {rule, step, message} ],
          "suggestions": [ {step, message} ]
        }
    """
    errors: List[Dict] = []
    warnings: List[Dict] = []
    suggestions: List[Dict] = []

    fm, body = split_frontmatter(dsl_text)
    steps = parse_steps(body)

    step_ids: Set[str] = {slugify(s["title"]) for s in steps}

    # Rule AI — atom ids must be unique (§1.3: titles must slugify to a unique
    # id). The scheduler keys nodes by slug, so a duplicate SILENTLY SWALLOWS
    # the earlier atom: its duration vanishes from makespan and its edges from
    # the DAG. ERROR tier — this destroys authored steps.
    _seen_ids: Dict[str, str] = {}
    for s in steps:
        sid_ = slugify(s["title"])
        if sid_ in _seen_ids:
            errors.append({
                "rule": "AI", "step": sid_,
                "message": (
                    f"duplicate atom id '{sid_}' — '{s['title']}' and "
                    f"'{_seen_ids[sid_]}' slugify identically, so the scheduler "
                    "silently drops the earlier atom; retitle one "
                    "('## Rest the Dough' / '## Rest the Steak')"
                ),
            })
        else:
            _seen_ids[sid_] = s["title"]

    # Note atoms never schedule — a dependency edge pointing at one dangles
    # (the scheduler drops it and the ordering intent is lost). Rule A below
    # checks existence; this checks schedulability.
    _note_ids = {slugify(s["title"]) for s in steps if is_note(s)}

    raw_phases = fm.get("phases") or []
    declared_mode = bool(raw_phases)  # frontmatter declared phases → strict mode

    # Strict-mode malformed-phase detection (only fires when frontmatter is present).
    malformed_phase_strings: List[str] = []
    if declared_mode:
        for p in raw_phases:
            if isinstance(p, str):
                malformed_phase_strings.append(p)
            elif isinstance(p, dict) and "id" not in p:
                errors.append({
                    "rule": "J",
                    "step": None,
                    "message": (
                        f"phases entry {p!r} is missing required `id` field. "
                        "Format: `- id: cook_rice\\n    section: bowls`"
                    ),
                })
        if malformed_phase_strings:
            errors.append({
                "rule": "J",
                "step": None,
                "message": (
                    f"phases list contains {len(malformed_phase_strings)} string(s) "
                    f"({malformed_phase_strings[:3]!r}...) instead of structured "
                    "{id, section} objects. Fix: rewrite each phase entry like "
                    "`- id: cook_rice\\n    section: bowls` (snake_case id, no spaces). "
                    "Step headers must then reference the id: `[phase=cook_rice ...]`."
                ),
            })

    # Inferred mode: phase_ids derive from atom metadata. Strict mode: phase_ids
    # come from frontmatter declarations (and orphan checks fire below).
    if declared_mode:
        phase_ids: Set[str] = {p["id"] for p in raw_phases if isinstance(p, dict) and "id" in p}
    else:
        phase_ids = {s["meta"]["phase"] for s in steps if s["meta"].get("phase")}

    # Rule I — depends_on cycle detection
    ts: TopologicalSorter = TopologicalSorter()
    for step in steps:
        sid = slugify(step["title"])
        deps = parse_depends_on(step["meta"].get("depends_on", ""))
        ts.add(sid, *deps)
    try:
        ts.prepare()
    except CycleError as e:
        cycle = e.args[1] if len(e.args) > 1 else []
        errors.append({"rule": "I", "step": None, "message": f"depends_on cycle: {' → '.join(cycle)}"})

    # Rule J — phase orphans (only checked when frontmatter declared phases).
    # In inferred mode, phase_ids == phases_with_atoms by construction, so
    # there are no orphans to check.
    phases_with_atoms: Set[str] = {s["meta"]["phase"] for s in steps if s["meta"].get("phase")}
    if declared_mode:
        for phase in phase_ids - phases_with_atoms:
            errors.append({
                "rule": "J",
                "step": None,
                "message": (
                    f"phase '{phase}' declared in frontmatter but no atom references it. "
                    "Either remove the orphaned phase declaration, or add the atom(s) it was "
                    "meant to group."
                ),
            })
    for phase in phases_with_atoms - phase_ids:
        if phase is None:
            continue
        # Common pitfall: metadata parser stops at whitespace, so `phase=Cook Rice`
        # parses as `phase=Cook`. Look for prefix collisions in both the proper
        # declared phase ids AND in the malformed string-list (so we can point
        # at the literal `- Cook Rice` the writer wrote).
        whitespace_collision = (
            [p for p in phase_ids if " " in p and p.split(" ", 1)[0].lower() == phase.lower()]
            + [p for p in malformed_phase_strings if " " in p and p.split(" ", 1)[0].lower() == phase.lower()]
        )
        declared_hint = sorted(phase_ids)[:6] or ["(none declared)"]
        if whitespace_collision:
            errors.append({
                "rule": "J",
                "step": None,
                "message": (
                    f"step references phase=[{phase}] but the closest declared id is "
                    f"'{whitespace_collision[0]}' (contains a space). "
                    "Phase ids must be snake_case slugs without whitespace — "
                    "metadata values stop at the first space. "
                    f"Declared phases: {declared_hint}"
                ),
            })
        else:
            errors.append({
                "rule": "J",
                "step": None,
                "message": (
                    f"step references phase=[{phase}] but it's not declared in frontmatter. "
                    f"Declared phases: {declared_hint}"
                ),
            })

    # First pass: collect partition defs and canonicals
    divided_canonicals: Set[str] = set()
    partition_defs: Set[Tuple[str, str]] = set()
    for step in steps:
        for m in ING_DEF.finditer(step["prose"]):
            if "divided" in m.group(2).lower():
                divided_canonicals.add(m.group(1))
        for m in ING_PART_DEF.finditer(step["prose"]):
            partition_defs.add((m.group(1), m.group(2)))

    # Per-step rules
    has_attention = 0
    total_atoms = 0
    for step in steps:
        sid = slugify(step["title"])
        prose = step["prose"]

        if not (is_derived(step) or is_note(step)):
            total_atoms += 1
            if step["meta"].get("attention_level") or step["meta"].get("attention"):
                has_attention += 1

        # Rule L — modern format required. Legacy v0 fields (out, t, a, w) AND
        # the absence of `phase=` on a non-derived non-note atom both produce a
        # silently-passes-but-unschedulable recipe. Catch both.
        if not (is_derived(step) or is_note(step)):
            legacy_used = sorted(_LEGACY_FIELDS.intersection(step["meta"].keys()))
            if legacy_used:
                errors.append({
                    "rule": "L",
                    "step": sid,
                    "message": (
                        f"uses legacy v0 metadata field(s) {legacy_used} — these don't schedule. "
                        f"Upgrade: t=N → active=N; a=F → attention_level=<none|low|medium|high|full>; "
                        f"w=N → hold=N; out=foo → drop (use phase= for grouping instead). "
                        "See DSL_SPEC §1.3."
                    ),
                })
            elif "phase" not in step["meta"]:
                errors.append({
                    "rule": "L",
                    "step": sid,
                    "message": (
                        "non-derived atom must declare phase=<phase_id>. Without phase, this step "
                        "can't be grouped into a Classic paragraph and can't be scheduled by the optimizer. "
                        "See DSL_SPEC §1.3."
                    ),
                })

        # Rule K — attention_level value valid
        level = step["meta"].get("attention_level")
        if level is not None:
            if str(level).strip().lower() not in _VALID_ATTENTION_LEVELS:
                errors.append({"rule": "K", "step": sid, "message": f"attention_level={level!r} — must be one of {sorted(_VALID_ATTENTION_LEVELS)}"})
            if step["meta"].get("attention") is not None:
                warnings.append({"rule": "K", "step": sid, "message": "both attention_level and attention set — attention_level wins; remove the numeric one"})

        # Rule H — count is positive integer
        count = step["meta"].get("count")
        if count is not None:
            try:
                if int(count) < 1:
                    errors.append({"rule": "H", "step": sid, "message": f"count={count} must be a positive integer"})
            except (TypeError, ValueError):
                errors.append({"rule": "H", "step": sid, "message": f"count={count} is not a valid integer"})

        # Rule O — kebab identifier shape on slug-position values
        for key in ("phase", "section"):
            raw = step["meta"].get(key)
            if raw is None:
                continue
            sev, msg = check_slug_shape(str(raw))
            if sev == "error":
                errors.append({"rule": "O", "step": sid, "message": f"{key}={raw!r} — {msg}"})
            elif sev == "warn":
                warnings.append({"rule": "O", "step": sid, "message": f"{key}={raw!r} — {msg}"})
        for dep_raw in parse_depends_on(step["meta"].get("depends_on", "")):
            sev, msg = check_slug_shape(str(dep_raw))
            if sev == "error":
                errors.append({"rule": "O", "step": sid, "message": f"depends_on=[…{dep_raw!r}…] — {msg}"})
            elif sev == "warn":
                warnings.append({"rule": "O", "step": sid, "message": f"depends_on=[…{dep_raw!r}…] — {msg}"})
        # Inline annotation slugs (canonicals, partition defs) — multi-word /
        # snake captures emit Rule O warnings.
        for m in ING_DEF.finditer(prose):
            slug = m.group(1)
            if " " in slug or "_" in slug:
                kebab = normalize_slug(slug).replace(" ", "-")
                if _KEBAB.match(kebab):
                    warnings.append({"rule": "O", "step": sid, "message": f"@{slug}{{…}} — multi-word/snake slug; canonical is `@{kebab}{{…}}`"})
        for m in ING_PART_DEF.finditer(prose):
            slug = m.group(1)
            if " " in slug or "_" in slug:
                kebab = normalize_slug(slug).replace(" ", "-")
                if _KEBAB.match(kebab):
                    warnings.append({"rule": "O", "step": sid, "message": f"@{slug}[…] — multi-word/snake slug; canonical is `@{kebab}[…]`"})

        # Rule A — depends_on resolves (normalized so kebab/snake interop) AND
        # points at a schedulable atom (a note never schedules; an edge into
        # one silently dangles in the DAG).
        step_ids_norm = {normalize_slug(s) for s in step_ids}
        note_ids_norm = {normalize_slug(s) for s in _note_ids}
        for dep in parse_depends_on(step["meta"].get("depends_on", "")):
            if normalize_slug(dep) not in step_ids_norm:
                errors.append({"rule": "A", "step": sid, "message": f"depends_on=[…{dep}…] — no step with that id"})
            elif normalize_slug(dep) in note_ids_norm:
                errors.append({
                    "rule": "A", "step": sid,
                    "message": (
                        f"depends_on=[…{dep}…] points at a type=note atom — notes never "
                        "schedule, so the edge silently dangles; depend on a regular atom "
                        "(or make the note a real step)"
                    ),
                })

        # Rule B — ^{step-slug} resolves to an in-recipe step. v1 carets are
        # in-recipe step references ONLY; the colon form ^{handle:artifact} is
        # removed — cross-recipe components are linked with @<handle>{yield}.
        phase_ids_norm = {normalize_slug(p) for p in phase_ids}
        for m in STEP_REF.finditer(prose):
            ref = m.group(1).strip()
            if ":" in ref:
                errors.append({"rule": "B", "step": sid, "message": f"^{{{ref}}} — ':' in a caret body is not valid in v1; carets are in-recipe refs by PHASE id `^{{phase-id}}`. Link another recipe with `@{{handle}}{{yield}}` instead."})
                continue
            if normalize_slug(ref) not in phase_ids_norm:
                # Refire-driven surgery (69 consecutive-wave repeats on the old
                # one-liner): name the fix moves, suggest the nearest valid id,
                # and teach the general rule ONCE so the model checks every
                # caret instead of fixing them one rejection at a time.
                import difflib  # noqa: PLC0415

                close = difflib.get_close_matches(
                    normalize_slug(ref), sorted(phase_ids_norm), n=1, cutoff=0.6
                )
                hint = f" Did you mean ^{{{close[0]}}}?" if close else ""
                errors.append({"rule": "B", "step": sid, "message": (
                    f"^{{{ref}}} matches no step's phase id in THIS recipe.{hint} "
                    "Every caret must name a phase id that appears on a ## step's "
                    "metadata — check ALL carets in the draft now, not just this one. "
                    "Fix moves: rename the caret to an existing id, add the step it "
                    "should point to, or delete the caret and write the step name in prose."
                )})

        # Rule C — partition refs resolve
        for m in ING_PART_REF.finditer(prose):
            slug, part = m.group(1), m.group(2)
            if (slug, part) in partition_defs:
                continue
            if part == "remainder":
                siblings = {p for (s, p) in partition_defs if s == slug}
                if slug in divided_canonicals or siblings:
                    continue
                warnings.append({"rule": "C", "step": sid, "message": f"@{slug}[remainder] but no canonical @{slug}{{…divided…}} or sibling partitions exist"})
            else:
                errors.append({"rule": "C", "step": sid, "message": f"@{slug}[{part}] but no @{slug}[{part}]{{…}} definition anywhere"})

        # Rule E — sentence-final punctuation
        if not (is_derived(step) or is_note(step)):
            trimmed = prose.rstrip()
            if trimmed and trimmed[-1] not in ".!?…":
                warnings.append({"rule": "E", "step": sid, "message": f"prose doesn't end with sentence-final punctuation (…{trimmed[-30:]!r})"})

        # Rule G — timer body parses
        for m in TIMER.finditer(prose):
            name, body_text = m.group(1) or "", m.group(2)
            segments = [s.strip() for s in body_text.split(",") if s.strip()]
            if not segments:
                errors.append({"rule": "G", "step": sid, "message": f"timer ~{name}{{}} has empty body"})
                continue
            for seg in segments:
                if not _TIMER_SEGMENT.match(seg):
                    errors.append({"rule": "G", "step": sid, "message": f"timer ~{name}{{{body_text}}} segment '{seg}' doesn't match <X[-Y]%unit [× N]>"})
                    break

        # Rule N — canonical and partition brackets must NOT use CookLang
        # qty%unit shorthand. Only timer ~name{X%min} brackets can use %.
        # Detects bare patterns like @x{2%lbs}, @x{1/4%cup}.
        for m in ING_DEF.finditer(prose):
            text = m.group(2)
            if _COOKLANG_SHORTHAND.match(text):
                errors.append({
                    "rule": "N",
                    "step": sid,
                    "message": (
                        f"@{m.group(1)}{{{text}}} uses CookLang qty%unit shorthand. "
                        "Canonical brackets hold the creator's verbatim ingredient line "
                        f"(e.g., `@{m.group(1)}{{2 lbs ground lamb}}`). The `%` syntax is "
                        "reserved for timer ~name{X%min} brackets. See DSL_SPEC §2.0."
                    ),
                })
        for m in ING_PART_DEF.finditer(prose):
            text = m.group(3)
            if _COOKLANG_SHORTHAND.match(text):
                errors.append({
                    "rule": "N",
                    "step": sid,
                    "message": (
                        f"@{m.group(1)}[{m.group(2)}]{{{text}}} uses CookLang qty%unit shorthand. "
                        "Partition brackets hold a natural-language qty phrase "
                        f"(e.g., `@{m.group(1)}[{m.group(2)}]{{1/4 cup}}` or `{{a splash of}}`). "
                        "See DSL_SPEC §2.0."
                    ),
                })

        # Rule F — partition def qty duplicates adjacent prose
        for m in ING_PART_DEF.finditer(prose):
            bracket = m.group(3).strip()
            if not bracket:
                continue
            window_start = max(0, m.start() - 40)
            context = prose[window_start:m.start()]
            if bracket.lower() in context.lower():
                snippet = context.strip()[-40:]
                warnings.append({"rule": "F", "step": sid, "message": (
                    f"@{m.group(1)}[{m.group(2)}]{{{bracket}}} — the quantity also appears in the "
                    f"prose just before it (\"…{snippet}\"), so the render shows it twice. "
                    f"DELETE the prose copy: the sigil bracket is the single source of quantity; "
                    f"let the sentence read naturally around @{m.group(1)}[{m.group(2)}]"
                )})

    # Rule M — recipe must contain at least one schedulable atom. Catches the
    # case where an agent submits some other schema entirely — fabricated YAML
    # with `proposals`/`contracts`/`demands`, raw prose, schema.org JSON, etc.
    # Without atoms, every per-step rule iterates empty and silently passes.
    if total_atoms == 0:
        errors.append({
            "rule": "M",
            "step": None,
            "message": (
                "recipe has no schedulable atoms — found 0 non-derived non-note `## <Title> [phase=…]` headers. "
                "A valid Fond DSL recipe must contain at least one atomic step with `phase=`. "
                "Author each step as its own `## <Verb Phrase> [phase=… section=… duration=… attention_level=…]` "
                "block and re-run the evaluation. See DSL_SPEC §1.2."
            ),
        })

    # Suggestions — soft hints, not gating. Must carry a rule key: LintIssue
    # requires it, and evaluate_dsl() crashes on rule-less suggestions.
    if total_atoms and has_attention < total_atoms / 2:
        suggestions.append({"rule": "S", "step": None, "message": f"{total_atoms - has_attention} of {total_atoms} non-derived atoms lack attention_level; optimizer can't find parallelism without it"})

    # Rule U — undeclared ordering (DSL_SPEC §6): ≥3 non-derived atoms and ZERO
    # depends_on edges anywhere. The scheduler treats dependency-free atoms as
    # fully parallel, so a bread flow presents every step as immediately
    # available. Suggestion — genuinely order-free recipes exist but are rare.
    real_steps = [s for s in steps if not is_derived(s) and not is_note(s)]
    if len(real_steps) >= 3 and not any(
        parse_depends_on(s["meta"].get("depends_on", "")) for s in real_steps
    ):
        suggestions.append({
            "rule": "U",
            "step": None,
            "message": (
                f"{len(real_steps)} steps but no depends_on edges — the scheduler treats "
                "every step as available at once; declare ordering (e.g. "
                "depends_on=[previous-step]) where the recipe requires it"
            ),
        })

    # Rule V — non-convergent step DAG (DSL_SPEC §6): ordering is partially
    # declared (≥1 edge) but the graph has >1 sink, so a branch dangles with no
    # step consuming it — usually a missing depends_on on the consumer. The
    # single-sink invariant, not edge counts: a correct parallel DAG stays
    # single-sink while a dropped edge strands an extra one.
    if len(real_steps) >= 3:
        health = dag_health(dsl_text)
        if health["edges"] and len(health["sinks"]) > 1:
            named = ", ".join(health["sinks"][:4])
            suggestions.append({
                "rule": "V",
                "step": None,
                "message": (
                    f"step DAG does not converge: {len(health['sinks'])} terminal steps "
                    f"({named}) — a recipe should flow to ONE final step; add depends_on "
                    "to the step that consumes each dangling branch"
                ),
            })

    # Rule W — numbered ingredient slugs (DSL_SPEC §6): @salt … @salt2 (or
    # @salt1/@salt2 with no bare base) splits ONE ingredient into fake distinct
    # entries on the derived list. Repeats are bare @slug refs; divided amounts
    # are partitions. Warning: the recipe still parses, the list is just wrong.
    def_sites: Dict[str, str] = {}  # slug -> first step id
    for step in steps:
        for m in ING_DEF.finditer(step["prose"]):
            def_sites.setdefault(m.group(1), slugify(step["title"]))
    numbered_bases: Dict[str, List[str]] = {}
    for slug in def_sites:
        base = slug.rstrip("0123456789")
        if base != slug and len(base) >= 2 and not base.endswith("-"):
            numbered_bases.setdefault(base, []).append(slug)
    for base, numbered in sorted(numbered_bases.items()):
        if base in def_sites or len(numbered) >= 2:
            offenders = ", ".join(f"@{s}" for s in sorted(numbered))
            warnings.append({
                "rule": "W",
                "step": def_sites[sorted(numbered)[0]],
                "message": (
                    f"numbered slug(s) {offenders} — one ingredient keeps ONE slug: repeat "
                    f"uses are bare @{base} references; a divided amount uses partitions "
                    f"(@{base}[part]{{qty}})"
                ),
            })

    # Rule O extension — a def slug that IS a measure word (@cloves{3 garlic
    # cloves}) canonicalizes to the wrong entity entirely (cloves-the-spice).
    # The slug names the FOOD; the measure lives in the phrase.
    for step in steps:
        sid = slugify(step["title"])
        for m in list(ING_DEF.finditer(step["prose"])) + list(ING_PART_DEF.finditer(step["prose"])):
            slug_l = normalize_slug(m.group(1)).lower()
            if slug_l in _UNITS:
                errors.append({
                    "rule": "O", "step": sid,
                    "message": (
                        f"@{m.group(1)} — the slug is a MEASURE word; name the food "
                        f"instead (e.g. @garlic{{3 garlic cloves}}, not @cloves)"
                    ),
                })

    # Rules P / Q / Z / R — conversion-agent idioms found by the zone pilot
    # (2026-07-10 founder cook test): markdown backticks in prose, "remainder"
    # in the qty slot, chained sigil forms, and divided totals restated in
    # parenthetical prose. P/Q/Z are errors (they corrupt the render); R is the
    # authoring-pattern nudge.
    _restated_total = re.compile(
        r"\(\s*from[^()]*@[a-z][a-z0-9-]*\{[^}]*divided[^}]*\}\s*\)", re.IGNORECASE
    )
    for step in steps:
        sid = slugify(step["title"])
        prose = step["prose"]
        if "`" in prose:
            errors.append({
                "rule": "P", "step": sid,
                "message": (
                    "backtick(s) in prose — markdown artifacts, never DSL syntax; they reach "
                    "clients as literal characters. Remove them (sigils need no quoting)"
                ),
            })
        for m in ING_PART_DEF.finditer(prose):
            if m.group(3).strip().lower() == "remainder":
                errors.append({
                    "rule": "Q", "step": sid,
                    "message": (
                        f"@{m.group(1)}[{m.group(2)}]{{remainder}} — 'remainder' is a partition "
                        f"NAME, not a quantity: write @{m.group(1)}[remainder] (no braces)"
                    ),
                })
        for m in ING_DEF.finditer(prose):
            # NB: tuple membership, not `in "[{"` — the empty slice at end-of-prose
            # is a substring of any string and falsely fired (then crashed the
            # message's direct index) whenever a def closed the prose block.
            nxt = prose[m.end():m.end() + 1]
            if nxt in ("[", "{"):
                errors.append({
                    "rule": "Z", "step": sid,
                    "message": (
                        f"@{m.group(1)}{{…}} is immediately followed by '{nxt}' — one "
                        "sigil carries ONE form; write the partition as its own @-sigil "
                        "(the tail renders as garbage otherwise)"
                    ),
                })
        for m in ING_PART_REF.finditer(prose):
            if prose[m.end():m.end() + 1] == "[":
                errors.append({
                    "rule": "Z", "step": sid,
                    "message": (
                        f"@{m.group(1)}[…] is immediately followed by a second '[' — one "
                        "partition per sigil (use @slug[remainder] alone for the rest)"
                    ),
                })
        if _restated_total.search(prose):
            suggestions.append({
                "rule": "R", "step": sid,
                "message": (
                    "the divided total is restated in prose ('(from @x{…, divided})') — the "
                    "total is DATA: declare it once in a [type=note] atom (e.g. '## Also "
                    "Needed [type=note]') and let each partition carry only its step amount"
                ),
            })

    # Rule Y — partition defs without a canonical total (DSL_SPEC §6): the
    # ingredient list projects from canonical defs only, so @x[a]{…} with no
    # @x{…} anywhere silently drops x from the derived list. Found in the wild
    # by the faithfulness judge — invisible to every other rule.
    canonical_slugs = set(def_sites)
    for pslug in sorted({s for s, _ in partition_defs}):
        if pslug not in canonical_slugs:
            parts = ", ".join(sorted(p for s, p in partition_defs if s == pslug))
            warnings.append({
                "rule": "Y",
                "step": None,
                "message": (
                    f"@{pslug} has partition defs ([{parts}]) but no canonical @{pslug}{{…}} "
                    f"definition — the derived ingredient list omits it; declare the total on "
                    f"first use (e.g. @{pslug}{{<total qty>, divided}}) and keep the partitions"
                ),
            })

    # Rule X — repeated action not modeled (DSL_SPEC §6): prose says "per side" /
    # "each side" but every timer on the atom is a single segment with no `× N`,
    # so the runtime fires ONE timer for a two-side task. No timer at all is
    # rule T's territory; X fires only when a timer exists but under-models.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        prose = step["prose"]
        if not re.search(r"\b(?:per|on\s+each|each)\s+side\b", prose, re.IGNORECASE):
            continue
        bodies = [m.group(2) for m in TIMER.finditer(prose)]
        if not bodies:
            continue
        modeled = any(
            "," in b or re.search(r"×\s*\d|(?<![A-Za-z0-9])[xX]\s*\d", b) for b in bodies
        )
        if not modeled:
            suggestions.append({
                "rule": "X",
                "step": slugify(step["title"]),
                "message": (
                    "prose says the action repeats per side but the timer has a single "
                    "segment — declare the repeat (~name{X%min × 2}) so the runtime fires "
                    "one timer per side"
                ),
            })

    # Rule T — un-sigiled duration (DSL_SPEC §6): the atom's prose states a
    # duration but carries NO ~timer, so the scheduler/runtime treat that time as
    # zero (a 17-minute simmer schedules as if instant, e.g. rice placed 3 minutes
    # before serving). Any timer on the atom counts as modeled — no nagging about
    # prose that restates a sigiled duration.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        if TIMER.search(step["prose"]):
            continue
        m = _PROSE_DURATION.search(step["prose"])
        if m:
            suggestions.append({
                "rule": "T",
                "step": slugify(step["title"]),
                "message": (
                    f"prose states a duration (\"{m.group(0).strip()}\") but the atom has no ~timer — "
                    "the runtime and lock screen only fire sigiled timers; add ~name{X%min} so the cook is alerted"
                ),
            })

    # Rule AA — time conservation (DSL_SPEC §1.4/§3.4; first two-letter rule).
    # active= is the atom's WALL-CLOCK duration; the scheduler models time from
    # it. Fires when (a) active= fails to parse (it would silently schedule as a
    # 0-minute atom), or (b) the atom's ~timer total meaningfully exceeds active=
    # (>2x and ≥10m gap) — the retired hands-on-minutes convention, which
    # collapses makespan (an 18h rise scheduling inside a 17-minute recipe).
    # A GATED WARNING, not an error: it blocks submit AND saving to the corpus (GATED_RULES)
    # with the same teaching strength, but never suppresses scheduling — the
    # back-compat duration floor must keep old-corpus compile output honest.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        slug = slugify(step["title"])
        raw_duration = atom_duration_raw(step["meta"])
        duration_val = 0
        if raw_duration is not None:
            try:
                duration_val = int(str(raw_duration).strip())
            except (TypeError, ValueError):
                warnings.append({
                    "rule": "AA",
                    "step": slug,
                    "message": (
                        f"duration={raw_duration!r} does not parse — duration= is the atom's wall-clock "
                        "duration in integer minutes (an unparseable value schedules as a 0-minute atom)"
                    ),
                })
                continue
        t_total = timer_total_minutes(step["prose"])
        # Strict invariant (founder 2026-07-15): an atom's timers are alarms
        # INSIDE its wall-clock — their sum may never exceed duration=. (The
        # old 2x + 10-minute looseness dated to the active=-era corpus.)
        if t_total > 0 and t_total > max(duration_val, 1):
            warnings.append({
                "rule": "AA",
                "step": slug,
                "message": (
                    f"timer total {t_total}m exceeds duration={duration_val} — duration= is the atom's "
                    "WALL-CLOCK time (the scheduler models time from it), not hands-on minutes; "
                    f"set duration={t_total} and let attention_level carry the hands-on share "
                    "(a passive stretch is attention_level=none)"
                ),
            })
        # Missing attention_level silently resolves to FULL (1.0) — under
        # wall-clock hands-on derivation that counts an unlabeled 18h rise as
        # 1,080 hands-on minutes. Required on every schedulable atom.
        if not step["meta"].get("attention_level") and not step["meta"].get("attention"):
            warnings.append({
                "rule": "AA",
                "step": slug,
                "message": (
                    "attention_level is missing — hands-on time DERIVES from it, and a "
                    "missing level defaults to full (the whole duration counts as hands-on). "
                    "Set attention_level=none|low|medium|high|full (verb rule of thumb: "
                    "sauté→medium, sear→high, whisk→full, bake/rise→none)"
                ),
            })

    # Rules AC / AD / AE — list-integrity checks promoted from the conversion
    # fidelity battery (F6/F7/F8, DSL_SPEC §6) so BOTH agent populations face
    # them: they need no source text, only the DSL. Gated warnings (GATED_RULES)
    # — block submit and saving to the corpus, never suppress scheduling.
    note_lines: list = []
    for step in steps:
        if is_note(step):
            note_lines.extend(ln.strip() for ln in step["prose"].splitlines() if ln.strip())
    all_def_texts = [m.group(2) for step in steps for m in ING_DEF.finditer(step["prose"])]
    all_def_texts += [m.group(3) for step in steps for m in ING_PART_DEF.finditer(step["prose"])]
    all_def_texts += note_lines
    for step in steps:
        slug = slugify(step["title"])
        for m in ING_DEF.finditer(step["prose"]):
            phrase = m.group(2).strip()
            if not phrase:
                continue
            if re.fullmatch(r"ingredient-\d+", m.group(1)):
                continue  # translator placeholder for a nameless legacy line — no food name exists
            base = re.sub(r"\([^)]*\)", "", phrase)
            toks = [t.strip(".,()").lower() for t in base.split()]
            food = [t for t in toks
                    if t and not _QUANTITY.match(t) and t not in _UNITS
                    and t not in _SIZE_ADJ and t not in _LEAD_FILLER
                    and t not in _NOUNLESS_STOP and not any(c.isdigit() for c in t)]
            if not food:
                warnings.append({
                    "rule": "AC", "step": slug,
                    "message": (
                        f"@{m.group(1)}{{{phrase}}} never names the food — the braces are the "
                        f"ingredient-list display line (write \"{phrase} {m.group(1).replace('-', ' ')}\"); "
                        "the slug is a key, not display text"
                    ),
                })
                continue
            words = [w.strip(".,()").lower() for w in short_noun(base).split(",")[0].split()]
            head_full = words[-1] if words else ""
            if _NON_FOOD_PHRASE.search(phrase) or head_full in _NON_FOOD_HEADS:
                warnings.append({
                    "rule": "AD", "step": slug,
                    "message": (
                        f"@{m.group(1)}{{{phrase}}} is equipment/packaging, not food — move it to "
                        "the atom's equipment=[…]; the ingredient list is a shopping list of FOOD"
                    ),
                })
    body_prose = "\n".join(step["prose"] for step in steps)
    pm = _PANTRY_PROSE.search(body_prose)
    if pm and not any(pm.group(1).lower() in t.lower() for t in all_def_texts):
        warnings.append({
            "rule": "AE", "step": None,
            "message": (
                f"\"{pm.group(1)}\" is used in a step but never reaches the ingredient list — "
                "give it a def (an Also Needed [type=note] atom with "
                f"@spray{{{pm.group(1).lower()}}} is enough)"
            ),
        })

    # Rule AF — one atom, one timed movement (DSL_SPEC §6). Two SEPARATE ~timer
    # sigils in one atom play back as one epically-long step with buried timers
    # (kitchen-found: "Build Fire and Heat Grate"); the card prefers a split.
    # Suggestion only — the multi-SEGMENT form (~x{3%min, 1%min}) stays legal.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        timers = TIMER.findall(step["prose"])
        if len(timers) >= 2:
            suggestions.append({
                "rule": "AF", "step": slugify(step["title"]),
                "message": (
                    f"{len(timers)} separate ~timer sigils in one atom — each timed "
                    "movement should be its own atom (split the step) so the runtime "
                    "plays one timer per step; a single multi-segment timer "
                    "(~name{3%min, 1%min}) is for sequential parts of ONE movement"
                ),
            })

    # Rule AG — the wait-split anti-pattern (founder ruling 2026-07-13, the
    # lamb-pita tzatziki): a "Wait for X" atom whose only job is a timer splits
    # one operation into two steps; the wait belongs to the atom that starts
    # it. Suggestion tier — standalone waits with no initiating action stay.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        deps = parse_depends_on(step["meta"].get("depends_on"))
        if (re.match(r"(?i)^\s*wait\b", step["title"]) and len(deps) == 1
                and TIMER.search(step["prose"])):
            suggestions.append({
                "rule": "AG", "step": slugify(step["title"]),
                "message": (
                    f"'{step['title']}' is a bare wait — fold its timer and wall-clock "
                    f"duration into '{deps[0]}' (one atom: the action plus its passive "
                    "tail, attention_level=none); the cook shouldn't advance into a "
                    "step whose only content is waiting"
                ),
            })

    # Rule AH — inert prep slot: an explicit `@slug{X}(clause)` whose clause the
    # lift can't classify silently refuses (the agent believes it authored a
    # prep task; nothing schedules). Teach the rephrase at authoring time.
    from fond_dsl.ingredients_spec import _SKIP_MARKERS, _detect  # noqa: PLC0415 — lazy: spec imports dsl

    for step in steps:
        if is_note(step):
            continue
        for m in _PREP_SLOT_RE.finditer(step["prose"]):
            clause = (m.group(4) or "").strip()
            if not clause or _SKIP_MARKERS.search(clause):
                continue  # empty or deliberately unliftable (optional/garnish/divided)
            phrase = f"{m.group(2).rstrip()}, {clause}" if m.group(2).strip() else clause
            if _detect(phrase) is None:
                suggestions.append({
                    "rule": "AH", "step": slugify(step["title"]),
                    "message": (
                        f"the prep slot ({clause}) isn't a recognized prep form — it "
                        "lifts VERBATIM (the slot is authoritative), but the step reads "
                        "\"Prep the …: {clause}\"; rephrase with known participles "
                        "(chopped/diced/husked/stemmed/'cut into …') for a clean "
                        "imperative title"
                    ),
                })

    # Rule D — partition qty sums reconcile with the canonical total (DSL_SPEC
    # §6; ported from reference/lint.py now that services/qty.py exists — the
    # lint layer stays dependency-free). WARNING tier, not yet gated: promotion
    # to GATED_RULES waits on a corpus false-positive audit (<1%). Catches the
    # measured "quantity drift on divided amounts" defect class.
    from fond_dsl import qty as _qty  # local import keeps module load light

    canonical_text: Dict[str, str] = {}
    partition_parts: Dict[str, list] = {}
    for step in steps:
        prose = absorb_prep_slot(step["prose"])
        # atom_count honors the deprecated iteration= alias (rule AB) — the
        # projection's remainder arithmetic uses it, so the sum-check must too
        # or the two layers disagree on an iteration= atom.
        count_mult = atom_count(step["meta"])
        for m in ING_DEF.finditer(prose):
            canonical_text.setdefault(normalize_slug(m.group(1)), m.group(2))
        for m in ING_PART_DEF.finditer(prose):
            partition_parts.setdefault(normalize_slug(m.group(1)), []).append(
                (m.group(2), m.group(3), count_mult)
            )

    for slug, parts in partition_parts.items():
        canonical = canonical_text.get(slug)
        if canonical is None:
            continue  # rule Y's territory (no canonical total)
        total = _qty.parse_phrase(canonical)
        if total is None:
            continue  # unbounded canonical ("salt", "vegetable oil") — skip
        partition_sum = None
        unparseable = []
        explicit_remainder = None
        for part, qty_text, mult in parts:
            parsed = _qty.parse_phrase(qty_text)
            if parsed is None:
                frac = _qty.parse_relative(qty_text)
                if frac is not None:
                    parsed = _qty.Qty(total.value * frac, total.dim)
                    mult = 1  # a fraction-of-total is the whole partition's share
            if parsed is None:
                unparseable.append(f"[{part}]={qty_text!r}")
                continue
            if mult > 1:
                parsed = _qty.Qty(parsed.value * mult, parsed.dim)
            if part == "remainder":
                explicit_remainder = parsed
                continue
            partition_sum = parsed if partition_sum is None else _qty.add(partition_sum, parsed)

        if partition_sum is None and explicit_remainder is None:
            continue
        if explicit_remainder is not None:
            full = _qty.add(partition_sum, explicit_remainder) if partition_sum else explicit_remainder
            if not _qty.approx_equal(full, total):
                warnings.append({
                    "rule": "D", "step": None,
                    "message": (
                        f"@{slug} partitions sum to {_qty.fmt(full)} (including explicit "
                        f"remainder) but the canonical total is {_qty.fmt(total)} — "
                        "make the partition amounts add up to the declared total"
                    ),
                })
        else:
            bare_remainder = any(
                m.group(2) == "remainder" and normalize_slug(m.group(1)) == slug
                for step in steps for m in ING_PART_REF.finditer(step["prose"])
            )
            if bare_remainder:
                if partition_sum is not None and partition_sum.dim == total.dim \
                        and partition_sum.value > total.value * 1.01:
                    warnings.append({
                        "rule": "D", "step": None,
                        "message": (
                            f"@{slug} named partitions sum to {_qty.fmt(partition_sum)}, "
                            f"exceeding the canonical total {_qty.fmt(total)} — "
                            "[remainder] would be negative"
                        ),
                    })
            elif not _qty.approx_equal(partition_sum, total):
                warnings.append({
                    "rule": "D", "step": None,
                    "message": (
                        f"@{slug} partitions sum to {_qty.fmt(partition_sum)} but the "
                        f"canonical total is {_qty.fmt(total)} and no [remainder] is "
                        "declared — partition every use or add @"
                        f"{slug}[remainder]"
                    ),
                })
        if unparseable:
            suggestions.append({
                "rule": "D", "step": None,
                "message": (
                    f"@{slug} partition quantities unparseable ({', '.join(unparseable)}) — "
                    "the sum check is incomplete; numeric per-step amounts make it verifiable"
                ),
            })

    # Rule AB — legacy field spelling (DSL_SPEC §1.4): `active=` is the retired
    # alias of `duration=`. The old name taught the wrong semantics (models
    # authored hands-on minutes into it); the value parses identically, only the
    # key changes. Gated suggestion so every new save migrates itself.
    for step in steps:
        if is_derived(step) or is_note(step):
            continue
        if "iteration" in step["meta"]:
            suggestions.append({
                "rule": "AB",
                "step": slugify(step["title"]),
                "message": (
                    "iteration= is the deprecated spelling of count= — rename the key "
                    "(the multiplier is honored either way; count wins if both are set)"
                ),
            })
        if "active" in step["meta"]:
            suggestions.append({
                "rule": "AB",
                "step": slugify(step["title"]),
                "message": (
                    "active= is the legacy spelling of duration= — rename the key (same value): "
                    "duration= is the atom's wall-clock time; 'active' now only ever names the "
                    "DERIVED hands-on metric"
                ),
            })

    return {"errors": errors, "warnings": warnings, "suggestions": suggestions}


def lint_summary(result: dict) -> str:
    """Human-readable one-line summary for tool result text."""
    e, w, s = len(result["errors"]), len(result["warnings"]), len(result["suggestions"])
    if e:
        return f"✗ {e} error(s), {w} warning(s), {s} suggestion(s)"
    if w:
        return f"⚠ clean ({w} warning(s), {s} suggestion(s))"
    return f"✓ clean ({s} suggestion(s))" if s else "✓ clean"
