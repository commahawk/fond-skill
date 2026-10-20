"""`check` over a local recipe file (recipe-authoring "`check` gates keeping and cooking",
"The envelope and its keys per origin", "The local id; no Fond id, handle or lineage is
minted"; cook-with-fond-authoring 6.4).

One DSL text per gated rule — R S T U V W X Y AA AB AC AD AE — each tripping exactly that
rule in the vendored `lint_dsl` and blocking with exit 1 and the teaching line (`pytest -q
tests/test_check.py -k gated` is those thirteen); a parse error blocks; AH never fires; the
ingredient floor is printed and never blocks; the variant ratchet of decision 1 (`--parent`
required at the write boundary, U and V inherited from the parent row's own findings and
gated when an edit introduces them); stdin, `--json`, the envelope errors, the parent
cross-check, `--out`, the 3.9 floor; and the 13/13 parity with apps/mcp's own `lint_dsl`
(skipped in the public mirror, where apps/mcp is absent). No network, no environment,
synthetic texts only.

Run from apps/skill:  ../mcp/.venv/bin/python -m pytest -q tests/test_check.py
"""

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
LOCAL = FIXTURES / "local"
VARIANT = LOCAL / "sample-variant.md"
COMPOSED = LOCAL / "sample-composed.md"
TRANSCRIBED = LOCAL / "sample-transcribed.md"
CLEAN_DSL = LOCAL / "sample-clean-dsl.md"
# apps/mcp beside apps/skill in fond-mono; absent in the public mirror (the parity test skips).
MCP_ROOT = HERE.parents[1] / "mcp"
MADE_ON = "2026-10-13"

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

GATED = ("R", "S", "T", "U", "V", "W", "X", "Y", "AA", "AB", "AC", "AD", "AE")
FLOOR_LINE = ("Local recipe files need Python 3.9 or newer (this interpreter is {}); "
              "every command over an export still works")


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out[:3000]}"
    return out


def run_json(*args, expect=0):
    return json.loads(run_cli(*args, "--json", expect=expect))


def write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def tmp_export(folder: Path, mutate) -> Path:
    """A copy of the v2 fixture with `mutate(data)` applied, written beside the test's files."""
    data = json.loads(V2.read_text(encoding="utf-8"))
    mutate(data)
    return write(folder, "fond-export-test.json", json.dumps(data, ensure_ascii=False))


def row_of(data, rid):
    return next(r for key in ("authoredRecipes", "savedRecipes") for r in data[key] if r.get("id") == rid)


# ---------------------------------------------------------------------------
# One text per gated rule (the vendored lint, probed: each trips its rule alone)
# ---------------------------------------------------------------------------

ENVELOPE = """---
title: Probe
lineage:
  origin: {origin}
  made_on: 2026-10-13
  changes:
    - composed by the assistant from the user's description
---
"""
HEAD = "# Probe\n\n"
SOAK = "## Soak the Beans [phase=prep section=main duration=10 attention_level=none]\nSoak the @beans{1 cup dried beans} in cold water.\n\n"
SIMMER = ("## Simmer the Beans [phase=cook section=main duration=30 attention_level=low depends_on=[soak-the-beans]]\n"
          "Simmer the beans gently with the @stock{2 cups stock}, ~simmer{30%min}.\n\n")
FINISH = ("## Finish the Beans [phase=serve section=main duration=3 attention_level=full depends_on=[simmer-the-beans]]\n"
          "Stir in the @herbs{1 bunch parsley}(chopped) and serve.\n")
FINISH_HEAD = "## Finish the Beans [phase=serve section=main duration=3 attention_level=full depends_on=[simmer-the-beans]]\n"
CLEAN = HEAD + SOAK + SIMMER + FINISH

RULE_TEXTS = {
    "R": HEAD + SOAK + SIMMER + FINISH_HEAD + "Stir in the @herbs{1 bunch parsley} and @salt[finish]{1 tsp} "
         "(from @salt{2 tsp salt, divided}) and serve with @salt[remainder].\n",
    "S": HEAD + SOAK.replace(" attention_level=none", "") + SIMMER.replace(" attention_level=low", "") + FINISH,
    "T": HEAD + SOAK + SIMMER.replace(", ~simmer{30%min}.", " for about 30 minutes.") + FINISH,
    "U": HEAD + SOAK + SIMMER.replace(" depends_on=[soak-the-beans]", "") + FINISH.replace(" depends_on=[simmer-the-beans]", ""),
    "V": HEAD + SOAK + SIMMER + FINISH.replace("depends_on=[simmer-the-beans]", "depends_on=[soak-the-beans]"),
    "W": HEAD + SOAK + SIMMER + FINISH_HEAD + "Stir in the @herbs{1 bunch parsley}, @salt{1 tsp salt} and @salt2{1 tsp salt} and serve.\n",
    "X": HEAD + SOAK + SIMMER + FINISH_HEAD.replace("duration=3 attention_level=full", "duration=6 attention_level=high")
         + "Sear the @herbs{1 bunch parsley} 3 minutes per side, ~sear{3%min}, and serve.\n",
    "Y": HEAD + SOAK + SIMMER + FINISH_HEAD + "Stir in the @herbs{1 bunch parsley} and @salt[finish]{1 tsp} and serve.\n",
    "AA": HEAD + SOAK + SIMMER.replace("duration=30", "duration=10") + FINISH,
    "AB": HEAD + SOAK.replace("duration=10", "active=10") + SIMMER + FINISH,
    "AC": HEAD + SOAK + SIMMER + FINISH_HEAD + "Stir in the @herbs{1 bunch parsley} and @onion{2 Tbsp} and serve.\n",
    "AD": HEAD + SOAK + SIMMER + FINISH_HEAD + "Stir in the @herbs{1 bunch parsley}, cover with @foil{aluminum foil} and serve.\n",
    "AE": HEAD + SOAK + SIMMER + FINISH_HEAD + "Grease a dish with cooking spray, stir in the @herbs{1 bunch parsley} and serve.\n",
}
# (kind, step, a fragment of the registry's teaching message) per rule.
TEACHING = {
    "R": ("suggestion", "finish-the-beans", "the divided total is restated in prose"),
    "S": ("suggestion", None, "of 3 non-derived atoms lack attention_level"),
    "T": ("suggestion", "simmer-the-beans", 'prose states a duration ("about 30 minutes") but the atom has no ~timer'),
    "U": ("suggestion", None, "3 steps but no depends_on edges"),
    "V": ("suggestion", None, "step DAG does not converge: 2 terminal steps"),
    "W": ("warning", "finish-the-beans", "numbered slug(s) @salt2"),
    "X": ("suggestion", "finish-the-beans", "prose says the action repeats per side but the timer has a single segment"),
    "Y": ("warning", None, "@salt has partition defs ([finish]) but no canonical @salt{…} definition"),
    "AA": ("warning", "simmer-the-beans", "timer total 30m exceeds duration=10"),
    "AB": ("suggestion", "soak-the-beans", "active= is the legacy spelling of duration="),
    "AC": ("warning", "finish-the-beans", "@onion{2 Tbsp} never names the food"),
    "AD": ("warning", "finish-the-beans", "@foil{aluminum foil} is equipment/packaging, not food"),
    "AE": ("warning", None, '"cooking spray" is used in a step but never reaches the ingredient list'),
}
assert set(RULE_TEXTS) == set(TEACHING) == set(GATED)


def composed(body: str, origin: str = "composed") -> str:
    return ENVELOPE.format(origin=origin) + body


@pytest.mark.parametrize("rule", GATED)
def test_gated_rule_blocks_with_its_teaching_line(rule, tmp_path):
    """recipe-authoring › `check` gates keeping and cooking: a finding whose rule is in the
    gate's set (the mirror, exact) refuses the file — exit 1, one teaching line naming the
    rule letter and the atom, nothing written — on a composed file, where all thirteen
    gate. Each text trips its own rule alone in the vendored lint; the one exception is
    S, which the registry's lint couples by construction with AA's "attention_level is
    missing" line on the same atoms (both key on the same metadata), so S is asserted
    beside exactly that companion."""
    path = write(tmp_path, "probe.md", composed(RULE_TEXTS[rule]))
    out = run_cli(path, "check", "--out", tmp_path / "kept.md", expect=1)
    result = run_json(path, "check", expect=1)
    assert result["ok"] is False and result["exit"] == 1
    gated = [f for f in result["findings"] if f["gated"]]
    rules = sorted({f["rule"] for f in gated})
    if rule == "S":
        assert rules == ["AA", "S"]
        assert all("attention_level is missing" in f["message"] for f in gated if f["rule"] == "AA")
    else:
        assert rules == [rule], gated
    assert sorted({f["rule"] for f in result["findings"]}) == rules  # nothing else fires, gated or not
    kind, step, fragment = TEACHING[rule]
    mine = [f for f in gated if f["rule"] == rule]
    assert len(mine) == 1 and mine[0]["kind"] == kind and mine[0]["step"] == step and fragment in mine[0]["message"]
    line = f"{kind} [{rule}]" + (f" @{step}" if step else "") + f": {mine[0]['message']}"
    assert line in out.splitlines(), out
    n = len(gated)
    # with `--out`, the recipe is gated and reported under the OUTPUT's id — local:kept, not local:probe
    assert f"{n} finding(s) block local:kept; nothing with a gated finding is written, kept or cooked." in out
    assert f"Nothing written to {tmp_path / 'kept.md'}: fix the findings in the draft and run check again." in out
    assert not (tmp_path / "kept.md").exists()
    assert "Plays as:" in out  # the preview still prints, so the fix is visible before the next run


def test_a_parse_error_blocks(tmp_path):
    """An error of the lint's own — a timer body that does not parse (rule G), a text with no
    schedulable atom (rule M) — blocks like a gated rule: exit 1, the teaching line."""
    bad_timer = write(tmp_path, "timer.md", composed(CLEAN.replace("~simmer{30%min}", "~simmer{thirty}")))
    out = run_cli(bad_timer, "check", expect=1)
    assert "error [G] @simmer-the-beans: timer ~simmer{thirty} segment 'thirty' doesn't match <X[-Y]%unit [× N]>" in out
    result = run_json(bad_timer, "check", expect=1)
    assert [(f["rule"], f["kind"], f["gated"]) for f in result["findings"]] == [("G", "error", True)]
    no_atoms = write(tmp_path, "prose.md", composed("# Probe\n\nJust prose, no atoms.\n"))
    out = run_cli(no_atoms, "check", expect=1)
    assert "error [M]: recipe has no schedulable atoms" in out
    assert "error [graph]:" in out  # no graph can be built either; both are named, neither is silent


def test_rule_ah_never_fires(tmp_path):
    """fond-dsl-open-release › the stub keeps rule AH silent: a prep slot the reference
    would flag as unrecognised passes `check` with no finding of any kind."""
    probe = write(tmp_path, "probe.md", composed(CLEAN.replace("(chopped)", "(zorbled)")))
    result = run_json(probe, "check")
    assert result["ok"] is True and result["findings"] == [] and "AH" not in run_cli(probe, "check")


def test_a_clean_text_passes_with_the_plays_as_lines_and_h(tmp_path):
    """exit 0, the "plays as" preview — each atom's kind as `plan --dsl` will say it — the
    mise-en-place wave, the estimate and `h`; the JSON carries the same under `plays_as`."""
    probe = write(tmp_path, "probe.md", composed(CLEAN))
    out = run_cli(probe, "check")
    lines = out.splitlines()
    assert lines[0] == f"check: {probe} — local:probe (composed)"
    assert "Plays as:" in lines
    assert "  1. Soak the Beans — about 10 min — no timer, no clock time; does not occupy you" in lines
    assert "  2. Simmer the Beans — Timer: 30 min" in lines
    assert "  3. Finish the Beans — ~3 min hands-on" in lines
    assert "  Mise en place (wave 1): 1. Soak the Beans" in lines
    assert "  Estimated time to serve: about 43 min" in lines
    assert lines[-1] == "Passes: nothing blocks local:probe."
    result = run_json(probe, "check")
    assert result["ok"] is True and result["findings"] == [] and result["notes"] == [] and result["exit"] == 0
    assert re.fullmatch(r"[0-9a-f]{8}", result["h"]) and f"h={result['h']}" in lines
    assert [s["kind"] for s in result["plays_as"]["steps"]] == ["watch", "timer", "hands-on"]
    assert result["plays_as"]["wave1"] == ["soak-the-beans"] and result["plays_as"]["estimate_minutes"] == 43
    assert result["h"] == run_json(probe, "--dsl", "plan")["h"]
    assert "Estimated time to serve: about 43 min" in run_cli(probe, "--dsl", "plan")


def test_the_ingredient_floor_is_printed_and_never_blocks():
    """recipe-authoring › `check` … › the ingredient floor never gates: the shipped composed
    fixture defines two canonical ingredients; `check` prints the count suffixed "(not gated
    for a local file)" as a note and exits 0."""
    out = run_cli(COMPOSED, "check")
    note = ("note: only 2 canonical @ingredient definitions — tag every ingredient (≥3 expected for a real recipe) "
            "(not gated for a local file)")
    assert note in out.splitlines() and out.rstrip().endswith("Passes: nothing blocks local:sample-composed.")
    result = run_json(COMPOSED, "check")
    assert result["ok"] is True and result["notes"] == [note]
    assert [(f["rule"], f["kind"], f["gated"]) for f in result["findings"]] == [(None, "note", False)]
    assert run_json(TRANSCRIBED, "check")["findings"] == []  # four defs: no note


# ---------------------------------------------------------------------------
# The variant baseline (decision 1)
# ---------------------------------------------------------------------------

FLAT_STEAK = """# Skillet Steak Supper

## Toast the Spices [phase=prep section=sauce duration=2 attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Sear the Steak [phase=cook section=main duration=4 attention_level=high]
Sear the @steak{1 strip steak} in the hot skillet, ~sear{2%min × 2}, flipping once.

## Plate the Supper [phase=serve section=main duration=3 attention_level=full]
Slice the @steak and plate it with the @greens{1 bunch broccoli rabe}.
"""


def test_check_on_a_variant_without_parent_exits_2_naming_the_flag_and_lints_nothing():
    """recipe-authoring › `check` … › check needs the parent, the read commands do not."""
    out = run_cli(VARIANT, "check", expect=2)
    assert out.strip() == fe.NO_PARENT_FOR_CHECK and "--parent <export>" in out and "Plays as" not in out
    assert run_json(VARIANT, "check", expect=2) == {"error": fe.NO_PARENT_FOR_CHECK, "code": 2}
    assert "Steps from: a local file" in run_cli(VARIANT, "--dsl", "plan")  # the read command proceeds


def test_u_inherited_from_the_export_informs_and_u_or_v_introduced_by_an_edit_blocks(tmp_path, monkeypatch):
    """recipe-authoring › `check` … › U inherited from the export informs, U introduced by an
    edit gates: the untouched copy of a parent whose own text trips U passes with the line
    suffixed "(inherited from the export)" and every step available at once; a variant of
    a parent that had edges fails on V when an edit adds an orphan atom, and on U when the
    edit removes the edges; a composed file with the same flat body fails on U."""
    flat_parent = tmp_export(tmp_path, lambda d: row_of(d, "rcp-steak-01").update({"dsl": FLAT_STEAK}))
    kept = tmp_path / "flat.recipe.md"
    out = run_cli(flat_parent, "convert", "Skillet Steak Supper", "--made-on", MADE_ON, "--out", kept)
    assert kept.is_file() and "it passes check" in out
    check = run_cli(kept, "check", "--parent", flat_parent)
    assert "note [U]: 3 steps but no depends_on edges" in check and "(inherited from the export)" in check
    assert "  Mise en place (wave 1): 1. Toast the Spices, 2. Sear the Steak, 3. Plate the Supper" in check
    assert check.rstrip().endswith("Passes: nothing blocks local:flat.")
    result = run_json(kept, "check", "--parent", flat_parent)
    assert result["ok"] is True
    assert [(f["rule"], f["kind"], f["gated"]) for f in result["findings"]] == [("U", "note", False)]
    assert result["findings"][0]["message"].endswith("(inherited from the export)")
    # The same flat body composed by the assistant: the assistant wrote the ordering, so U gates.
    flat_composed = write(tmp_path, "flat-composed.md", composed(FLAT_STEAK.replace("# Skillet Steak Supper", "# Probe")))
    assert "suggestion [U]: 3 steps but no depends_on edges" in run_cli(flat_composed, "check", expect=1)
    # A parent that had edges (the fixture's steak row): an edit that adds an orphan atom
    # strands a second sink — V, absent from the baseline — and gates.
    orphan = write(tmp_path, "orphan.md", VARIANT.read_text(encoding="utf-8").rstrip("\n") + "\n\n"
                   "## Warm the Plates [phase=serve section=main duration=2 attention_level=none]\n"
                   "Warm the plates in the oven's last minutes.\n")
    out = run_cli(orphan, "check", "--parent", V2, expect=1)
    assert "suggestion [V]: step DAG does not converge: 2 terminal steps" in out and "(inherited" not in out
    # An edit that removes every edge: U, absent from the baseline, gates.
    text = VARIANT.read_text(encoding="utf-8")
    assert text.count(" depends_on=[") > 1
    edgeless = write(tmp_path, "edgeless.md", re.sub(r" depends_on=\[[^\]]*\]", "", text))
    out = run_cli(edgeless, "check", "--parent", V2, expect=1)
    assert "suggestion [U]: 13 steps but no depends_on edges" in out and "(inherited" not in out
    # Removing one edge of the untouched copy strands a sink: V, gated.
    one_less = write(tmp_path, "one-less.md", text.replace(" depends_on=[sear-the-second-side]", "", 1))
    assert "suggestion [V]: step DAG does not converge" in run_cli(one_less, "check", "--parent", V2, expect=1)


def test_a_nodes_only_parents_baseline_is_the_convert_outputs_findings(tmp_path):
    """The parent row carries nodes only: its baseline is the lint of the `convert` draft, so a
    flat nodes recipe's U is inherited by its variant and gated on a composed copy."""
    flat_nodes = [{"id": 1, "title": "Toast the Bread", "text": "Toast the [bread] under the grill.", "time": 3,
                   "until": "golden", "dependencies": []},
                  {"id": 2, "title": "Boil the Egg", "text": "Lower the [egg] into boiling water.", "time": 6,
                   "until": "set but runny", "dependencies": []},
                  {"id": 3, "title": "Serve", "text": "Butter the toast with the [butter] and serve with the egg.", "time": 1,
                   "until": None, "dependencies": []}]
    parent = tmp_export(tmp_path, lambda d: row_of(d, "rcp-toast-03").update({"nodes": flat_nodes}))
    kept = tmp_path / "toast.recipe.md"
    run_cli(parent, "convert", "Toast Soldiers", "--made-on", MADE_ON, "--out", kept)
    result = run_json(kept, "check", "--parent", parent)
    assert result["ok"] is True and [(f["rule"], f["gated"]) for f in result["findings"]] == [("U", False)]
    assert result["findings"][0]["message"].endswith("(inherited from the export)")
    body = fe.split_envelope(kept.read_text(encoding="utf-8"))[1]
    flat_composed = write(tmp_path, "toast-composed.md", composed(body.replace("# Toast Soldiers", "# Probe")))
    assert [(f["rule"], f["gated"]) for f in run_json(flat_composed, "check", expect=1)["findings"]] == [("U", True)]


# ---------------------------------------------------------------------------
# stdin, --json, the envelope, the parent cross-check, --out, the floor
# ---------------------------------------------------------------------------


def test_stdin_dash_names_the_draft_from_out_or_the_title(tmp_path, monkeypatch):
    """`check -` reads the draft from stdin: its id is `--out`'s basename when given, else the
    slug of the title; with `--out` the clean draft is written once."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(composed(CLEAN)))
    out = run_cli("-", "check")
    assert out.splitlines()[0] == "check: - (stdin) — local:probe (composed)"
    target = tmp_path / "my-beans.recipe.md"
    monkeypatch.setattr(sys, "stdin", io.StringIO(composed(CLEAN)))
    out = run_cli("-", "check", "--out", target)
    assert out.splitlines()[0] == "check: - (stdin) — local:my-beans (composed)"
    assert target.read_text(encoding="utf-8") == composed(CLEAN) and f"Wrote {target}" in out
    monkeypatch.setattr(sys, "stdin", io.StringIO(composed(RULE_TEXTS["T"])))
    out = run_cli("-", "check", "--out", tmp_path / "bad.md", expect=1)
    assert "[T]" in out and not (tmp_path / "bad.md").exists()


def test_json_shape():
    """`--json` → {ok, findings:[{rule, step, kind, message, gated}], notes, plays_as, h} plus
    the id, origin, path, warnings, written and exit fields the text answer is built from."""
    result = run_json(VARIANT, "check", "--parent", V2)
    assert set(result) >= {"ok", "findings", "notes", "plays_as", "h", "id", "origin", "path", "warnings", "written", "exit"}
    assert result["ok"] is True and result["written"] is None and result["exit"] == 0
    assert result["id"] == "local:sample-variant" and result["origin"] == "variant"
    assert set(result["plays_as"]) == {"steps", "wave1", "estimate_minutes", "warnings"}
    assert re.fullmatch(r"[0-9a-f]{8}", result["h"])
    failing = run_json(COMPOSED.parent.parent / "local" / "sample-variant.md", "check", expect=2)
    assert failing == {"error": fe.NO_PARENT_FOR_CHECK, "code": 2}
    orphan = run_json(VARIANT, "check", "--parent", V2)  # every finding entry has exactly the five keys
    for f in orphan["findings"]:
        assert set(f) == {"rule", "step", "kind", "message", "gated"}


VARIANT_ENV = """---
title: Probe
author: "@ana"
source_url: https://blog.example/skillet-steak-supper
attribution:
  - source Cara
lineage:
  origin: variant
  parent_id: rcp-steak-01
  parent_handle: skillet-steak-supper-a1b2c3
  parent_lineage: forked from rcp-parent-77 at v2; credits @cara, @ben
  exported_at: 2026-10-08T12:00:00+00:00
  credits:
    - cara
    - ben
  made_on: 2026-10-13
  changes:
    - copied from the Fond-format steps the export carries
---
"""


def test_envelope_errors_are_named(tmp_path):
    """recipe-authoring › The envelope and its keys per origin / The local id: an unknown
    key, a Fond-looking key, a uid-shaped value, a digit-only scalar kept as text, a
    title/H1 mismatch, a missing origin, a parent key on a composed file, an origin
    outside the three, a compact list, a basename outside the shape — each a `check` error
    naming its key; a colon in a `changes` entry is the one warning ("write -> not :")."""
    def check_errors(name, text):
        result = run_json(write(tmp_path, name, text), "check", expect=1)
        return [f["message"] for f in result["findings"] if f["rule"] == "envelope"]

    env = ENVELOPE.format(origin="composed")
    assert "`notes` is not a DSL_SPEC §1.2 key (title, author, yield, source_url, attribution, lineage)" in \
        check_errors("unknown.md", env.replace("title: Probe\n", "title: Probe\nnotes: mine\n") + CLEAN)
    errors = check_errors("fond-id.md", env.replace("title: Probe\n", "title: Probe\nid: rcp-steak-01\nhandle: soup-xyz789\n") + CLEAN)
    assert "`id`: a local file never carries a Fond id" in errors and "`handle`: a local file never carries a Fond id" in errors
    uid = "A" * 28  # built here, never written as a literal (the must-not-publish check scans this file too)
    assert any("a 28-character account-id-shaped value — a local file never carries a uid" in e
               for e in check_errors("uid.md", env.replace("title: Probe\n", f"title: Probe\nauthor: {uid}\n") + CLEAN))
    assert any("a local file never carries a Fond id or a fork point" in e
               for e in check_errors("fork-point.md", env.replace("  made_on:", "  fork_point: v2\n  made_on:") + CLEAN))
    assert "`title` (`Probe`) and the `# H1` (`Other`) disagree" in check_errors("mismatch.md", env + CLEAN.replace("# Probe", "# Other"))
    assert "`lineage.origin` is required (composed | variant | transcribed)" in \
        check_errors("no-origin.md", env.replace("  origin: composed\n", "") + CLEAN)
    assert "`lineage.origin` must be composed, variant or transcribed, not `forked`" in \
        check_errors("bad-origin.md", env.replace("origin: composed", "origin: forked") + CLEAN)
    assert "`lineage.parent_id` belongs to a variant; a composed file names no parent" in \
        check_errors("parent-on-composed.md", env.replace("  made_on:", "  parent_id: rcp-steak-01\n  made_on:") + CLEAN)
    assert any("compact list `[Ana, Ben]` — write one `- item` per line" in e
               for e in check_errors("compact.md", env.replace("title: Probe\n", "title: Probe\nattribution: [Ana, Ben]\n") + CLEAN))
    assert any("is not a local id: the file name up to its first dot must match ^[a-z][a-z0-9-]*$" in e
               for e in check_errors("Bad_Name.md", env + CLEAN))
    assert "a file composed from a page needs an `attribution` line beside `source_url`" in \
        check_errors("page-no-credit.md", env.replace("title: Probe\n", "title: Probe\nsource_url: https://blog.example/x\n") + CLEAN)[0]
    # A digit-only scalar stays text: the reader never int-ifies, so `check` reports the string.
    data, errors, warnings = fe.parse_envelope("title: Probe\nlineage:\n  origin: variant\n  parent_id: 12345678\n  made_on: 2026-10-13\n")
    assert data["lineage"]["parent_id"] == "12345678" and errors == [] and warnings == []
    digits = write(tmp_path, "digits.md", VARIANT_ENV.replace("parent_id: rcp-steak-01", "parent_id: 12345678") + CLEAN)
    out = run_cli(digits, "check", "--parent", V2, expect=1)
    assert "error [parent]: `lineage.parent_id` '12345678' names no recipe in the --parent export" in out
    # The colon warning: printed, not gated — the file passes.
    colon = write(tmp_path, "colon.md", env.replace("    - composed by the assistant from the user's description\n",
                                                     "    - composed by the assistant from the user's description\n    - added: a timer on the simmer\n") + CLEAN)
    out = run_cli(colon, "check")
    colon_warning = r"lineage\.changes entry 2 \(line \d+\): write -> not : \(`added: a timer on the simmer`\)"
    assert re.search("^warning: " + colon_warning + "$", out, re.M)
    assert out.rstrip().endswith("Passes: nothing blocks local:colon.")
    warnings = run_json(colon, "check")["warnings"]
    assert len(warnings) == 1 and re.fullmatch(colon_warning, warnings[0])


def test_a_tab_in_the_indent_and_a_duplicated_key_are_refused_by_file_line(tmp_path):
    """recipe-authoring › The envelope and its keys per origin: a tab in the indent and a
    duplicated key are `check` errors naming the file's line (line 1 is the opening `---`),
    never a guess at what was meant."""
    env = ENVELOPE.format(origin="composed")

    def envelope_errors(name, text):
        result = run_json(write(tmp_path, name, text), "check", expect=1)
        return [f["message"] for f in result["findings"] if f["rule"] == "envelope"]

    # `  made_on:` is file line 5; the tabbed line is dropped, so its key is reported missing too.
    errors = envelope_errors("tab.md", env.replace("  made_on:", "\tmade_on:") + CLEAN)
    assert errors[0] == "line 5: a tab in the indent — indent with two spaces"
    assert fe.MADE_ON_EMPTY in errors  # "fill lineage.made_on with today's date (YYYY-MM-DD)"
    assert envelope_errors("dup-title.md", env.replace("title: Probe\n", "title: Probe\ntitle: Probe\n") + CLEAN) == \
        ["line 3: duplicated key `title`"]
    assert envelope_errors("dup-made-on.md", env.replace("  made_on: 2026-10-13\n", "  made_on: 2026-10-13\n  made_on: 2026-10-14\n") + CLEAN) == \
        ["line 6: duplicated key `lineage.made_on`"]
    # The reader numbers from the text `split_envelope` hands it, which opens with the fence's newline.
    assert fe.parse_envelope("\ntitle: Probe\ntitle: Probe\n")[1] == ["line 3: duplicated key `title`"]


def test_a_tab_anywhere_in_the_envelope_is_refused_by_file_line(tmp_path):
    """recipe-authoring › The envelope and its keys per origin: every tab in the envelope is
    a `check` error naming the file's line — after the indent inside a `changes` entry, inside
    a quoted scalar, in a comment, and in the indent as before — never read as what it might
    have meant (the line is dropped, so a key it carried is reported missing too)."""
    env = ENVELOPE.format(origin="composed")

    def envelope_errors(name, text):
        result = run_json(write(tmp_path, name, text), "check", expect=1)
        return [f["message"] for f in result["findings"] if f["rule"] == "envelope"]

    after = " — the envelope carries no tabs; write a space"
    # the `changes` entry is file line 7; the tab sits between two words, after the indent
    errors = envelope_errors("tab-entry.md", env.replace("composed by the assistant", "composed by\tthe assistant") + CLEAN)
    assert errors[0] == "line 7: a tab after the indent" + after, errors
    # inside a quoted scalar (file line 2): named by line, and the dropped title is missing
    errors = envelope_errors("tab-quoted.md", env.replace("title: Probe\n", 'title: "Pro\tbe"\n') + CLEAN)
    assert errors[0] == "line 2: a tab after the indent" + after and "`title` is required" in errors, errors
    # in a comment line (file line 3)
    errors = envelope_errors("tab-comment.md", env.replace("lineage:\n", "# a\tnote\nlineage:\n") + CLEAN)
    assert errors == ["line 3: a tab after the indent" + after], errors
    # a trailing tab after a value (file line 2)
    errors = envelope_errors("tab-trailing.md", env.replace("title: Probe\n", "title: Probe\t\n") + CLEAN)
    assert errors[0] == "line 2: a tab after the indent" + after, errors
    # the leading tab keeps its own message
    errors = envelope_errors("tab-indent.md", env.replace("  made_on:", "\tmade_on:") + CLEAN)
    assert errors[0] == "line 5: a tab in the indent — indent with two spaces", errors


def test_a_tab_on_an_envelope_fence_is_refused_by_file_line(tmp_path):
    """recipe-authoring › The envelope and its keys per origin ("a tab", anywhere in the
    envelope): the fence pattern's whitespace class swallows a tab after either `---` — and,
    after the opening one, a whitespace-only line below it — before the reader sees it, so
    each is refused here by its file line; spaces after a fence stay accepted (the split is
    the reference `split_frontmatter`'s), and blank lines under the opening fence no longer
    shift the line numbers the reader reports."""
    env = ENVELOPE.format(origin="composed")

    def envelope_errors(name, text):
        result = run_json(write(tmp_path, name, text), "check", expect=1)
        return [f["message"] for f in result["findings"] if f["rule"] == "envelope"]

    fence = " — the envelope carries no tabs; write the fence as `---`"
    assert envelope_errors("tab-open.md", "---\t\n" + env[len("---\n"):] + CLEAN) == ["line 1: a tab on the `---` fence" + fence]
    assert envelope_errors("tab-open-spaced.md", "--- \t \n" + env[len("---\n"):] + CLEAN) == ["line 1: a tab on the `---` fence" + fence]
    # the closing fence is file line 8
    assert env.splitlines()[7] == "---"
    assert envelope_errors("tab-close.md", env[:-len("---\n")] + "---\t\n" + CLEAN) == ["line 8: a tab on the `---` fence" + fence]
    both = envelope_errors("tab-both.md", "---\t\n" + env[len("---\n"):-len("---\n")] + "---\t\n" + CLEAN)
    assert both == ["line 1: a tab on the `---` fence" + fence, "line 8: a tab on the `---` fence" + fence], both
    # a tab-only line just under the opening fence (swallowed by the same match) is file line 2
    assert envelope_errors("tab-blank.md", "---\n\t\n" + env[len("---\n"):] + CLEAN) == \
        ["line 2: a tab in the indent — indent with two spaces"]
    # the gate refuses to cook it too
    assert "a tab on the `---` fence" in run_cli(write(tmp_path, "tab-cook.md", "---\t\n" + env[len("---\n"):] + CLEAN),
                                                 "--dsl", "plan", expect=1)
    # spaces after either fence are accepted, and the h is the clean file's
    clean = write(tmp_path, "clean.md", env + CLEAN)
    spaced = write(tmp_path, "spaced.md", "---   \n" + env[len("---\n"):-len("---\n")] + "---  \n" + CLEAN)
    for path in (clean, spaced):
        out = run_cli(path, "check")
        assert out.rstrip().endswith(f"Passes: nothing blocks local:{path.stem}."), out
    assert run_json(spaced, "check")["h"] == run_json(clean, "check")["h"]
    # a blank line under the opening fence: the duplicated `title` is file line 9, not 8
    blank = "---\n\n" + env[len("---\n"):].replace("---\n", "title: Probe\n---\n")
    assert envelope_errors("blank-dup.md", blank + CLEAN) == ["line 9: duplicated key `title`"]


def test_a_quoted_or_colon_bearing_title_renders_unchanged_and_checks_against_its_h1(tmp_path):
    """recipe-authoring › Variant › a DSL row becomes a variant unchanged (the body byte for
    byte; any cookable row): the envelope renderer never rewrites a scalar — `"Best" Soup`
    goes in single quotes, `It's "hot"` and `Soup: The Sequel` bare, a value carrying both
    quote kinds in single quotes — and the strict reader reads each back exactly, so `check`
    sees no title/H1 mismatch."""
    titles = ['"Best" Soup', 'It\'s "hot"', '\'Tis "the" season', "Soup: The Sequel", '"Best"', "'quoted'"]
    for i, title in enumerate(titles):
        env = fe.render_envelope({"title": title, "lineage": {"origin": "composed", "made_on": "2026-10-13",
                                                            "changes": ["composed by the assistant from the user's description"]}})
        data, errors, warnings = fe.parse_envelope(fe.split_envelope(env)[0])
        assert (data["title"], errors, warnings) == (title, [], []), (title, env)
        out = run_cli(write(tmp_path, f"quoted-{i}.md", env + CLEAN.replace("# Probe", f"# {title}")), "check")
        assert out.rstrip().endswith(f"Passes: nothing blocks local:quoted-{i}."), out
    assert fe._env_scalar('"Best" Soup') == "'\"Best\" Soup'" and fe._env_scalar('It\'s "hot"') == 'It\'s "hot"'
    assert fe._env_scalar('\'Tis "the" season') == "''Tis \"the\" season'" and fe._env_scalar("'quoted'") == "\"'quoted'\""
    assert fe._env_scalar("@cara") == '"@cara"' and fe._env_scalar("Soup: The Sequel") == "Soup: The Sequel"


def test_a_map_under_a_list_item_ends_check_before_lint_runs_with_no_traceback(tmp_path):
    """recipe-authoring › The envelope and its keys per origin › a shape the reference
    reader would misread is refused, not guessed (verifier finding, 2026-10-13): a map
    nested under a list item is a strict-reader error, and on any strict-reader error
    `check` — and every `--dsl` command, which runs the same gate — ends before the
    vendored lint runs, because the reference `parse_yaml` raises a TypeError on that
    shape: exit 1, the reader's error printed, no "Plays as", no traceback (the CLI runs
    in-process here, so a traceback would fail this test outright)."""
    env = ENVELOPE.format(origin="composed").replace("title: Probe\n", "title: Probe\nattribution:\n  - Ana\n    role: cook\n")
    nested = write(tmp_path, "nested.md", env + CLEAN)
    out = run_cli(nested, "check", expect=1)
    assert "nothing may be indented under a list item" in out and "Traceback" not in out
    assert "Plays as:" not in out and "[T]" not in out and "[U]" not in out  # lint never ran
    assert out.rstrip().endswith("1 finding(s) block local:nested; nothing with a gated finding is written, kept or cooked.")
    result = run_json(nested, "check", expect=1)
    assert [f["rule"] for f in result["findings"]] == ["envelope"] and result["plays_as"] == {}
    for cmd in ("plan", "show"):
        out = run_cli(nested, "--dsl", cmd, expect=1)
        assert "nothing may be indented under a list item" in out and "Traceback" not in out
    # the same shape via stdin, and `--out` writes nothing
    target = tmp_path / "kept.md"
    out = run_cli(nested, "check", "--out", target, expect=1)
    assert not target.exists() and f"Nothing written to {target}" in out


def test_parent_mismatch_is_refused_by_name(tmp_path):
    """recipe-authoring › `check` … › parent mismatch: a `parent_id` the `--parent` export does
    not carry, or carries with another handle, author, source, attribution, lineage line or
    `credits` (exact equality, order included) — each named with the key and the row's value;
    "no `credits` key" asserted against a null parent `lineage`."""
    body = fe.split_envelope(VARIANT.read_text(encoding="utf-8"))[1]
    good = VARIANT.read_text(encoding="utf-8")

    def refused(name, text, fragment):
        out = run_cli(write(tmp_path, name, text), "check", "--parent", V2, expect=1)
        assert fragment in out, out
        return out

    refused("gone.md", good.replace("parent_id: rcp-steak-01", "parent_id: rcp-nope-99"),
            "error [parent]: `lineage.parent_id` 'rcp-nope-99' names no recipe in the --parent export")
    refused("handle.md", good.replace("parent_handle: skillet-steak-supper-a1b2c3", "parent_handle: other-h4n5d6"),
            "error [parent]: `lineage.parent_handle` is 'other-h4n5d6'; the row carries 'skillet-steak-supper-a1b2c3'")
    refused("author.md", good.replace('author: "@ana"', 'author: "@ben"'), "error [parent]: `author` is '@ben'; the row carries '@ana'")
    refused("source.md", good.replace("source_url: https://blog.example/skillet-steak-supper", "source_url: https://blog.example/other"),
            "error [parent]: `source_url` is 'https://blog.example/other'; the row carries 'https://blog.example/skillet-steak-supper'")
    refused("attribution.md", good.replace("  - source Cara", "  - source Dana"),
            "error [parent]: `attribution` is ['source Dana']; the row carries ['source Cara']")
    refused("lineage.md", good.replace("credits @cara, @ben\n", "credits @cara\n"),
            "error [parent]: `lineage.parent_lineage` is 'forked from rcp-parent-77 at v2; credits @cara'; "
            "the row carries 'forked from rcp-parent-77 at v2; credits @cara, @ben'")
    refused("exported.md", good.replace("exported_at: 2026-10-08T12:00:00+00:00", "exported_at: 2026-10-09T12:00:00+00:00"),
            "error [parent]: `lineage.exported_at` is '2026-10-09T12:00:00+00:00'; the row carries '2026-10-08T12:00:00+00:00'")
    refused("order.md", good.replace("  credits:\n    - cara\n    - ben\n", "  credits:\n    - ben\n    - cara\n"),
            "error [parent]: `lineage.credits` is ['ben', 'cara']; the row carries ['cara', 'ben']")
    refused("extra.md", good.replace("    - ben\n", "    - ben\n    - ana\n"),
            "error [parent]: `lineage.credits` is ['cara', 'ben', 'ana']; the row carries ['cara', 'ben']")
    refused("no-credits.md", good.replace("  credits:\n    - cara\n    - ben\n", ""),
            "error [parent]: `lineage.credits` is absent; the row carries ['cara', 'ben']")
    # A null parent lineage: no credits key belongs in the file.
    clean = CLEAN_DSL.read_text(encoding="utf-8")
    refused("null-lineage.md", clean.replace("  made_on:", "  credits:\n    - ana\n  made_on:"),
            "error [parent]: `lineage.credits` is present; the row's `lineage` is null, so no credits key belongs here")
    assert "Passes: nothing blocks" in run_cli(VARIANT, "check", "--parent", V2)
    assert "Passes: nothing blocks" in run_cli(CLEAN_DSL, "check", "--parent", V2)
    assert body in good  # the body was never the subject above


def test_out_writes_only_on_a_clean_gate_and_never_over_an_existing_path(tmp_path):
    """recipe-authoring › Written only to a file the user asks for: nothing with findings is
    written, the clean draft is written once, an existing path is refused with exit 1."""
    failing = write(tmp_path, "failing.md", composed(RULE_TEXTS["AA"]))
    target = tmp_path / "kept.recipe.md"
    out = run_cli(failing, "check", "--out", target, expect=1)
    assert not target.exists() and f"Nothing written to {target}" in out
    clean = write(tmp_path, "clean.md", composed(CLEAN))
    out = run_cli(clean, "check", "--out", target)
    assert target.read_text(encoding="utf-8") == composed(CLEAN) and f"Wrote {target}" in out
    assert run_json(clean, "check", "--out", tmp_path / "other.md")["written"] == str(tmp_path / "other.md")
    out = run_cli(clean, "check", "--out", target, expect=1)
    assert out.strip() == f"`{target}` exists; pass --out <other> or edit that file"
    assert target.read_text(encoding="utf-8") == composed(CLEAN)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clean.md", "failing.md", "kept.recipe.md", "other.md"]


def test_out_basename_must_be_a_local_id_before_anything_is_written(tmp_path, monkeypatch):
    """recipe-authoring › The local id: `check <clean file> --out <path>` validates the OUTPUT
    basename against ^[a-z][a-z0-9-]*$ before anything is read or written — a clean `good.md`
    is never written as `BAD NAME.md`, a file `check` would then refuse — with the text an
    envelope error uses for a file so named, exit 1 and nothing written; the same over stdin
    and under `--json`; a basename that is a local id still writes."""
    clean = write(tmp_path, "good.md", composed(CLEAN))
    for name in ("BAD NAME.md", "Bad_Name.recipe.md", "9-lives.md", "my beans.md"):
        slug = name.split(".")[0]
        out = run_cli(clean, "check", "--out", tmp_path / name, expect=1)
        assert out.strip() == f"{fe.not_a_local_id(slug)}; pass --out <another name>"
        assert out.startswith(f"`{slug}` is not a local id: the file name up to its first dot must match ^[a-z][a-z0-9-]*$")
        assert not (tmp_path / name).exists()
    monkeypatch.setattr(sys, "stdin", io.StringIO(composed(CLEAN)))
    out = run_cli("-", "check", "--out", tmp_path / "BAD NAME.md", expect=1)
    assert out.strip() == f"{fe.not_a_local_id('BAD NAME')}; pass --out <another name>"
    assert run_json(clean, "check", "--out", tmp_path / "BAD NAME.md", expect=1)["error"].startswith("`BAD NAME` is not a local id")
    assert not (tmp_path / "BAD NAME.md").exists()
    # the envelope error for a file so named is the same text
    assert fe.not_a_local_id("Bad_Name") in run_json(write(tmp_path, "Bad_Name.md", composed(CLEAN)), "check", expect=1)["text"]
    out = run_cli(clean, "check", "--out", tmp_path / "good-copy.recipe.md")
    assert f"Wrote {tmp_path / 'good-copy.recipe.md'}" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Bad_Name.md", "good-copy.recipe.md", "good.md"]


def test_out_names_the_recipe_the_write_would_produce_and_refuses_a_sibling_with_its_id(tmp_path, monkeypatch):
    """recipe-authoring › The local id (review finding, 2026-10-14): `check <file> --out
    <path>` constructs, gates and reports the recipe under the OUTPUT basename — the id the
    kept file will carry — so `source.md --out foo.recipe.md` says `local:foo` on the header,
    the Passes line and in `--json`, never `local:source`; and a recipe file in the output
    folder that already resolves to that id (`dal.md` beside the `dal.recipe.md` to be
    written: both `local:dal`) is refused with the library's collision line naming both
    files, exit 1, nothing written — when that file is the input itself and over stdin too —
    so no file the skill writes trips the rule `--dsl list` enforces. A `.md` without an
    envelope is not a recipe file and does not block; the same basename in another folder is
    no sibling, so the copy is written under its unchanged id."""
    source = write(tmp_path, "source.md", composed(CLEAN))
    out = run_cli(source, "check", "--out", tmp_path / "foo.recipe.md")
    assert out.splitlines()[0] == f"check: {source} — local:foo (composed)"
    assert out.rstrip().endswith(f"Passes: nothing blocks local:foo.\nWrote {tmp_path / 'foo.recipe.md'}")
    assert "local:source" not in out
    assert (tmp_path / "foo.recipe.md").read_text(encoding="utf-8") == composed(CLEAN)
    result = run_json(source, "check", "--out", tmp_path / "bar.md")
    assert (result["id"], result["path"], result["written"]) == ("local:bar", str(source), str(tmp_path / "bar.md"))
    # a gated draft is reported under the output's id too, and nothing is written
    failing = write(tmp_path, "failing.md", composed(RULE_TEXTS["AA"]))
    out = run_cli(failing, "check", "--out", tmp_path / "baz.recipe.md", expect=1)
    assert "1 finding(s) block local:baz; nothing with a gated finding is written, kept or cooked." in out
    assert not (tmp_path / "baz.recipe.md").exists()
    # a sibling already resolving to the output's id: refused before anything is gated, nothing written
    sibling = write(tmp_path, "dal.md", composed(CLEAN))
    target = tmp_path / "dal.recipe.md"
    line = (f"two files share the basename `dal` ({sibling}, {target}) — rename all but one; "
            "local ids must be unique in a folder; pass --out <another name>")
    assert run_cli(source, "check", "--out", target, expect=1).strip() == line
    assert run_json(source, "check", "--out", target, expect=1) == {"error": line, "code": 1}
    assert run_cli(sibling, "check", "--out", target, expect=1).strip() == line  # the input itself is that file
    monkeypatch.setattr(sys, "stdin", io.StringIO(composed(CLEAN)))
    assert run_cli("-", "check", "--out", target, expect=1).strip() == line
    assert not target.exists()
    # a `.md` without an envelope is not a recipe file: no sibling, the copy is written
    write(tmp_path, "notes.md", "my notes\n")
    assert f"Wrote {tmp_path / 'notes.recipe.md'}" in run_cli(source, "check", "--out", tmp_path / "notes.recipe.md")
    # the same basename in another folder is no sibling: the id is the file's own
    kept = tmp_path / "kept"
    kept.mkdir()
    out = run_cli(sibling, "check", "--out", kept / "dal.recipe.md")
    assert out.splitlines()[0] == f"check: {sibling} — local:dal (composed)" and (kept / "dal.recipe.md").is_file()
    # the folder's reader finds no collision among the files check wrote
    for folder in (tmp_path, kept):
        assert "share the basename" not in run_cli(folder, "--dsl", "list")
    assert sorted(p.name for p in tmp_path.iterdir()) == \
        ["bar.md", "dal.md", "failing.md", "foo.recipe.md", "kept", "notes.md", "notes.recipe.md", "source.md"]


def test_check_below_3_9_prints_the_floor_line_while_the_export_commands_run(monkeypatch):
    """recipe-authoring › `check` … › the floor on 3.8: one line, exit 1, and `plan` over the
    export still runs (the lazy import is the only 3.9 dependency)."""
    monkeypatch.setattr(sys, "version_info", (3, 8, 18, "final", 0))
    out = run_cli(VARIANT, "check", "--parent", V2, expect=1)
    assert out.strip() == FLOOR_LINE.format("3.8.18")
    assert run_json(COMPOSED, "check", expect=1) == {"error": FLOOR_LINE.format("3.8.18"), "code": 1}
    assert "Estimated time to serve" in run_cli(V2, "plan", "Skillet Steak Supper")


# ---------------------------------------------------------------------------
# Parity with apps/mcp's own lint (fond-mono only)
# ---------------------------------------------------------------------------

def reference_lint(texts: dict):
    """apps/mcp's `services.dsl.lint_dsl` over `texts`, in a subprocess with apps/mcp on
    sys.path (its lazy ingredient-spec import needs the venv's pydantic). Skips when
    apps/mcp is absent — the public mirror — or cannot import on this interpreter."""
    if not (MCP_ROOT / "services" / "dsl.py").is_file():
        pytest.skip("apps/mcp is absent (the public mirror carries no reference lint)")
    code = ("import json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from services.dsl import lint_dsl\n"
            "texts = json.loads(sys.stdin.read())\n"
            "print(json.dumps({k: [[p, i['rule'], i.get('step')] for p in ('errors', 'warnings', 'suggestions')\n"
            "                      for i in lint_dsl(t)[p]] for k, t in texts.items()}))\n")
    proc = subprocess.run([sys.executable, "-B", "-I", "-c", code, str(MCP_ROOT)], input=json.dumps(texts),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"apps/mcp's lint does not import on this interpreter: {proc.stderr.strip().splitlines()[-1:]}")
    return json.loads(proc.stdout)


def gate_view(result):
    """The gate's view of a lint result: every error, and every (rule, step) of a gated rule."""
    return sorted({(i["rule"], i.get("step")) for pool in ("errors", "warnings", "suggestions") for i in result[pool]
                   if pool == "errors" or i["rule"] in GATED})


def test_thirteen_rule_texts_and_the_fixture_dsl_rows_lint_the_same_in_apps_mcp():
    """fond-dsl-open-release › the vendored copy is the registry's lint: each of the thirteen
    rule texts trips the same rule in apps/mcp's `lint_dsl` (13/13), and over the fixtures'
    DSL rows and every shipped local file the gate's view of both lints is identical."""
    fond_dsl = fe._import_fond_dsl()
    export = fe.load_export(V2)
    texts = {rule: composed(text) for rule, text in RULE_TEXTS.items()}
    texts.update({rid: fe.find_recipe(export, rid).dsl for rid in ("rcp-steak-01", "rcp-rice-09")})
    texts.update({path.name: path.read_text(encoding="utf-8") for path in sorted(LOCAL.glob("*.md"))})
    reference = reference_lint(texts)
    agreed = 0
    for key, text in texts.items():
        ours = gate_view(fond_dsl.dsl.lint_dsl(text))
        theirs = sorted({(rule, step) for _pool, rule, step in reference[key] if _pool == "errors" or rule in GATED})
        assert ours == theirs, (key, ours, theirs)
        if key in GATED:
            assert key in {rule for rule, _step in theirs}
            agreed += 1
    assert agreed == 13
