"""The player's ENGINE block against the script (recipe-authoring "The player": "engine
parity with plan", the FOND1 round trip, reconcile-by-slug, the paste sheet's reader).

This driver builds the fixture payloads with the script (`player --out -` over both export
fixtures, the variant file and the reconcile pair), generates random valid cook states and
what `plan --json` says about each, runs node over the ENGINE block sliced from
scripts/player.template.html (tests/engine/*.mjs), and feeds every FOND1 replay tail the
engine emitted back to the real `plan … --done … --running … --h …`.

CI story (cook-with-fond-authoring decision 8): node is required in both CIs. Without
`node` on PATH these tests skip with "node not found" — unless FOND_REQUIRE_NODE=1, which
turns the skip into a failure; both workflows set it.

Run from apps/skill:  FOND_REQUIRE_NODE=1 ../mcp/.venv/bin/python -m pytest -q tests/test_player_engine.py
"""

import contextlib
import importlib.util
import io
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ENGINE_DIR = HERE / "engine"
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
TEMPLATE = SKILL / "scripts" / "player.template.html"
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
V1 = FIXTURES / "sample-export-v1.json"
LOCAL = FIXTURES / "local"
VARIANT = LOCAL / "sample-variant.md"
BEFORE = LOCAL / "sample-reconcile-before.md"
AFTER = LOCAL / "sample-reconcile-after.md"

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

sys.path.insert(0, str(HERE))
from test_no_leak import FOND1_RE  # noqa: E402  (the one grammar, kept by the no-leak check)

PAYLOAD_LINE_RE = re.compile(r"^const DATA = (.*);$", re.M)
CASES_PER_RECIPE = 400
ROUNDTRIP_RUNS = 150


# ---------------------------------------------------------------------------
# node: skip, or fail under FOND_REQUIRE_NODE=1
# ---------------------------------------------------------------------------


def node_status(which, env):
    """("run", path) when node is on PATH; otherwise ("fail", reason) under
    FOND_REQUIRE_NODE=1 and ("skip", reason) without it."""
    if which:
        return "run", which
    reason = "node not found on PATH (the player engine tests need node; set FOND_REQUIRE_NODE=1 to make this a failure)"
    if env.get("FOND_REQUIRE_NODE") == "1":
        return "fail", "node not found on PATH and FOND_REQUIRE_NODE=1: the player engine tests must run"
    return "skip", reason


def node_or_skip() -> str:
    status, detail = node_status(shutil.which("node"), os.environ)
    if status == "fail":
        pytest.fail(detail)
    if status == "skip":
        pytest.skip(detail)
    return detail


def test_node_status_skips_without_node_and_fails_under_the_variable():
    assert node_status("/usr/bin/node", {"FOND_REQUIRE_NODE": "1"}) == ("run", "/usr/bin/node")
    assert node_status(None, {})[0] == "skip" and "node not found" in node_status(None, {})[1]
    assert node_status(None, {"FOND_REQUIRE_NODE": "1"})[0] == "fail"
    assert node_status(None, {"FOND_REQUIRE_NODE": "0"})[0] == "skip"


def run_node(script: str, *args) -> str:
    node = node_or_skip()
    proc = subprocess.run([node, str(ENGINE_DIR / script), str(TEMPLATE)] + [str(a) for a in args],
                          capture_output=True, text=True, cwd=str(HERE))
    assert proc.returncode == 0, f"{script} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


# ---------------------------------------------------------------------------
# Payloads and cases, from the script
# ---------------------------------------------------------------------------


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out[:2000]}"
    return out


def payload_from(*args) -> dict:
    """The payload the built page carries: `player --out -`, the `const DATA` line parsed."""
    page = run_cli(*args, "--out", "-")
    lines = PAYLOAD_LINE_RE.findall(page)
    assert len(lines) == 1
    return json.loads(lines[0])


def random_cases(export, rids, n_per: int, seed: int):
    """Random valid cook states over each recipe and what `plan --json` says about each."""
    rng = random.Random(seed)
    cases = []
    for rid in rids:
        recipe = fe.find_recipe(export, rid)
        graph = fe.build_graph(export.content_of(recipe))
        for _ in range(n_per):
            done, running = [], {}
            for _move in range(rng.randint(0, len(graph.steps) * 2)):
                avail = [s for s in graph.steps if s.id not in done and s.id not in running and all(d in done for d in s.deps)]
                choices = []
                if avail:
                    choices += ["resolve", "start"]
                if running:
                    choices.append("finish")
                if not choices:
                    break
                move = rng.choice(choices)
                if move == "resolve":
                    done.append(rng.choice(avail).id)
                elif move == "start":
                    s = rng.choice(avail)
                    running[s.id] = rng.randint(0, int(max(1, s.scheduled)) + 2)
                else:
                    sid = rng.choice(list(running))
                    del running[sid]
                    done.append(sid)
            out = fe.cmd_plan(export, rid, ",".join(done) or None, ",".join(f"{k}={v}" for k, v in running.items()) or None, True)
            cases.append({"rid": rid, "done": done, "running": list(running.items()),
                          "expect": {k: out[k] for k in ("available", "held", "held_by", "locked", "estimate_minutes", "estimate_exact")}})
    return cases


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Every payload the node tests read, written once: the two exports, the variant (with
    its parent), the reconcile pair."""
    folder = tmp_path_factory.mktemp("player-engine")
    exports = {
        "v2": (fe.load_export(V2), payload_from(V2, "player")),
        "v1": (fe.load_export(V1), payload_from(V1, "player")),
        "variant": (fe.load_library(VARIANT, fe.load_export(V2)), payload_from(VARIANT, "--dsl", "player", "--parent", V2)),
    }
    paths = {}
    for name, (_export, payload) in exports.items():
        paths[name] = folder / f"{name}.json"
        paths[name].write_text(json.dumps(payload), encoding="utf-8")
    for name, path in (("before", BEFORE), ("after", AFTER)):
        paths[name] = folder / f"{name}.json"
        paths[name].write_text(json.dumps(payload_from(path, "--dsl", "player")), encoding="utf-8")
    return {"folder": folder, "exports": exports, "paths": paths}


# ---------------------------------------------------------------------------
# The five node runs
# ---------------------------------------------------------------------------


def test_engine_parity_with_plan_over_random_states(built):
    """derive/simulate against `plan --json` over ≥ 2,000 random states, 0 disagreements,
    plus the hand-worked minutesLeft, tap and fmtMinutes cases (parity.mjs)."""
    total = 0
    for name, (export, payload) in built["exports"].items():
        rids = [r["id"] for r in payload["recipes"]]
        cases = random_cases(export, rids, CASES_PER_RECIPE, seed=20261013 + len(name))
        cases_path = built["folder"] / f"cases-{name}.json"
        cases_path.write_text(json.dumps(cases), encoding="utf-8")
        out = run_node("parity.mjs", built["paths"][name], cases_path)
        m = re.search(r"derive/simulate parity: (\d+)/(\d+) cases match", out)
        assert m and m.group(1) == m.group(2) == str(len(cases)), out
        total += len(cases)
    assert total >= 2000


def test_fond1_round_trip_and_replay_through_plan(built):
    """Random cooks: every FOND1 line the engine emits matches the grammar, carries h=,
    parses back to the same cook (roundtrip.mjs), and its replay tail — with its h — is
    accepted by the real `plan` with the same available/held/locked sets and estimate. The
    cooks start between 17:30 and 23:30, so some ends fall past midnight and carry the
    grammar's `+<days>d`: the day offset round-trips under the random cooks too."""
    accepted = 0
    day_offsets = 0
    for name, (export, payload) in built["exports"].items():
        out_path = built["folder"] / f"rt-{name}.json"
        out = run_node("roundtrip.mjs", built["paths"][name], out_path, ROUNDTRIP_RUNS)
        m = re.search(r"FOND1 round trip: (\d+)/(\d+) snapshots parse back", out)
        assert m and m.group(1) == m.group(2) and int(m.group(2)) > 0, out
        d = re.search(r"; (\d+) carry a day offset", out)
        assert d, out
        day_offsets += int(d.group(1))
        for case in json.loads(out_path.read_text(encoding="utf-8")):
            assert FOND1_RE.fullmatch(case["line"]), case["line"]
            args = shlex.split(case["replay"])
            done = args[args.index("--done") + 1] if "--done" in args else None
            running = args[args.index("--running") + 1] if "--running" in args else None
            plan = fe.cmd_plan(export, case["rid"], done, running, True, h_arg=case["h"])
            got = {k: plan[k] for k in ("available", "held", "locked", "estimate_minutes")}
            assert got == case["expect"], (case["line"], got, case["expect"])
            accepted += 1
    assert accepted >= 200
    assert day_offsets >= 1, "no random cook crossed midnight: the +<days>d end never round-tripped"


def test_reconcile_by_slug_cases(built):
    """The ten original cases, the seven gaps A–G and the alias chains H–J — `rename a -> b`
    then `rename b -> c`, rename then split, a chain that ends in a vanished slug (dropped
    and named once) — over payloads the script built (reconcile.mjs)."""
    out = run_node("reconcile.mjs", built["paths"]["before"], built["paths"]["after"], built["paths"]["variant"], built["paths"]["v2"])
    assert "all reconcile cases pass" in out, out
    assert "FAIL" not in out


def test_parse_line_cases(built):
    """h= matching, stale and absent lines, the retired :o@ form, n/s/started0, the 18-hour
    timer, the DST hour, the day offset — a 36-hour phase one hour in round-trips to 2,100
    minutes left (`@05:00+2d`), a countdown past midnight to `+1d`, the bare form of the same
    line reads the same — garbage and duplicate inputs, and a malformed stamp (`h=garbage`,
    seven or nine digits, upper case, empty) refusing the whole line by name rather than
    reading as an unstamped earlier line, the head matched as a whole, and wrapper punctuation
    around a paste (quotes, bold, brackets, `>`, a full stop, inline code in a sentence) read
    through with a bad stamp inside it still refused by name (parse_line.mjs)."""
    out = run_node("parse_line.mjs", built["paths"]["v2"], built["paths"]["variant"])
    assert "all parse_line cases pass" in out, out
    assert "FAIL" not in out


def test_paste_sheet_confirmation_cases(built):
    """The paste sheet's confirmation (recipe-authoring › The player: a paste sheet "that
    warns before a pasted line would undo or stop progress"): the warning names what the
    line takes back, the NEXT Apply applies it with no wait between the two presses, an edit
    re-arms it, and a line that keeps or adds progress applies at once (paste_confirm.mjs)."""
    out = run_node("paste_confirm.mjs", built["paths"]["v2"])
    assert "all paste_confirm cases pass" in out, out
    assert "FAIL" not in out


def test_a_stale_h_is_refused_by_plan_too(built):
    export, payload = built["exports"]["variant"]
    rid = payload["recipes"][0]["id"]
    with pytest.raises(fe.ExportError) as e:
        fe.cmd_plan(export, rid, None, None, True, h_arg="00000000")
    assert "that line is for h=00000000; the recipe is now h=" in str(e.value)
