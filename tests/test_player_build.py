"""The player page as the script builds it (recipe-authoring "The player", "Written only to
a file the user asks for"): the payload's shape and `h` on every row, the HTML-safe
embedding, the marker line, the write rule (a new path, its own marked page rebuilt in
place, every other existing path refused, `--out -` byte-equal to the file), the masked
by-line, and the gate before a local file is played.

Run from apps/skill:  ../mcp/.venv/bin/python -m pytest -q tests/test_player_build.py
"""

import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
TEMPLATE = SKILL / "scripts" / "player.template.html"
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
V1 = FIXTURES / "sample-export-v1.json"
MD2 = FIXTURES / "sample-export.md"
MD1 = FIXTURES / "sample-export-v1.md"
LOCAL = FIXTURES / "local"
VARIANT = LOCAL / "sample-variant.md"
ADVERSARIAL = LOCAL / "sample-adversarial.md"
BEFORE = LOCAL / "sample-reconcile-before.md"
AFTER = LOCAL / "sample-reconcile-after.md"

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

MARKER_RE = re.compile(r"^<!-- fond-player built by fond_export\.py h=([0-9a-f]{8}) id=(\S+) -->$")
PAYLOAD_LINE_RE = re.compile(r"^const DATA = (.*);$", re.M)
H_RE = re.compile(r"^[0-9a-f]{8}$")


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out[:2000]}"
    return out


def run_json(*args, expect=0):
    return json.loads(run_cli(*args, "--json", expect=expect))


def page_of(*args):
    """`player --out -`: the page exactly as it would be on disk (the text is printed with one
    final newline, which the page ends with)."""
    return run_cli(*args, "--out", "-")


def payload_of(page: str) -> dict:
    lines = PAYLOAD_LINE_RE.findall(page)
    assert len(lines) == 1, "the payload sits on exactly one `const DATA` line"
    return json.loads(lines[0])


# ---------------------------------------------------------------------------
# The payload
# ---------------------------------------------------------------------------


def test_every_export_row_carries_h_source_and_the_masked_byline():
    """Nodes rows included: no row can ever print `h=undefined`; the profile is masked so
    "you (@ana)" never reaches a page that travels (the fixture's profile handle is `ana`,
    the steak row's author)."""
    payload = payload_of(page_of(V2, "player"))
    assert payload["schema"] == "fond-player/1"
    ids = [r["id"] for r in payload["recipes"]]
    assert ids == ["rcp-steak-01", "rcp-pasta-02", "rcp-toast-03", "rcp-rice-09", "rcp-soup-05"]
    for row in payload["recipes"]:
        assert H_RE.match(row["h"]), row["id"]
        assert row["source"] in ("dsl", "nodes") and row["origin"] is None and row["aliases"] == {}
        assert "you" not in row["byline"] and not any("you (" in line for line in row["provenance_lines"])
        assert row["provenance_lines"][0].startswith(row["title"] + " — " + row["byline"])
        assert row["steps"] and row["wave1"] and isinstance(row["estimate_minutes"], int)
    steak = payload["recipes"][0]
    assert steak["byline"].startswith("by Cara (saved to Fond by @ana)")
    assert steak["credits"] == ["cara", "ben"] and steak["lineage"].startswith("forked from rcp-parent-77")
    assert payload["recipes"][1]["credits"] == [] and payload["recipes"][1]["lineage"] is None


def test_h_matches_plan_for_every_row():
    payload = payload_of(page_of(V2, "player"))
    for row in payload["recipes"]:
        assert row["h"] == run_json(V2, "plan", row["id"])["h"]


def test_phases_are_normalised_per_source():
    """A DSL atom's countdowns are one iteration × count; a legacy timer's countdowns arrive
    already expanded × repeat — the payload carries one shape for both."""
    payload = payload_of(page_of(V2, "player"))
    steak = {s["id"]: s for s in payload["recipes"][0]["steps"]}
    rest = steak["rest-the-dough"]
    assert [p["min"] for p in rest["phases"]] == [5, 10] and rest["segs"] == 2 and rest["iters"] == 1
    assert [(p["iter"], p["seg"], p["segs"], p["iters"]) for p in rest["phases"]] == [(1, 1, 2, 1), (1, 2, 2, 1)]
    flat = steak["cook-the-flatbreads"]
    assert [p["min"] for p in flat["phases"]] == [3, 3] and flat["segs"] == 1 and flat["iters"] == 2
    assert [p["iter"] for p in flat["phases"]] == [1, 2] and flat["surplus"] == 1
    pasta = {s["id"]: s for s in payload["recipes"][1]["steps"]}
    repeat = next(s for s in pasta.values() if s["kind"] == "timer" and s["iters"] > 1)
    assert len(repeat["phases"]) == repeat["iters"] and repeat["segs"] == 1
    assert all(p["segs"] == 1 and p["iters"] == repeat["iters"] for p in repeat["phases"])
    for row in payload["recipes"]:
        for s in row["steps"]:
            if s["kind"] != "timer":
                assert s["phases"] == [] and s["segs"] == 0 and s["iters"] == 1
            else:
                assert len(s["phases"]) == s["segs"] * s["iters"] > 0
                assert s["timing"] and s["rank"] >= 0


def test_a_local_file_row_carries_source_local_origin_aliases_credits_and_changes():
    payload = payload_of(page_of(VARIANT, "--dsl", "player", "--parent", V2))
    (row,) = payload["recipes"]
    assert row["id"] == "local:sample-variant" and row["source"] == "local" and row["origin"] == "variant"
    assert H_RE.match(row["h"]) and row["h"] == run_json(VARIANT, "--dsl", "plan", "--parent", V2)["h"]
    assert row["aliases"] == {"blanch-the-greens": ["blanch-the-rabe"],
                              "sear-the-steak": ["sear-the-first-side", "sear-the-second-side"]}
    assert row["credits"] == ["cara", "ben"]
    assert row["changes"][0] == "copied from the Fond-format steps the export carries" and len(row["changes"]) == 9
    assert row["byline"] == "local variant of Skillet Steak Supper by Cara (saved to Fond by @ana) · local:sample-variant"
    lines = row["provenance_lines"]
    assert lines[0] == "Skillet Steak Supper — " + row["byline"]
    assert any(line.startswith("  Derived from: Fond id rcp-steak-01 (handle skillet-steak-supper-a1b2c3) — by Cara") for line in lines)
    assert "  Credits: @cara, @ben" in lines and "  Changes:" in lines
    assert not any("you" in line.split() for line in lines)
    # The provenance lines are exactly what `show` prints.
    shown = run_cli(VARIANT, "--dsl", "show", "--parent", V2).splitlines()
    assert shown[:len(lines)] == lines


def test_without_parent_the_variant_page_says_not_in_this_export():
    row = payload_of(page_of(VARIANT, "--dsl", "player"))["recipes"][0]
    assert "  Derived from: Fond id rcp-steak-01 (not in this export)" in row["provenance_lines"]  # the spec's form: no handle
    assert row["credits"] == ["cara", "ben"]


def test_a_composed_and_a_variant_row_never_name_a_fond_id_for_their_own_identity():
    for path, args in ((ADVERSARIAL, ()), (BEFORE, ()), (VARIANT, ("--parent", V2))):
        row = payload_of(page_of(path, "--dsl", "player", *args))["recipes"][0]
        own = [line for line in row["provenance_lines"] if not line.lstrip().startswith("Derived from:")]
        assert not any("Fond id" in line for line in own), own
        assert "Fond id" not in row["byline"]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def test_first_line_is_the_marker_and_the_payload_is_one_line():
    page = page_of(V2, "player", "Weeknight Garlic Pasta")
    first = page.split("\n", 1)[0]
    m = MARKER_RE.match(first)
    assert m and m.group(2) == "rcp-pasta-02" and m.group(1) == run_json(V2, "plan", "rcp-pasta-02")["h"]
    assert page.count("<script") == 1 and page.count("</script>") == 1
    whole = page_of(V2, "player")
    m = MARKER_RE.match(whole.split("\n", 1)[0])
    assert m and m.group(2) == "export:" + fe.load_export(V2).exported_at == "export:2026-10-08T12:00:00+00:00"
    assert len(payload_of(whole)["recipes"]) == 5


def test_the_page_is_the_template_with_the_two_placeholders_filled():
    template = TEMPLATE.read_text(encoding="utf-8")
    page = page_of(V2, "player", "Toast Soldiers")
    t_rest = template.split("\n", 1)[1]
    p_rest = page.split("\n", 1)[1]
    before, after = t_rest.split("__FOND_PAYLOAD__")
    assert p_rest.startswith(before) and p_rest.endswith(after)
    assert "__FOND" not in page


def test_adversarial_strings_are_escaped_and_the_payload_element_is_intact():
    """A title, step text, URL and author label carrying `</script><script>fetch(` and `-->`
    reach the page only as \\u003c/\\u003e escapes; the element has one opener and its
    closing tag only where the template puts it."""
    template = TEMPLATE.read_text(encoding="utf-8")
    page = page_of(ADVERSARIAL, "--dsl", "player")
    assert page.count("<script") == template.count("<script") == 1
    assert page.count("</script>") == template.count("</script>") == 1
    assert page.count("-->") == template.count("-->")
    assert "</script><script>" not in page and "<script>fetch(" not in page
    assert "\\u003c/script\\u003e\\u003cscript\\u003efetch( --\\u003e" in page
    row = payload_of(page)["recipes"][0]
    bad = "</script><script>fetch( -->"
    assert bad in row["title"] and bad in row["steps"][0]["text"] and "</script><script>fetch(" in row["url"]
    assert any(bad in line for line in row["provenance_lines"] if line.startswith("  Attribution:"))
    # & and the two line separators are escaped too, so the JSON can never end the string.
    assert fe.html_safe_json({"a": "<&>\u2028\u2029"}) == '{"a":"\\u003c\\u0026\\u003e\\u2028\\u2029"}'
    assert json.loads(fe.html_safe_json({"a": "<&>\u2028\u2029"})) == {"a": "<&>\u2028\u2029"}


# ---------------------------------------------------------------------------
# The write rule
# ---------------------------------------------------------------------------


def test_default_path_is_beside_the_export_or_the_file(tmp_path):
    export = tmp_path / "fond-export-test.json"
    shutil.copy(V2, export)
    out = run_cli(export, "player", "Tomato Soup")
    assert (tmp_path / "tomato-soup.player.html").is_file() and "Wrote" in out
    run_cli(export, "player")
    assert (tmp_path / "fond-player.html").is_file()
    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copy(VARIANT, lib / "steak-tonight.md")
    run_cli(lib / "steak-tonight.md", "--dsl", "player", "--parent", V2)
    assert (lib / "steak-tonight.player.html").is_file()
    shutil.copy(ADVERSARIAL, lib / "pancakes.md")
    run_cli(lib, "--dsl", "player", "--parent", V2)
    page = (lib / "fond-player.html").read_text(encoding="utf-8")
    assert [r["id"] for r in payload_of(page)["recipes"]] == ["local:pancakes", "local:steak-tonight"]
    run_cli(lib, "--dsl", "player", "Skillet Steak Supper", "--parent", V2, "--out", lib / "one.player.html")
    assert MARKER_RE.match((lib / "one.player.html").read_text(encoding="utf-8").split("\n", 1)[0]).group(2) == "local:steak-tonight"


def test_stdout_is_byte_equal_to_the_file(tmp_path):
    target = tmp_path / "steak.player.html"
    run_cli(V2, "player", "Skillet Steak Supper", "--out", target)
    assert page_of(V2, "player", "Skillet Steak Supper") == target.read_text(encoding="utf-8")


def test_rebuilds_only_its_own_marked_page(tmp_path):
    target = tmp_path / "steak.player.html"
    run_cli(V2, "player", "Skillet Steak Supper", "--out", target)
    first = target.read_text(encoding="utf-8")
    run_cli(V2, "player", "Skillet Steak Supper", "--out", target)  # its own page: rebuilt in place
    assert target.read_text(encoding="utf-8") == first
    other = tmp_path / "notes.html"
    other.write_text("<!doctype html>\n<p>mine</p>\n", encoding="utf-8")
    out = run_cli(V2, "player", "Skillet Steak Supper", "--out", other, expect=1)
    assert f"`{other}` exists; pass --out <other> or edit that file" in out
    assert other.read_text(encoding="utf-8") == "<!doctype html>\n<p>mine</p>\n"
    recipe = tmp_path / "dal.recipe.md"
    recipe.write_text(VARIANT.read_text(encoding="utf-8"), encoding="utf-8")
    run_cli(V2, "player", "Skillet Steak Supper", "--out", recipe, expect=1)
    assert recipe.read_text(encoding="utf-8") == VARIANT.read_text(encoding="utf-8")


def test_a_marked_page_for_another_id_is_never_replaced(tmp_path):
    """recipe-authoring › Written only … › the player rebuilds in place only its OWN page —
    the marker's `id=` is the identity: the same id under another `h=` rebuilds; another
    recipe's page, the whole-export page (id `export:<exportedAt>`) against a recipe's and
    the reverse are refused with one line naming both ids and the path, the file untouched;
    a file that does not open with the marker is refused as before."""
    whole_id = MARKER_RE.match(page_of(V2, "player").split("\n", 1)[0]).group(2)
    target = tmp_path / "dinner.player.html"
    run_cli(V2, "player", "Tomato Soup", "--out", target)
    soup = target.read_text(encoding="utf-8")
    soup_id = MARKER_RE.match(soup.split("\n", 1)[0]).group(2)
    stale = re.sub(r"h=[0-9a-f]{8}", "h=00000000", soup, count=1)  # the same id, an older h=
    target.write_text(stale, encoding="utf-8")
    out = run_cli(V2, "player", "Tomato Soup", "--out", target)
    assert "rebuilt in place" in out and target.read_text(encoding="utf-8") == soup
    toast_id = MARKER_RE.match(page_of(V2, "player", "Toast Soldiers").split("\n", 1)[0]).group(2)
    assert toast_id != soup_id
    out = run_cli(V2, "player", "Toast Soldiers", "--out", target, expect=1)
    assert out.strip() == f"`{target}` is the player page for {soup_id}, not {toast_id}; pass --out <another path>"
    assert target.read_text(encoding="utf-8") == soup
    out = run_cli(V2, "player", "--out", target, expect=1)  # the whole-export page against a recipe's
    assert out.strip() == f"`{target}` is the player page for {soup_id}, not {whole_id}; pass --out <another path>"
    assert target.read_text(encoding="utf-8") == soup
    whole = tmp_path / "fond-player.html"
    run_cli(V2, "player", "--out", whole)
    whole_text = whole.read_text(encoding="utf-8")
    out = run_cli(V2, "player", "Tomato Soup", "--out", whole, expect=1)  # and the reverse
    assert out.strip() == f"`{whole}` is the player page for {whole_id}, not {soup_id}; pass --out <another path>"
    assert whole.read_text(encoding="utf-8") == whole_text
    run_cli(V2, "player", "--out", whole)  # its own page: rebuilt in place
    assert whole.read_text(encoding="utf-8") == whole_text
    other = tmp_path / "notes.html"
    other.write_text("<!-- fond-player built by someone else -->\n<p>mine</p>\n", encoding="utf-8")
    out = run_cli(V2, "player", "Tomato Soup", "--out", other, expect=1)
    assert out.strip() == f"`{other}` exists; pass --out <other> or edit that file"
    assert other.read_text(encoding="utf-8") == "<!-- fond-player built by someone else -->\n<p>mine</p>\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dinner.player.html", "fond-player.html", "notes.html"]


def test_a_collection_page_belongs_to_one_export_or_folder(tmp_path):
    """recipe-authoring › Written only … › own page only, for a multi-recipe page too: its
    marker id is the collection's, never a literal shared by every export — `export:
    <exportedAt>` for a whole export, `library:<8hex>` (SHA-256 over the sorted local ids)
    for a folder — so export A's page at a path is never replaced by export B's, nor by a
    folder's, nor the reverse (refused naming both ids, the file untouched); the same export
    rebuilds in place under any `h=`, the same folder too; a recipe's page keeps the
    recipe id whatever the header says."""
    target = tmp_path / "dinner.player.html"
    run_cli(V2, "player", "--out", target)
    page_a = target.read_text(encoding="utf-8")
    id_a = MARKER_RE.match(page_a.split("\n", 1)[0]).group(2)
    assert id_a == "export:2026-10-08T12:00:00+00:00"
    # export B: the same rows under another header timestamp — another collection
    data = json.loads(V2.read_text(encoding="utf-8"))
    data["exportedAt"] = "2026-10-15T08:30:00+00:00"
    export_b = tmp_path / "fond-export-later.json"
    export_b.write_text(json.dumps(data), encoding="utf-8")
    id_b = MARKER_RE.match(page_of(export_b, "player").split("\n", 1)[0]).group(2)
    assert id_b == "export:2026-10-15T08:30:00+00:00"
    out = run_cli(export_b, "player", "--out", target, expect=1)
    assert out.strip() == f"`{target}` is the player page for {id_a}, not {id_b}; pass --out <another path>"
    assert target.read_text(encoding="utf-8") == page_a
    # the same export rebuilt in place, under any h=; the Wrote line names the collection
    target.write_text(re.sub(r"h=[0-9a-f]{8}", "h=00000000", page_a, count=1), encoding="utf-8")
    out = run_cli(V2, "player", "--out", target)
    assert "rebuilt in place" in out and f"5 recipes ({id_a})" in out and target.read_text(encoding="utf-8") == page_a
    # a folder's page: library:<hash of its sorted local ids>, refused against an export's page and the reverse
    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copy(VARIANT, lib / "steak-tonight.md")
    shutil.copy(ADVERSARIAL, lib / "pancakes.md")
    run_cli(lib, "--dsl", "player", "--parent", V2)
    lib_page = (lib / "fond-player.html").read_text(encoding="utf-8")
    lib_id = MARKER_RE.match(lib_page.split("\n", 1)[0]).group(2)
    assert lib_id == "library:" + fe.body_hash("local:pancakes\nlocal:steak-tonight")
    out = run_cli(lib, "--dsl", "player", "--parent", V2, "--out", target, expect=1)
    assert out.strip() == f"`{target}` is the player page for {id_a}, not {lib_id}; pass --out <another path>"
    assert target.read_text(encoding="utf-8") == page_a
    out = run_cli(V2, "player", "--out", lib / "fond-player.html", expect=1)
    assert out.strip() == f"`{lib / 'fond-player.html'}` is the player page for {lib_id}, not {id_a}; pass --out <another path>"
    assert (lib / "fond-player.html").read_text(encoding="utf-8") == lib_page
    run_cli(lib, "--dsl", "player", "--parent", V2)  # the same folder: its own page, rebuilt in place
    assert (lib / "fond-player.html").read_text(encoding="utf-8") == lib_page
    # a recipe's page keeps the recipe id — in either export, and in the folder
    for src in (V2, export_b):
        assert MARKER_RE.match(page_of(src, "player", "Weeknight Garlic Pasta").split("\n", 1)[0]).group(2) == "rcp-pasta-02"
    one = MARKER_RE.match(page_of(lib / "steak-tonight.md", "--dsl", "player", "--parent", V2).split("\n", 1)[0])
    assert one.group(2) == "local:steak-tonight"


def test_the_export_is_byte_identical_after_player(tmp_path):
    export = tmp_path / "fond-export-test.json"
    shutil.copy(V2, export)
    before = export.read_bytes()
    run_cli(export, "player")
    run_cli(export, "player", "Tomato Soup")
    assert export.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fond-export-test.json", "fond-player.html", "tomato-soup.player.html"]


def test_stdin_needs_out(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(ADVERSARIAL.read_text(encoding="utf-8")))
    out = run_cli("-", "--dsl", "player", expect=2)
    assert "needs --out" in out
    monkeypatch.setattr(sys, "stdin", io.StringIO(ADVERSARIAL.read_text(encoding="utf-8")))
    page = page_of("-", "--dsl", "player")
    assert payload_of(page)["recipes"][0]["id"] == "local:pancake-script-script-fetch-stack"


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_a_local_file_with_findings_is_not_played(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text(BEFORE.read_text(encoding="utf-8").replace("~sear{2%min × 2}, flipping once", "2 minutes a side"),
                   encoding="utf-8")
    out = run_cli(bad, "--dsl", "player", expect=1)
    assert "nothing with findings is cooked" in out and "[T]" in out
    assert not (tmp_path / "bad.player.html").exists()


def test_a_markdown_row_without_a_fond_id_is_skipped_and_named():
    out = run_cli(MD1, "--md", "player", expect=1)
    assert "nothing to play" in out and "carries no Fond id in this Markdown export" in out
    payload = payload_of(page_of(MD2, "--md", "player"))
    assert payload["recipes"] and all(H_RE.match(r["h"]) for r in payload["recipes"])
    assert all(r["source"] in ("dsl", "md-steps", "md-list") for r in payload["recipes"])
    assert any(r["source"] == "md-steps" for r in payload["recipes"])


def test_a_recipe_without_steps_is_refused():
    out = run_cli(V2, "player", "Grandma's Stew", expect=1)
    assert "has no steps in this export" in out


def test_player_over_an_export_runs_without_the_vendored_lint(monkeypatch):
    """`<export> player` lints nothing, so it keeps Python 3.8 with the v0.1 commands."""
    monkeypatch.setattr(fe, "_import_fond_dsl", lambda: (_ for _ in ()).throw(AssertionError("lint imported")))
    assert payload_of(page_of(V2, "player"))["recipes"]


@pytest.mark.parametrize("path", [BEFORE, AFTER, ADVERSARIAL])
def test_each_local_fixture_builds_a_page(path):
    row = payload_of(page_of(path, "--dsl", "player"))["recipes"][0]
    assert row["source"] == "local" and row["origin"] == "composed" and H_RE.match(row["h"])
