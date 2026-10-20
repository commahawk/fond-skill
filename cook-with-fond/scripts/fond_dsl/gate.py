# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""The acceptance gate for a local recipe file — skill-owned, not a copy.

`GATED_RULES` and `MIN_INGREDIENTS` mirror the registry's acceptance bar byte for byte
(the module that defines them imports pydantic and is not vendored; fond-mono's drift test
compares the two). `gate_findings` applies that bar to one `lint_dsl` result the way the
registry does — every error, and every warning or suggestion whose rule is gated — with
the two things that are the skill's own and live here beside the mirror, never inside it:

* the variant baseline for rules U and V: a variant's structure is the export's, so a U
  or V finding the parent row already carries is inherited, printed, and never gated,
  while one the parent does not carry was introduced by an edit and gates like every
  other gated rule; without the parent (`--parent` not given — the read commands) U and
  V are printed as not gated and the command proceeds;
* the ingredient floor as a note that never gates a local file.

No rule is added; "no" cooks as written. Standard library only.
"""

from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

GATED_RULES = ("R", "S", "T", "U", "V", "W", "X", "Y", "AA", "AB", "AC", "AD", "AE")
MIN_INGREDIENTS = 3

# The rules the variant baseline applies to: both judge whether a conversion omitted
# structure a source had, and for the untouched copy that structure is the export's.
BASELINE_RULES = ("U", "V")
INHERITED_SUFFIX = "(inherited from the export)"
NO_PARENT_SUFFIX = "(not gated without --parent — pass it to gate edits)"
FLOOR_SUFFIX = "(not gated for a local file)"

Key = Tuple[str, Optional[str]]
Baseline = Union[dict, Iterable[Key], None]


def issue_line(kind: str, rule: Optional[str], step: Optional[str], message: str) -> str:
    """One teaching line in the registry's register: `<kind> [<rule>] @<step>: <message>`."""
    head = f"{kind} [{rule}]" if rule else kind
    return f"{head}{f' @{step}' if step else ''}: {message}"


def baseline_keys(baseline: Baseline) -> Set[Key]:
    """The (rule, step) pairs of the parent row's own U and V findings.

    `baseline` is the parent's `lint_dsl` result (the caller lints the row as the export
    carries it — its `dsl` body, or the `convert` output of a nodes-only row) or an
    iterable of (rule, step) pairs already computed.
    """
    if baseline is None:
        return set()
    if isinstance(baseline, dict):
        pairs = ((i["rule"], i.get("step")) for pool in ("errors", "warnings", "suggestions")
                 for i in baseline.get(pool, ()))
    else:
        pairs = ((rule, step) for rule, step in baseline)
    return {(rule, step) for rule, step in pairs if rule in BASELINE_RULES}


def gate_findings(lint_result: dict, ingredient_count: Optional[int], origin: Optional[str],
                  baseline: Baseline = None) -> List[Dict[str, object]]:
    """The findings of one `lint_dsl` result under the local-file gate, in lint order.

    Each entry: `{"rule", "step", "kind", "message", "gated", "line"}` — `kind` is the
    lint pool (`error`, `warning`, `suggestion`) or `note`; `gated` is True on every error
    and on every warning or suggestion whose rule is in `GATED_RULES`, except the U and V
    findings a variant inherits (`origin == "variant"` and the key is in `baseline`) or
    cannot check (`origin == "variant"` and no baseline), which become notes with their
    suffix; `line` is the teaching line. The ingredient floor, when `ingredient_count` is
    below `MIN_INGREDIENTS`, is the last entry, a note. The caller exits 1 when any entry
    is gated and prints the lines it chooses (the registry prints the gated ones).
    """
    inherited = baseline_keys(baseline) if origin == "variant" else set()
    out: List[Dict[str, object]] = []
    for pool, pool_kind in (("errors", "error"), ("warnings", "warning"), ("suggestions", "suggestion")):
        for issue in lint_result.get(pool, ()):
            kind = pool_kind  # per finding: a relabelled U must not relabel the next finding
            rule, step, message = issue["rule"], issue.get("step"), issue["message"]
            gated = kind == "error" or rule in GATED_RULES
            if gated and origin == "variant" and rule in BASELINE_RULES and kind != "error":
                if baseline is None:
                    kind, gated, message = "note", False, f"{message} {NO_PARENT_SUFFIX}"
                elif (rule, step) in inherited:
                    kind, gated, message = "note", False, f"{message} {INHERITED_SUFFIX}"
            out.append({"rule": rule, "step": step, "kind": kind, "message": message, "gated": gated,
                        "line": issue_line(kind, rule, step, message)})
    if ingredient_count is not None and ingredient_count < MIN_INGREDIENTS:
        message = (f"only {ingredient_count} canonical @ingredient definitions — tag every ingredient "
                   f"(≥{MIN_INGREDIENTS} expected for a real recipe) {FLOOR_SUFFIX}")
        out.append({"rule": None, "step": None, "kind": "note", "message": message, "gated": False,
                    "line": issue_line("note", None, None, message)})
    return out


def gated_lines(findings: List[Dict[str, object]]) -> List[str]:
    """The lines that block: what `check` prints before exit 1."""
    return [str(f["line"]) for f in findings if f["gated"]]


def note_lines(findings: List[Dict[str, object]]) -> List[str]:
    """The lines that inform and never block."""
    return [str(f["line"]) for f in findings if f["kind"] == "note"]
