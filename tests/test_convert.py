"""`convert` over an export row (recipe-authoring "Variant — of a recipe the export
carries", "`convert` is a labelled, deterministic draft", "Written only to a file the user
asks for"; cook-with-fond-authoring 6.3).

The session's schedule parity made permanent: EVERY nodes-only recipe in both fixtures
converts to a draft that passes `check` and whose `plan --dsl` agrees with `plan` over the
row — step count, each step's kind, countdown structure, occupancy, dependency order and
the estimate — with exactly the losses the spec names and nothing silent. A DSL row
converts byte for byte, `--from nodes` is refused, and the case "inherited findings on a
DSL row" pins the five AA lines the fixture's `rcp-steak-01` carries. No network, no
environment, synthetic fixtures only.

Run from apps/skill:  ../mcp/.venv/bin/python -m pytest -q tests/test_convert.py
"""

import contextlib
import importlib.util
import io
import json
import math
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
V1 = FIXTURES / "sample-export-v1.json"
CLEAN_DSL = FIXTURES / "local" / "sample-clean-dsl.md"
MADE_ON = "2026-10-13"  # the date from the conversation — the script reads no clock

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out[:3000]}"
    return out


def run_json(*args, expect=0):
    return json.loads(run_cli(*args, "--json", expect=expect))


def convert(path, rid, *extra, expect=0):
    return run_cli(path, "convert", rid, "--made-on", MADE_ON, *extra, expect=expect)


def atoms_of(draft: str):
    """The draft's schedulable atoms: (slug, meta, prose), notes left out."""
    _env, body = fe.split_envelope(draft)
    _title, dsl_body = fe.split_dsl(body)
    return [(fe.slugify(a["title"]), a["meta"], a["prose"]) for a in fe.parse_atoms(dsl_body)
            if a["meta"].get("type") != "note"]


def sigil_total(prose: str) -> float:
    total = 0.0
    for m in fe.TIMER.finditer(prose):
        for minutes, _label, rep in fe.parse_timer_body(m.group(2) or ""):
            total += minutes * rep
    return total


def nodes_only_rows():
    """(fixture, Fond id) for every cookable row without `dsl` in both fixtures — the v2
    authored and saved nodes rows and, with the v1 fixture, every version-1 authored row
    with nodes (its steak row carries `dsl` too, so it is a DSL row there)."""
    out = []
    for path in (V2, V1):
        export = fe.load_export(path)
        for r in fe.partition(export)[0]:
            content = export.content_of(r)
            if content is not None and not content.dsl:
                out.append((path, r.id))
    return out


NODES_ROWS = nodes_only_rows()
ROW_IDS = [f"{p.name}:{rid}" for p, rid in NODES_ROWS]


def test_the_parametrisation_covers_every_nodes_only_fixture_row():
    """Pinned, so the per-row tests below can never run over an empty list."""
    assert {(p.name, rid) for p, rid in NODES_ROWS} == {
        ("sample-export.json", "rcp-pasta-02"), ("sample-export.json", "rcp-toast-03"),
        ("sample-export.json", "rcp-soup-05"),
        ("sample-export-v1.json", "rcp-pasta-02"), ("sample-export-v1.json", "rcp-toast-03"),
    }


# ---------------------------------------------------------------------------
# Every nodes-only row: a draft that passes check and plays as the nodes did
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,rid", NODES_ROWS, ids=ROW_IDS)
def test_every_nodes_only_row_converts_to_a_draft_whose_check_is_empty(path, rid, tmp_path):
    """recipe-authoring › `convert` is a labelled, deterministic draft: "it passes `check` for
    every fixture nodes recipe". `--out <tmp>` writes it, `check --parent` over the file
    reports nothing — no finding of any kind, gated or not — and the first `changes` entry
    is the fixed label."""
    out = tmp_path / f"{rid}.recipe.md"
    text = convert(path, rid, "--out", out)
    assert out.is_file() and "it passes check" in text
    check = run_json(out, "check", "--parent", path)
    assert check["ok"] is True and check["findings"] == [] and check["notes"] == []
    assert run_cli(out, "check", "--parent", path).rstrip().endswith(f"Passes: nothing blocks local:{rid}.")
    draft = out.read_text(encoding="utf-8")
    env, _errors, _warnings = fe.parse_envelope(fe.split_envelope(draft)[0])
    assert env["lineage"]["origin"] == "variant" and env["lineage"]["parent_id"] == rid
    assert env["lineage"]["changes"] == ["converted by the assistant from the app's steps"]


@pytest.mark.parametrize("path,rid", NODES_ROWS, ids=ROW_IDS)
def test_schedule_parity_with_the_nodes_path(path, rid, tmp_path):
    """recipe-authoring › `convert` … › schedule parity: `plan --dsl` over the draft and
    `plan "<title>"` over the row agree on the step count, each step's kind, its countdown
    structure (segments, `× N`, `count=`), occupancy, dependency order (what each step
    follows, the available order, the waves) and the estimate. Two differences are the
    losses the spec names, asserted as such: a legacy cue (`until`, time 0) has no DSL
    kind and plays as an instant atom ("a cue-only `until` surviving only as prose"), and a
    sub-minute timer's scheduled length is its `duration=` ceiled to 1 — the exact seconds
    stay in the sigil, so the countdown is unchanged."""
    out = tmp_path / f"{rid}.recipe.md"
    text = convert(path, rid, "--out", out)
    dsl = run_json(out, "--dsl", "plan", "--parent", path)
    row = run_json(path, "plan", rid)
    assert dsl["source"] == "dsl" and row["source"] == "nodes"
    assert len(dsl["steps"]) == len(row["steps"]) > 0
    o_dsl = {s["id"]: s["ordinal"] for s in dsl["steps"]}
    o_row = {s["id"]: s["ordinal"] for s in row["steps"]}
    for a, b in zip(dsl["steps"], row["steps"]):
        assert a["ordinal"] == b["ordinal"] and a["title"] == b["title"]
        if b["kind"] == "cue":
            assert a["kind"] == "instant" and "cue-only `until`" in text  # the named loss
        else:
            assert a["kind"] == b["kind"], (a["title"], a["kind"], b["kind"])
        assert a["structure"] == b["structure"] and a["count"] == b["count"]
        assert abs(a["timer_total"] - b["timer_total"]) < 1e-9
        assert a["occupies"] == b["occupies"]
        assert a["after"] == b["after"]  # the ordinals each step follows
        if a["kind"] == "timer" and b["scheduled"] != math.floor(b["scheduled"]):
            assert a["scheduled"] == max(1, math.ceil(b["scheduled"] - 1e-9))
            assert re.search(r"node \S+: \d*\.\d+-min timer written with duration=\d+", text)
        else:
            assert abs(a["scheduled"] - b["scheduled"]) < 1e-9, (a["title"], a["scheduled"], b["scheduled"])
    assert [o_dsl[i] for i in dsl["available"]] == [o_row[i] for i in row["available"]]
    assert [[o_dsl[i] for i in w] for w in dsl["waves"]] == [[o_row[i] for i in w] for w in row["waves"]]
    assert dsl["estimate_minutes"] == row["estimate_minutes"]
    assert abs(dsl["estimate_exact"] - row["estimate_exact"]) < 1e-9


@pytest.mark.parametrize("path,rid", NODES_ROWS, ids=ROW_IDS)
def test_timer_atoms_carry_duration_equal_to_the_sigil_total_and_low_attention(path, rid):
    """recipe-authoring › `convert` …: a timer atom for `until` with `time > 0` carries
    `duration=` the sigil total — `ceil(minutes) ≥ 1` for a sub-minute timer, with the
    rounding named under the losses — and `attention_level=low`; hands-on work is
    `attention_level=full`; the prose never carries the projection's `<title> — N min`
    clause."""
    text = convert(path, rid, "--out", "-")
    draft = text.split("\nDraft only", 1)[0] if "\nConverted with these losses:" not in text \
        else text.split("\nConverted with these losses:", 1)[0]
    atoms = atoms_of(draft)
    assert atoms
    for slug, meta, prose in atoms:
        assert not re.search(r" — \d+(?:-\d+)? min\b", prose), (slug, prose)
        total = sigil_total(prose)
        if total > 0:
            assert meta.get("attention_level") == "low", slug
            duration = int(meta["duration"])
            if abs(total - round(total)) < 1e-9:
                assert duration == int(round(total)), (slug, duration, total)
            else:
                assert duration == max(1, math.ceil(total - 1e-9)), (slug, duration, total)
                assert re.search(rf"node \S+: {total:g}-min timer written with duration={duration}", text), slug
        elif meta.get("duration"):
            assert meta.get("attention_level") == "full", slug


def test_the_sub_minute_garlic_node_rounds_up_and_the_losses_say_so():
    """The pasta row's 30-second sizzle: `~timer{30%sec}` with `duration=1` and the loss line."""
    text = convert(V2, "rcp-pasta-02", "--out", "-")
    sizzle = next(a for a in atoms_of(text) if a[0] == "sizzle-the-garlic")
    assert "~timer{30%sec}" in sizzle[2] and sizzle[1]["duration"] == "1" and sizzle[1]["attention_level"] == "low"
    assert "  - node 4: 0.5-min timer written with duration=1 (DSL_SPEC §1.4 int minutes; the sigil keeps the exact seconds)" in text


@pytest.mark.parametrize("path,rid", NODES_ROWS, ids=ROW_IDS)
def test_the_losses_block_lists_the_full_attention_on_every_hands_on_node(path, rid):
    """recipe-authoring › `convert` …: "the `full` attention on every hands-on node — a boil
    occupies the cook where the card would say `low`" is printed under "Converted with these
    losses:" once per hands-on node, never silently."""
    text = convert(path, rid, "--out", "-")
    row = run_json(path, "plan", rid)
    hands_on = [s for s in row["steps"] if s["kind"] == "hands-on"]
    assert "Converted with these losses:" in text
    losses = [ln for ln in text.splitlines() if ln.startswith("  - ")]
    full = [ln for ln in losses if "hands-on step written attention_level=full" in ln]
    assert len(full) == len(hands_on) > 0
    if any(s["kind"] == "cue" for s in row["steps"]):
        assert any("cue-only `until`" in ln and "survives only as prose" in ln for ln in losses)


def test_the_synthetic_until_label_is_stripped_and_a_reintroduced_one_is_caught(tmp_path, monkeypatch):
    """recipe-authoring › `convert` … › the synthetic until is stripped: a projected node's
    `until` "Preheat the Oven — 15 min" leaves no "— 15 min" fragment in the prose — the
    minutes live in `~preheat{15%min}` and `duration=15`. The guard is real: with the
    label detection switched off in a scratch run (the session's "deliberately re-introduced
    until-label"), the clause reappears and the same assertion fails."""
    data = json.loads(V2.read_text(encoding="utf-8"))
    steak = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-steak-01")
    assert steak["nodes"][0]["until"] == "Preheat the Oven — 15 min"
    steak["dsl"] = None  # the nodes alone, so `convert` transliterates
    export = tmp_path / "fond-export-test.json"
    export.write_text(json.dumps(data), encoding="utf-8")
    text = convert(export, "rcp-steak-01", "--out", "-")
    preheat = next(a for a in atoms_of(text) if a[0] == "preheat-the-oven")
    assert "— 15 min" not in preheat[2] and "~preheat{15%min}" in preheat[2] and preheat[1]["duration"] == "15"
    assert not any(" — 15 min" in a[2] for a in atoms_of(text))
    n2d = fe._import_nodes_to_dsl()
    monkeypatch.setattr(n2d, "is_synthetic_label", lambda until, title: False)
    scratch = convert(export, "rcp-steak-01", "--out", "-")
    reintroduced = next(a for a in atoms_of(scratch) if a[0] == "preheat-the-oven")
    assert "until Preheat the Oven — 15 min" in reintroduced[2]  # the prose assertion above would now fail


def test_a_renamed_title_still_strips_its_synthetic_label_and_a_dashed_cue_survives(tmp_path):
    """recipe-authoring › `convert` … › the synthetic until is stripped: the label is matched
    against the node's OWN title, not the atom title rewritten for a unique slug — a second
    "Rest the Dough" becomes "Rest the Dough (2)" (a named loss) and its `until` "Rest the
    Dough — 25 min" is still the projection's label, stripped, the minutes in the sigil and
    `duration=`. Only that exact form is: a cue that merely contains " — " ("simmered — the
    sauce coats a spoon") and one headed by the title but ending in words ("Rest the Dough —
    doubled in size") stay cues; the fixture's Preheat case is stripped as before."""
    data = json.loads(V2.read_text(encoding="utf-8"))
    steak = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-steak-01")
    steak["dsl"] = None  # the nodes alone, so `convert` transliterates
    nodes = {str(n["id"]): n for n in steak["nodes"]}
    assert nodes["4"]["title"] == "Rest the Dough" and nodes["11"]["title"] == "Roast the Vegetables"
    nodes["4"]["until"] = "Rest the Dough — doubled in size"
    nodes["11"]["title"], nodes["11"]["until"] = "Rest the Dough", "Rest the Dough — 25 min"
    nodes["6"]["until"] = "simmered — the sauce coats a spoon"
    export = tmp_path / "fond-export-test.json"
    export.write_text(json.dumps(data), encoding="utf-8")
    text = convert(export, "rcp-steak-01", "--out", "-")
    assert "  - node 11: title changed for a unique kebab slug ('Rest the Dough' → 'Rest the Dough (2)')" in text
    atoms = {a[0]: a for a in atoms_of(text)}
    second = atoms["rest-the-dough-2"]
    assert "— 25 min" not in second[2] and "until Rest the Dough" not in second[2]
    assert re.search(r"~\w+\{25%min\}", second[2]) and second[1]["duration"] == "25"
    assert "until Rest the Dough — doubled in size" in atoms["rest-the-dough"][2]
    assert "until simmered — the sauce coats a spoon" in atoms["simmer-the-sauce"][2]
    preheat = atoms["preheat-the-oven"]
    assert "— 15 min" not in preheat[2] and "~preheat{15%min}" in preheat[2]
    assert not any(" — 25 min" in a[2] or " — 15 min" in a[2] for a in atoms_of(text))


# ---------------------------------------------------------------------------
# A DSL row: byte-equal, one verb
# ---------------------------------------------------------------------------


def test_a_dsl_row_converts_to_a_body_byte_equal_to_its_dsl_and_the_shipped_clean_fixture():
    """recipe-authoring › Variant › a DSL row becomes a variant unchanged: the printed body is
    the row's `dsl` byte for byte, the first `changes` entry is the copy entry, and the
    draft is exactly `fixtures/local/sample-clean-dsl.md` (made on the fixture's date)."""
    export = fe.load_export(V2)
    for rid in ("rcp-rice-09", "rcp-steak-01"):
        row = fe.find_recipe(export, rid)
        out = run_json(V2, "convert", rid, "--made-on", MADE_ON, "--out", "-", expect=0 if rid == "rcp-rice-09" else 1)
        assert out["body"] == row.dsl and row.dsl.endswith("\n")
        assert out["draft"].endswith(row.dsl) and out["losses"] == []
        env, _e, _w = fe.parse_envelope(fe.split_envelope(out["draft"])[0])
        assert env["lineage"]["changes"] == ["copied from the Fond-format steps the export carries"]
    draft = convert(V2, "rcp-rice-09", "--out", "-")
    assert draft.split("\nDraft only (--out -)", 1)[0].rstrip("\n") + "\n" == CLEAN_DSL.read_text(encoding="utf-8")
    assert draft.rstrip().endswith("Draft only (--out -): nothing written. h=" + run_json(V2, "plan", "rcp-rice-09")["h"])


def test_a_title_with_quotes_or_a_colon_converts_and_checks_unchanged(tmp_path):
    """recipe-authoring › Variant › a DSL row becomes a variant unchanged (any cookable row;
    the body byte for byte): a row titled `"Best" Soup`, `It's "hot"` or `Soup: The Sequel`
    converts to a draft whose envelope reads the title back exactly — never `'Best' Soup` —
    so `check --parent` sees no title/H1 mismatch and the draft is written."""
    for i, title in enumerate(['"Best" Soup', 'It\'s "hot"', "Soup: The Sequel"]):
        data = json.loads(V2.read_text(encoding="utf-8"))
        row = next(r for key in ("authoredRecipes", "savedRecipes") for r in data[key] if r.get("id") == "rcp-rice-09")
        assert row["dsl"].startswith("# Steamed Coconut Rice\n")
        row["title"] = title
        row["dsl"] = "# " + title + row["dsl"][len("# Steamed Coconut Rice"):]
        export = tmp_path / f"fond-export-t{i}.json"
        export.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / f"titled-{i}.recipe.md"
        result = run_json(export, "convert", "rcp-rice-09", "--made-on", MADE_ON, "--out", str(out))
        assert result["written"] == str(out), result
        draft = out.read_text(encoding="utf-8")
        assert draft.endswith(row["dsl"]) and f"\n# {title}\n" in draft
        env, errors, _w = fe.parse_envelope(fe.split_envelope(draft)[0])
        assert env["title"] == title and errors == [], (env, errors)
        check = run_cli(out, "check", "--parent", export)
        assert check.rstrip().endswith(f"Passes: nothing blocks local:titled-{i}."), check


def test_from_nodes_is_refused_on_a_dsl_row_and_on_every_row():
    """recipe-authoring › Variant: "no `--from nodes` for a row that carries `dsl`" — one verb;
    the body is the Fond-format steps the export carries, else the app's steps, and the
    first `changes` entry says which. The refusal is an argument error (exit 2), before
    any draft, on every row."""
    for rid, extra in (("rcp-steak-01", ("--from", "nodes")), ("rcp-rice-09", ("--from", "nodes")),
                       ("rcp-pasta-02", ("--from", "nodes")), ("rcp-rice-09", ("--to", "6")), ("rcp-rice-09", ("--factor", "2"))):
        out = convert(V2, rid, "--out", "-", *extra, expect=2)
        assert out.startswith("convert takes no --from, --to or --factor: the body is the Fond-format steps the export carries")
        assert "---" not in out and "scale a recipe with `scale`" in out


# ---------------------------------------------------------------------------
# Inherited findings on a DSL row (the fixture's rcp-steak-01)
# ---------------------------------------------------------------------------

FIVE_AA = {
    "toast-the-spices": "timer total 2m exceeds duration=0",
    "rest-the-dough": "timer total 15m exceeds duration=0",
    "sear-the-steak": "timer total 4m exceeds duration=0",
    "reduce-the-glaze": "timer total 25m exceeds duration=10",
    "griddle-the-corn-cakes": "timer total 3m exceeds duration=0",
}
FIVE_FIXES = (
    ("## Toast the Spices [phase=prep section=sauce attention_level=high]",
     "## Toast the Spices [phase=prep section=sauce duration=2 attention_level=high]",
     "set duration=2 on toast-the-spices, the sigil total"),
    ("## Rest the Dough [phase=prep section=bread attention_level=none]",
     "## Rest the Dough [phase=prep section=bread duration=15 attention_level=none]",
     "set duration=15 on rest-the-dough, the sigil total"),
    ("## Sear the Steak [phase=cook section=main attention_level=high depends_on=[toast-the-spices]]",
     "## Sear the Steak [phase=cook section=main duration=4 attention_level=high depends_on=[toast-the-spices]]",
     "set duration=4 on sear-the-steak, the sigil total"),
    ("## Reduce the Glaze [phase=cook section=sauce duration=10 attention_level=low depends_on=[simmer-the-sauce]]",
     "## Reduce the Glaze [phase=cook section=sauce duration=25 attention_level=low depends_on=[simmer-the-sauce]]",
     "set duration=25 on reduce-the-glaze, the sigil total"),
    ("## Griddle the Corn Cakes [phase=cook section=sides attention_level=medium count=3]",
     "## Griddle the Corn Cakes [phase=cook section=sides duration=3 attention_level=medium count=3]",
     "set duration=3 on griddle-the-corn-cakes, the sigil total"),
)


def repaired_draft(draft: str) -> str:
    """The assistant's mechanical fix: `duration=` raised to the sigil total on each of the
    five atoms, one `changes` line per atom — nothing else in the body changes."""
    text = draft
    for old, new, _line in FIVE_FIXES:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    marker = "    - copied from the Fond-format steps the export carries\n"
    assert text.count(marker) == 1
    return text.replace(marker, marker + "".join(f"    - {line}\n" for _o, _n, line in FIVE_FIXES))


def test_inherited_findings_on_a_dsl_row(tmp_path, monkeypatch):
    """recipe-authoring › Variant › inherited findings on a DSL row: `convert "Skillet Steak
    Supper" --out skillet-steak-supper.recipe.md` prints the body byte for byte, the five AA
    lines under "Inherited findings:", writes nothing and says so; the draft with each
    `duration=` raised to its sigil total and five `changes` lines passes `check - --parent
    <export> --out <path>` and is written once; the export's bytes never change."""
    before = V2.read_bytes()
    target = tmp_path / "skillet-steak-supper.recipe.md"
    out = convert(V2, "Skillet Steak Supper", "--out", target, expect=1)
    assert not target.exists()
    lines = out.splitlines()
    head = lines.index("Inherited findings:")
    aa = [ln for ln in lines[head + 1:] if ln.startswith("  warning [AA] @")]
    assert len(aa) == 5 and "Findings:" not in out.replace("Inherited findings:", "")
    seen = {}
    for ln in aa:
        m = re.match(r"  warning \[AA\] @([a-z-]+): (timer total \d+m exceeds duration=\d+) — ", ln)
        assert m, ln
        seen[m.group(1)] = m.group(2)
    assert seen == FIVE_AA
    assert (f"Nothing written to {target}: 5 finding(s) block the draft. Fix them in the draft above and persist it "
            f"with `check - --parent <export> --out {target}`.") in out
    body = run_json(V2, "convert", "Skillet Steak Supper", "--made-on", MADE_ON, "--out", "-", expect=1)
    assert body["body"] == fe.find_recipe(fe.load_export(V2), "rcp-steak-01").dsl and body["written"] is None
    assert [f["step"] for f in body["findings"] if f["gated"]] == list(FIVE_AA)
    draft = out.split("\nInherited findings:", 1)[0] + "\n"
    repaired = repaired_draft(draft)
    monkeypatch.setattr(sys, "stdin", io.StringIO(repaired))
    kept = run_cli("-", "check", "--parent", V2, "--out", target)
    assert target.is_file() and f"Wrote {target}" in kept and "Passes: nothing blocks local:skillet-steak-supper." in kept
    assert target.read_text(encoding="utf-8") == repaired
    assert "[AA]" not in kept
    # The same draft a second time: the path exists, nothing is written over it (exit 1).
    monkeypatch.setattr(sys, "stdin", io.StringIO(repaired))
    again = run_cli("-", "check", "--parent", V2, "--out", target, expect=1)
    assert again.strip() == f"`{target}` exists; pass --out <other> or edit that file"
    assert target.read_text(encoding="utf-8") == repaired
    assert V2.read_bytes() == before
    # The kept file cooks: the five atoms now carry the sigil totals the fixture variant does.
    plan = run_json(target, "--dsl", "plan", "--parent", V2)
    assert plan["h"] == run_json(target, "check", "--parent", V2)["h"]
    assert {s["id"]: s["scheduled"] for s in plan["steps"] if s["id"] in FIVE_AA} == {
        "toast-the-spices": 2.0, "rest-the-dough": 15.0, "sear-the-steak": 4.0, "reduce-the-glaze": 25.0,
        "griddle-the-corn-cakes": 9.0}


# ---------------------------------------------------------------------------
# The write rule
# ---------------------------------------------------------------------------


def test_out_dash_writes_nothing_and_an_existing_path_is_refused(tmp_path, monkeypatch):
    """recipe-authoring › Written only to a file the user asks for: `--out -` prints the
    draft only; an existing `--out` path is refused with exit 1 and the message; the default
    path is `<slug>.recipe.md` in the working folder; the export's bytes are unchanged."""
    before = V2.read_bytes()
    monkeypatch.chdir(tmp_path)
    out = convert(V2, "Tomato Soup", "--out", "-")
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    h = run_json(V2, "convert", "Tomato Soup", "--made-on", MADE_ON, "--out", "-")["h"]
    assert re.fullmatch(r"[0-9a-f]{8}", h) and out.rstrip().endswith(f"Draft only (--out -): nothing written. h={h}")
    written = convert(V2, "Tomato Soup")
    assert run_json(tmp_path / "tomato-soup.recipe.md", "check", "--parent", V2)["h"] == h  # the draft body's hash
    assert (tmp_path / "tomato-soup.recipe.md").is_file() and "Wrote tomato-soup.recipe.md" in written
    refused = convert(V2, "Tomato Soup", expect=1)
    assert refused.strip() == "`tomato-soup.recipe.md` exists; pass --out <other> or edit that file"
    taken = tmp_path / "taken.md"
    taken.write_text("mine\n", encoding="utf-8")
    assert convert(V2, "Toast Soldiers", "--out", taken, expect=1).strip() == \
        f"`{taken}` exists; pass --out <other> or edit that file"
    assert taken.read_text(encoding="utf-8") == "mine\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["taken.md", "tomato-soup.recipe.md"]
    assert V2.read_bytes() == before


def test_out_basename_must_be_a_local_id(tmp_path):
    """recipe-authoring › The local id / Written only to a file the user asks for: `convert …
    --out <path>` refuses an output basename outside ^[a-z][a-z0-9-]*$ before the draft is
    built — the text an envelope error uses for a file so named, exit 1, nothing written —
    so no draft lands under a name `check` would refuse as a file; the refusal precedes the
    existing-path one."""
    for name in ("BAD NAME.md", "Toast_Soldiers.recipe.md", "1-toast.md"):
        target = tmp_path / name
        out = convert(V2, "Toast Soldiers", "--out", target, expect=1)
        assert out.strip() == f"{fe.not_a_local_id(name.split('.')[0])}; pass --out <another name>"
        assert not target.exists()
    taken = tmp_path / "BAD NAME.md"
    taken.write_text("x", encoding="utf-8")
    assert convert(V2, "Toast Soldiers", "--out", taken, expect=1).strip().startswith("`BAD NAME` is not a local id")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["BAD NAME.md"]


def test_out_refuses_a_sibling_that_resolves_to_the_drafts_id(tmp_path, monkeypatch):
    """recipe-authoring › The local id (review finding, 2026-10-14): `convert … --out <path>`,
    and the default `<slug>.recipe.md`, is refused with the library's collision line, exit 1,
    nothing written, when a recipe file in the output folder already resolves to the draft's
    id — `tomato-soup.md` beside the `tomato-soup.recipe.md` the default would write — so no
    file `convert` writes trips the rule `--dsl list` enforces; the refusal follows the
    output-name and existing-path ones and precedes the draft and the gate. A `.md` without
    an envelope is not a recipe file and does not block; another folder is no sibling."""
    monkeypatch.chdir(tmp_path)
    sibling = tmp_path / "tomato-soup.md"
    assert "it passes check" in convert(V2, "Tomato Soup", "--out", sibling)
    line = ("two files share the basename `tomato-soup` (tomato-soup.md, tomato-soup.recipe.md) — rename all but one; "
            "local ids must be unique in a folder; pass --out <another name>")
    assert convert(V2, "Tomato Soup", expect=1).strip() == line  # the default path, named relative to the folder
    assert run_json(V2, "convert", "Tomato Soup", "--made-on", MADE_ON, expect=1) == {"error": line, "code": 1}
    explicit = tmp_path / "tomato-soup.recipe.md"
    assert convert(V2, "Tomato Soup", "--out", explicit, expect=1).strip() == \
        line.replace("(tomato-soup.md, tomato-soup.recipe.md)", f"({sibling}, {explicit})")
    # the output-name and existing-path refusals come first
    assert convert(V2, "Tomato Soup", "--out", tmp_path / "Tomato Soup.md", expect=1).strip().startswith(
        "`Tomato Soup` is not a local id")
    assert convert(V2, "Tomato Soup", "--out", sibling, expect=1).strip() == \
        f"`{sibling}` exists; pass --out <other> or edit that file"
    # a `.md` without an envelope is not a recipe file: no sibling
    (tmp_path / "toast.md").write_text("mine\n", encoding="utf-8")
    assert "Wrote toast.recipe.md" in convert(V2, "Toast Soldiers", "--out", "toast.recipe.md")
    # another folder is no sibling
    sub = tmp_path / "sub"
    sub.mkdir()
    assert "it passes check" in convert(V2, "Tomato Soup", "--out", sub / "tomato-soup.recipe.md")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sub", "toast.md", "toast.recipe.md", "tomato-soup.md"]
    assert "share the basename" not in run_cli(tmp_path, "--dsl", "list")


def test_convert_never_writes_the_export_or_any_other_file(tmp_path):
    """recipe-authoring › Written only … › the export's bytes are unchanged, over a copy of
    the export so the folder listing can be asserted whole."""
    export = tmp_path / "fond-export-test.json"
    export.write_bytes(V2.read_bytes())
    before = export.read_bytes()
    for rid in ("rcp-pasta-02", "rcp-toast-03", "rcp-rice-09"):
        convert(export, rid, "--out", "-")
    convert(export, "rcp-toast-03", "--out", tmp_path / "toast.recipe.md")
    convert(export, "Skillet Steak Supper", "--out", tmp_path / "steak.recipe.md", expect=1)
    assert export.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fond-export-test.json", "toast.recipe.md"]


def test_a_saved_row_without_steps_and_a_markdown_row_have_nothing_to_convert():
    assert "has no steps in this export; nothing to convert." in convert(V2, "Grandma's Stew", "--out", "-", expect=1)
    md = run_cli(FIXTURES / "sample-export-v1.md", "--md", "convert", "Toast Soldiers", "--made-on", MADE_ON,
                 "--out", "-", expect=1)
    assert "carries no Fond id in this Markdown export" in md and "convert from the .json export" in md
