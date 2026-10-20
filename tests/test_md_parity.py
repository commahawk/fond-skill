"""JSON-vs-Markdown parity for cook-with-fond/scripts/fond_export.py over the fixture pairs.

cook-playback › Markdown fallback › "Markdown parity with the JSON" (tasks.md 13.3): the
shipped renderer's Markdown of `sample-export.json` — `fixtures/sample-export.md`, the
`d142ab74` renderer's output — and the JSON itself are run through `list`, `missing`,
`show` and `plan` for every cookable title, `history`, `cook-again` and `history
"<title>"` for every recipe with counted cooks, all with `--json`, and compared field by
field. The only differences accepted are the inherent Markdown losses, each named in
ALLOWED below; the test fails on any new difference AND on any allowed entry that no
longer occurs (an allow-list entry that stops differing is a stale entry, not a pass —
the `exported_at` reader gap this test once named was closed that way, tasks.md 13.1(f)).

The version-1 pair (`sample-export-v1.json` and its `.md`, the `2f896058` renderer's
output kept as committed) runs `list`, `missing`, `history` and `cook-again` only: its
Markdown carries no timing, so `show` and `plan` are not parity surfaces there.

A "field" is a key whose value is a scalar or a list of scalars (a list of step ids, a
list of waves): dicts and lists of dicts are walked, `text` keys — the rendering of the
other fields, tested in test_fond_export.py — are left out at every level.
No network, no environment, synthetic fixtures only.
"""

import contextlib
import io
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
FIXTURES = SKILL / "fixtures"
PAIRS = {
    "v2": (FIXTURES / "sample-export.json", FIXTURES / "sample-export.md"),
    "v1": (FIXTURES / "sample-export-v1.json", FIXTURES / "sample-export-v1.md"),
}

_spec = importlib.util.spec_from_file_location("fond_export_parity", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

def run_json(path, md, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(path)] + (["--md"] if md else []) + list(args) + ["--json"])
    out = json.loads(buf.getvalue())
    if "error" in out and set(out) == {"error", "code"}:
        return {"error": out["error"], "code": code}
    return out


def fields(value, prefix=""):
    """Flatten to {path: value}: dicts and lists of dicts are walked; a list of scalars (or
    of lists of scalars) is one field; `text` keys are skipped."""
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "text":
                continue
            out.update(fields(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        for i, v in enumerate(value):
            out.update(fields(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = value
    return out


def differences(pair):
    """Every (command, title, path) whose value differs between the JSON and the Markdown."""
    jpath, mpath = PAIRS[pair]
    runs = [("list", None), ("missing", None), ("history", None), ("cook-again", None)]
    listing = run_json(jpath, False, "list")
    if pair == "v2":
        for title in [r["title"] for r in listing["cookable"]]:
            runs += [("show", title), ("plan", title)]
        for title in [r["title"] for r in run_json(jpath, False, "history")["rows"]]:
            runs.append(("history", title))
    diffs = {}
    for command, title in runs:
        args = (command, title) if title else (command,)
        a, b = fields(run_json(jpath, False, *args)), fields(run_json(mpath, True, *args))
        for path in sorted(set(a) | set(b)):
            if a.get(path, "<absent>") != b.get(path, "<absent>"):
                diffs[(command, title, path)] = (a.get(path, "<absent>"), b.get(path, "<absent>"))
    return diffs


# ---------------------------------------------------------------------------
# The allow-list: the inherent Markdown losses, by category, on each fixture pair — the
# "no Fond id / recipe handle / sourceAuthor / lineage" losses on ONE-LINE ROWS ONLY. A
# full section's `- **Fond id:**` line, its by-line and its `Lineage:` line are read and
# compared on every command (test_every_recipe_agrees… asserts `id`, `byline` and
# `lineage` on `show` for every cookable title); no entry below names a section's id.
# ---------------------------------------------------------------------------

def one_line_rows(command, title, key, rows):
    """A one-line saved row prints no Fond id, recipe handle, sourceAuthor or lineage
    (user_export._saved_line), so `id` is null and the by-line carries no `Fond handle`
    / `Fond id` part — on `list`/`missing` rows and wherever the row is presented.
    "Handle" here is the recipe's own Fond `handle` (DSL_SPEC §1.2 — the by-line's
    `Fond handle <h>` part), never `authorHandle`: the row DOES print that as
    ` by @<handle>`, `_md_saved_line` reads it, and so the author handle is compared on
    every row (the by-line field differs only by its `Fond handle` part). The one
    exception to "no Fond id" is an `authoredRecipeRef` row, whose `(Fond id <id>)` tail
    the reader takes as the row's `id` (tasks.md 13.1(e)): that id is a compared field,
    never an entry here."""
    return {(command, title, f"{key}[{i}].{f}") for i in rows for f in ("id", "byline")}


# v2 pair: fixtures/sample-export.md, the d142ab74 renderer over sample-export.json.
# Weeknight Garlic Pasta: node ids 7, 2, 5, 9, 4, 8, 3, 6, 10 — not positions; the second
# node's id happens to equal its ordinal, so that one field agrees.
PASTA_STEPS = [i for i in range(9) if i != 1]
ALLOWED_V2 = (
    # 1. No Fond id or recipe handle on one-line rows (Grandma's Stew — a LIVE saved row
    #    without steps is one-line at tier 0 too —, Old Favourite Curry, the gone row). The
    #    fourth one-line row, the Weeknight Garlic Pasta `authoredRecipeRef` row, is not
    #    here: its `(Fond id rcp-pasta-02)` tail gives its id, and it folds into the
    #    authored recipe on both paths.
    one_line_rows("list", None, "missing", range(3))
    | one_line_rows("missing", None, "missing", range(3))
    | {("history", None, "rows[2].id"), ("history", None, "rows[2].byline")}            # Grandma's Stew
    | {("history", "Grandma's Stew", "id"), ("history", "Grandma's Stew", "byline")}
    | {("cook-again", None, "not_cookable[0].id"), ("cook-again", None, "not_cookable[0].byline")}
    # 2. Ordinal step ids in place of node ids (the printed list is numbered by position;
    #    `(after step k)` is an ordinal), and everything that lists ids.
    | {("show", "Weeknight Garlic Pasta", f"steps[{i}].id") for i in PASTA_STEPS}
    | {("plan", "Weeknight Garlic Pasta", f"steps[{i}].id") for i in PASTA_STEPS}
    | {("plan", "Weeknight Garlic Pasta", f"steps[{i}].deps") for i in (3, 4, 5, 7, 8)}  # the steps with dependencies
    | {("plan", "Weeknight Garlic Pasta", k) for k in ("available", "locked", "waves")}
    # 3. A nodes-only section is read from its printed step list: `source` is md-steps.
    | {(cmd, t, "source") for cmd in ("show", "plan") for t in ("Weeknight Garlic Pasta", "Toast Soldiers", "Tomato Soup")}
    # 4. The absent "DSL and nodes" warning: a Markdown section carries no nodes beside
    #    its fence, so the reader cannot raise it.
    | {(cmd, t, "warnings") for cmd in ("show", "plan") for t in ("Skillet Steak Supper", "Steamed Coconut Rice")}
    # 5. The lineage OBJECT behind a full section's `Lineage:` line: the line itself is read
    #    and compared (`lineage` agrees); the parentId/forkPoint/attributionHandles object
    #    it was rendered from is not in the Markdown as fields (null on --md).
    | {("show", "Skillet Steak Supper", f"lineage_raw{k}") for k in ("", ".parentId", ".forkPoint", ".attributionHandles")}
    # 6. A node's `time: 0` prints as no timing at all (user_export._step_timing), so the
    #    raw `time` reads back null — the kind, the scheduled length and the timing line agree.
    | {("plan", "Weeknight Garlic Pasta", f"steps[{i}].time") for i in (1, 2, 8)}
    # 7. `h` on a nodes-only section (recipe-authoring "The FOND1 line carries `h=`"): one
    #    body per input — the JSON's hash is over its slim nodes, the Markdown's over its
    #    step lines — so a FOND1 line replays only against the input it came from. A DSL
    #    section's `h` is over the fenced text on both paths and is compared (it agrees).
    | {(cmd, t, "h") for cmd in ("show", "plan") for t in ("Weeknight Garlic Pasta", "Toast Soldiers", "Tomato Soup")}
)

# v1 pair: fixtures/sample-export-v1.md, the 2f896058 renderer over sample-export-v1.json
# — `list`, `missing`, `history`, `cook-again` only (no timing in a version-1 .md).
ALLOWED_V1 = (
    # 1. The version-1 renderer wrote `- **Handle:**` and no `Fond id` line on authored
    #    sections, and every saved row is one-line: no Fond id anywhere — the version-1
    #    render's own omission (that renderer never printed a section's id), not a loss the
    #    reader allows on a section that carries one.
    {("list", None, f"cookable[{i}].{f}") for i in range(3) for f in ("id", "content_id")}
    | one_line_rows("list", None, "missing", range(4))
    | one_line_rows("missing", None, "missing", range(4))
    | {("history", None, "rows[0].id"), ("history", None, "rows[0].byline"),    # Grandma's Stew (one-line)
       ("history", None, "rows[1].id"),                                         # Weeknight Garlic Pasta (section, no Fond id)
       ("history", None, "rows[2].id"), ("history", None, "rows[2].byline")}   # Tomato Soup (one-line)
    | {("cook-again", None, "suggestions[0].id"), ("cook-again", None, "not_cookable[0].id"),
       ("cook-again", None, "not_cookable[0].byline")}
)


def _check(pair, allowed):
    diffs = differences(pair)
    unexpected = {k: v for k, v in diffs.items() if k not in allowed}
    stale = allowed - set(diffs)
    assert not unexpected, "new JSON-vs-Markdown differences:\n" + "\n".join(
        f"  {k}: json={v[0]!r} md={v[1]!r}" for k, v in sorted(unexpected.items(), key=str))
    assert not stale, f"allow-list entries that no longer differ (remove them): {sorted(stale, key=str)}"
    return diffs


def test_v2_markdown_matches_the_json_except_for_the_inherent_losses():
    """cook-playback › Markdown parity with the JSON: every step kind, timing, need,
    estimate and cook count agrees; only the allow-listed inherent losses differ."""
    diffs = _check("v2", ALLOWED_V2)
    assert len(diffs) == len(ALLOWED_V2)
    # The categories named by the spec, spelled out: a one-line row's by-line loses only
    # its `Fond handle` part; a step id on the Markdown is its printed ordinal.
    assert diffs[("list", None, "missing[0].byline")] == (
        "by @ben · from blog.example · Fond handle grandmas-stew-k2l3m4", "by @ben · from blog.example")
    assert diffs[("plan", "Weeknight Garlic Pasta", "steps[0].id")] == ("7", "1")
    assert diffs[("show", "Skillet Steak Supper", "warnings")] == (
        ["this recipe carries both DSL and legacy nodes; the DSL wins and the nodes are ignored"], [])
    # The authoredRecipeRef row's `(Fond id <id>)` tail is read as its id (13.1(e)) — a
    # compared field on both paths, not an allow-listed loss; the row resolves by that id.
    jpath, mpath = PAIRS["v2"]
    jref, mref = (next(r for r in fe.load_export(p).saved if r.ref) for p in (jpath, mpath))
    assert (jref.title, jref.id, jref.ref) == (mref.title, mref.id, mref.ref) == \
        ("Weeknight Garlic Pasta", "rcp-pasta-02", "rcp-pasta-02")
    assert fe.load_export(mpath).content_of(mref).id == "rcp-pasta-02"


def test_v1_markdown_matches_the_json_on_the_four_timing_free_commands():
    """cook-playback › legacy Markdown: the version-1 pair agrees on `list`, `missing`,
    `history` and `cook-again` except for the Fond ids the version-1 renderer never wrote."""
    diffs = _check("v1", ALLOWED_V1)
    assert len(diffs) == len(ALLOWED_V1)
    assert diffs[("list", None, "cookable[0].id")] == ("rcp-steak-01", None)


def test_every_recipe_agrees_on_kind_timing_needs_estimate_and_cook_count():
    """The spec's own sentence, asserted directly on the v2 pair: step kinds, timings,
    needs, the time-to-serve estimate and the cook counts never differ."""
    jpath, mpath = PAIRS["v2"]
    lj, lm = run_json(jpath, False, "list"), run_json(mpath, True, "list")
    assert [(r["title"], r["cooked"], r["source"]) for r in lj["cookable"]] == \
        [(r["title"], r["cooked"], r["source"]) for r in lm["cookable"]]
    for title in [r["title"] for r in lj["cookable"]]:
        pj, pm = run_json(jpath, False, "plan", title), run_json(mpath, True, "plan", title)
        assert pj["estimate_minutes"] == pm["estimate_minutes"], title
        assert [(s["kind"], s["timing"], s["needs"], s["scheduled"], s["countdowns"]) for s in pj["steps"]] == \
            [(s["kind"], s["timing"], s["needs"], s["scheduled"], s["countdowns"]) for s in pm["steps"]], title
        assert pj.get("timers_notice") == pm.get("timers_notice"), title
        # A full section's `- **Fond id:**`, by-line and `Lineage:` lines are read and
        # compared — never allow-listed (cook-playback, "on one-line rows only").
        sj, sm = run_json(jpath, False, "show", title), run_json(mpath, True, "show", title)
        assert sj["id"] and (sj["id"], sj["byline"], sj["lineage"]) == (sm["id"], sm["byline"], sm["lineage"]), title
    hj, hm = run_json(jpath, False, "history"), run_json(mpath, True, "history")
    assert [(r["title"], r["times"], r["verdict"], r["last"]) for r in hj["rows"]] == \
        [(r["title"], r["times"], r["verdict"], r["last"]) for r in hm["rows"]]
