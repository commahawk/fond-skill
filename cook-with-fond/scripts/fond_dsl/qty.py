# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""Quantity arithmetic for the live lint/fidelity plane — a dependency-free
port of ``reference/qty.py`` (the pint-based canonical implementation).

Why a port and not pint: ``services/dsl.py`` commits the deployed lint layer to
zero dependencies, and recipe arithmetic needs exactly two conversion families
(volume, mass) plus a dimensionless count — a small factor table reproduces the
reference behavior without pint's registry in the server image. Parity is
pinned by ``tests/test_qty_parity.py`` (pint lives in dev deps only).

Same contract as the reference: ``parse_phrase`` returns a ``Qty`` or None for
anything not fully parseable (caller decides severity); parentheticals are
stripped (equivalents, not additions); plus-additions sum; fraction-of-total
phrases return None here and a float from ``parse_relative``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional

# --- unit table --------------------------------------------------------------
# Base units: volume=ml, mass=g, count=item. Factors mirror reference/qty.py's
# pint definitions (tablespoon = 0.5 fl oz, teaspoon = tbsp/3, cup = 8 fl oz,
# stick = 8 tbsp) with US fluid ounce = 29.5735295625 ml.

_FLOZ_ML = 29.5735295625

_UNIT_TABLE = {
    # volume → ml
    "teaspoon": ("volume", _FLOZ_ML / 6),
    "tablespoon": ("volume", _FLOZ_ML / 2),
    "cup": ("volume", _FLOZ_ML * 8),
    "stick": ("volume", _FLOZ_ML * 4),  # 8 tbsp
    "milliliter": ("volume", 1.0),
    "liter": ("volume", 1000.0),
    # mass → g
    "gram": ("mass", 1.0),
    "kilogram": ("mass", 1000.0),
    "ounce": ("mass", 28.349523125),
    "pound": ("mass", 453.59237),
    # dimensionless
    "count": ("count", 1.0),
}

UNIT_ALIASES = {
    "cup": "cup", "cups": "cup",
    "tablespoon": "tablespoon", "tablespoons": "tablespoon",
    "tbsp": "tablespoon", "tbsps": "tablespoon", "tbsp.": "tablespoon",
    "teaspoon": "teaspoon", "teaspoons": "teaspoon",
    "tsp": "teaspoon", "tsps": "teaspoon", "tsp.": "teaspoon",
    "pound": "pound", "pounds": "pound", "lb": "pound", "lbs": "pound",
    "ounce": "ounce", "ounces": "ounce", "oz": "ounce", "oz.": "ounce",
    "gram": "gram", "grams": "gram", "g": "gram",
    "kilogram": "kilogram", "kilograms": "kilogram", "kg": "kilogram",
    "milliliter": "milliliter", "milliliters": "milliliter", "ml": "milliliter",
    "liter": "liter", "liters": "liter", "l": "liter",
    "stick": "stick", "sticks": "stick",
    # Multilingual spoon/cup/gram spellings (keep-source-language ruling
    # 2026-07-13: German/French/Spanish/Italian/Dutch recipes stay in their
    # language, so F2/F4 quantity checks must parse their units). Same
    # kitchen measures, same factors.
    "el": "tablespoon", "esslöffel": "tablespoon", "eßlöffel": "tablespoon",
    "tl": "teaspoon", "teelöffel": "teaspoon",
    "tasse": "cup", "tassen": "cup",
    "gramm": "gram", "kilo": "kilogram",
    "cuillère à soupe": "tablespoon", "cuillères à soupe": "tablespoon",
    "c. à s.": "tablespoon", "c.à.s.": "tablespoon",
    "cuillère à café": "teaspoon", "cuillères à café": "teaspoon",
    "c. à c.": "teaspoon", "c.à.c.": "teaspoon",
    "cda": "tablespoon", "cdas": "tablespoon", "cdta": "teaspoon", "cdtas": "teaspoon",
    "taza": "cup", "tazas": "cup",
    "cucchiaio": "tablespoon", "cucchiai": "tablespoon",
    "cucchiaino": "teaspoon", "cucchiaini": "teaspoon",
    "tazza": "cup", "tazze": "cup",
    "eetlepel": "tablespoon", "eetlepels": "tablespoon",
    "theelepel": "teaspoon", "theelepels": "teaspoon",
}

UNICODE_FRAC = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

NUMBER_WORDS = {
    "another": 1,
    "one": 1,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

FRACTION_WORDS = {
    "half": 0.5, "halves": 0.5,
    "quarter": 0.25, "quarters": 0.25, "fourth": 0.25, "fourths": 0.25,
    "third": 1.0 / 3.0, "thirds": 1.0 / 3.0,
    "fifth": 0.2, "fifths": 0.2,
    "two-thirds": 2.0 / 3.0,
    "three-quarters": 0.75, "three-fourths": 0.75,
    "one-third": 1.0 / 3.0, "one-quarter": 0.25, "one-half": 0.5,
}

_UNIT_KEYS = sorted(UNIT_ALIASES.keys(), key=len, reverse=True)
_UNIT_RE = "|".join(re.escape(u) for u in _UNIT_KEYS)
_NUMBER_RE = (
    r"\d+\s\d+/\d+|"   # mixed: "1 1/4"
    r"\d+/\d+|"        # fraction: "1/4"
    r"\d+\.\d+|"       # decimal: "0.5"
    r"\d+|"            # int: "2"
    r"another|"
    + "|".join(re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True) if w != "another")
)

QTY_RE = re.compile(
    r"(?P<qty>" + _NUMBER_RE + r")\s*(?P<unit>" + _UNIT_RE + r")\b",
    re.IGNORECASE,
)
BARE_NUMBER_RE = re.compile(r"^\s*(?P<qty>" + _NUMBER_RE + r")\b", re.IGNORECASE)

_FRAC_KEYS = sorted(FRACTION_WORDS.keys(), key=len, reverse=True)
FRACTION_OF_RE = re.compile(
    r"\b(?P<frac>" + "|".join(re.escape(w) for w in _FRAC_KEYS) + r"|\d+/\d+)"
    r"\s+of\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Qty:
    """A parsed quantity: magnitude in the family's base unit (ml / g / item)."""

    value: float
    dim: str  # "volume" | "mass" | "count"

    def to(self, unit: str) -> float:
        dim, factor = _UNIT_TABLE[UNIT_ALIASES.get(unit, unit)]
        if dim != self.dim:
            raise ValueError(f"cannot express {self.dim} as {unit}")
        return self.value / factor


def _parse_number(s: str) -> float:
    s = s.strip()
    if s.lower() in NUMBER_WORDS:
        return float(NUMBER_WORDS[s.lower()])
    if " " in s:
        whole, frac = s.split(" ", 1)
        return float(whole) + float(Fraction(frac))
    if "/" in s:
        return float(Fraction(s))
    return float(s)


def _normalize(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)
    # Dual-unit square brackets ("3/4 cup [180 g] whole milk", "1 lb [450 g]")
    # are EQUIVALENTS like parentheticals, not additions — left in, a
    # same-dimension pair would sum ("1 lb [450 g]" → 903 g, a 2x total).
    text = re.sub(r"\[[^\]]*\]", "", text)
    # FRACTION SLASH (U+2044) composes arbitrary fractions ("1⁄2", "1⁄4") in
    # scraped JSON-LD — distinct from the precomposed vulgar-fraction glyphs
    # below. Left unnormalized, "1⁄2 cup" fails the qty+unit adjacency check,
    # and the regex falls through to matching the bare denominator digit next
    # to the unit ("2 cup") — a silent 4x/16x overstatement, not a None.
    text = text.replace("⁄", "/")
    for u, a in UNICODE_FRAC.items():
        text = text.replace(u, a)
    return text


def parse_phrase(text: str) -> Optional[Qty]:
    """Parse a qty phrase, summing plus-additions; None if not fully parseable.

    "¼ cup plus 2 tablespoons" → 6 tbsp of volume; "1 large onion" → 1 count;
    "a splash" → None; fraction-of-total → None (see ``parse_relative``)."""
    text = _normalize(text)

    parts: List[Qty] = []
    for m in QTY_RE.finditer(text):
        try:
            n = _parse_number(m.group("qty"))
            dim, factor = _UNIT_TABLE[UNIT_ALIASES[m.group("unit").lower()]]
            parts.append(Qty(n * factor, dim))
        except (ValueError, KeyError):
            continue

    if parts:
        total = parts[0]
        for q in parts[1:]:
            if q.dim != total.dim:
                return None  # mixed dimensions; can't sum
            total = Qty(total.value + q.value, total.dim)
        return total

    if FRACTION_OF_RE.search(text):
        return None

    m = BARE_NUMBER_RE.match(text)
    if m:
        after = text[m.end():].lstrip().lower()
        if after.startswith("of"):
            return None
        try:
            return Qty(_parse_number(m.group("qty")), "count")
        except (ValueError, KeyError):
            pass

    return None


def parse_relative(text: str) -> Optional[float]:
    """Float fraction for a 'fraction of (the)' phrase, else None."""
    text = _normalize(text)
    m = FRACTION_OF_RE.search(text)
    if not m:
        return None
    frac = m.group("frac").lower()
    if frac in FRACTION_WORDS:
        return FRACTION_WORDS[frac]
    if "/" in frac:
        try:
            return float(Fraction(frac))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def add(q1: Optional[Qty], q2: Optional[Qty]) -> Optional[Qty]:
    """Sum two quantities; None on dimension mismatch or missing operand."""
    if q1 is None or q2 is None or q1.dim != q2.dim:
        return None
    return Qty(q1.value + q2.value, q1.dim)


def subtract(q1: Optional[Qty], q2: Optional[Qty]) -> Optional[Qty]:
    """q1 − q2; None on dimension mismatch or missing operand (mirror of add)."""
    if q1 is None or q2 is None or q1.dim != q2.dim:
        return None
    return Qty(q1.value - q2.value, q1.dim)


def approx_equal(q1: Optional[Qty], q2: Optional[Qty], rel_tol: float = 0.02) -> bool:
    """True if q1 ≈ q2 within rel_tol (2% default — generous for recipe math)."""
    if q1 is None or q2 is None or q1.dim != q2.dim:
        return False
    if q1.value == 0 and q2.value == 0:
        return True
    return abs(q1.value - q2.value) / max(abs(q1.value), abs(q2.value)) < rel_tol


_FMT_UNITS = ("tablespoon", "cup", "teaspoon", "gram", "milliliter", "pound", "ounce")


def fmt(q: Optional[Qty]) -> str:
    """Pretty-print, preferring whole or simple-fraction values."""
    if q is None:
        return "unknown"
    if q.dim == "count":
        v = q.value
        if abs(v - round(v)) < 0.01:
            n = round(v)
            return f"{n} item{'s' if n != 1 else ''}"
        return f"{v:g} items"
    best = None
    for unit in _FMT_UNITS:
        dim, factor = _UNIT_TABLE[unit]
        if dim != q.dim:
            continue
        v = q.value / factor
        if abs(v - round(v)) < 0.02 and 0.5 <= v <= 64:
            s = f"{round(v):g} {unit}{'s' if round(v) != 1 else ''}"
            if best is None or len(s) < len(best):
                best = s
    if best:
        return best
    unit = "milliliter" if q.dim == "volume" else "gram"
    return f"{q.value:g} {unit}s"


# --- kitchen-natural display (the remainder render, DSL_SPEC §2.5) -----------
# `fmt` prints near-integer values only; a computed remainder is usually a
# fraction ("1/2 tsp"). This formatter renders the way a recipe would write it,
# or returns None when no natural form exists (caller falls back to no qty —
# an awkward "0.42 tsp" is worse than none).
#
# Register matters as much as the number: 50 g and 1 3/4 oz are the same amount
# within 1%, so without knowing which family the recipe was AUTHORED in the
# unit choice is undecidable — a US recipe showing "remaining parmesan (340 g)"
# or a German one showing "(2 tsp)" breaks the recipe's voice. The caller
# derives `metric` from the canonical phrase (`phrase_units_metric`) and the
# formatter never crosses families.

_KITCHEN_FRACS = ((0.125, "1/8"), (0.25, "1/4"), (1 / 3, "1/3"), (0.5, "1/2"),
                  (2 / 3, "2/3"), (0.75, "3/4"))

_METRIC_UNITS = {"gram", "kilogram", "milliliter", "liter"}


def phrase_units_metric(text: str) -> Optional[bool]:
    """True/False for the unit family of the FIRST unit in the phrase (metric /
    US-imperial), None when the phrase has no recognized unit (count-only)."""
    m = QTY_RE.search(_normalize(text or ""))
    if not m:
        return None
    return UNIT_ALIASES[m.group("unit").lower()] in _METRIC_UNITS


def _mixed_str(v: float) -> Optional[str]:
    """v as a whole number or common kitchen mixed fraction ("1 1/2") within a
    2% RELATIVE tolerance (the pipeline's approx_equal standard), else None.

    Remainders come from exact arithmetic on authored values, so a natural form
    exists in whichever unit the recipe used — a loose absolute tolerance would
    let a larger unit's near-miss shadow it (5 Tbsp is 0.3125 cup, only 0.02
    from "1/3 cup" — 6.7% wrong)."""
    if v <= 0:
        return None
    w = round(v)
    if w >= 1 and abs(v - w) <= 0.02 * w:
        return f"{int(w)}"
    whole = int(v + 1e-9)
    for val, s in _KITCHEN_FRACS:
        target = whole + val
        if abs(v - target) <= 0.02 * target:
            return f"{whole} {s}" if whole else s
    return None


def _metric_int(value: float, suffix: str) -> Optional[str]:
    n = round(value)
    if n >= 1 and abs(value - n) <= 0.02 * n:
        return f"{n:g} {suffix}"
    return None


def fmt_kitchen(q: Optional[Qty], metric: bool = False) -> Optional[str]:
    """Recipe-style render ("1/2 tsp", "1/4 cup", "8 oz"; "50 g" when metric),
    else None. Never crosses unit families — pass the authored register."""
    if q is None or q.value <= 0:
        return None
    if q.dim == "count":
        return _mixed_str(q.value)
    if q.dim == "volume":
        if metric:
            return _metric_int(q.value, "ml")
        for unit, label, floor in (("cup", "cup", 0.25), ("tablespoon", "Tbsp", 1.0),
                                   ("teaspoon", "tsp", 0.125)):
            v = q.value / _UNIT_TABLE[unit][1]
            if v + 1e-9 >= floor:
                s = _mixed_str(v)
                if s:
                    return f"{s} {label}"
        return None
    if metric:
        return _metric_int(q.value, "g")
    for unit, label, floor in (("pound", "lb", 1.0), ("ounce", "oz", 0.25)):
        v = q.value / _UNIT_TABLE[unit][1]
        if v + 1e-9 >= floor:
            s = _mixed_str(v)
            if s:
                return f"{s} {label}"
    return None
