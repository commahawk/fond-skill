"""The envelope, the presentation lines, `h` and the player over the shipped local fixtures
(recipe-authoring "The envelope and its keys per origin", "The local id; no Fond id, handle
or lineage is minted", "Composed", "Variant", "Transcribed", "Library reading via `--dsl`",
"The FOND1 line carries `h=`", "The player"; cook-with-fond-authoring 6.5).

The envelope round-trips field for field with every scalar a string; the never-list is
grepped over every command's output for the three origins, with and without `--parent`,
and with the export's `profile.handle` equal to the parent's `authorHandle` — scoped
exactly as the spec scopes it; the variant line leads with the parent's by-line head; the
credits chain keeps its recorded order; the composed and transcribed lines read the same
on `list`, `show` and the player's mise screen; `strip`, `scale` and the read commands'
gate; `h` and the stale line; the Option B yes-path over the zero-sigil row; the built
page. No network, no environment, synthetic fixtures only.

Run from apps/skill:  ../mcp/.venv/bin/python -m pytest -q tests/test_variant.py
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
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
LOCAL = FIXTURES / "local"
VARIANT = LOCAL / "sample-variant.md"
COMPOSED = LOCAL / "sample-composed.md"
TRANSCRIBED = LOCAL / "sample-transcribed.md"
CLEAN_DSL = LOCAL / "sample-clean-dsl.md"
ADVERSARIAL = LOCAL / "sample-adversarial.md"
MADE_ON = "2026-10-13"
PAYLOAD_LINE_RE = re.compile(r"^const DATA = (.*);$", re.M)
MARKER_RE = re.compile(r"^<!-- fond-player built by fond_export\.py h=([0-9a-f]{8}) id=(\S+) -->$")
H_RE = re.compile(r"^[0-9a-f]{8}$")

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

THREE = [VARIANT, COMPOSED, TRANSCRIBED]
VARIANT_LINE = "Skillet Steak Supper — local variant of Skillet Steak Supper by Cara (saved to Fond by @ana) · local:sample-variant"
COMPOSED_LINE = "Weeknight Dal — composed by the assistant · from blog.example, credited to Ana · local:sample-composed"
TRANSCRIBED_LINE = "Nonna's Ragù — transcribed by the assistant from Nonna's card · local:sample-transcribed"
DERIVED_WITH_PARENT = ("  Derived from: Fond id rcp-steak-01 (handle skillet-steak-supper-a1b2c3) — by Cara (saved to Fond by @ana) "
                       "· from blog.example · Fond handle skillet-steak-supper-a1b2c3")
DERIVED_WITHOUT_PARENT = "  Derived from: Fond id rcp-steak-01 (not in this export)"  # the spec's exact form: no handle


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out[:3000]}"
    return out


def run_json(*args, expect=0):
    return json.loads(run_cli(*args, "--json", expect=expect))


def payload_of(*args) -> dict:
    page = run_cli(*args, "--out", "-")
    lines = PAYLOAD_LINE_RE.findall(page)
    assert len(lines) == 1
    return json.loads(lines[0])


def provenance_lines(out: str):
    """The block `show`/`plan` open with: the head line down to the first blank line, without
    the gate's note and warning lines `show` and `plan` print after it (the payload carries
    the provenance lines alone)."""
    return [ln for ln in out.split("\n\n", 1)[0].splitlines() if not ln.startswith(("  note", "  warning:"))]


def parent_args(path):
    return ("--parent", V2) if fe.load_library_file(path).origin == "variant" else ()


# ---------------------------------------------------------------------------
# The envelope round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", THREE + [CLEAN_DSL], ids=lambda p: p.stem)
def test_envelope_round_trip_is_field_equal_and_every_scalar_a_string(path, tmp_path):
    """recipe-authoring › The envelope …: load → re-serialise → load is field-equal for every
    origin; every scalar is read back as a string (`made_on`, `exported_at`, `yield`,
    `parent_id` — the reference reader would int-ify a digit-only value; this one never does)."""
    text = path.read_text(encoding="utf-8")
    fm, body = fe.split_envelope(text)
    env, errors, warnings = fe.parse_envelope(fm)
    assert errors == [] and warnings == []
    assert set(env) <= set(fe.ENVELOPE_FIELDS) and set(env["lineage"]) <= set(fe.LINEAGE_FIELDS)
    rendered = fe.render_envelope(env)
    again, errors2, warnings2 = fe.parse_envelope(fe.split_envelope(rendered + body)[0])
    assert again == env and errors2 == [] and warnings2 == []

    def leaves(value):
        if isinstance(value, dict):
            for v in value.values():
                yield from leaves(v)
        elif isinstance(value, list):
            for v in value:
                yield from leaves(v)
        else:
            yield value
    assert all(isinstance(v, str) for v in leaves(env))
    # The re-serialised file is the same recipe: id, title, origin, url and h.
    copy = tmp_path / path.name
    copy.write_text(rendered + body, encoding="utf-8")
    a, b = fe.load_library_file(path), fe.load_library_file(copy)
    assert (a.title, a.origin, a.url, fe.recipe_h(a)) == (b.title, b.origin, b.url, fe.recipe_h(b))
    assert fe.parse_envelope("lineage:\n  parent_id: 12345678\n  made_on: 2026-10-13\n")[0]["lineage"] == \
        {"parent_id": "12345678", "made_on": "2026-10-13"}


# ---------------------------------------------------------------------------
# The never-list, scoped to a local file's own identity
# ---------------------------------------------------------------------------

NEVER = ("by you", "your recipe", "Fond recipe", "registered", "published", "verified", "original", "adapted", "None")
FORK_RE = re.compile(r"\bfork(ed|s)?\b|\bfork point\b", re.IGNORECASE)
YOU_RE = re.compile(r"\byou\b")


def is_head(line: str) -> bool:
    """The `list`/head line of a variant, or the payload's `byline` (the same text after the title)."""
    return " — local variant of " in line or line.startswith("local variant of ")


def assert_own_identity_clean(lines, where, you_lines=None):
    """"Fond id"/"Fond handle" only on the `Derived from:` line naming the parent; "fork"
    only inside the echoed `Lineage (parent):` line; "saved to Fond" only inside the parent
    by-line head of `Derived from:` and the `list`/head line; the rest nowhere — over every
    line; "you" never as a word on a provenance line, a by-line or in a payload (`you_lines`,
    the provenance block; cook-playback's own step wording — "does not occupy you" — is
    about the step, not the file)."""
    for line in (lines if you_lines is None else you_lines):
        assert not YOU_RE.search(line), f"{where}: {line!r}"
    for line in lines:
        body = line.strip()
        derived = body.startswith("Derived from:")
        echo = body.startswith("Lineage (parent):")
        head = is_head(line)
        for word in NEVER:
            assert word not in line, f"{where}: {word!r} on {line!r}"
        if not derived:
            assert "Fond id" not in line and "Fond handle" not in line, f"{where}: {line!r}"
        if not echo:
            assert not FORK_RE.search(line), f"{where}: {line!r}"
        if not (derived or head):
            assert "saved to Fond" not in line, f"{where}: {line!r}"


def every_presentation(path, with_parent):
    """label → (every line of the command's output, its provenance lines) over `path` —
    list, show, plan, scale, check, the player payload — with or without `--parent`."""
    extra = ("--parent", V2) if with_parent else ()
    origin = fe.load_library_file(path).origin
    out = {}
    listing = run_cli(LOCAL, "--dsl", "list", *extra)
    rows = [ln for ln in listing.splitlines() if f"local:{path.stem}" in ln]
    assert len(rows) == 1
    out["list"] = (rows, rows)
    show = run_cli(path, "--dsl", "show", *extra)
    out["show"] = (show.splitlines(), provenance_lines(show))
    plan = run_cli(path, "--dsl", "plan", *extra)
    out["plan"] = (plan.splitlines(), provenance_lines(plan))
    scale = run_cli(path, "--dsl", "scale", "--factor", "2", *extra)
    out["scale"] = (scale.splitlines(), scale.splitlines()[:1])
    if origin != "variant" or with_parent:
        check = run_cli(path, "check", *extra)
        out["check"] = (check.splitlines(), check.split("Plays as:", 1)[0].splitlines())
    row = payload_of(path, "--dsl", "player", *extra)["recipes"][0]
    page = [row["byline"]] + row["provenance_lines"]
    out["player"] = (page, page)
    return out


@pytest.mark.parametrize("with_parent", [False, True], ids=["without-parent", "with-parent"])
@pytest.mark.parametrize("path", THREE, ids=lambda p: p.stem)
def test_the_never_list_over_every_command(path, with_parent):
    """recipe-authoring › The local id …: the grep over every command's output for the three
    origins, with and without `--parent`, the export's `profile.handle` ("ana") equal to the
    parent's `authorHandle` — the user's handle appears only as that `authorHandle`
    (`@ana` inside the parent by-line head), never as "you"."""
    export = fe.load_export(V2)
    assert export.profile_handle == "ana" == fe.find_recipe(export, "rcp-steak-01").author_handle
    for label, (lines, you_lines) in every_presentation(path, with_parent).items():
        assert_own_identity_clean(lines, f"{path.stem} {label}", you_lines)
        for line in lines:
            if "@ana" in line:
                assert path is VARIANT and (line.strip().startswith("Derived from:") or is_head(line)), line
    text = path.read_text(encoding="utf-8")
    assert not YOU_RE.search(text) and "Fond id" not in text and not FORK_RE.search(text.split("parent_lineage:", 1)[-1][:0])
    if path is VARIANT:
        assert text.count("ana") == 1 and 'author: "@ana"' in text  # exactly where the row's authorHandle goes


def test_the_unmasked_byline_would_say_you_and_the_variant_never_does():
    """`byline()` prints "you (@ana)" beside a matching `profile.handle` (the export's own
    presentation); the variant's lines are built as after `strip`, so the head reads "@ana"."""
    export = fe.load_export(V2)
    steak = fe.find_recipe(export, "rcp-steak-01")
    assert fe.byline(steak, export).startswith("by Cara (saved to Fond by you (@ana))")
    assert fe.byline(steak, fe.masked_view(export)).startswith("by Cara (saved to Fond by @ana)")
    assert run_cli(V2, "list").count("by you (@ana)") >= 1  # the export's own listing keeps the form
    for extra in ((), ("--parent", V2)):
        assert "you" not in run_cli(VARIANT, "--dsl", "show", *extra).split("\n\n", 1)[0]


# ---------------------------------------------------------------------------
# The variant line and the provenance lines of 3.2
# ---------------------------------------------------------------------------


def test_the_variant_line_leads_with_the_parents_byline_head_on_list_show_and_plan():
    """recipe-authoring › Variant: `<Title> — local variant of <parent title> <parent by-line
    head> · local:<slug>`, the head exactly as `byline()` prints it for the row — the
    `sourceAuthor` leading, never dropped — identical on `list`, `show`, `plan`, `scale` and
    the player; without `--parent` the parent is named by its id."""
    listing = run_cli(LOCAL, "--dsl", "list", "--parent", V2)
    assert "  - " + VARIANT_LINE in listing.splitlines()
    assert run_cli(VARIANT, "--dsl", "show", "--parent", V2).splitlines()[0] == VARIANT_LINE
    assert run_cli(VARIANT, "--dsl", "plan", "--parent", V2).splitlines()[0] == VARIANT_LINE
    assert run_cli(VARIANT, "--dsl", "scale", "--factor", "2", "--parent", V2).splitlines()[0].startswith(VARIANT_LINE + " — ×2 variant")
    row = payload_of(VARIANT, "--dsl", "player", "--parent", V2)["recipes"][0]
    assert row["provenance_lines"][0] == VARIANT_LINE and row["byline"] == VARIANT_LINE.split(" — ", 1)[1]
    without = VARIANT_LINE.replace("local variant of Skillet Steak Supper by Cara", "local variant of rcp-steak-01 by Cara")
    assert run_cli(VARIANT, "--dsl", "show").splitlines()[0] == without
    assert "  - " + without in run_cli(LOCAL, "--dsl", "list").splitlines()
    # A null-lineage parent: the head is the bare handle form, and the line never says "(unknown)" for a known author.
    clean = run_cli(CLEAN_DSL, "--dsl", "show", "--parent", V2).splitlines()[0]
    assert clean == "Steamed Coconut Rice — local variant of Steamed Coconut Rice by @ana · local:sample-clean-dsl"


def test_show_prints_the_provenance_lines_with_and_without_the_parent():
    """recipe-authoring › Variant / Library reading: `Local file:`, `Source:`, `Attribution:`,
    `Derived from:` (the parent's by-line with "you" suppressed under `--parent`, "(not in
    this export)" without it — printed from the file alone), `Lineage (parent):` only when
    the parent's lineage is non-null, `Credits:` in the recorded order, `Exported:` and every
    `changes` entry under `Changes:`, the first never dropped; "None" nowhere."""
    changes = [
        "copied from the Fond-format steps the export carries",
        "set duration=2 on toast-the-spices, the sigil total",
        "set duration=15 on rest-the-dough, the sigil total",
        "set duration=4 on sear-the-steak, the sigil total",
        "set duration=25 on reduce-the-glaze, the sigil total",
        "set duration=3 on griddle-the-corn-cakes, the sigil total",
        "rename blanch-the-greens -> blanch-the-rabe",
        "split sear-the-steak -> sear-the-first-side, sear-the-second-side",
        "add ~preheat{15%min} on preheat-the-oven",
    ]
    for extra, derived, head in ((("--parent", V2), DERIVED_WITH_PARENT, VARIANT_LINE),
                                 ((), DERIVED_WITHOUT_PARENT, VARIANT_LINE.replace("of Skillet Steak Supper by", "of rcp-steak-01 by"))):
        out = run_cli(VARIANT, "--dsl", "show", *extra)
        lines = provenance_lines(out)
        assert lines == [head, f"  Local file: {VARIANT}", "  Source: https://blog.example/skillet-steak-supper",
                         "  Attribution: source Cara", derived,
                         "  Lineage (parent): forked from rcp-parent-77 at v2; credits @cara, @ben",
                         "  Credits: @cara, @ben", "  Exported: 2026-10-08T12:00:00+00:00", "  Changes:"] + \
            [f"    - {c}" for c in changes]
        assert "None" not in out
        plan = provenance_lines(run_cli(VARIANT, "--dsl", "plan", *extra))
        assert plan[:-1] == lines and plan[-1].startswith("  Steps from: a local file (h=")
    # The clean-DSL variant: its parent's lineage is null — no `Lineage (parent):`, no `Credits:`, no such keys.
    clean = provenance_lines(run_cli(CLEAN_DSL, "--dsl", "show", "--parent", V2))
    assert clean[1:] == [f"  Local file: {CLEAN_DSL}", "  Source: https://blog.example/coconut-rice",
                         "  Derived from: Fond id rcp-rice-09 (handle steamed-coconut-rice-w4x5y6) — by @ana · from blog.example "
                         "· Fond handle steamed-coconut-rice-w4x5y6",
                         "  Exported: 2026-10-08T12:00:00+00:00", "  Changes:",
                         "    - copied from the Fond-format steps the export carries"]
    env = fe.parse_envelope(fe.split_envelope(CLEAN_DSL.read_text(encoding="utf-8"))[0])[0]
    assert "credits" not in env["lineage"] and "parent_lineage" not in env["lineage"] and "attribution" not in env


def test_a_version_1_parent_row_keeps_its_stamped_handle_in_the_by_line_head(tmp_path, monkeypatch):
    """recipe-authoring › Variant: the head is "exactly as the parent's `byline()` prints it
    for the row … (the profile masked as after `strip`)" — and `strip` STAMPS
    `profile.handle` onto a version-1 authored row, which has no `authorHandle` key
    (verifier finding, 2026-10-13: the row was looked up in the unmasked parent, so the
    masked copy's stamp never reached `byline()` and the head read "by (unknown)"). Over a
    variant of the v1 fixture's nodes-only row, with `--parent` the v1 export: `list`,
    `show`, `plan`, the player payload's `byline` and `provenance_lines` all say "by @ana",
    never "by (unknown)" and never "by you"; `check --parent` passes."""
    monkeypatch.chdir(tmp_path)
    v1 = FIXTURES / "sample-export-v1.json"
    out = run_cli(v1, "convert", "Weeknight Garlic Pasta", "--made-on", MADE_ON)
    assert "it passes check" in out
    path = tmp_path / "weeknight-garlic-pasta.recipe.md"
    assert 'author: "@ana"' in path.read_text(encoding="utf-8")
    head = "Weeknight Garlic Pasta — local variant of Weeknight Garlic Pasta by @ana · local:weeknight-garlic-pasta"
    derived = ("  Derived from: Fond id rcp-pasta-02 (handle weeknight-garlic-pasta-d4e5f6) — by @ana · from blog.example "
               "· Fond handle weeknight-garlic-pasta-d4e5f6")
    assert run_cli(path, "--dsl", "list", "--parent", v1).splitlines()[1] == f"  - {head}"
    for cmd in ("show", "plan"):
        lines = provenance_lines(run_cli(path, "--dsl", cmd, "--parent", v1))
        assert lines[0] == head and derived in lines, lines
        assert "(unknown)" not in "\n".join(lines) and "you" not in lines[0]
    assert run_cli(path, "check", "--parent", v1).rstrip().endswith("Passes: nothing blocks local:weeknight-garlic-pasta.")
    row = run_json(path, "--dsl", "player", "--parent", v1, "--out", "-")["payload"]["recipes"][0]
    assert row["byline"] == head.split(" — ", 1)[1] and derived in row["provenance_lines"]
    # without --parent the spec's exact absent-parent line, from the file alone
    assert "  Derived from: Fond id rcp-pasta-02 (not in this export)" in provenance_lines(run_cli(path, "--dsl", "show"))


def test_the_credits_chain_keeps_its_recorded_order_and_a_null_position(tmp_path):
    """recipe-authoring › Variant › the credits chain is unchanged by an edit: the row's
    `attributionHandles` verbatim — order kept, a null position as `(unknown)`, the author
    on the by-line and never in the chain; `check --parent` holds exact equality and asserts
    "no `credits` key" against a null parent lineage."""
    data = json.loads(V2.read_text(encoding="utf-8"))
    steak = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-steak-01")
    steak["lineage"]["attributionHandles"] = [None, "ben", "cara"]
    export = tmp_path / "fond-export-test.json"
    export.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    draft = run_cli(export, "convert", "Skillet Steak Supper", "--made-on", MADE_ON, "--out", "-", expect=1)
    env_text = fe.split_envelope(draft)[0]
    assert "  credits:\n    - (unknown)\n    - ben\n    - cara\n" in env_text and 'author: "@ana"' in env_text
    assert "parent_lineage: forked from rcp-parent-77 at v2; credits (unknown), @ben, @cara" in env_text
    # The shipped variant, re-homed under this parent with the chain copied: it passes and prints the chain.
    text = VARIANT.read_text(encoding="utf-8").replace("  credits:\n    - cara\n    - ben\n",
                                                        "  credits:\n    - (unknown)\n    - ben\n    - cara\n")
    text = text.replace("credits @cara, @ben", "credits (unknown), @ben, @cara")
    variant = tmp_path / "steak-variant.md"
    variant.write_text(text, encoding="utf-8")
    assert "Passes: nothing blocks" in run_cli(variant, "check", "--parent", export)
    show = run_cli(variant, "--dsl", "show", "--parent", export)
    assert "  Credits: (unknown), @ben, @cara" in show.splitlines() and "@ana" not in show.split("Credits:")[1].split("\n")[0]
    reordered = tmp_path / "reordered.md"
    reordered.write_text(text.replace("    - ben\n    - cara\n", "    - cara\n    - ben\n"), encoding="utf-8")
    out = run_cli(reordered, "check", "--parent", export, expect=1)
    assert "`lineage.credits` is ['(unknown)', 'cara', 'ben']; the row carries ['(unknown)', 'ben', 'cara']" in out
    assert "  Credits: @cara, @ben" in run_cli(VARIANT, "--dsl", "show").splitlines()  # from the file alone


# ---------------------------------------------------------------------------
# Composed and transcribed lines
# ---------------------------------------------------------------------------


def test_the_composed_line_is_identical_on_list_show_and_the_players_mise_screen():
    """recipe-authoring › Composed › from a page the user hands over (R-C6): `· from <host>,
    credited to <creator>` — the page's creator as the page states it, never a "by @"
    handle — the same on `list`, `show`, `plan` and the payload's provenance lines; `Source:`
    and `Attribution:` one line each; no lineage line, no `Derived from:`."""
    assert "  - " + COMPOSED_LINE in run_cli(LOCAL, "--dsl", "list").splitlines()
    show = run_cli(COMPOSED, "--dsl", "show")
    assert provenance_lines(show) == [COMPOSED_LINE, f"  Local file: {COMPOSED}", "  Source: https://blog.example/weeknight-dal",
                                      "  Attribution: Ana", "  Changes:",
                                      "    - composed by the assistant from the page the user handed over, procedure only"]
    assert provenance_lines(run_cli(COMPOSED, "--dsl", "plan"))[:-1] == provenance_lines(show)
    row = payload_of(COMPOSED, "--dsl", "player")["recipes"][0]
    assert row["provenance_lines"] == provenance_lines(show) and row["byline"] == COMPOSED_LINE.split(" — ", 1)[1]
    assert "by @" not in show and "Derived from" not in show and "Lineage" not in show and "Credits" not in show
    assert "\n  note: only 2 canonical @ingredient definitions" in show  # the gate's note follows the block on show
    # A page that names no author is credited to its site name — the assistant writes the site name.
    assert fe.host_of("https://blog.example/weeknight-dal") == "blog.example"


def test_the_transcribed_line_with_and_without_its_from_clause(tmp_path):
    """recipe-authoring › Transcribed: `<Title> — transcribed by the assistant[ from
    <attribution source>] · local:<slug>`, the clause only when the user named a source;
    `author` is the name the user gave and is printed on no by-line; no lineage line."""
    assert "  - " + TRANSCRIBED_LINE in run_cli(LOCAL, "--dsl", "list").splitlines()
    show = run_cli(TRANSCRIBED, "--dsl", "show")
    assert provenance_lines(show) == [TRANSCRIBED_LINE, f"  Local file: {TRANSCRIBED}", "  Attribution: Nonna's card", "  Changes:",
                                      "    - transcribed from the card the user photographed, wording kept"]
    assert payload_of(TRANSCRIBED, "--dsl", "player")["recipes"][0]["provenance_lines"][0] == TRANSCRIBED_LINE
    assert "by Nonna" not in show and "by @" not in show
    plain = tmp_path / "plain-card.md"
    plain.write_text(TRANSCRIBED.read_text(encoding="utf-8").replace("author: Nonna\nattribution:\n  - Nonna's card\n", ""),
                     encoding="utf-8")
    line = "Nonna's Ragù — transcribed by the assistant · local:plain-card"
    assert run_cli(plain, "--dsl", "show").splitlines()[0] == line
    assert provenance_lines(run_cli(plain, "--dsl", "show")) == [line, f"  Local file: {plain}", "  Changes:",
                                                                 "    - transcribed from the card the user photographed, wording kept"]


# ---------------------------------------------------------------------------
# strip, scale, the read commands' gate
# ---------------------------------------------------------------------------


def test_strip_over_a_dsl_input_exits_0_writes_nothing_and_prints_the_one_line(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(VARIANT, folder / "steak.md")
    for args in ((folder / "steak.md", "--dsl", "strip"), (folder / "steak.md", "--dsl", "strip", "--out", folder / "out.json"),
                 (folder, "--dsl", "strip"), (folder / "steak.md", "--dsl", "strip", "--parent", V2)):
        out = run_cli(*args)
        assert out.strip() == "a local file is not an export; its provenance block is the file"
    assert [p.name for p in folder.iterdir()] == ["steak.md"]
    assert run_json(folder / "steak.md", "--dsl", "strip") == {"path": None, "text": fe.NOT_AN_EXPORT_LOCAL}


def test_scale_dsl_prints_and_writes_nothing(tmp_path):
    """cook-playback › Scaling is a labelled variant, over a local file: the base from `yield`
    when it states servings (the composed fixture's `4 servings`), `--from` otherwise;
    nothing is written."""
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(COMPOSED, folder / "dal.md")
    shutil.copy(VARIANT, folder / "steak.md")
    out = run_cli(folder / "dal.md", "--dsl", "scale", "--to", "8")
    assert out.splitlines()[0] == COMPOSED_LINE.replace("local:sample-composed", "local:dal") + \
        " — ×2 variant (the file is unchanged; ask for it any time)"
    assert "  - 2 cup red lentils" in out and "  - 6 cups water" in out  # the unit word is kept as written
    assert run_cli(folder / "steak.md", "--dsl", "scale", "--factor", "1.5", "--parent", V2).count("3 strip steak") == 0
    assert "- 1 1/2 strip steak" in run_cli(folder / "steak.md", "--dsl", "scale", "--factor", "1.5", "--parent", V2)
    assert sorted(p.name for p in folder.iterdir()) == ["dal.md", "steak.md"]
    assert (folder / "dal.md").read_bytes() == COMPOSED.read_bytes()


def test_the_read_commands_refuse_a_file_with_findings_and_list_marks_it(tmp_path):
    """recipe-authoring › `check` gates keeping and cooking: `show`, `plan`, `scale` and
    `player` with `--dsl` run the gate first and refuse (exit 1) with the findings; `--dsl
    list` prints "(does not pass check)" after the row."""
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(COMPOSED, folder / "dal.md")
    bad = folder / "bad-dal.md"
    bad.write_text(COMPOSED.read_text(encoding="utf-8").replace(", ~simmer{20%min}.", " for about 20 minutes."), encoding="utf-8")
    for command, extra in (("show", ()), ("plan", ()), ("scale", ("--factor", "2")), ("player", ("--out", "-"))):
        out = run_cli(bad, "--dsl", command, *extra, expect=1)
        assert "1 finding(s) block it; nothing with findings is cooked. Fix the file and run check." in out
        assert "suggestion [T] @simmer-the-dal:" in out and "Ingredients (" not in out
    listing = run_cli(folder, "--dsl", "list").splitlines()
    assert any(ln.endswith("· local:bad-dal (does not pass check)") for ln in listing)
    assert any(ln.endswith("· local:dal") for ln in listing)
    assert not (folder / "bad-dal.player.html").exists()


def test_dsl_list_names_two_files_that_share_a_basename(tmp_path):
    """recipe-authoring › The local id › two files cannot share a basename in one folder, and
    Library reading via `--dsl`: over `dal.md` and `dal.recipe.md`, `--dsl list` prints both
    rows under `local:dal`, marks BOTH "(does not pass check)" — neither file is the winner —
    and names both paths in one note, the collision once; nothing is written."""
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(COMPOSED, folder / "dal.md")
    shutil.copy(COMPOSED, folder / "dal.recipe.md")
    lines = run_cli(folder, "--dsl", "list").splitlines()
    row = "  - " + COMPOSED_LINE.replace("local:sample-composed", "local:dal") + " (does not pass check)"
    note = (f"two files share the basename `dal` ({folder / 'dal.md'}, {folder / 'dal.recipe.md'}) — rename all but one; "
            "local ids must be unique in a folder")
    assert lines == [f"Library {folder} — 2 recipe file(s):", row, row, f"Note: {note}"]
    result = run_json(folder, "--dsl", "list")
    assert result["warnings"] == [note]
    assert [(r["id"], r["ok"], r["path"]) for r in result["recipes"]] == \
        [("local:dal", False, str(folder / "dal.md")), ("local:dal", False, str(folder / "dal.recipe.md"))]
    assert sorted(p.name for p in folder.iterdir()) == ["dal.md", "dal.recipe.md"]


def test_a_shared_basename_refuses_every_member_and_any_lookup_by_the_id(tmp_path):
    """recipe-authoring › The local id › the collision rule: over `dal.md` and `dal.recipe.md`
    no file is `local:dal` — `show`, `plan`, `scale` and `player` by the id (and by the title
    the two share) refuse with the one line naming both files, exit 1, nothing written —
    never whichever file sorted first; each file read on its own still works; renaming one
    file dissolves the collision; a three-way collision names three files once, marks every
    row and gives each file an error naming the other two."""
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(COMPOSED, folder / "dal.md")
    shutil.copy(COMPOSED, folder / "dal.recipe.md")
    line = (f"two files share the basename `dal` ({folder / 'dal.md'}, {folder / 'dal.recipe.md'}) — rename all but one; "
            "local ids must be unique in a folder")
    for command, extra in (("show", ()), ("plan", ()), ("scale", ("--factor", "2")),
                           ("player", ()), ("player", ("--out", "-")), ("player", ("--out", folder / "x.player.html"))):
        for query in ("local:dal", "Weeknight Dal"):
            assert run_cli(folder, "--dsl", command, query, *extra, expect=1).strip() == line
        assert run_json(folder, "--dsl", command, "local:dal", *extra, expect=1) == {"error": line, "code": 1}
    # the whole folder as one page: the gate refuses the first member with its own error
    out = run_cli(folder, "--dsl", "player", expect=1)
    assert "local:dal: 1 finding(s) block it" in out
    assert f"basename `dal` is also the basename of {folder / 'dal.recipe.md'}; rename all but one" in out
    assert sorted(p.name for p in folder.iterdir()) == ["dal.md", "dal.recipe.md"]
    # each file on its own is a one-file library: no collision, the id from its own name
    for name in ("dal.md", "dal.recipe.md"):
        assert "· local:dal" in run_cli(folder / name, "--dsl", "show")
        assert run_json(folder / name, "--dsl", "list")["recipes"][0]["ok"] is True
    # renaming one file dissolves the collision for both ids
    (folder / "dal.recipe.md").rename(folder / "dal-two.recipe.md")
    assert run_json(folder, "--dsl", "list")["warnings"] == []
    assert run_json(folder, "--dsl", "show", "local:dal")["id"] == "local:dal"
    assert run_json(folder, "--dsl", "show", "local:dal-two")["id"] == "local:dal-two"
    # three files: the line names all three once; every row is marked; each error names the other two
    (folder / "dal-two.recipe.md").rename(folder / "dal.recipe.md")
    shutil.copy(COMPOSED, folder / "dal.v2.md")
    paths = [str(folder / n) for n in ("dal.md", "dal.recipe.md", "dal.v2.md")]
    three = f"three files share the basename `dal` ({', '.join(paths)}) — rename all but one; local ids must be unique in a folder"
    result = run_json(folder, "--dsl", "list")
    assert result["warnings"] == [three]
    assert [(r["id"], r["ok"]) for r in result["recipes"]] == [("local:dal", False)] * 3
    assert run_cli(folder, "--dsl", "list").count("Note: ") == 1
    assert run_cli(folder, "--dsl", "plan", "local:dal", expect=1).strip() == three
    library = fe.load_library(folder)
    for r in library.authored:
        others = ", ".join(p for p in paths if p != r.local_path)
        assert r.envelope_errors == [f"basename `dal` is also the basename of {others}; rename all but one — "
                                     "local ids must be unique in a folder"]
    assert sorted(p.name for p in folder.iterdir()) == ["dal.md", "dal.recipe.md", "dal.v2.md"]


def test_a_kept_scaled_variant_passes_check_and_scales_from_its_yield(tmp_path):
    """cook-playback › Scaling is a labelled variant › a kept scaled variant, yield in the
    file: the clean-DSL variant kept at ×1.5 — `yield: 6 servings`, the entry `scaled ×1.5
    from 4 servings`, the canonical `@slug{…}` amounts scaled, the parent's provenance as
    `convert` wrote it — passes `check --parent`, `show` prints the entry, and `scale --dsl`
    takes the file's yield as the base without asking; the export row is unchanged."""
    before = V2.read_bytes()
    scaled = CLEAN_DSL.read_text(encoding="utf-8")
    scaled = scaled.replace("source_url: https://blog.example/coconut-rice\n",
                            "source_url: https://blog.example/coconut-rice\nyield: 6 servings\n")
    scaled = scaled.replace("    - copied from the Fond-format steps the export carries\n",
                            "    - copied from the Fond-format steps the export carries\n    - scaled ×1.5 from 4 servings\n")
    for canonical, up in (("@rice{1 cup jasmine rice}", "@rice{1 1/2 cups jasmine rice}"),
                          ("@coconut{1/2 cup coconut flakes}", "@coconut{3/4 cup coconut flakes}"),
                          ("@coconut-milk{1 cup coconut milk}", "@coconut-milk{1 1/2 cups coconut milk}"),
                          ("@water{1 cup water}", "@water{1 1/2 cups water}")):
        assert scaled.count(canonical) == 1
        scaled = scaled.replace(canonical, up)
    kept = tmp_path / "coconut-rice-for-six.md"
    kept.write_text(scaled, encoding="utf-8")
    out = run_cli(kept, "check", "--parent", V2)
    assert "Passes: nothing blocks local:coconut-rice-for-six." in out and "[parent]" not in out
    show = run_cli(kept, "--dsl", "show", "--parent", V2).splitlines()
    assert show[0] == "Steamed Coconut Rice — local variant of Steamed Coconut Rice by @ana · local:coconut-rice-for-six"
    assert "    - scaled ×1.5 from 4 servings" in show and "  - 1 1/2 cups jasmine rice" in show
    doubled = run_cli(kept, "--dsl", "scale", "--to", "12", "--parent", V2)
    assert doubled.splitlines()[0] == show[0] + " — ×2 variant (the file is unchanged; ask for it any time)"
    assert "  - 3 cups jasmine rice" in doubled and "  - 3 cups water" in doubled
    assert "rcp-rice-09" in run_cli(V2, "show", "Steamed Coconut Rice") and V2.read_bytes() == before
    assert kept.read_text(encoding="utf-8") == scaled and sorted(p.name for p in tmp_path.iterdir()) == ["coconut-rice-for-six.md"]


FLAT_VARIANT = """---
title: Skillet Steak Supper
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
    - dropped every step but three
---
# Skillet Steak Supper

## Toast the Spices [phase=prep section=sauce duration=2 attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Sear the Steak [phase=cook section=main duration=4 attention_level=high]
Sear the @steak{1 strip steak} in the hot skillet, ~sear{2%min × 2}, flipping once.

## Plate the Supper [phase=serve section=main duration=3 attention_level=full]
Slice the steak and plate it with the @greens{1 bunch broccoli rabe}.
"""


def test_plan_on_a_variant_without_parent_proceeds_and_with_it_gates_an_edit(tmp_path):
    """recipe-authoring › `check` … › check needs the parent, the read commands do not: `plan
    --dsl` on a variant without `--parent` prints U and V "(not gated without --parent —
    pass it to gate edits)" and proceeds; with `--parent` the ratchet applies as in `check`
    (R-C2a): the flat edit of a parent that had edges is refused on U, an orphan atom on V."""
    flat = tmp_path / "flat-steak.md"
    flat.write_text(FLAT_VARIANT, encoding="utf-8")
    out = run_cli(flat, "--dsl", "plan")
    assert "  note [U]: 3 steps but no depends_on edges" in out
    assert "(not gated without --parent — pass it to gate edits)" in out and "Estimated time to serve" in out
    assert run_json(flat, "--dsl", "show")["origin"] == "variant"
    out = run_cli(flat, "--dsl", "plan", "--parent", V2, expect=1)
    assert "suggestion [U]: 3 steps but no depends_on edges" in out and "nothing with findings is cooked" in out
    orphan = tmp_path / "orphan.md"
    orphan.write_text(VARIANT.read_text(encoding="utf-8").rstrip("\n") + "\n\n"
                      "## Warm the Plates [phase=serve section=main duration=2 attention_level=none]\n"
                      "Warm the plates in the oven's last minutes.\n", encoding="utf-8")
    assert "Estimated time to serve" in run_cli(orphan, "--dsl", "plan")  # V printed, not gated, without the parent
    assert "note [V]:" in run_cli(orphan, "--dsl", "plan")
    out = run_cli(orphan, "--dsl", "plan", "--parent", V2, expect=1)
    assert "suggestion [V]: step DAG does not converge" in out
    assert "suggestion [V]: step DAG does not converge" in run_cli(orphan, "check", "--parent", V2, expect=1)


# ---------------------------------------------------------------------------
# h and the stale line
# ---------------------------------------------------------------------------


def test_h_mismatch_is_refused_absent_accepted_and_an_envelope_edit_keeps_h(tmp_path):
    """recipe-authoring › The FOND1 line carries `h=`: `plan … --h` refuses a mismatch with
    the message and estimates nothing, accepts an absent `h` and the current one; a
    `changes` line appended leaves `h` unchanged; any body edit changes it."""
    h = run_json(VARIANT, "check", "--parent", V2)["h"]
    assert H_RE.match(h) and run_json(VARIANT, "--dsl", "plan")["h"] == h
    assert run_json(VARIANT, "--dsl", "show")["h"] == h
    out = run_cli(VARIANT, "--dsl", "plan", "--done", "preheat-the-oven", "--h", "00000000", expect=1)
    assert out.strip() == (f"that line is for h=00000000; the recipe is now h={h} — paste the line from the updated player, "
                           "or tell me which steps are done")
    assert "Estimated" not in out
    assert "Estimated time to go" in run_cli(VARIANT, "--dsl", "plan", "--done", "preheat-the-oven")
    assert "Estimated time to go" in run_cli(VARIANT, "--dsl", "plan", "--done", "preheat-the-oven", "--h", h)
    text = VARIANT.read_text(encoding="utf-8")
    envelope_only = tmp_path / "sample-variant.md"
    envelope_only.write_text(text.replace("    - add ~preheat{15%min} on preheat-the-oven\n",
                                          "    - add ~preheat{15%min} on preheat-the-oven\n    - noted the pan size\n"), encoding="utf-8")
    assert run_json(envelope_only, "--dsl", "plan")["h"] == h
    body_edit = tmp_path / "body-edit.md"
    body_edit.write_text(text.replace("duration=25 attention_level=none depends_on=[preheat-the-oven]",
                                      "duration=30 attention_level=none depends_on=[preheat-the-oven]"), encoding="utf-8")
    assert run_json(body_edit, "--dsl", "plan")["h"] != h


def test_a_malformed_h_is_refused_with_exit_2_naming_it(capsys):
    """recipe-authoring › The FOND1 line carries `h=`: `--h` takes the stamp exactly as the
    line carries it — eight hex digits, 0-9 and a-f — or argparse exits 2 naming the value,
    in either mode, before anything is estimated; nothing is trimmed or case-folded into a
    stamp, so a malformed one is never read as stale or as absent (as the page's paste box)."""
    h = run_json(VARIANT, "--dsl", "plan")["h"]
    upper = h.upper() if re.search("[a-f]", h) else "D0ED784F"
    for bad in ("garbage", h[:7], h + "0", upper, "", " " + h, h + " ", h + "\n"):
        for argv in ((VARIANT, "--dsl", "plan", "--done", "preheat-the-oven", "--h", bad),
                     (V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices", "--h", bad)):
            capsys.readouterr()
            with pytest.raises(SystemExit) as exc:
                run_cli(*argv)
            assert exc.value.code == 2, (bad, argv)
            out, err = capsys.readouterr()
            assert "Estimated" not in out
            assert f"argument --h: takes the eight hex digits (0-9, a-f) after `h=` in the FOND1 line, not {bad!r}" in err, err
    assert "Estimated time to go" in run_cli(VARIANT, "--dsl", "plan", "--done", "preheat-the-oven", "--h", h)
    assert "Estimated time to go" in run_cli(VARIANT, "--dsl", "plan", "--done", "preheat-the-oven")
    # the plan check is as strict when called directly (no argparse in front of it)
    export = fe.load_library(VARIANT, fe.load_export(V2))
    with pytest.raises(fe.ExportError) as exc:
        fe.cmd_plan(export, export.authored[0].id, "preheat-the-oven", None, True, h_arg=upper)
    assert exc.value.code == 2
    assert fe.body_hash("a\r\nb  \n\n") == fe.body_hash("a\nb\n")  # CRLF, trailing whitespace and the final newline normalised


def test_every_payload_row_carries_h_for_every_local_fixture_and_the_export():
    for path in sorted(LOCAL.glob("*.md")):
        for row in payload_of(path, "--dsl", "player", *parent_args(path))["recipes"]:
            assert H_RE.match(row["h"]) and row["source"] == "local", path.name
    for row in payload_of(V2, "player")["recipes"]:
        assert H_RE.match(row["h"])


# ---------------------------------------------------------------------------
# The Option B yes-path over the zero-sigil row (3.8 over 6.2's rcp-rice-09)
# ---------------------------------------------------------------------------


def test_the_option_b_yes_path_over_the_zero_sigil_row(tmp_path, monkeypatch):
    """recipe-authoring › Variant › the Option B yes: the notice names "Toast the Coconut 2 min
    × 2" and "Simmer the Rice 15 min"; the assistant takes the `convert` draft (the body
    verbatim), appends "add timers from the app's steps" and one `add ~<name>{N%min} on
    <atom>` per matched title, puts the sigil inside each atom's sentence with `duration=`
    at least the minutes, persists it with `check - --parent <export> --out`, and the file's
    `plan --dsl` shows exactly those countdowns and no notice while `plan` on the export row
    still prints the notice."""
    before = V2.read_bytes()
    notice = run_json(V2, "plan", "rcp-rice-09")["timers_notice"]
    assert notice == {"dsl": 0, "nodes": 2, "steps": [{"title": "Toast the Coconut", "minutes": 2.0, "repeat": 2},
                                                      {"title": "Simmer the Rice", "minutes": 15.0, "repeat": 1}]}
    assert "Note: the Fond-format steps carry no timers; the app's steps for this recipe had 2 (Toast the Coconut 2 min × 2, " \
           "Simmer the Rice 15 min)" in run_cli(V2, "plan", "rcp-rice-09")
    draft = run_cli(V2, "convert", "Steamed Coconut Rice", "--made-on", MADE_ON, "--out", "-").split("\nDraft only", 1)[0].rstrip("\n") + "\n"
    assert draft == CLEAN_DSL.read_text(encoding="utf-8")
    edited = draft.replace("    - copied from the Fond-format steps the export carries\n",
                           "    - copied from the Fond-format steps the export carries\n"
                           "    - add timers from the app's steps\n"
                           "    - add ~toast{2%min} on toast-the-coconut\n"
                           "    - add ~simmer{15%min} on simmer-the-rice\n")
    edited = edited.replace("in a dry pan, one batch at a time, until golden.", "in a dry pan, one batch at a time, until golden, ~toast{2%min}.")
    edited = edited.replace("simmer over the lowest heat until the liquid is absorbed.",
                            "simmer over the lowest heat until the liquid is absorbed, ~simmer{15%min}.")
    assert fe.split_envelope(edited)[1].count("~") == 2
    kept = tmp_path / "steamed-coconut-rice.recipe.md"
    monkeypatch.setattr(sys, "stdin", io.StringIO(edited))
    out = run_cli("-", "check", "--parent", V2, "--out", kept)
    assert kept.read_text(encoding="utf-8") == edited and "Passes: nothing blocks local:steamed-coconut-rice." in out
    plan = run_cli(kept, "--dsl", "plan", "--parent", V2)
    assert "Toast the Coconut" in plan and "Timer: 2 min × 2 (2 countdowns, one at a time)" in plan
    assert "Timer: 15 min" in plan and "carry no timers" not in plan and "Note: the Fond-format" not in plan
    result = run_json(kept, "--dsl", "plan", "--parent", V2)
    assert "timers_notice" not in result
    timers = {s["id"]: s for s in result["steps"] if s["kind"] == "timer"}
    assert set(timers) == {"toast-the-coconut", "simmer-the-rice"}
    assert timers["toast-the-coconut"]["count"] == 2 and timers["toast-the-coconut"]["countdowns"] == [[2.0, "2 min"]]
    assert timers["simmer-the-rice"]["countdowns"] == [[15.0, "15 min"]]
    # Nothing else changed: every other atom's text and metadata is the parent's.
    base = {s["id"]: s for s in run_json(V2, "plan", "rcp-rice-09")["steps"]}
    for sid, s in {s["id"]: s for s in result["steps"]}.items():
        if sid not in timers:
            assert (s["text"], s["scheduled"], s["after"], s["kind"]) == (base[sid]["text"], base[sid]["scheduled"], base[sid]["after"], base[sid]["kind"])
    assert "timers_notice" in run_json(V2, "plan", "rcp-rice-09") and V2.read_bytes() == before
    assert "rcp-rice-09" in run_cli(V2, "show", "Steamed Coconut Rice")  # the row is never shadowed


# ---------------------------------------------------------------------------
# The built page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", THREE + [CLEAN_DSL], ids=lambda p: p.stem)
def test_the_built_page_embeds_h_source_local_aliases_and_the_marker(path):
    """recipe-authoring › The player: the marker comment names the file's id and `h`; the
    payload row carries `source: "local"`, its origin, `h`, the aliases parsed from the
    `rename`/`split` entries, and a by-line and provenance lines without "you" while the
    parent export's profile is present."""
    extra = parent_args(path)
    page = run_cli(path, "--dsl", "player", *extra, "--out", "-")
    m = MARKER_RE.match(page.split("\n", 1)[0])
    h = run_json(path, "--dsl", "plan", *extra)["h"]
    assert m and m.group(1) == h and m.group(2) == f"local:{path.stem}"
    (row,) = payload_of(path, "--dsl", "player", *extra)["recipes"]
    assert row["id"] == f"local:{path.stem}" and row["h"] == h and row["source"] == "local"
    assert row["origin"] == fe.load_library_file(path).origin
    expected_aliases = {"blanch-the-greens": ["blanch-the-rabe"],
                        "sear-the-steak": ["sear-the-first-side", "sear-the-second-side"]} if path is VARIANT else {}
    assert row["aliases"] == expected_aliases
    assert not YOU_RE.search(row["byline"]) and not any(YOU_RE.search(line) for line in row["provenance_lines"])
    assert row["provenance_lines"] == provenance_lines(run_cli(path, "--dsl", "show", *extra))


def test_player_out_refuses_a_foreign_page_rebuilds_its_own_and_prints_byte_equal(tmp_path):
    """recipe-authoring › Written only … › the player rebuilds only its own page, over a local
    file: a path whose first line is not the marker is refused (exit 1) and untouched, the
    player's own page is rebuilt in place, `--out -` is byte-equal to the file."""
    folder = tmp_path / "lib"
    folder.mkdir()
    shutil.copy(COMPOSED, folder / "dal.md")
    target = folder / "dal.player.html"
    run_cli(folder / "dal.md", "--dsl", "player")
    first = target.read_text(encoding="utf-8")
    assert first == run_cli(folder / "dal.md", "--dsl", "player", "--out", "-")
    run_cli(folder / "dal.md", "--dsl", "player", "--out", target)
    assert target.read_text(encoding="utf-8") == first
    foreign = folder / "notes.html"
    foreign.write_text("<!doctype html>\n<p>mine</p>\n", encoding="utf-8")
    out = run_cli(folder / "dal.md", "--dsl", "player", "--out", foreign, expect=1)
    assert out.strip() == f"`{foreign}` exists; pass --out <other> or edit that file"
    assert foreign.read_text(encoding="utf-8") == "<!doctype html>\n<p>mine</p>\n"
    out = run_cli(folder / "dal.md", "--dsl", "player", "--out", folder / "dal.md", expect=1)
    assert (folder / "dal.md").read_bytes() == COMPOSED.read_bytes()
    assert sorted(p.name for p in folder.iterdir()) == ["dal.md", "dal.player.html", "notes.html"]
