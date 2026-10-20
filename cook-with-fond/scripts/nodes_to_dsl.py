#!/usr/bin/env python3
# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""nodes_to_dsl.py — the deterministic transliteration `convert` applies to a nodes-only
export row: legacy `nodes[]` → Fond DSL v1 text (DSL_SPEC §1–§8). Standard library only;
imported by fond_export.py, never run on its own.

Mapping (one atom per node, node order kept, so the script's ordinals line up):

  node field                     DSL v1
  -----------------------------  ------------------------------------------------------
  title                          `## <title>` (brackets stripped, made slug-unique, made
                                 to slugify to [a-z][a-z0-9-]*)
  dependencies                   depends_on=[<atom slugs>] (unknown ids dropped, like
                                 steps_from_nodes; a self-reference kept so it is refused)
  until + time > 0  (timer)      ~<name>{N%min} (or {S%sec} when N is not whole) and
                                 attention_level=low (a legacy timer never occupies the
                                 cook); duration= on EVERY timer atom — the sigil total,
                                 ceil(minutes) ≥ 1 on a sub-minute timer (rule AA compares
                                 the sigil total with max(duration, 1); the rounding is a
                                 loss)
  + repeat R > 1                 `× R` inside the sigil when the text says per/each/both
                                 side(s) — the rule-X case — else count=R (`repeat_mode=
                                 "auto"`, the one lint- and gate-clean mode)
  time > 0, no until (hands-on)  duration=<N> and attention_level=full (the app ran such a
                                 step serially; the card would say `low` for a boil — a
                                 loss, printed), count=R for repeat R > 1
  until, time 0/null (cue)       no sigil, no duration, attention_level=low; the cue is
                                 kept as prose ("…, until <cue>.")
  neither (instant)              no sigil, no duration, attention_level=none
  [bracketed] phrase             @slug sigil matched against `ingredients`:
                                   phrase == an ingredient line (first use) → @slug{phrase}
                                   phrase == "<qty> <slug words>"           → @slug[<atom>]{<qty>}
                                   otherwise matched                         → bare @slug
                                   unmatched                                 → @slug{phrase}
                                 every ingredient line not defined inline goes into one
                                 leading `## Ingredients [type=note section=main]` atom,
                                 so the DSL's projected list carries every exported line
  phase / section                phase=<atom slug>, section=main (nothing to infer them from)

The legacy projection's own synthetic until-label — `<title> — N min` (what the shipped
projection writes when a timer atom's prose has no doneness clause) — is dropped, never
written into prose: the minutes live in the sigil and in duration=. It is recognised
against the node's OWN title (the one the projection wrote), never the atom title a
rename for a unique slug produced, and in that exact form only.

Every loss the mapping cannot avoid is returned in `losses` (never silently).
"""

import json
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

BRACKET = re.compile(r"\[([^\[\]]+)\]")
KEBAB = re.compile(r"^[a-z][a-z0-9-]*$")
# DSL sigil starts that legacy prose may contain by accident: DSL v1 has no escape.
SIGIL_LIKE = re.compile(r"(@[A-Za-z]|#[A-Za-z]|~[A-Za-z_]*\{|\^\{)")
_QTY = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])"
_UNITS = {
    "a", "an", "of", "cup", "cups", "c", "tbsp", "tbsps", "tablespoon", "tablespoons", "tsp", "tsps",
    "teaspoon", "teaspoons", "g", "gram", "grams", "kg", "ml", "l", "litre", "liter", "litres", "liters",
    "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "clove", "cloves", "can", "cans", "tin",
    "tins", "slice", "slices", "bunch", "bunches", "ball", "balls", "batch", "batches", "strip",
    "strips", "quart", "quarts", "pint", "pints", "handful", "handfuls", "pinch", "pinches", "dash",
    "dashes", "large", "small", "medium", "sprig", "sprigs", "stick", "sticks", "piece", "pieces",
    "head", "heads", "package", "packages", "pkg", "jar", "jars", "bag", "bags", "box", "boxes",
}
NOISE_TIMER_NAMES = {"timer", "time", "t", "x"}
# The projection's synthetic until-label tail: a rendered timer body ("15 min", "2-3 min",
# "30 sec", "5 min, then 10 min", "2 min × 2") — nothing a cook could act on.
_LABEL_DURATION = (r"\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*"
                   r"(?:min|mins|minutes?|sec|secs|seconds?|hr|hrs|hours?|days?)(?:\s*[×x]\s*\d+)?")
SYNTHETIC_LABEL_TAIL = re.compile(rf"^{_LABEL_DURATION}(?:\s*,\s*(?:then\s+)?{_LABEL_DURATION})*$", re.IGNORECASE)
PER_SIDE = re.compile(r"\b(per|each|both|other)\s+sides?\b", re.IGNORECASE)


def slugify(title: str) -> str:
    """The skill script's own slugify — DSL_SPEC §1.3."""
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", "-", s.strip())


def humanize(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ")


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


def parse_nodes(nodes: Any) -> List[Any]:
    if nodes is None:
        return []
    if isinstance(nodes, str):
        try:
            return parse_nodes(json.loads(nodes)) if nodes.strip() else []
        except ValueError:
            return []
    if isinstance(nodes, dict):
        return list(nodes.values())
    return nodes if isinstance(nodes, list) else []


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4 and word[-3] in "sxz":
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _sing_norm(s: str) -> str:
    return " ".join(_singular(w) for w in _norm(s).split())


def noun_of(line: str) -> str:
    """'300 g spaghetti' → 'spaghetti'; '1 bunch broccoli rabe, trimmed' → 'broccoli rabe'."""
    head = re.split(r"[,(;]", line, maxsplit=1)[0]
    words = head.split()
    while words and (re.fullmatch(_QTY + r"(?:-" + _QTY + r")?", words[0]) or words[0].lower() in _UNITS):
        words.pop(0)
    words = [w for w in words if re.search(r"[A-Za-z]", w)]
    return " ".join(words[-3:]) if words else ""


def _kebab_from(text: str) -> str:
    s = slugify(text)
    s = re.sub(r"^[0-9-]+", "", s)
    return s if KEBAB.match(s or "") else ""


class Ingredients:
    """The exported ingredient lines, each with one slug for the whole recipe."""

    def __init__(self, lines: List[str]):
        self.lines = [str(x) for x in lines]
        self.slug: Dict[int, str] = {}
        self.inline: set = set()  # indexes defined inline (first use = the exact line)
        self.referenced: set = set()  # indexes already used as a bare ref or partition
        self.used_slugs: set = set()
        self.extra: List[Tuple[str, str]] = []  # unmatched phrases minted as their own defs

    def match(self, phrase: str) -> Optional[int]:
        p, ps = _norm(phrase), _sing_norm(phrase)
        if not p:
            return None
        for i, line in enumerate(self.lines):  # 1. the whole line
            if _norm(line) == p:
                return i
        for i, line in enumerate(self.lines):  # 2. the noun (singular/plural folded)
            if _sing_norm(noun_of(line)) == ps:
                return i
        for i, line in enumerate(self.lines):  # 3. the phrase inside the line, word-bounded
            if re.search(r"(?<!\w)" + re.escape(ps) + r"(?!\w)", _sing_norm(line)):
                return i
        for i, line in enumerate(self.lines):  # 4. the line's noun inside the phrase
            n = _sing_norm(noun_of(line))
            if n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", ps):
                return i
        return None

    def _unique(self, base: str) -> str:
        base = base or "ingredient"
        s, n = base, 2
        while s in self.used_slugs:
            s = f"{base}-{n}"
            n += 1
        self.used_slugs.add(s)
        return s

    def slug_for(self, i: int, phrase: Optional[str]) -> str:
        if i not in self.slug:
            cand = ""
            if phrase is not None and humanize(slugify(phrase)) == phrase and KEBAB.match(slugify(phrase)):
                cand = slugify(phrase)  # renders back to the phrase exactly
            cand = cand or _kebab_from(noun_of(self.lines[i])) or _kebab_from(self.lines[i])
            self.slug[i] = self._unique(cand or f"ingredient-{i + 1}")
        return self.slug[i]


def _timer_body(minutes: float) -> Tuple[str, bool]:
    """(sigil body, exact?). Whole minutes → 'N%min'; else whole seconds → 'S%sec'."""
    if abs(minutes - round(minutes)) < 1e-9:
        return f"{int(round(minutes))}%min", True
    secs = minutes * 60
    exact = abs(secs - round(secs)) < 1e-6
    return f"{int(round(secs))}%sec", exact


def _num(x: float) -> str:
    return str(int(round(x))) if abs(x - round(x)) < 1e-9 else f"{x:g}"


def _strip_times_tag(until: str) -> str:
    return re.sub(r"\s*\(\s*[×x]\s*\d+\s*\)\s*$", "", until).strip() or until


def is_synthetic_label(until: str, title: str) -> bool:
    """The projection's own `<title> — <rendered timer>` label (its `label()` fallback when a
    timer atom's prose had no doneness clause): not a cue the cook can act on. `title` is
    the node's own title — the one the projection wrote — so a title renamed for a unique
    slug (`Rest the Dough (2)`) still strips its label; any other tail is a real cue."""
    head, sep, tail = until.partition(" — ")
    return bool(sep) and head.strip() == title.strip() and bool(SYNTHETIC_LABEL_TAIL.match(tail.strip()))


def transliterate(nodes_raw: Any, ingredients: List[str], title: Optional[str] = None,
                  repeat_mode: str = "auto", strict_v1: bool = True,
                  instant_attention: Optional[str] = "none",
                  hands_on_attention: Optional[str] = "full") -> Tuple[str, List[str]]:
    """Legacy nodes → (DSL v1 text, losses). `repeat_mode` is 'count' (count=R), 'times'
    (`× R` inside the sigil) or 'auto' (`× R` when the text says per/each/both side(s) — the
    rule-X case — else count=R). `hands_on_attention` 'full' is the one mode whose drafts
    clear the reference linter's gated rules (a `None` attention trips AA on every hands-on
    atom); None leaves attention unset. `strict_v1` keeps duration= an integer (DSL_SPEC
    §1.4 / rule AA) at the cost of exactness for fractional hands-on minutes; off, it
    writes the float the skill script tolerates."""
    losses: List[str] = []
    nodes = parse_nodes(nodes_raw)
    ing = Ingredients(ingredients or [])

    # ---- normalise ids exactly like steps_from_nodes ----
    prepared, ids = [], []
    for pos, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            node = {"text": str(node)}
        raw_id = node.get("id")
        sid = str(pos) if raw_id is None or str(raw_id).strip() == "" else str(raw_id).strip()
        if re.fullmatch(r"\d+\.0", sid):
            sid = sid[:-2]
        base, n = sid, 2
        while sid in ids:
            sid = f"{base}-{n}"
            n += 1
        ids.append(sid)
        prepared.append((pos, sid, node))

    # ---- titles → unique, kebab-slugifiable atom titles ----
    atom_title: Dict[str, str] = {}
    atom_slug: Dict[str, str] = {}
    node_title: Dict[str, str] = {}  # the node's own title: what the projection's label names
    seen: set = {"ingredients"}  # the note atom's slug
    for pos, sid, node in prepared:
        t = node.get("title")
        t = str(t).strip() if isinstance(t, str) and t.strip() else f"Step {pos}"
        t0 = t
        node_title[sid] = t0
        t = re.sub(r"\s+", " ", t.replace("[", "(").replace("]", ")"))
        if not KEBAB.match(slugify(t) or "-"):
            t = f"Step {pos} {t}" if slugify(t) else f"Step {pos}"
        s, n = slugify(t), 2
        while s in seen:
            t2 = f"{t} ({n})"
            s, n = slugify(t2), n + 1
            if s not in seen:
                t = t2
        seen.add(s)
        if t != t0:
            losses.append(f"node {sid}: title changed for a unique kebab slug ({t0!r} → {t!r})")
        atom_title[sid], atom_slug[sid] = t, s

    known = set(ids)
    atoms_out: List[str] = []
    for pos, sid, node in prepared:
        slug = atom_slug[sid]
        text = node.get("text")
        text = str(text).strip() if isinstance(text, str) else ""
        if "\n" in text:
            losses.append(f"node {sid}: newlines in text joined with spaces (a '## ' line would start a new atom)")
            text = re.sub(r"\s*\n\s*", " ", text)
        if SIGIL_LIKE.search(BRACKET.sub("", text)):
            losses.append(f"node {sid}: text has sigil-like characters (@word/#word/~x{{/^{{) that DSL v1 reads as "
                          "sigils — no escape exists in §1–§8")
        # deps
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
                if atom_slug[ds] not in deps:
                    deps.append(atom_slug[ds])
            else:
                losses.append(f"node {sid}: dependency {ds!r} names no node; dropped (as the nodes path does)")
        # timing
        time = _to_float(node.get("time"))
        until = node.get("until")
        until = until.strip() if isinstance(until, str) and until.strip() else None
        repeat = max(1, _to_int(node.get("repeat"), 1)) if node.get("repeat") is not None else 1
        per = time or 0.0
        meta: List[str] = [f"phase={slug}", "section=main"]
        sigil = None
        mode = repeat_mode
        if mode == "auto":
            mode = "times" if PER_SIDE.search(text) else "count"
        if until is not None and per > 0:  # timer step
            body, exact = _timer_body(per)
            if not exact:
                losses.append(f"node {sid}: timer {per!r} min is not a whole number of seconds; rounded to {body}")
            if repeat > 1 and mode == "times":
                body += f" × {repeat}"
            total = per * (repeat if mode == "times" else 1)
            if abs(total - round(total)) < 1e-9:
                meta.append(f"duration={_num(total)}")
            else:
                ceil = max(1, int(math.ceil(total - 1e-9)))
                meta.append(f"duration={ceil}")
                losses.append(f"node {sid}: {total:g}-min timer written with duration={ceil} (DSL_SPEC §1.4 int "
                              "minutes; the sigil keeps the exact seconds)")
            meta.append("attention_level=low")
            if repeat > 1 and mode == "count":
                meta.append(f"count={repeat}")
            first = (slugify(re.sub(r"^prep:\s*", "", atom_title[sid], flags=re.I)).split("-") or [""])[0]
            name = first if (len(first) >= 3 and first.isalpha() and first not in NOISE_TIMER_NAMES
                             and re.search(r"(?<![A-Za-z])" + re.escape(first), text, re.I)) else "timer"
            sigil = f"~{name}{{{body}}}"
        elif per > 0:  # hands-on
            if abs(per - round(per)) < 1e-9 or not strict_v1:
                meta.append(f"duration={_num(per)}")
            else:
                ceil = int(math.ceil(per))
                meta.append(f"duration={ceil}")
                losses.append(f"node {sid}: hands-on {per:g} min written as duration={ceil} (int minutes only)")
            if hands_on_attention:
                meta.append(f"attention_level={hands_on_attention}")
                losses.append(f"node {sid}: hands-on step written attention_level={hands_on_attention} (the export "
                              "carries no attention; the app ran it serially — adjust if a watch-over would do)")
            if repeat > 1:
                meta.append(f"count={repeat}")
        elif until is not None:  # cue only
            meta.append("attention_level=low")
            if repeat > 1:
                losses.append(f"node {sid}: repeat {repeat} on a zero-time cue has nothing to multiply; dropped")
        else:  # instant
            if instant_attention:
                meta.append(f"attention_level={instant_attention}")
            if repeat > 1:
                losses.append(f"node {sid}: repeat {repeat} on a zero-time step has nothing to multiply; dropped")
        if deps:
            meta.append(f"depends_on=[{', '.join(deps)}]")

        # [bracketed] phrases → sigils
        def sub(m: "re.Match[str]") -> str:
            phrase = m.group(1).strip()
            nxt = text[m.end():m.end() + 1]
            i = ing.match(phrase)
            if i is None:
                for s_, p_ in ing.extra:
                    if p_ == phrase:
                        return f"@{s_}"
                s_ = ing._unique(_kebab_from(noun_of(phrase)) or _kebab_from(phrase) or "ingredient")
                ing.extra.append((s_, phrase))
                losses.append(f"node {sid}: [{phrase}] matches no exported ingredient line; minted @{s_}{{…}} "
                              "(the DSL's projected list gains it)")
                return f"@{s_}{{{phrase}}}"
            islug = ing.slug_for(i, phrase)
            line = ing.lines[i]
            if _norm(phrase) == _norm(line) and i not in ing.inline and i not in ing.referenced:
                ing.inline.add(i)
                if nxt == "(":
                    losses.append(f"node {sid}: [{phrase}] is followed by '(' — a space is inserted so DSL_SPEC "
                                  "§2.1.1 does not read it as a prep slot")
                    return f"@{islug}{{{phrase}}} "
                return f"@{islug}{{{phrase}}}"
            ing.referenced.add(i)
            words = humanize(islug)
            qm = re.match(r"^\s*(" + _QTY + r"(?:\s*-\s*" + _QTY + r")?(?:\s+[A-Za-z]+)?)\s+" + re.escape(words) + r"\s*$",
                          phrase)
            if qm:
                return f"@{islug}[{slug}]{{{qm.group(1)}}}"
            if words != phrase:
                losses.append(f"node {sid}: [{phrase}] renders as [{words}] (bare @{islug}; one slug per ingredient)")
            if re.match(r"[A-Za-z0-9_-]", nxt or ""):
                losses.append(f"node {sid}: [{phrase}] is followed by '{nxt}', which a bare @{islug} would swallow")
            return f"@{islug}"

        prose = BRACKET.sub(sub, text)

        # the cue and the timer go into the prose (DSL v1 has no done-when field); the
        # projection's synthetic `<title> — N min` label is not a cue and is dropped — matched
        # against the node's own title, not an atom title renamed for a unique slug
        cue = _strip_times_tag(until) if until is not None else None
        if cue is not None and is_synthetic_label(cue, node_title[sid]):
            cue = None
        cue_in_text = cue is not None and _norm(cue) in _norm(text)
        if sigil or (cue is not None and not cue_in_text):
            core = re.sub(r"[.!?…]+\s*$", "", prose).rstrip()
            parts = [core] if core else []
            if sigil:
                parts.append(sigil)
            if cue is not None and not cue_in_text:
                parts.append(f"until {cue}")
            prose = ", ".join(parts) + "."
        elif prose and not re.search(r"[.!?…]$", prose):
            prose += "."  # DSL_SPEC §3.3 sentence-final punctuation (rule E)
        if until is not None and per <= 0:
            losses.append(f"node {sid}: cue-only `until` ({cue!r}) survives only as prose; the step becomes an "
                          "instant atom (no structured done-when in DSL v1)")
        atoms_out.append(f"## {atom_title[sid]} [{' '.join(meta)}]\n{prose}\n")

    # every exported line not defined inline goes to one leading note atom
    rest = []
    for i, line in enumerate(ing.lines):
        if i in ing.inline:
            continue
        s = ing.slug_for(i, None)
        rest.append(f"@{s}{{{line}}}")
    head = f"# {title}\n" if title else ""
    if rest:
        head += "\n## Ingredients [type=note section=main]\n" + "Also needed: " + ", ".join(rest) + ".\n"
    if ing.inline and rest:
        losses.append("ingredient list order: lines used verbatim in a step are defined inline at first use, "
                      "the rest in the leading note — the DSL's projected order can differ from the exported order")
    dsl = head + "\n" + "\n".join(atoms_out)
    return dsl, losses
