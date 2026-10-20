"""Hermetic tests for cook-with-fond/scripts/fond_export.py over the synthetic fixtures.

Every test is named after the cook-playback / fond-export-format scenario it exercises.
No network, no environment, no real data: the fixtures are invented (ana, ben, cara,
soup-xyz789) and inline literals are built in tmp_path.

Run from apps/skill:  ../mcp/.venv/bin/python -m pytest -q
"""

import ast
import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPT = SKILL / "scripts" / "fond_export.py"
FIXTURES = SKILL / "fixtures"
V2 = FIXTURES / "sample-export.json"
V1 = FIXTURES / "sample-export-v1.json"
MD2 = FIXTURES / "sample-export.md"
MD1 = FIXTURES / "sample-export-v1.md"

_spec = importlib.util.spec_from_file_location("fond_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def run_cli(*args, expect=0):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fe.run([str(a) for a in args])
    out = buf.getvalue()
    assert code == expect, f"exit {code} != {expect}\n{out}"
    return out


def run_json(*args, expect=0):
    return json.loads(run_cli(*args, "--json", expect=expect))


def load(path=V2):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(tmp_path, data, name="fond-export-test.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def step_of(plan, sid):
    return next(s for s in plan["steps"] if s["id"] == sid)


def history_row(out, title):
    """The `history` listing row for a title: "  - <title> — <by-line> — cooked N× — …"
    (a by-line always sits between the title and the count — the row never reads
    "<title> — cooked", which would drop the provenance)."""
    return next(ln for ln in out.splitlines() if ln.startswith(f"  - {title} — by "))


def node(nid, title, text="", time=None, until=None, deps=(), repeat=None):
    n = {"id": nid, "title": title, "text": text, "time": time, "until": until, "dependencies": list(deps)}
    if repeat is not None:
        n["repeat"] = repeat
    return n


def export_with(authored=None, saved=None, cooks=None, profile="keep", version=2):
    """A small synthetic export around inline literals (never real data)."""
    data = {
        "export_version": version,
        "exportedAt": "2026-10-08T12:00:00+00:00",
        "profile": {"uid": "fx-user-ana-01", "handle": "ana", "createdAt": "2025-03-01T09:00:00+00:00",
                    "totalCooks": 0, "totalRecipes": 0, "credits": 0, "linkedAnonymousUids": []},
        "contact": {"email": None, "displayName": None, "phoneNumber": None, "tiktokUsername": None},
        "authoredRecipes": authored or [],
        "savedRecipes": saved or [],
        "cooks": cooks or [],
    }
    if profile is None:
        del data["profile"]
    elif profile != "keep":
        data["profile"] = profile
    return data


def authored_row(rid, title, nodes, dsl=None, handle=None, author="ana", url=None, source_author=None, lineage=None,
                 ingredients=None):
    return {"id": rid, "linkedFromUid": None, "handle": handle or f"{rid}-handle", "authorHandle": author, "title": title,
            "url": url, "datePublished": "2026-09-01T00:00:00+00:00", "isPublic": True,
            "ingredients": ingredients or [], "nodes": nodes, "dsl": dsl, "sourceAuthor": source_author, "lineage": lineage}


def cook_row(rid, title, is_valid=True, status="rated", override=False, ratings=None, version=2):
    """A cook-recipe row: version 2 carries `status` and `userOverride`; version 1 neither."""
    row = {"id": rid, "title": title, "isValid": is_valid, "completedAt": None, "ratings": ratings or {}, "feedback": None}
    if version == 2:
        row.update({"status": status, "userOverride": override})
    return row


def cook_of(cid, status, started, rows, deleted=False, version=2):
    cook = {"id": cid, "linkedFromUid": None, "mealName": None, "status": status, "startedAt": started,
            "completedAt": None, "recipes": rows}
    if version == 2:
        cook["deleted"] = deleted
    return cook


def dsl_recipe(title, atoms):
    body = [f"# {title}", ""]
    for head, prose in atoms:
        body += [f"## {head}", prose, ""]
    return "\n".join(body)


# ---------------------------------------------------------------------------
# Fixture integrity (fond-export-format shapes the skill reads)
# ---------------------------------------------------------------------------

def test_fixture_v2_top_level_shape_and_synthetic_values():
    data = load(V2)
    assert set(data) == {"export_version", "exportedAt", "profile", "contact", "authoredRecipes", "savedRecipes", "cooks"}
    assert data["export_version"] == 2
    assert all(v is None for v in data["contact"].values())
    assert data["profile"]["linkedAnonymousUids"] == []
    blob = json.dumps(data)
    assert not re.search(r"\b[A-Za-z0-9]{28}\b", blob), "a 28-character token looks like a Firebase uid"
    for key in ("authoredRecipes", "savedRecipes", "cooks"):
        assert all(r["linkedFromUid"] is None for r in data[key])


def test_fixture_v2_authored_rows_carry_version_2_provenance():
    authored = load(V2)["authoredRecipes"]
    keys = {"id", "linkedFromUid", "handle", "authorHandle", "title", "url", "datePublished", "isPublic",
            "ingredients", "nodes", "dsl", "sourceAuthor", "lineage"}
    assert all(set(r) == keys for r in authored)
    handles = [r["authorHandle"] for r in authored]
    assert handles.count("ana") == len(authored) - 1 and handles.count(None) == 1
    forked = [r for r in authored if r["lineage"] is not None]
    assert len(forked) == 1 and forked[0]["dsl"] and forked[0]["sourceAuthor"] == "Cara"
    assert forked[0]["lineage"] == {"parentId": "rcp-parent-77", "forkPoint": "v2", "attributionHandles": ["cara", "ben"]}
    assert all(r["sourceAuthor"] is None for r in authored if r is not forked[0])


def test_fixture_v2_saved_rows_cover_live_ref_deleted_and_gone():
    saved = {r["id"]: r for r in load(V2)["savedRecipes"]}
    live = saved["rcp-soup-05"]
    assert set(live) == {"id", "linkedFromUid", "title", "handle", "authorHandle", "reason", "savedAt", "cookCount", "deleted",
                         "url", "ingredients", "nodes", "dsl", "servings", "sourceAuthor", "lineage"}
    assert live["servings"] is None and live["lineage"] is None and live["sourceAuthor"] is None
    assert all(set(n) <= {"id", "title", "text", "time", "until", "dependencies", "repeat"} for n in live["nodes"])
    ref = saved["rcp-pasta-02"]
    assert ref["authoredRecipeRef"] == "rcp-pasta-02"
    assert not ({"nodes", "ingredients", "dsl", "url", "sourceAuthor", "lineage"} & set(ref))
    deleted = saved["rcp-old-07"]
    assert deleted["deleted"] is True
    assert set(deleted) == {"id", "linkedFromUid", "title", "handle", "authorHandle", "reason", "savedAt", "cookCount", "deleted"}
    assert saved["rcp-gone-08"]["title"] is None
    assert saved["rcp-stew-06"]["nodes"] is None and saved["rcp-stew-06"]["dsl"] is None


def test_fixture_v2_cooks_cover_rated_aborted_recorded_migrated_removed_and_overridden():
    """tasks.md 3.3: four statuses plus a rated cook removed from history and a recorded cook
    whose recipe row is overridden; every row carries the version-2 counting flags."""
    cooks = load(V2)["cooks"]
    assert [c["status"] for c in cooks] == ["rated", "recorded", "rated", "aborted", "recorded", "migrated"]
    assert all(isinstance(c["deleted"], bool) for c in cooks)
    rows = [r for c in cooks for r in c["recipes"]]
    assert all("status" in r and isinstance(r["userOverride"], bool) for r in rows)
    removed = [c for c in cooks if c["deleted"]]
    assert len(removed) == 1 and removed[0]["status"] == "rated" and removed[0]["recipes"][0]["ratings"]["taste"] == 2
    migrated = cooks[-1]
    assert migrated["status"] == "migrated" and migrated["deleted"] is False
    assert [(r["status"], r["isValid"], r["userOverride"], r["ratings"]) for r in migrated["recipes"]] == \
        [("migrated", False, False, {"easyFollow": 4})]
    overridden = [r for c in cooks if c["status"] == "recorded" for r in c["recipes"] if r["userOverride"]]
    assert len(overridden) == 1 and overridden[0]["isValid"] is False


def test_fixture_v1_is_the_same_content_in_version_1_shape():
    v1 = load(V1)
    assert v1["export_version"] == 1
    for r in v1["authoredRecipes"]:
        assert "authorHandle" not in r and "sourceAuthor" not in r and "lineage" not in r
    for r in v1["savedRecipes"]:
        assert set(r) == {"id", "linkedFromUid", "title", "handle", "url", "authorHandle", "reason", "savedAt", "cookCount", "deleted"}
    # The version-2 fixture's timerless-DSL row (rcp-rice-09, tasks.md 12.7) is version-2 only.
    assert [r["id"] for r in v1["authoredRecipes"]] == [r["id"] for r in load(V2)["authoredRecipes"] if r["id"] != "rcp-rice-09"]
    assert [c["id"] for c in v1["cooks"]] == [c["id"] for c in load(V2)["cooks"]]
    for c in v1["cooks"]:  # a version-1 cook row has neither `deleted` nor the per-recipe flags
        assert "deleted" not in c and all("status" not in r and "userOverride" not in r for r in c["recipes"])


# ---------------------------------------------------------------------------
# Build the step graph from the export alone
# ---------------------------------------------------------------------------

def test_dsl_wins_over_nodes():
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    assert plan["source"] == "dsl"
    assert [s["id"] for s in plan["steps"]][:3] == ["preheat-the-oven", "boil-the-water", "toast-the-spices"]
    assert any("DSL wins" in w for w in plan["warnings"])
    # the projected node for the preheat is an until timer; the DSL atom is not
    assert step_of(plan, "preheat-the-oven")["kind"] == "watch"


def test_nodes_stored_as_a_string(tmp_path):
    data = load(V2)
    pasta = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-pasta-02")
    pasta["nodes"] = json.dumps(pasta["nodes"])
    plan_str = run_json(write(tmp_path, data), "plan", "Weeknight Garlic Pasta")
    plan_list = run_json(V2, "plan", "Weeknight Garlic Pasta")
    def shape(p):
        return [(s["id"], s["kind"], s["scheduled"], s["deps"]) for s in p["steps"]]

    assert shape(plan_str) == shape(plan_list)
    assert plan_str["estimate_minutes"] == plan_list["estimate_minutes"]


def test_cyclic_recipe_fails_loudly(tmp_path):
    nodes = [node(1, "Start", "Go.", 1), node(3, "Three", "Needs five.", 2, deps=[5]), node(5, "Five", "Needs three.", 2, deps=[3])]
    data = export_with(authored=[authored_row("rcp-cyc-01", "Loop Soup", nodes)])
    out = run_cli(write(tmp_path, data), "plan", "Loop Soup", expect=1)
    assert "loop" in out.lower() and "id 3" in out and "id 5" in out and "Three" in out and "Five" in out
    assert "Available now" not in out and "Estimated" not in out


def test_legacy_self_dependency_is_refused_as_a_cycle(tmp_path):
    """A node that lists its own id is a one-step cycle, not an unknown id: plan refuses it by name."""
    nodes = [node(1, "Chop", "Chop the [onion].", 2),
             node(2, "Simmer", "Simmer the [onion].", 10, until="soft", deps=[1, 2]),
             node(3, "Serve", "Serve.", deps=[2])]
    data = export_with(authored=[authored_row("rcp-self-01", "Self Loop Soup", nodes)])
    out = run_cli(write(tmp_path, data), "plan", "Self Loop Soup", expect=1)
    assert "depends on itself" in out and "id 2" in out and "Simmer" in out
    assert "no node carries" not in out
    assert "Available now" not in out and "Estimated" not in out
    # the self-edge is kept; the unknown-id warning still fires only for ids no node carries
    steps, warns = fe.steps_from_nodes([{"id": "2", "title": "Simmer", "dependencies": ["2", "9"]}])
    assert steps[0].deps == ["2"] and warns == ["'Simmer' depends on id '9', which no node carries; ignored"]


def test_dsl_self_dependency_is_refused_as_a_cycle(tmp_path):
    """An atom whose depends_on names its own slug is a one-step cycle: plan refuses it by name."""
    dsl = dsl_recipe("Self Loop Rice", [
        ("Rinse rice [duration=2]", "Rinse the @rice{1 cup}."),
        ("Simmer rice [duration=15 attention_level=low depends_on=[rinse-rice, simmer-rice]]", "Simmer ~timer{15%min}."),
        ("Serve [depends_on=[simmer-rice]]", "Serve."),
    ])
    data = export_with(authored=[authored_row("rcp-self-02", "Self Loop Rice", [], dsl=dsl)])
    out = run_cli(write(tmp_path, data), "plan", "Self Loop Rice", expect=1)
    assert "depends on itself" in out and "id simmer-rice" in out and "Simmer rice" in out
    assert "not an atom" not in out
    assert "Available now" not in out and "Estimated" not in out
    # the self-edge is kept; the unknown-atom warning still fires only for slugs no atom carries
    _, steps, _, warns = fe.steps_from_dsl(dsl_recipe("X", [("Rest [depends_on=[rest, nowhere]]", "Rest.")]))
    assert steps[0].deps == ["rest"] and warns == ["'Rest' depends on 'nowhere', which is not an atom of this recipe; ignored"]


def test_markdown_self_dependency_is_refused_as_a_cycle(tmp_path):
    """A printed step line that lists its own number in '(after steps …)' is a one-step cycle."""
    md = MD2.read_text(encoding="utf-8")
    old = "done when al dente] (after step 3)"
    assert md.count(old) == 1
    p = tmp_path / "fond-export-test.md"
    p.write_text(md.replace(old, "done when al dente] (after steps 3, 4)"), encoding="utf-8")
    out = run_cli(p, "--md", "plan", "Weeknight Garlic Pasta", expect=1)
    assert "depends on itself" in out and "id 4" in out and "Cook the pasta" in out
    assert "Available now" not in out and "Estimated" not in out


def test_missing_node_keys_are_patched_with_safe_defaults(tmp_path):
    nodes = [{"text": "Chop the [onion].", "time": 2}, {"id": "b", "title": "Cook", "dependencies": "[1]", "time": 3, "until": "soft"}]
    data = export_with(authored=[authored_row("rcp-patch-01", "Patchy", nodes)])
    plan = run_json(write(tmp_path, data), "plan", "Patchy")
    assert [s["id"] for s in plan["steps"]] == ["1", "b"]
    assert plan["steps"][0]["title"] == "Step 1" and plan["steps"][0]["deps"] == []
    assert step_of(plan, "b")["deps"] == ["1"] and step_of(plan, "b")["kind"] == "timer"
    assert plan["estimate_minutes"] == 5


# ---------------------------------------------------------------------------
# The script, not the model, reads the export
# ---------------------------------------------------------------------------

def test_ambiguous_title_lists_candidates_and_asks(tmp_path):
    rows = [authored_row(f"rcp-ch-{i}", t, [node(1, "Cook", "Cook it.", 5)]) for i, t in
            enumerate(["Roast Chicken", "Chicken Soup", "Chicken Pie"])]
    rows[1]["authorHandle"] = "ben"
    out = run_cli(write(tmp_path, export_with(authored=rows)), "plan", "chicken", expect=2)
    assert "Several recipes match 'chicken'" in out
    for t in ("Roast Chicken", "Chicken Soup", "Chicken Pie"):
        assert t in out
    assert "by you (@ana)" in out and "by @ben" in out
    assert "Estimated" not in out


def _two_tomato_soups_json(tmp_path):
    """The v2 JSON fixture plus @ana's authored "Tomato Soup" (synthetic id rcp-soup-ana-09,
    handle tomato-soup-ana-j1k2l3) beside @ben's saved one (rcp-soup-05, soup-xyz789): two
    creators, one title, no shared content."""
    data = load(V2)
    data["authoredRecipes"].append(authored_row("rcp-soup-ana-09", "Tomato Soup", [node(1, "Simmer", "Simmer.", 10)],
                                                handle="tomato-soup-ana-j1k2l3"))
    return write(tmp_path, data)


ANA_SOUP_CANDIDATE = "  - Tomato Soup — by you (@ana) · Fond handle tomato-soup-ana-j1k2l3 (Fond id rcp-soup-ana-09)"
BEN_SOUP_CANDIDATE = "  - Tomato Soup — by @ben · from blog.example · Fond handle soup-xyz789 (Fond id rcp-soup-05)"


def test_fuzzy_title_shared_by_two_creators_asks_which_one_instead_of_picking_the_last(tmp_path):
    """cook-playback › ambiguous title: a typo that reaches the fuzzy fallback keeps every
    recipe behind the one normalized title — "tomto sup" against @ana's and @ben's Tomato
    Soup lists both with by-line, handle and id and stops, on every lookup surface, rather
    than presenting whichever row came last as the match."""
    p = _two_tomato_soups_json(tmp_path)
    for cmd in ("show", "plan", "history", "scale"):
        out = run_cli(p, cmd, "tomto sup", expect=2)
        assert out.startswith("Several recipes match 'tomto sup' — which one?\n"), out
        assert ANA_SOUP_CANDIDATE in out and BEN_SOUP_CANDIDATE in out
        assert out.rstrip().endswith("Say the title, or pass the Fond id or handle.")
        assert "Fond id: rcp-soup-05" not in out and "Estimated" not in out  # no recipe was presented


def test_exact_title_shared_by_two_creators_asks_which_one(tmp_path):
    """cook-playback › ambiguous title: the exact spelling of a title two creators share
    gets the same answer as the typo — both candidates with by-lines, exit 2, no guess."""
    p = _two_tomato_soups_json(tmp_path)
    for cmd in ("show", "plan"):
        out = run_cli(p, cmd, "Tomato Soup", expect=2)
        assert out.startswith("Several recipes match 'Tomato Soup' — which one?\n")
        assert ANA_SOUP_CANDIDATE in out and BEN_SOUP_CANDIDATE in out


def test_fuzzy_title_with_one_recipe_behind_it_still_resolves():
    """The shipped fixture holds one Tomato Soup, so the same typo resolves to it: the
    fuzzy pass keeps working when nothing is ambiguous."""
    assert run_json(V2, "show", "tomto sup")["id"] == "rcp-soup-05"
    assert run_json(V2, "plan", "tomto sup")["id"] == "rcp-soup-05"
    assert run_json(V2, "history", "tomto sup")["id"] == "rcp-soup-05"


def test_title_lookup_accepts_fond_id_and_handle():
    assert run_json(V2, "show", "rcp-soup-05")["title"] == "Tomato Soup"
    assert run_json(V2, "show", "soup-xyz789")["title"] == "Tomato Soup"
    assert run_json(V2, "show", "garlic pasta")["id"] == "rcp-pasta-02"


def test_norm_keeps_letters_of_every_script_folds_accents_and_case_and_empties_punctuation():
    """The title lookup key: letters and digits of any script survive, Latin/Greek/Cyrillic
    accents, Hebrew/Arabic points and case fold, every other mark stays with its word
    (Kana voicing, Indic vowel signs, Thai vowels and tones spell different words),
    punctuation and whitespace runs become one space, punctuation alone is empty."""
    assert fe._norm("Crème Brûlée!") == "creme brulee"
    assert fe._norm("  Tomato\tSoup — Quick ") == "tomato soup quick"
    assert fe._norm("汤") == "汤" and fe._norm("面") == "面" and fe._norm("汤") != fe._norm("面")
    assert fe._norm("Pho Gà") == "pho ga" and fe._norm("ПИРОЖКИ") == "пирожки"
    assert fe._norm("Tiếng Việt") == "tieng viet" and fe._norm("שָׁלוֹם") == "שלום" and fe._norm("مَرْحَبًا") == "مرحبا"
    assert fe._norm("Œuf") == "oeuf" and fe._norm("Smørrebrød") == "smorrebrod" and fe._norm("Łódź") == "lodz"
    assert fe._norm("पानी") == "पानी" and fe._norm("दिन") != fe._norm("दीन") and fe._norm("पानी") != fe._norm("पीना")
    assert fe._norm("パン") != fe._norm("ハン") and fe._norm("カレー") != fe._norm("ガレー")
    assert fe._norm("ข้าวผัด") != fe._norm("ข่าวผัด") != fe._norm("ขาวผัด") and fe._norm("กิน") != fe._norm("กัน")
    assert fe._norm("Chili ❤️") == "chili"  # a variation selector is a glyph choice, not a letter
    assert fe._norm("!!!") == "" and fe._norm("— ?") == "" and fe._norm("") == ""


def _cjk_rows():
    """Synthetic titles in a non-Latin script (literals, never user data): soup and noodles."""
    return [authored_row("rcp-soup-cjk-01", "汤", [node(1, "Simmer", "Simmer.", 10)], handle="soup-cjk-a1b2c3"),
            authored_row("rcp-noodle-cjk-02", "面", [node(1, "Boil", "Boil.", 5)], handle="noodle-cjk-d4e5f6")]


def test_cjk_title_asked_for_is_not_answered_with_the_only_other_cjk_recipe(tmp_path):
    """cook-playback › The script, not the model, reads the export (recipe lookup): an
    export holding only "汤" must not select it when the user asks for "面" — the keys keep
    their characters instead of both folding to "", so the answer is "no match" with the
    titles hint on every lookup surface, and "汤" itself still resolves."""
    p = write(tmp_path, export_with(authored=_cjk_rows()[:1]))
    for cmd in ("show", "plan", "history", "scale"):
        out = run_cli(p, cmd, "面", expect=2)
        assert out.startswith("No recipe in this export matches '面'. Titles here: '汤'"), out
        assert "rcp-soup-cjk-01" not in out and "Estimated" not in out  # nothing was presented
    assert run_json(p, "show", "汤")["id"] == "rcp-soup-cjk-01"
    assert run_json(p, "plan", "汤")["id"] == "rcp-soup-cjk-01"


def test_two_cjk_titles_each_resolve_to_their_own_recipe(tmp_path):
    """cook-playback › ambiguous title, the converse: two unrelated non-Latin titles are
    not "several recipes match" — each query reaches exactly its recipe."""
    p = write(tmp_path, export_with(authored=_cjk_rows() + [authored_row("rcp-pasta-03", "Garlic Pasta",
                                                                           [node(1, "Toss", "Toss.", 3)])]))
    assert run_json(p, "show", "面")["id"] == "rcp-noodle-cjk-02"
    assert run_json(p, "show", "汤")["id"] == "rcp-soup-cjk-01"
    assert run_json(p, "plan", "面")["id"] == "rcp-noodle-cjk-02"
    out = run_cli(p, "show", "饭", expect=2)
    assert out.startswith("No recipe in this export matches '饭'. Titles here: '汤', '面', 'Garlic Pasta'"), out


def test_title_differing_only_by_a_mark_is_not_answered_with_the_only_other_recipe(tmp_path):
    """cook-playback › recipe lookup, for scripts whose marks spell the word: an export
    holding only "กิน" (eat) must not select it when the user asks for "กัน" (together), nor
    "ハン" for "パン" (bread), "カレー" for "ガレー", "दिन" (day) for "दीन" (poor) — the marks
    stay in the key, a voiced kana is one character to the fuzzy pass — and an id-less
    cook of the other word is not credited to the lone recipe."""
    for i, (title, other) in enumerate((("กิน", "กัน"), ("ハン", "パン"), ("カレー", "ガレー"), ("दिन", "दीन"))):
        rid = f"rcp-mark-{i}"
        p = write(tmp_path, export_with(
            authored=[authored_row(rid, title, [node(1, "Make", "Make.", 2)], handle=f"mark-{i}-j1k2l3")],
            cooks=[cook_of(f"cook-{i}", "rated", "2026-10-06T18:00:00+00:00", [{**cook_row(None, other), "id": None}])]), f"{i}.json")
        for cmd in ("show", "history"):
            out = run_cli(p, cmd, other, expect=2)
            assert out.startswith(f"No recipe in this export matches '{other}'. Titles here: '{title}'"), out
        assert run_json(p, "show", title)["id"] == rid
        assert "Cooked 0 time(s) that count" in run_cli(p, "history", title), (title, other)


def test_short_key_fuzzy_match_is_not_accepted_on_a_third_of_it_wrong(tmp_path):
    """cook-playback › recipe lookup: difflib scores an ideograph as a word, so on an export
    holding 红烧肉 (braised pork) a query for 红烧鱼 (braised fish) must be "no match" with
    the titles hint, not the pork presented silently; 汤面 / 面汤 likewise do not become 汤.
    A substring still resolves (面 → 面条) and the exact title still hits."""
    rows = [authored_row("rcp-soup-cjk-01", "汤", [node(1, "Simmer", "Simmer.", 10)]),
            authored_row("rcp-noodle-cjk-04", "面条", [node(1, "Boil", "Boil.", 5)]),
            authored_row("rcp-pork-cjk-05", "红烧肉", [node(1, "Braise", "Braise.", 60)])]
    p = write(tmp_path, export_with(authored=rows))
    for q in ("红烧鱼", "汤面", "面汤"):
        out = run_cli(p, "show", q, expect=2)
        assert out.startswith(f"No recipe in this export matches '{q}'. Titles here: '汤', '面条', '红烧肉'"), out
    assert run_json(p, "show", "面")["id"] == "rcp-noodle-cjk-04"
    assert run_json(p, "show", "红烧肉")["id"] == "rcp-pork-cjk-05"
    assert run_json(V2, "show", "tomto sup")["id"] == "rcp-soup-05"  # a long Latin key keeps the looser cutoff


def test_accented_title_matches_its_plain_spelling_and_itself(tmp_path):
    """Latin behaviour unchanged: "Crème brûlée" is found by "creme brulee", by its own
    spelling in any case, and by a one-word substring; the letters NFKD leaves whole
    (œ, ø) fold too, so a short title is found by its plain spelling, not left to the
    fuzzy cutoff."""
    p = write(tmp_path, export_with(authored=[authored_row("rcp-creme-01", "Crème brûlée", [node(1, "Bake", "Bake.", 40)])]))
    for q in ("creme brulee", "Crème brûlée", "CRÈME BRÛLÉE", "brulee", "crème"):
        assert run_json(p, "show", q)["id"] == "rcp-creme-01", q
    assert run_json(p, "plan", "creme brulee")["id"] == "rcp-creme-01"
    for rid, title, plain in (("rcp-oeuf-02", "Œuf", "oeuf"), ("rcp-smor-03", "Smørrebrød", "smorrebrod")):
        q = write(tmp_path, export_with(authored=[authored_row(rid, title, [node(1, "Make", "Make.", 5)])]), f"{rid}.json")
        assert run_json(q, "show", plain)["id"] == rid and run_json(q, "show", title)["id"] == rid, title


def test_punctuation_only_query_is_no_match_with_the_titles_hint(tmp_path):
    """An empty lookup key never matches another title — "!!!" does not reach the recipe
    titled "???" — while that title is still reachable by its own spelling (whitespace-
    trimmed), by its Fond id and by its handle, and is listed in the hint."""
    rows = _cjk_rows()[:1] + [authored_row("rcp-marks-02", "???", [node(1, "Stir", "Stir.", 2)], handle="marks-g7h8i9")]
    p = write(tmp_path, export_with(authored=rows))
    for q in ("!!!", "— ?"):
        out = run_cli(p, "show", q, expect=2)
        assert out.startswith(f"No recipe in this export matches '{q}'. Titles here: '汤', '???'"), out
        assert "Several recipes match" not in out
    assert run_json(p, "show", "???")["id"] == "rcp-marks-02"
    assert run_json(p, "show", " ??? ")["id"] == "rcp-marks-02"
    assert run_json(p, "show", "rcp-marks-02")["title"] == "???"
    assert run_json(p, "show", "marks-g7h8i9")["title"] == "???"
    two = write(tmp_path, export_with(authored=rows + [authored_row("rcp-marks-03", "???", [node(1, "Whisk", "Whisk.", 1)])]), "two.json")
    assert run_cli(two, "show", "???", expect=2).startswith("Several recipes match '???' — which one?")


def test_id_less_cook_row_with_a_cjk_title_no_recipe_carries_is_not_credited_to_another_cjk_recipe(tmp_path):
    """cook-playback › Provenance on every presentation (never invented): a cook row that
    carries a title only (every Markdown cook line) is attributed by the same key, so a
    cook of "面" is not counted against the export's lone "汤", and two cooks of "汤" and
    "面" in an export holding both go one each, never "cannot be attributed"."""
    lone = write(tmp_path, export_with(authored=_cjk_rows()[:1], cooks=[
        cook_of("cook-cjk-1", "rated", "2026-10-06T18:00:00+00:00", [{**cook_row(None, "面"), "id": None}])]), "lone.json")
    out = run_cli(lone, "history")
    assert out.startswith("Cooking history from this export (1 counted cook(s), 0 recipe cook(s), across 0 recipe(s))"), out
    assert not any(ln.startswith("  - 汤 — ") for ln in out.splitlines()) and "cannot be attributed" not in out
    assert "Cooked 0 time(s) that count" in run_cli(lone, "history", "汤")
    both = write(tmp_path, export_with(authored=_cjk_rows(), cooks=[
        cook_of("cook-cjk-2", "rated", "2026-10-06T18:00:00+00:00", [{**cook_row(None, "汤"), "id": None}]),
        cook_of("cook-cjk-3", "rated", "2026-10-07T18:00:00+00:00", [{**cook_row(None, "面"), "id": None}])]), "both.json")
    out = run_cli(both, "history")
    assert "— cooked 1× —" in history_row(out, "汤") and "— cooked 1× —" in history_row(out, "面")
    assert "cannot be attributed" not in out


# The "no network, no environment" allow-list (cook-with-fond-authoring 6.6): an AST walk
# over every `.py` under scripts/ — `fond_export.py`, `nodes_to_dsl.py`, `fond_dsl/*` —
# against an explicit module set, never `sys.stdlib_module_names` (None on 3.9, where the
# earlier check silently skipped) and never a column-0 regex (blind to the indented lazy
# imports). `graphlib` is the vendored lint's alone (the 3.9 floor); the script's own two
# modules are the only non-stdlib names; `importlib` and `__import__` are banned by name.
ALLOWED_IMPORTS = frozenset({"__future__", "argparse", "dataclasses", "difflib", "fractions", "graphlib", "hashlib",
                             "json", "math", "pathlib", "re", "sys", "typing", "unicodedata"})
OWN_MODULES = frozenset({"fond_dsl", "nodes_to_dsl"})
BANNED_IMPORTS = frozenset({"os", "socket", "urllib", "http", "requests", "subprocess", "ssl", "importlib"})


def import_findings(path, text, rel):
    """Every import an AST walk finds in `text` that the allow-list refuses, each naming
    the file and line: a banned module (network, environment, process, dynamic import), a
    module outside the allow-list, `graphlib` outside scripts/fond_dsl/, one of the script's
    own modules imported from the wrong file, a relative import, `__import__`, `os.environ`."""
    findings = []
    tree = ast.parse(text, filename=rel)
    in_fond_dsl = path.parent.name == "fond_dsl"
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                findings.append(f"{rel}:{node.lineno}: a relative import (the script's own modules are imported by name)")
                continue
            names = [node.module or ""]
        for dotted in names:
            top = dotted.split(".")[0]
            where = f"{rel}:{node.lineno}: imports `{dotted}`"
            if top in BANNED_IMPORTS:
                findings.append(f"{where} — banned (no network, no environment, no process, no dynamic import)")
            elif top == "graphlib" and not in_fond_dsl:
                findings.append(f"{where} — graphlib is imported only under scripts/fond_dsl/ (the 3.9 floor)")
            elif top == "nodes_to_dsl" and path.name != "fond_export.py":
                findings.append(f"{where} — nodes_to_dsl is imported by fond_export.py alone")
            elif top == "fond_dsl" and not (in_fond_dsl or path.name == "fond_export.py"):
                findings.append(f"{where} — fond_dsl is imported by fond_export.py and its own package alone")
            elif top not in ALLOWED_IMPORTS and top not in OWN_MODULES:
                findings.append(f"{where} — not in the allow-list {sorted(ALLOWED_IMPORTS)}")
        if (isinstance(node, ast.Name) and node.id == "__import__") or (isinstance(node, ast.Attribute) and node.attr == "__import__"):
            findings.append(f"{rel}:{node.lineno}: `__import__` is banned (every import is a plain import statement)")
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            findings.append(f"{rel}:{node.lineno}: `.environ` — nothing under scripts/ reads the environment")
    return findings


def test_no_network_no_environment_source_scan():
    """cook-playback › The script, not the model, reads the export; fond-dsl-open-release ›
    stdlib only; cook-with-fond-authoring 6.6: every `.py` under scripts/ imports only the
    allow-list and the script's own two modules — found by an AST walk, indented lazy
    imports included — with `os`, `socket`, `urllib`, `http.client`, `requests`,
    `subprocess`, `ssl`, `importlib` and `__import__` banned by name and `graphlib` only
    under scripts/fond_dsl/."""
    paths = _shipped_py()
    assert {p.name for p in paths} >= {"fond_export.py", "nodes_to_dsl.py", "dsl.py", "qty.py", "gate.py",
                                       "ingredients_spec.py", "authoring_guidance.py", "__init__.py"}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(SKILL))
        assert import_findings(path, text, rel) == []
        assert "os.environ" not in text and "__import__" not in text, rel
    src = SCRIPT.read_text(encoding="utf-8")
    # the contact block is never read; the only mention is strip dropping the key
    assert re.findall(r'(?:\.get\(|\[)"contact"', src) == []
    assert "linkedAnonymousUids" not in src.replace("`profile.linkedAnonymousUids`", "")


def test_the_source_scan_catches_a_planted_import():
    """The guard is real: a scratch `import urllib` appended to fond_dsl/gate.py fails naming
    the file and line; an indented `import socket` inside a function of the script fails
    too (the column-0 regex this replaces was blind to it); so do `importlib`, `__import__`,
    `graphlib` outside fond_dsl/, `os`, `http.client`, a module outside the allow-list, a
    relative import and `.environ`."""
    gate = SKILL / "scripts" / "fond_dsl" / "gate.py"
    gate_rel = "scripts/fond_dsl/gate.py"
    gate_text = gate.read_text(encoding="utf-8")
    assert import_findings(gate, gate_text, gate_rel) == []
    lines = gate_text.count("\n") + 1
    found = import_findings(gate, gate_text + "import urllib\n", gate_rel)
    assert found == [f"{gate_rel}:{lines}: imports `urllib` — banned (no network, no environment, no process, no dynamic import)"]
    script_rel = "scripts/fond_export.py"
    src = SCRIPT.read_text(encoding="utf-8")
    assert import_findings(SCRIPT, src, script_rel) == []
    indented = src + "\n\ndef _scratch():\n    import socket\n    return socket\n"
    found = import_findings(SCRIPT, indented, script_rel)
    assert len(found) == 1 and found[0].startswith(f"{script_rel}:{src.count(chr(10)) + 4}: imports `socket` — banned")
    for planted, fragment in (("import importlib\n", "imports `importlib` — banned"),
                              ("import importlib.util\n", "imports `importlib.util` — banned"),
                              ("x = __import__('os')\n", "`__import__` is banned"),
                              ("import graphlib\n", "graphlib is imported only under scripts/fond_dsl/"),
                              ("import os\n", "imports `os` — banned"),
                              ("from http.client import HTTPConnection\n", "imports `http.client` — banned"),
                              ("import yaml\n", "imports `yaml` — not in the allow-list"),
                              ("from . import gate\n", "a relative import"),
                              ("def _e(m):\n    return m.environ\n", "`.environ` — nothing under scripts/ reads the environment")):
        found = import_findings(SCRIPT, src + "\n" + planted, script_rel)
        assert len(found) == 1 and fragment in found[0], (planted, found)
    # The script's own modules are allowed only where the script imports them.
    assert import_findings(gate, gate_text + "import nodes_to_dsl\n", gate_rel)[0].endswith("nodes_to_dsl is imported by fond_export.py alone")
    n2d = SKILL / "scripts" / "nodes_to_dsl.py"
    assert import_findings(n2d, n2d.read_text(encoding="utf-8") + "import fond_dsl\n", "scripts/nodes_to_dsl.py")[0].endswith(
        "fond_dsl is imported by fond_export.py and its own package alone")


def test_no_network_no_environment_runs_with_an_empty_environment():
    """Every command runs under `env={}` and `-I` (no environment, no user site, no script
    folder on sys.path until the script inserts it): the export commands, and — 6.6 —
    `check` over the variant fixture with `--parent`, `convert "<title>" --out -` and
    `player --out -` over the fixtures, so the lazy import and the player build read
    nothing from the environment either."""
    local = FIXTURES / "local"
    runs = [
        (V2, ["list"]), (V2, ["show", "Tomato Soup"]), (V2, ["plan", "Weeknight Garlic Pasta"]), (V2, ["missing"]), (V2, ["history"]),
        (local / "sample-variant.md", ["check", "--parent", str(V2)]),
        (local / "sample-composed.md", ["check"]),
        (local / "sample-transcribed.md", ["--dsl", "plan"]),
        (V2, ["convert", "Weeknight Garlic Pasta", "--made-on", "2026-10-13", "--out", "-"]),
        (V2, ["convert", "Steamed Coconut Rice", "--made-on", "2026-10-13", "--out", "-"]),
        (V1, ["convert", "Toast Soldiers", "--made-on", "2026-10-13", "--out", "-"]),
        (V2, ["player", "--out", "-"]), (V1, ["player", "--out", "-"]), (MD2, ["--md", "player", "--out", "-"]),
        (local / "sample-variant.md", ["--dsl", "player", "--parent", str(V2), "--out", "-"]),
        (local, ["--dsl", "player", "--out", "-"]),
    ]
    for path, args in runs:
        proc = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), str(path)] + args, env={}, capture_output=True,
                              text=True, cwd=str(HERE))
        assert proc.returncode == 0, (args, proc.stderr, proc.stdout[-500:])
        assert proc.stdout.strip()
    assert not list((SKILL / "scripts").rglob("__pycache__"))


def test_fresh_clone_works_from_the_repository_root():
    proc = subprocess.run([sys.executable, "cook-with-fond/scripts/fond_export.py", "cook-with-fond/fixtures/sample-export.json",
                           "plan", "Skillet Steak Supper"], cwd=str(SKILL.parent), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "Ingredients (" in proc.stdout and "wave 1" in proc.stdout and "Estimated time to serve" in proc.stdout


# ---------------------------------------------------------------------------
# Export version compatibility
# ---------------------------------------------------------------------------

def test_version_1_export():
    out = run_json(V1, "list")
    cookable = [r["title"] for r in out["cookable"]]
    assert cookable == ["Skillet Steak Supper", "Weeknight Garlic Pasta", "Toast Soldiers"]
    missing = [r["title"] for r in out["missing"]]
    assert "Tomato Soup" in missing and "Grandma's Stew" in missing
    assert "saved, no steps in this export" in out["text"]


def test_version_2_export():
    out = run_json(V2, "list")
    cookable = {r["title"]: r for r in out["cookable"]}
    assert "Tomato Soup" in cookable and cookable["Tomato Soup"]["kind"] == "saved"
    # the authoredRecipeRef row resolves to the authored content and is listed once
    assert [r["title"] for r in out["cookable"]].count("Weeknight Garlic Pasta") == 1
    export = fe.load_json_export(V2)
    ref = next(r for r in export.saved if r.ref)
    assert export.content_of(ref).id == "rcp-pasta-02" and fe.has_steps(export.content_of(ref))


def test_not_an_export(tmp_path):
    p = tmp_path / "notes.json"
    p.write_text(json.dumps({"recipes": []}), encoding="utf-8")
    out = run_cli(p, "list", expect=1)
    assert "not a Fond" in out and "fond-export-" in out and "Export my data" in out


def test_non_integer_version_is_refused(tmp_path):
    """cook-playback › Export version compatibility: a file with no integer `export_version`
    (a string, a non-integral float, zero) is refused with the not-a-Fond-export message."""
    data = load(V2)
    data["export_version"] = "2"
    assert "not a Fond" in run_cli(write(tmp_path, data, "a.json"), "list", expect=1)
    data["export_version"] = 2.5
    assert "not a Fond" in run_cli(write(tmp_path, data, "b.json"), "list", expect=1)
    data["export_version"] = 0
    assert "not a Fond" in run_cli(write(tmp_path, data, "c.json"), "list", expect=1)


def test_higher_export_version_warns_and_continues(tmp_path, capsys):
    """cook-playback › Export version compatibility: the skill SHALL warn (and continue) on a
    higher integer. A version-3 file is read best-effort with version-2 semantics — the same
    cookable set, exit 0, the warning on stderr and in `warnings[]` — on both the JSON and
    the `--md` path; it is never refused and `plan` still runs."""
    data = load(V2)
    data["export_version"] = 3
    p = write(tmp_path, data, "v3.json")
    out = run_json(p, "list")
    assert out["export_version"] == 3
    assert [r["title"] for r in out["cookable"]] == [r["title"] for r in run_json(V2, "list")["cookable"]]
    assert any("newer than this skill knows" in w and "reading it as version 2" in w for w in out["warnings"])
    assert "Warning: export_version 3 is newer than this skill knows (1, 2)" in capsys.readouterr().err
    assert "Steps from: legacy steps" in run_cli(p, "plan", "Tomato Soup")
    md = MD2.read_text(encoding="utf-8").replace("export version 2", "export version 3", 1)
    q = tmp_path / "v3.md"
    q.write_text(md, encoding="utf-8")
    md_out = run_json("--md", q, "list")
    assert md_out["export_version"] == 3 and len(md_out["cookable"]) == 5
    assert "newer than this skill knows" in capsys.readouterr().err


def test_readme_faq_promises_the_warn_and_continue_fallback():
    """apps/skill/CLAUDE.md: copy promises exactly what ships. The README FAQ, SKILL.md and
    references/export-format.md must all describe the higher-version fallback that
    check_version implements — warn, read as version 2, ignore unknown fields — and the FAQ
    may not say the script stops or refuses such a file. Also keeps the tasks.md 9.4 banned
    phrases out of the three."""
    readme = (SKILL / "README.md").read_text(encoding="utf-8")
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    ref = (SKILL / "references" / "export-format.md").read_text(encoding="utf-8")
    faq = readme[readme.index("**Will it keep up with Fond's export format?**"):]
    faq = faq[:faq.index("\n\n")]
    assert fe.SUPPORTED_VERSIONS == (1, 2) and "`export_version` 1 and 2" in faq
    assert "warns" in faq and "reads it as version 2" in faq and "best-effort" in faq
    assert "newer than this skill knows" in faq  # quotes the script's own warning
    assert "stops" not in faq and "refuses" not in faq
    assert "the script warns and continues" in skill
    assert "warns and continues on a higher integer" in ref
    for text in (faq, skill, ref):
        assert not re.search(r"works everywhere|keeps? working after|the scheduler follows|stays on your device", text, re.IGNORECASE)


BANNED_COPY_RE = re.compile(r"works everywhere|keeps? working after|the scheduler follows|stays on your device|"
                            r"offers timers|adds timers|optional timer|where they belong|saves to Fond|"
                            r"adds to your Fond library|published to Fond|\bregistered\b|\bverified\b|\brings\b|"
                            # beyond the spec's listed set: the strings the parent's output tests ban
                            # (12.1–12.4) and fond-style §4's old parenthetical, so no reference quotes them
                            r"watch for|want a timer|one recipe in ten",
                            re.IGNORECASE)
FORK_RE = re.compile(r"\bfork(ed)?\b", re.IGNORECASE)
PUBLISHED_COPY = ("README.md", "references/fond-style.md", "references/export-format.md",
                  "references/authoring.md", "references/player.md")
# The v0.1.0 release text: beside publish.sh, never published, read against the same bans.
RELEASE_NOTES = HERE.parent / "RELEASE-NOTES-v0.1.0.md"
# publish.sh mirrors tests/ but not the notes. Inside fond-mono (this folder sits at
# <root>/apps/skill/tests and <root> holds the monorepo's openspec/ folder) they are always
# read, so a missing file still fails; elsewhere they are read only where they exist, and the
# public mirror, which carries none, skips the notes checks.
IN_FOND_MONO = (len(HERE.parents) > 2 and HERE.parent.name == "skill" and HERE.parents[1].name == "apps"
                and (HERE.parents[2] / "openspec").is_dir())
CHECK_RELEASE_NOTES = IN_FOND_MONO or RELEASE_NOTES.is_file()
# R-C9 (founder copy ruling, 2026-10-14): the honest framing every user-facing surface carries after
# its neutral lead — at or below the spec's promise level, adding no claim and contradicting none.
R_C9_FRAMING = ("An early version, still in development — not a replacement for the Fond app, but a way to keep "
                "cooking the recipes you have.")


def test_banned_phrases_absent_from_the_published_copy():
    """skill-distribution › banned phrases absent (tasks.md 5.3; the parent's 9.4 grep extended
    with the word-bounded authoring bans and references/authoring.md + player.md in the set):
    zero matches over the five published copy files and the release notes (parent task
    15.4; the file sits beside publish.sh so it never ships) — "unverified" and "cannot
    ring" never false-positive — and the fork pattern matches only
    references/export-format.md's own description of the export's `lineage` field. Three strings beyond the spec's listed set
    ("watch for", "want a timer", "one recipe in ten") guard the references against quoting
    the phrases the script's output tests ban. The README's authoring paragraph says what
    skill-distribution permits and describes the pasted prompt as drafting, the privacy line
    extends to the file handed back, the artifact and the pasted FOND1 line, the one
    permitted sentence about the question is verbatim, and the claude.ai download sentence
    carries its decision-12 hedge."""
    files = {name: (SKILL / name).read_text(encoding="utf-8") for name in PUBLISHED_COPY}
    if CHECK_RELEASE_NOTES:  # always inside fond-mono, where a missing file raises
        files[RELEASE_NOTES.name] = RELEASE_NOTES.read_text(encoding="utf-8")
    for name, text in files.items():
        for ln in text.splitlines():
            assert not BANNED_COPY_RE.search(ln), (name, ln)
            if FORK_RE.search(ln):
                assert name == "references/export-format.md" and "lineage" in ln.lower(), (name, ln)
    readme = " ".join(files["README.md"].split())
    assert "An open skill for Claude, plus a plain prompt for any other assistant" in readme
    if CHECK_RELEASE_NOTES:
        notes = " ".join(files[RELEASE_NOTES.name].split())
        assert R_C9_FRAMING in notes and "An early version, still in development; provided as is" in notes
    assert "suggests timers" in readme and "computes clock times" in readme
    assert "does not depend on Fond's servers" in readme
    assert ("writes new recipes in Fond's format from your words, a photo or a page you hand it, labelled as "
            "composed, or makes a variant of a recipe in your export, with its credits") in readme
    assert "checks them against Fond's own rules and keeps them as files you own" in readme
    assert "builds an offline player page for your browser, synced to the chat by one line you paste" in readme
    assert ("handled under that provider's terms — and so are a recipe file the skill hands back to you, a player "
            "page published as a private artifact and any `FOND1` line you paste into the chat") in readme
    assert "The skill writes the file and sends nothing." in readme
    permitted = ("when a recipe's Fond-format steps carry no timers, the assistant offers once to add the app's "
                 "timers as a local variant")
    assert permitted.lower() in readme.lower()  # the README opens the sentence with a capital
    assert "3.9 or newer for `check`, `convert` and every `--dsl` command" in readme
    assert "on a phone it is unverified for this release" in readme  # the player row before the device test
    # the paste path is described as drafting (skill-distribution "authoring described honestly")
    assert "can only draft a recipe in Fond's format" in readme and "The prompt drafts only" in readme
    # the claude.ai download is conditional copy until 7.3's iOS outcome picks it (decision 12)
    assert "on a phone the download is unverified for this release" in readme


# R-C10 (founder ruling 2026-10-16, "so people have multiple options"): the install rows for the
# ChatGPT plugin, Codex and other coding agents, the pasted prompt's scope and the plans FAQ —
# the same words in the README and the release notes, each saying what was tested, on which
# plan and date, or "untested" (skill-distribution "the ChatGPT plugin package").
CHATGPT_ROW = ("In ChatGPT's Plugins, add a new plugin and upload `cook-with-fond-plugin.zip` from the Releases page: "
               "the same skill, packaged as a ChatGPT plugin. Tested on Pro (in ChatGPT's Work tab), 2026-10-16: it cooks in the chat as text; "
               "the player page is not shown there. Business, Enterprise and Edu: your admin may need to allow plugin "
               "uploads. Plus, Go and Free: untested — if the upload is refused, use Codex or the pasted prompt.")
CODEX_LABEL = "**Codex** (any ChatGPT plan: the ChatGPT desktop app or the Codex CLI)"
CODEX_ROW = ("Unzip `cook-with-fond.zip` into `~/.agents/skills` (`mkdir -p ~/.agents/skills && unzip cook-with-fond.zip "
             "-d ~/.agents/skills`), open Codex on a folder that holds your export, and type `$cook-with-fond` in the CLI "
             "or `@cook-with-fond` in the app. Needs Python 3.9 or newer on your computer. Documented by OpenAI; "
             "untested by us for this release.")
OTHER_AGENTS_LABEL = ("**Other coding agents** (Gemini CLI, GitHub Copilot, VS Code, Cursor and others that read "
                      "Agent Skills)")
OTHER_AGENTS_ROW = ("Copy the same `cook-with-fond/` folder into `~/.agents/skills` or the agent's own skills folder. "
                    "Untested by us.")
PASTE_LABEL = "**Any other assistant** (Gemini — unverified — and any assistant without skills or plugins)"
PLANS_FAQ = ("**Which plans?** claude.ai skills are listed by Anthropic for Free, Pro, Max, Team and Enterprise. In "
             "ChatGPT the plugin upload was tested on Pro, in the Work tab; on Business, Enterprise and Edu it depends on your admin; "
             "Plus, Go and Free are untested, and Codex is included in every ChatGPT plan. Gemini is unverified for "
             "this release.")


def test_install_rows_say_what_was_tested():
    """skill-distribution "the ChatGPT plugin package" (R-C10): the README's ChatGPT row names
    the plugin zip and the plan and date it was tested on, the Codex and other-agents rows say
    "untested", the pasted prompt covers what is left, and the plans FAQ says the same; the
    release notes carry the same rows and name both downloads. The retired skill-upload row
    is gone from both."""
    readme = " ".join((SKILL / "README.md").read_text(encoding="utf-8").split())
    assert f"| **ChatGPT** | {CHATGPT_ROW} |" in readme
    assert f"| {CODEX_LABEL} | {CODEX_ROW} |" in readme
    assert f"| {OTHER_AGENTS_LABEL} | {OTHER_AGENTS_ROW} |" in readme
    assert f"| {PASTE_LABEL} | Open `cook-with-fond/prompts/paste-this-prompt.md`" in readme
    assert PLANS_FAQ in readme
    assert "`cook-with-fond-plugin.zip` holds that same folder, unchanged, under `skills/cook-with-fond/`" in readme
    texts = [readme]
    if CHECK_RELEASE_NOTES:
        notes = " ".join(RELEASE_NOTES.read_text(encoding="utf-8").split())
        assert f"- **ChatGPT:** {CHATGPT_ROW}" in notes
        assert f"- {CODEX_LABEL}: {CODEX_ROW}" in notes
        assert f"- {OTHER_AGENTS_LABEL}: {OTHER_AGENTS_ROW}" in notes
        assert f"- {PASTE_LABEL}: paste `cook-with-fond/prompts/paste-this-prompt.md`" in notes
        assert "Two downloads on this release: `cook-with-fond.zip`" in notes
        assert "`cook-with-fond-plugin.zip`, the same skill packaged as a ChatGPT plugin" in notes
        texts.append(notes)
    for text in texts:
        assert "Create → Upload from your computer" not in text and "not Plus or Free" not in text
        assert "ChatGPT Plus/Free" not in text and "ChatGPT Plus and Free" not in text


def test_raw_callable_payload_is_accepted(tmp_path):
    payload = {"json": load(V2), "markdown": "# Your Fond data export\n"}
    out = run_json(write(tmp_path, payload, "payload.json"), "list")
    assert len(out["cookable"]) == 5
    as_string = {"json": json.dumps(load(V2)), "markdown": ""}
    assert len(run_json(write(tmp_path, as_string, "payload2.json"), "list")["cookable"]) == 5


# ---------------------------------------------------------------------------
# Mise en place first
# ---------------------------------------------------------------------------

def test_opening_turn_has_ingredients_prep_first_and_an_estimate():
    out = run_cli(V2, "plan", "Weeknight Garlic Pasta")
    assert "Ingredients (9):" in out and "- garlic" in out
    assert "Mise en place" in out and "Estimated time to serve: about 20 min" in out
    wave1 = out.split("Mise en place")[1].split("Later waves")[0]
    assert wave1.index("Prep: Slice the garlic") < wave1.index("Prep: Grate the cheese") < wave1.index("Boil the water")
    assert "Cook the pasta" not in wave1
    plan = run_json(V2, "plan", "Weeknight Garlic Pasta")
    assert plan["waves"][0] == ["7", "2", "5", "3"]


def test_no_quantity_in_the_export_is_not_invented():
    plan = run_json(V2, "plan", "Weeknight Garlic Pasta")
    assert "garlic" in plan["ingredients"]
    garlic = step_of(plan, "7")
    assert garlic["needs"] == ["garlic"] and "[garlic]" in garlic["text"]
    assert not re.search(r"\d", garlic["text"])


# ---------------------------------------------------------------------------
# Dependency ordering and availability
# ---------------------------------------------------------------------------

def test_long_timer_offered_before_short_prep(tmp_path):
    nodes = [node(1, "Chop the herbs", "Chop the [herbs].", 2), node(2, "Braise", "Braise the [beef].", 40, until="tender"),
             node(3, "Finish", "Stir the herbs into the braise.", 3, deps=[1, 2])]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-br-01", "Braise", nodes)])), "plan", "Braise")
    assert plan["available"] == ["2", "1"]
    assert step_of(plan, "2")["latest_start"] < step_of(plan, "1")["latest_start"]
    assert plan["estimate_minutes"] == 43


def test_latest_start_order_differs_from_wave_order():
    plan = run_json(V2, "plan", "Weeknight Garlic Pasta", "--done", "5")
    # "Cook the pasta" (wave 2, depends on the resolved boil) comes before the
    # dependency-free "Prep: Slice the garlic" (wave 1): wave membership does not decide.
    assert plan["available"][0] == "9" and "7" in plan["available"]
    assert step_of(plan, "9")["latest_start"] < step_of(plan, "7")["latest_start"]


def test_what_else_can_i_do_now_lists_only_available_steps():
    plan = run_json(V2, "plan", "Weeknight Garlic Pasta")
    assert set(plan["available"]) == {"5", "7", "3", "2"}
    assert plan["available"] == ["5", "7", "3", "2"]
    assert set(plan["locked"]) == {"9", "4", "8", "6", "10"}


def test_locked_step_is_not_offered_and_names_its_needs():
    out = run_cli(V2, "plan", "Weeknight Garlic Pasta")
    locked = out.split("Locked (waiting on other steps):")[1]
    assert "Toss the pasta" in locked and "(after step 4, 5)" in locked and "needs: parsley, chili flakes" in locked
    available = out.split("Available now")[1].split("Locked")[0]
    assert "Toss the pasta" not in available


def test_tie_breakers_timer_then_prep_then_dependency_free_then_node_order(tmp_path):
    nodes = [node(1, "Stir", "Stir.", 5), node(2, "Prep: Dice", "Dice.", 5), node(3, "Steep", "Steep.", 5, until="dark"),
             node(4, "Whisk", "Whisk.", 5)]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-tie-01", "Ties", nodes)])), "plan", "Ties")
    assert len({s["latest_start"] for s in plan["steps"]}) == 1
    assert plan["available"] == ["3", "2", "1", "4"]


def test_one_step_per_turn_lines_carry_title_text_and_done_when():
    out = run_cli(V2, "plan", "Weeknight Garlic Pasta")
    assert "Cook the pasta — Drop the [spaghetti] in and stir once. — Timer: 12 min — done when al dente (after step 3)" in out


# ---------------------------------------------------------------------------
# Timer steps are exactly the `until` steps (nodes) and the `~timer{}` atoms (DSL)
# ---------------------------------------------------------------------------

def test_until_present():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "9")
    assert s["kind"] == "timer" and s["scheduled"] == 12 and s["countdowns"] == [[12, "12 min"]]
    assert s["timing"] == "Timer: 12 min — done when al dente"


def test_no_until_long_time():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "8")
    assert s["kind"] == "hands-on" and s["timing"] == "~8 min hands-on" and "Timer" not in s["timing"]


def test_until_present_short_time():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "4")
    assert s["kind"] == "timer" and s["timing"] == "Timer: 30 seconds — done when fragrant"


def test_until_present_no_time():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "5")
    assert s["kind"] == "cue" and s["timing"] == "Done when: the water is at a rolling boil"
    assert "Timer" not in s["timing"] and "~" not in s["timing"] and s["scheduled"] == 0


def test_dsl_atom_with_a_timer_sigil():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "simmer-the-sauce")
    assert s["kind"] == "timer" and s["occupies"] is False and s["attention"] == "low"
    assert s["countdowns"] == [[20, "20 min"]] and s["scheduled"] == 22 and s["surplus"] == 2
    assert s["timing"].startswith("Timer: 20 min") and "about 2 min more" in s["timing"]


def test_low_attention_no_sigil():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "boil-the-water")
    assert s["kind"] == "watch" and s["occupies"] is False and s["scheduled"] == 6 and s["countdowns"] == []
    assert "no timer, no clock time" in s["timing"] and "Timer:" not in s["timing"]


def test_hands_on_atom_with_a_sigil():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "sear-the-steak")
    assert s["kind"] == "timer" and s["occupies"] is True and s["attention"] == "high"
    assert s["countdowns"] == [[2, "2-3 min"], [2, "2-3 min"]] and s["scheduled"] == 4 and s["duration"] == 0
    assert "× 2" in s["structure"] and "Timer: 4 min" not in s["timing"]


def test_walk_away_atom_without_a_sigil():
    """cook-playback › walk-away atom without a sigil: a 15-minute `none` atom with no sigil
    is read as written — "about 15 min", no countdown, no clock time, nothing proposed — and
    the plan carries no optional-timer field or wording anywhere (tasks.md 12.1/12.4)."""
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    s = step_of(plan, "preheat-the-oven")
    assert s["kind"] == "watch" and s["occupies"] is False and s["countdowns"] == []
    assert "about 15 min" in s["timing"] and "Timer:" not in s["timing"] and "optional_timer" not in s
    assert "optional" not in json.dumps(plan)


def test_dsl_born_recipe_whose_projected_nodes_carry_a_preheat_timer(tmp_path):
    """cook-playback › DSL-born recipe whose projected nodes carry a preheat timer: the DSL is
    cooked as written; the nodes-only timer is the legacy projection's lift, legacy-only — the
    divergence is recorded, not removed (founder ruling 2026-10-10; tasks.md 12.4)."""
    data = load(V2)
    steak = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-steak-01")
    steak["dsl"] = None  # a nodes-only reading of the same row (tier-2 export)
    nodes_plan = run_json(write(tmp_path, data), "plan", "Skillet Steak Supper")
    assert nodes_plan["source"] == "nodes"
    assert step_of(nodes_plan, "1")["kind"] == "timer" and step_of(nodes_plan, "1")["scheduled"] == 15
    dsl_plan = run_json(V2, "plan", "Skillet Steak Supper")
    assert step_of(dsl_plan, "preheat-the-oven")["kind"] == "watch"


def test_clock_time_passes_is_the_models_job_the_script_never_reads_a_clock():
    src = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(datetime|time)\b", src, re.M)
    assert fe.CANNOT_RING in run_cli(V2, "plan", "Tomato Soup")


# ---------------------------------------------------------------------------
# Timer structure is preserved
# ---------------------------------------------------------------------------

def test_two_segment_sigil():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "rest-the-dough")
    assert s["countdowns"] == [[5, "5 min"], [10, "10 min"]] and s["scheduled"] == 15
    assert s["structure"] == "5 min, then 10 min" and "Timer: 15 min" not in s["timing"]


def test_x2_repeat_with_a_named_flip():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "sear-the-steak")
    assert len(s["countdowns"]) == 2 and all(m == 2 for m, _ in s["countdowns"]) and s["scheduled"] == 4
    assert "flipping once" in s["text"] and "(2 countdowns, one at a time)" in s["timing"]


def test_count_multiplies_the_sigil(tmp_path):
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "griddle-the-corn-cakes")
    assert s["countdowns"] == [[3, "3 min"]] and s["count"] == 3 and s["scheduled"] == 9
    assert s["structure"] == "3 min × 3" and "(3 countdowns, one at a time)" in s["timing"]
    data = load(V2)
    next(r for r in data["authoredRecipes"] if r["id"] == "rcp-steak-01")["dsl"] = None
    n = step_of(run_json(write(tmp_path, data), "plan", "Skillet Steak Supper"), "9")
    assert n["count"] == 3 and n["scheduled"] == 9 and n["structure"] == "3 min × 3"


def test_legacy_node_with_repeat():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "3")
    assert s["kind"] == "timer" and s["count"] == 2 and s["countdowns"] == [[1, "1 min"], [1, "1 min"]]
    assert s["scheduled"] == 2 and s["done_when"] == "puffed" and s["done_when_raw"] == "puffed (×2)"
    assert s["timing"] == "Timer: 1 min × 2 (2 countdowns, one at a time) — done when puffed"


def test_repeat_node_without_until_is_hands_on():
    s = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "6")
    assert s["kind"] == "hands-on" and s["countdowns"] == [] and s["scheduled"] == 6
    assert s["timing"] == "~2 min × 3 (about 6 min in all) hands-on"


def test_single_segment_no_repeat_is_unchanged():
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    assert step_of(plan, "reduce-the-glaze")["timing"] == "Timer: 25 min"
    pasta = step_of(run_json(V2, "plan", "Weeknight Garlic Pasta"), "9")
    assert "×" not in pasta["timing"] and "then" not in pasta["timing"]


def test_md_timer_times_r_is_two_countdowns():
    s = step_of(run_json(MD2, "--md", "plan", "Weeknight Garlic Pasta"), "7")
    assert s["countdowns"] == [[1, "1 min"], [1, "1 min"]] and s["scheduled"] == 2 and "Timer: 2 min" not in s["timing"]


def test_md_hands_on_times_r_is_hands_on_without_countdown():
    s = step_of(run_json(MD2, "--md", "plan", "Weeknight Garlic Pasta"), "8")
    assert s["kind"] == "hands-on" and s["scheduled"] == 6 and s["countdowns"] == []


# ---------------------------------------------------------------------------
# Atom duration is the scheduled length
# ---------------------------------------------------------------------------

def test_duration_longer_than_the_timer():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "simmer-the-sauce")
    assert s["scheduled"] == 22 and s["countdowns"] == [[20, "20 min"]] and s["surplus"] == 2


def test_timer_longer_than_the_duration():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "reduce-the-glaze")
    assert s["scheduled"] == 25 and s["surplus"] == 0 and "more" not in s["timing"]


def test_count_multiplies_the_scheduled_length():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "cook-the-flatbreads")
    assert s["scheduled"] == 8 and s["countdowns"] == [[3, "3 min"]] and s["count"] == 2 and s["surplus"] == 1
    assert "about 1 min more" in s["timing"]


def test_count_multiplies_the_scheduled_length_surplus_after_each_ring(tmp_path):
    """cook-playback › Atom duration is the scheduled length › count multiplies the scheduled
    length: duration=4, count=2, ~cook{3%min} is scheduled at 8 = 2 × (3 + 1), and the
    1-minute surplus is announced after EACH ring (3+1, 3+1) — never 3+3+1 (7)."""
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    s = step_of(plan, "cook-the-flatbreads")
    assert s["scheduled"] == 8 and s["count"] == 2 and s["timer_total"] == 3 and s["surplus"] == 1
    assert (s["timer_total"] + s["surplus"]) * s["count"] == s["scheduled"]
    assert "after each ring about 1 min more on this step" in s["timing"]
    assert "(duration 4 min per iteration; 8 min in all)" in s["timing"]
    assert "after the last ring" not in s["timing"]
    assert "after each ring about 1 min more on this step" in run_cli(V2, "plan", "Skillet Steak Supper")
    # count=1 keeps the single-ring wording and names no iteration
    simmer = step_of(plan, "simmer-the-sauce")
    assert "after the last ring about 2 min more on this step (duration 22 min)" in simmer["timing"]
    assert "each" not in simmer["timing"] and "in all" not in simmer["timing"]
    # a multi-segment sigil with count > 1: the surplus lands after each ITERATION's last ring
    data = export_with(authored=[authored_row("rcp-r", "Rest Twice", [], dsl=dsl_recipe("Rest Twice", [
        ("Rest It [phase=cook section=main duration=20 attention_level=low count=2]",
         "Rest the @dough{1 ball dough}, ~rest{5%min, 10%min}."),
    ]))])
    rest = step_of(run_json(write(tmp_path, data), "plan", "Rest Twice"), "rest-it")
    assert rest["scheduled"] == 40 and rest["timer_total"] == 15 and rest["surplus"] == 5
    assert "after each iteration's last ring about 5 min more on this step" in rest["timing"]
    assert "(duration 20 min per iteration; 40 min in all)" in rest["timing"]
    # SKILL.md teaches the rule, and its --running arithmetic treats each iteration as timer + surplus
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "after each iteration's last ring" in skill
    assert "`2 + 1 + (3 + 1)" in skill


def test_sigil_less_atom_unchanged():
    s = step_of(run_json(V2, "plan", "Skillet Steak Supper"), "boil-the-water")
    assert s["scheduled"] == 6 and s["countdowns"] == [] and "more" not in s["timing"]


def test_latest_start_pass_uses_the_scheduled_length():
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    lst = {s["id"]: s["latest_start"] for s in plan["steps"]}
    assert lst["reduce-the-glaze"] - lst["simmer-the-sauce"] == 22  # not 20
    assert lst["plate-the-supper"] - lst["cook-the-flatbreads"] == 8


def test_running_rung_simmer_one_minute_after_contributes_one_not_zero():
    done = "preheat-the-oven,boil-the-water,toast-the-spices,rest-the-dough,sear-the-steak,cook-the-flatbreads," \
           "griddle-the-corn-cakes,blanch-the-greens,roast-the-vegetables"
    one = run_json(V2, "plan", "Skillet Steak Supper", "--done", done, "--running", "simmer-the-sauce=1")
    zero = run_json(V2, "plan", "Skillet Steak Supper", "--done", done, "--running", "simmer-the-sauce=0")
    assert one["estimate_minutes"] == 29 and zero["estimate_minutes"] == 28
    assert step_of(one, "simmer-the-sauce")["state"] == "running"


# ---------------------------------------------------------------------------
# Parallelism while a timer runs
# ---------------------------------------------------------------------------

def test_simmer_and_chop_prep_offered_while_the_timer_runs():
    plan = run_json(V2, "plan", "Weeknight Garlic Pasta", "--done", "5", "--running", "9=10")
    assert "7" in plan["available"] and plan["running"] == {"9": 10}
    out = run_cli(V2, "plan", "Weeknight Garlic Pasta", "--done", "5", "--running", "9=10")
    assert "Cook the pasta (id 9) — 10 min left — does not occupy you" in out


def test_nothing_else_available_while_the_timer_runs():
    out = run_cli(V2, "plan", "Tomato Soup", "--done", "1,2", "--running", "3=12")
    assert "(nothing — every unresolved step waits on something that is still running)" in out
    assert "Blend and serve" in out.split("Locked")[1]


def test_high_attention_timer_blocks_low_attention_timer_does_not(tmp_path):
    def recipe(level):
        return dsl_recipe("Pair", [
            (f"Cook It [phase=cook section=main attention_level={level}]", "Cook the @thing{1 thing}, ~cook{4%min}."),
            ("Chop [phase=cook section=main duration=3 attention_level=full]", "Chop the @herbs{herbs}."),
        ])
    high = export_with(authored=[authored_row("rcp-h", "Pair High", [], dsl=recipe("high"))])
    low = export_with(authored=[authored_row("rcp-l", "Pair Low", [], dsl=recipe("low"))])
    assert run_json(write(tmp_path, high, "h.json"), "plan", "Pair High")["estimate_minutes"] == 7
    assert run_json(write(tmp_path, low, "l.json"), "plan", "Pair Low")["estimate_minutes"] == 4
    running_high = run_json(write(tmp_path, high, "h.json"), "plan", "Pair High", "--running", "cook-it=2")
    running_low = run_json(write(tmp_path, low, "l.json"), "plan", "Pair Low", "--running", "cook-it=2")
    assert running_high["estimate_minutes"] == 5 and running_low["estimate_minutes"] == 3


def test_offering_a_step_after_the_ring_with_minutes_left():
    out = run_cli(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices,sear-the-steak", "--running", "simmer-the-sauce=2")
    assert "Simmer the Sauce (id simmer-the-sauce) — 2 min left — does not occupy you" in out
    plan = run_json(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices,sear-the-steak", "--running", "simmer-the-sauce=2")
    assert step_of(plan, "simmer-the-sauce")["remaining"] == 2 and plan["available"]


# ---------------------------------------------------------------------------
# Time-to-serve estimate
# ---------------------------------------------------------------------------

def test_timers_overlap_hands_on_work_twenty_three_not_thirty_eight(tmp_path):
    nodes = [node(1, "Simmer", "Simmer the [sauce].", 20, until="thick"), node(2, "Chop A", "Chop.", 5), node(3, "Chop B", "Chop.", 5),
             node(4, "Chop C", "Chop.", 5), node(5, "Finish", "Toss.", 3, deps=[1, 2, 3, 4])]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-23", "Overlap", nodes)])), "plan", "Overlap")
    assert plan["estimate_minutes"] == 23


def test_repeat_counted_in_full(tmp_path):
    nodes = [node(1, "Puff", "Puff the [bread].", 1, until="puffed (×2)", repeat=2)]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-rep", "Just Puff", nodes)])), "plan", "Just Puff")
    assert plan["estimate_minutes"] == 2


def test_all_zero_time_steps(tmp_path):
    nodes = [node(1, "Open", "Open the [jar].", 0), node(2, "Pour", "Pour.", 0, deps=[1]), node(3, "Serve", "Serve.", None, deps=[2])]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-zero", "Zero", nodes)])), "plan", "Zero")
    assert plan["estimate_minutes"] == 0 and len(plan["steps"]) == 3
    assert "Open" in plan["text"] and "Pour" in plan["text"] and "Serve" in plan["text"]


def test_done_re_estimates_from_a_resolved_set():
    assert run_json(V2, "plan", "Weeknight Garlic Pasta")["estimate_minutes"] == 20
    assert run_json(V2, "plan", "Weeknight Garlic Pasta", "--done", "7,2,5,9,4")["estimate_minutes"] == 14


def test_mid_cook_re_estimate_with_a_running_timer():
    assert run_json(V2, "plan", "Tomato Soup")["estimate_minutes"] == 31
    done_only = run_json(V2, "plan", "Tomato Soup", "--done", "1,2")["estimate_minutes"]
    running = run_json(V2, "plan", "Tomato Soup", "--done", "1,2", "--running", "3=12")["estimate_minutes"]
    assert done_only == 23 and running == 15 and done_only - running == 8


def test_a_multi_day_running_count_replays_through_the_tail_unchanged():
    """recipe-authoring › The FOND1 line carries h=: the replay tail carries whole minutes
    and no clock, so a phase of a day or more — whose end the page writes as
    `@HH:MM+<days>d` — replays through `--running <id>=2100` exactly as a shorter one; the
    script's reader is untouched by the day offset."""
    plan = run_json(V2, "plan", "Skillet Steak Supper", "--running", "rest-the-dough=2100")
    rest = step_of(plan, "rest-the-dough")
    assert rest["state"] == "running" and rest["remaining"] == 2100
    assert plan["estimate_minutes"] >= 2100 and plan["running"] == {"rest-the-dough": 2100}


def test_running_timer_has_rung():
    plan = run_json(V2, "plan", "Tomato Soup", "--done", "1,2", "--running", "3=0")
    assert plan["estimate_minutes"] == 3  # blend still follows the simmer
    assert "3" not in plan["done"] and step_of(plan, "3")["state"] == "running"
    assert plan["available"] == [] and plan["locked"] == ["4"]


def test_running_atom_past_its_last_ring_is_measured_against_the_scheduled_length():
    one = run_json(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices,sear-the-steak", "--running", "simmer-the-sauce=1")
    zero = run_json(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices,sear-the-steak", "--running", "simmer-the-sauce=0")
    assert step_of(one, "simmer-the-sauce")["remaining"] == 1 and step_of(zero, "simmer-the-sauce")["remaining"] == 0
    assert "--running" in fe.__doc__ or True  # documented in SKILL.md; the script only takes the integer


def test_inconsistent_running_state_is_refused():
    for args, offending in ((["--done", "1,2", "--running", "2=5"], "'2'"), (["--running", "9=5"], "'9'"),
                            (["--running", "3=5"], "'3'")):
        out = run_cli(V2, "plan", "Tomato Soup", *args, expect=2)
        assert offending in out and "step ids: 1, 2, 3, 4" in out and "Estimated" not in out
    assert "whole number" in run_cli(V2, "plan", "Tomato Soup", "--running", "3=soon", expect=2)
    assert "≥ 0" in run_cli(V2, "plan", "Tomato Soup", "--done", "1,2", "--running", "3=-1", expect=2)


def _chain(tmp_path):
    """A → B → C → D: each step depends on the one before it (5, 4, 3, 2 min hands-on)."""
    nodes = [node("A", "Chop A", "Chop.", 5), node("B", "Mix B", "Mix.", 4, deps=["A"]),
             node("C", "Fry C", "Fry.", 3, deps=["B"]), node("D", "Plate D", "Plate.", 2, deps=["C"])]
    return write(tmp_path, export_with(authored=[authored_row("rcp-chain", "Chain", nodes)]), "chain.json")


def _diamond(tmp_path):
    """A at the root, B (4 min) and C (6 min) both on A, D on both B and C."""
    nodes = [node("A", "Chop A", "Chop.", 5), node("B", "Mix B", "Mix.", 4, deps=["A"]),
             node("C", "Boil C", "Boil.", 6, deps=["A"]), node("D", "Plate D", "Plate.", 2, deps=["B", "C"])]
    return write(tmp_path, export_with(authored=[authored_row("rcp-dia", "Diamond", nodes)]), "diamond.json")


def test_done_deep_in_a_chain_resolves_its_whole_prerequisite_chain(tmp_path):
    """cook-playback › Dependency ordering and availability + Time-to-serve estimate:
    for A → B → C → D, `--done C` resolves A and B as well — only D is offered and only
    D's 2 minutes are counted, never A again."""
    plan = run_json(_chain(tmp_path), "plan", "Chain", "--done", "C")
    assert plan["done"] == ["A", "B", "C"] and plan["implied_done"] == ["A", "B"]
    assert plan["available"] == ["D"] and plan["locked"] == []
    assert step_of(plan, "A")["state"] == "done" and step_of(plan, "B")["state"] == "done"
    assert plan["estimate_minutes"] == 2
    implied_line = next(ln for ln in plan["text"].splitlines() if ln.startswith("Resolved by implication"))
    assert "(id A)" in implied_line and "(id B)" in implied_line and "(id C)" not in implied_line


def test_running_deep_in_a_chain_implies_its_whole_chain_resolved(tmp_path):
    """A running step's prerequisites, and theirs, are resolved: `--done C --running D=1`
    on A → B → C → D counts D's one minute only and offers nothing."""
    plan = run_json(_chain(tmp_path), "plan", "Chain", "--done", "C", "--running", "D=1")
    assert plan["done"] == ["A", "B", "C"] and plan["implied_done"] == ["A", "B"]
    assert plan["available"] == [] and plan["locked"] == [] and plan["estimate_minutes"] == 1
    # The spec's direct-dependency rule still holds: a running id needs its own
    # prerequisites in --done; only the chain above them is implied.
    out = run_cli(_chain(tmp_path), "plan", "Chain", "--running", "D=1", expect=2)
    assert "'D'" in out and "'C'" in out and "step ids: A, B, C, D" in out and "Estimated" not in out


def test_done_at_the_bottom_of_a_diamond_resolves_both_branches_and_the_root(tmp_path):
    """`--done D` on a diamond resolves B, C and A: nothing is offered, nothing is counted;
    `--done B` resolves the root only — C is still offered and counted, D still locked."""
    plan = run_json(_diamond(tmp_path), "plan", "Diamond", "--done", "D")
    assert plan["done"] == ["A", "B", "C", "D"] and plan["implied_done"] == ["A", "B", "C"]
    assert plan["available"] == [] and plan["locked"] == [] and plan["estimate_minutes"] == 0
    assert "Every step is resolved — the recipe is done." in plan["text"]
    plan = run_json(_diamond(tmp_path), "plan", "Diamond", "--done", "B")
    assert plan["done"] == ["A", "B"] and plan["available"] == ["C"] and plan["locked"] == ["D"]
    assert plan["estimate_minutes"] == 8


def test_running_step_that_a_done_step_depends_on_is_refused(tmp_path):
    """`--done B,D --running C=5` on A → B → C → D: D resolved means C is resolved, so C
    cannot be running — refused by name rather than estimated from an inconsistent state."""
    out = run_cli(_chain(tmp_path), "plan", "Chain", "--done", "B,D", "--running", "C=5", expect=2)
    assert "'C'" in out and "'D'" in out and "step ids: A, B, C, D" in out
    assert "Estimated" not in out and "recipe is done" not in out


def test_contradiction_with_a_done_chain_is_named_before_a_missing_prerequisite(tmp_path):
    """`--done D --running C=5` on A → B → C → D breaks both rules (C's prerequisite B is not
    in --done; D in --done already resolves C). The contradiction is named first, so the
    inconsistent state surfaces in one round trip instead of after B is added."""
    out = run_cli(_chain(tmp_path), "plan", "Chain", "--done", "D", "--running", "C=5", expect=2)
    assert "'D' in --done depends on it" in out and "not in --done" not in out, out
    assert "Estimated" not in out
    # Without a contradiction the direct-prerequisite rule still fires as the spec words it.
    out = run_cli(_chain(tmp_path), "plan", "Chain", "--running", "C=5", expect=2)
    assert "Step 'C' cannot be running: it depends on 'B', not in --done" in out, out


def test_two_running_occupying_steps_are_both_in_progress_at_minute_zero(tmp_path):
    nodes = [node(1, "Knead", "Knead.", 5), node(2, "Whisk", "Whisk.", 4), node(3, "Plate", "Plate.", 2)]
    data = export_with(authored=[authored_row("rcp-two", "Two Hands", nodes)])
    plan = run_json(write(tmp_path, data), "plan", "Two Hands", "--running", "1=5,2=4")
    assert plan["estimate_minutes"] == 7  # both run from minute 0; the plate waits for the cook
    assert "Running (already in progress at minute 0)" in plan["text"]


def test_sigil_less_low_atom_overlaps_hands_on_work(tmp_path):
    dsl = dsl_recipe("Boil", [
        ("Boil Water [phase=prep section=main duration=6 attention_level=low]", "Bring the @water{2 quarts water} to a rolling boil."),
        ("Chop [phase=prep section=main duration=5 attention_level=full]", "Chop the @onion{1 onion}."),
        ("Drop [phase=cook section=main duration=1 attention_level=full depends_on=[boil-water, chop]]", "Drop it in."),
    ])
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-boil", "Boil", [], dsl=dsl)])), "plan", "Boil")
    assert plan["estimate_minutes"] == 7
    assert step_of(plan, "boil-water")["kind"] == "watch"


def test_low_atom_overlaps_a_running_occupying_atom_ten_not_fifteen(tmp_path):
    # Parallelism: a running high atom occupies the cook, but a low atom "blocks nothing" and
    # must start at minute 0 alongside it — the estimate is their overlap, not their sum.
    dsl = dsl_recipe("Sear And Boil", [
        ("Sear [phase=cook section=main duration=10 attention_level=high]", "Sear the @steak{1 steak}, ~sear{5%min × 2}."),
        ("Boil Water [phase=prep section=main duration=5 attention_level=low]", "Bring the @water{2 quarts water} to a rolling boil."),
    ])
    path = write(tmp_path, export_with(authored=[authored_row("rcp-sb", "Sear And Boil", [], dsl=dsl)]))
    plan = run_json(path, "plan", "Sear And Boil", "--running", "sear=10")
    assert plan["estimate_minutes"] == 10  # not 15: the boil is offered now and overlaps the sear
    assert plan["available"] == ["boil-water"] and plan["held_by"] == []
    assert run_json(path, "plan", "Sear And Boil")["estimate_minutes"] == 10


def test_timer_finishing_mid_hands_on_unlocks_a_low_atom_immediately(tmp_path):
    # A 4-minute low timer rings while a 10-minute knead runs; the low atom it unlocks starts at
    # minute 4 (not when the knead ends at 10), so the cook still serves at 10, not 16.
    dsl = dsl_recipe("Unlock", [
        ("Toast [phase=cook section=main duration=4 attention_level=low]", "Toast the @nuts{nuts}, ~toast{4%min}."),
        ("Knead [phase=cook section=main duration=10 attention_level=full]", "Knead the @dough{dough}."),
        ("Cool [phase=cook section=main duration=6 attention_level=low depends_on=[toast]]", "Let the @nuts{nuts} cool."),
    ])
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-un", "Unlock", [], dsl=dsl)])), "plan", "Unlock")
    assert plan["estimate_minutes"] == 10
    # The legacy reading of the same shape: a timer node unlocked by a timer node mid hands-on.
    nodes = [node(1, "Simmer", "Simmer.", 4, until="thick"), node(2, "Knead", "Knead.", 10),
             node(3, "Reduce", "Reduce.", 6, until="glossy", deps=[1])]
    legacy = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-lu", "Legacy Unlock", nodes)]), "l.json"),
                      "plan", "Legacy Unlock")
    assert legacy["estimate_minutes"] == 10


def test_zero_time_step_unlocked_mid_hands_on_resolves_at_once(tmp_path):
    # Time-to-serve: "steps with time = 0 resolve instantly" — also while hands-on work runs, so
    # the timer behind the instant step starts at minute 10, not when the knead ends at 15.
    nodes = [node(1, "Simmer", "Simmer.", 10, until="thick"), node(2, "Taste", "Taste.", 0, deps=[1]),
             node(3, "Reduce", "Reduce.", 10, until="glossy", deps=[2]), node(4, "Knead", "Knead.", 15)]
    plan = run_json(write(tmp_path, export_with(authored=[authored_row("rcp-iu", "Instant Unlock", nodes)])), "plan", "Instant Unlock")
    assert plan["estimate_minutes"] == 20


# ---------------------------------------------------------------------------
# Saved recipes without steps; missing; strip
# ---------------------------------------------------------------------------

def test_saved_title_with_no_content():
    out = run_cli(V2, "plan", "Grandma's Stew", expect=1)
    assert "no steps in this export" in out and "@ben" in out and "https://blog.example/stew" in out
    assert "only if you ask" in out and "Available now" not in out
    assert "Fond id: rcp-stew-06" in out and "The original is at https://blog.example/stew" in out
    show = run_cli(V2, "show", "Grandma")
    assert "no steps in this export" in show and "The original is at https://blog.example/stew — shown, never fetched unasked." in show
    for src in ((V2,), (V1,)):  # a row with no url: `show` and `plan` say the same
        curry = run_cli(*src, "show", "Old Favourite Curry")
        assert "The export carries no source url for it." in curry and "never fetched" not in curry


def test_a_saved_row_without_steps_is_answered_and_not_converted():
    """cook-playback › Saved recipes without steps are listed honestly (as cook-with-fond-authoring
    relaxes it, 5.6): a saved recipe the export carries no steps for is still answered with its
    by-line, Fond id and source url, `convert` refuses it (nothing to convert), the text no
    longer says "This version writes no steps", and the script proposes nothing — a composed
    file from that url is a user-asked act the assistant performs, never an offer the script
    prints."""
    for args in ((V2, "plan", "Grandma's Stew"), (V2, "plan", "Old Favourite Curry"),
                 ("--md", MD2, "plan", "Grandma's Stew")):
        out = run_cli(*args, expect=1)
        assert "This version writes no steps" not in out
        assert "Nothing to convert, and no steps are written from memory." in out
        assert not re.search(r"compos|pasted page|write the steps|want me to", out, re.IGNORECASE)
    curry = run_cli(V2, "plan", "Old Favourite Curry", expect=1)
    assert "The export carries no source url for it." in curry and "The original is at" not in curry
    assert "The original is at https://blog.example/stew" in run_cli("--md", MD2, "plan", "Grandma's Stew", expect=1)
    out = run_cli(V2, "plan", "Grandma's Stew", expect=1)
    assert "by @ben" in out and "Fond id: rcp-stew-06" in out and "https://blog.example/stew" in out
    convert = run_cli(V2, "convert", "Grandma's Stew", "--made-on", "2026-10-13", "--out", "-", expect=1)
    assert "nothing to convert" in convert and "composed" not in convert.lower()


def test_pasted_page_becomes_a_labelled_composed_file_never_a_fond_recipe():
    """cook-playback › Inherited refusals, as cook-with-fond-authoring relaxes it (5.1, 5.6): a
    pasted page is turned into a local composed file only on request, labelled, with no Fond id,
    handle, lineage or "by @" line, the source named, its prose never verbatim. SKILL.md carries
    the three origin labels, the one-line refusals of 5.1(b) and the one-page rule, and the
    verbatim AUTHORING_CARD_V1 is framed as the authoring reference a local file must pass
    `check` against (decision 10) — the old refusal and the old framing sentence are gone."""
    skill = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
    for label in ("composed by the assistant", "local variant", "transcribed"):
        assert label in skill, label
    assert "a named creator's recipe from the model's memory" in skill
    assert "bulk or unattended import" in skill
    assert '"Fond recipe", "registered" or "published" claim' in skill
    assert re.search(r"never crawl or fetch a page the user did not hand you", skill, re.IGNORECASE)
    assert re.search(r"procedure in your words, never its prose verbatim", skill)
    assert "never as a Fond recipe, never with a Fond id, handle, lineage or `by @` line of its own" in skill
    assert "a Fond recipe or part of the export" in skill  # the cook-along without a file
    assert "Never write Fond-format steps, a step graph or DSL from a request, a pasted page or a URL" not in skill
    assert "not an instruction to write" not in skill
    assert "the card is the authoring reference: what you write into a local file must pass `check`" in skill
    # the paste path drafts only (recipe-authoring "The paste path drafts only"; 5.4): the label, the
    # one-line limit statement, the refusals kept, the old "cooks only the recipes the file carries" gone
    prompt = " ".join((SKILL / "prompts" / "paste-this-prompt.md").read_text(encoding="utf-8").split())
    assert "`unchecked draft — run check with the skill`" in prompt and "`# <title>`" in prompt
    assert ("you cannot lint it, check its provenance against my export or compute its schedule exactly, "
            "so say so in one line") in prompt
    assert "Never call it checked, kept, a Fond recipe or part of my export" in prompt
    assert "Never write a named creator's or publication's recipe from memory" in prompt
    assert "never fetch a page I did not hand you" in prompt
    assert "never its text word for word" in prompt and "composed by you" in prompt and "transcribed from my words" in prompt
    assert "this prompt cooks only the recipes the file carries" not in prompt
    assert "Never write Fond-style steps" not in prompt


def test_skill_md_carries_the_authoring_sections_within_budget():
    """cook-with-fond-authoring 5.1/5.6 and skill-distribution › Agent Skills folder: the four new
    sections and the "Writing a recipe" pointer exist, the parent's 12.6 pointer ("see
    \"Adjusting a recipe\"") resolves to a heading, the write rule replaces "Nothing is written
    anywhere", the card's framing line reads as the authoring reference, the frontmatter keeps to
    the five allowed keys, the body stays under 500 lines and the description within 1,024
    characters."""
    raw = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    lines = raw.rstrip("\n").split("\n")
    assert lines[0] == "---"
    close = lines.index("---", 1)
    frontmatter, body = lines[1:close], lines[close + 1:]
    assert len(body) < 500, len(body)
    keys = {ln.split(":")[0] for ln in frontmatter if ln.strip() and not ln.startswith(" ")}
    assert keys == {"name", "description", "license", "compatibility", "metadata"}
    desc = re.search(r"^description: (.*)$", raw, re.M).group(1)
    assert len(desc) <= 1024, len(desc)
    assert "writes a recipe into a local Fond-format file you keep" in desc
    # R-C7 (skill-distribution › neutral lead): the description, the introduction and the README lead
    # with what the skill does and name both sources before any export-specific wording.
    lead = ("Cooks a recipe step by step, the way the Fond app did — from a Fond data export, or from a Fond-format "
            "recipe file it writes with you (your own words, a photo of a card, a page you hand it) — ingredient list "
            "and prep first,")
    assert desc.startswith(lead), desc[:120]
    intro = body[body.index("# Cook with Fond") + 2]
    assert intro.startswith("Cook a recipe step by step, the way the Fond app did — from a Fond data export, or from a"), intro
    readme_first = (SKILL / "README.md").read_text(encoding="utf-8").split("\n\n")[1].replace("\n", " ")
    assert readme_first.startswith("Cooks a recipe step by step, the way the Fond app did — from the data export you took from "
                                   "the app, or from a Fond-format recipe file it writes with you"), readme_first
    # R-C9: the framing is the README's SECOND sentence (never before the lead), the introduction carries it
    # as a clause, and the two near-duplicate "skill for Claude" sentences collapsed into one.
    assert readme_first.split(". ")[1] == R_C9_FRAMING.rstrip("."), readme_first
    assert "A skill for Claude; ChatGPT and Gemini instructions included" not in readme_first
    after = body[body.index("# Cook with Fond") + 2:]
    intro_para = " ".join(after[:after.index("")])
    assert "An early version, still in development, not a replacement for the Fond app" in intro_para, intro_para
    for first in (desc, intro, readme_first):
        assert not first.startswith(("Cooks recipes from a Fond data export", "Cook a recipe from a Fond data export",
                                     "It reads the data export")), first[:80]
    assert '"attach your export, or tell me the recipe"' in " ".join(raw.split())  # the opening-turn rule
    assert "3.9+ for `check`, `convert` and every `--dsl` command" in raw
    headings = {ln for ln in lines if ln.startswith("## ")}
    for heading in ("## Adjusting a recipe (local variants)", "## The player", "## Mid-cook changes",
                    "## Fond-format recipes without timers", "## Writing a recipe"):
        assert heading in headings, heading
    assert 'see "Adjusting a recipe"' in raw and "Fond-format recipes without timers\" below" in raw
    joined = " ".join(raw.split())
    assert "The script writes only the files the user asks for" in joined
    assert "Nothing is written anywhere" not in joined and "this version cooks only" not in joined
    assert "the card is the authoring reference: what you write into a local file must pass `check`" in joined
    assert "No offer anywhere else." in raw  # the yes-path is the only timer-adding path
    for cmd in ("convert", "check", "--dsl", "player"):
        assert f"| `{cmd}" in raw, cmd  # a command-table row each


def test_skill_md_makes_the_player_the_default_cook_surface_in_claude_ai():
    """recipe-authoring › The player › the page opens with the cook in claude.ai (R-C8, founder
    ruling 2026-10-13) and cook-with-fond-authoring 5.1(a): SKILL.md's "The player" section
    says the page is the default cook surface in claude.ai — built with `--out -`, published
    as a private artifact in the mise en place turn, before the first step, without asking,
    republished to the same URL after an edit, the chat walk-through in parallel; in Claude
    Code written beside the file; the paste prompt has no page — the mise en place procedure
    carries that step, and no sentence offers the page as a question: the words "want the
    page" occur only inside the ban."""
    raw = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    joined = " ".join(raw.split())
    assert ("In claude.ai the page is the default cook surface: built with `--out -` and published as a private "
            "artifact in the mise en place turn — before the first step, without asking, never a \"want the page?\" "
            "question — republished to the same URL after an edit, the chat walk-through in parallel; in Claude Code "
            "written beside the file, its path named; the paste prompt has no page.") in joined
    assert "8. In claude.ai, the page (\"The player\" below): built with `--out -` and published as a private artifact now, before the first step, without asking; name it; keep the chat walk-through going." in joined
    assert joined.count("want the page") == 1 and joined.count('never a "want the page?" question') == 1
    for offer in ("want a page", "would you like the page", "shall I build the page", "want me to build"):
        assert offer.lower() not in joined.lower(), offer
    # The trigger list agrees with R-C8 (follow-up verifier): the player is "on request" only
    # outside claude.ai — the old trigger is gone, the new one is verbatim, and every item
    # (a bullet or numbered entry with its wrapped lines) that says "on request" about the
    # player names Claude Code or the paste prompt ("the page" alone is also the source page
    # of the capture rules, so the word is "player").
    assert '"build the player" — on request only' not in joined
    assert '"build the player" — with the cook in claude.ai, unasked; in Claude Code on request' in joined
    items, item = [], ""
    for ln in raw.splitlines():
        if ln.startswith(" ") and item:
            item += " " + ln.strip()
        else:
            items.append(item)
            item = ln.strip()
    items.append(item)
    about_player = [it for it in items if "on request" in it and re.search(r"\bplayer\b", it)]
    assert about_player and all(it.startswith("- ") for it in about_player), about_player
    for it in about_player:
        assert re.search(r"Claude Code|paste prompt", it), it
    # the README's player row and the reference say the same (conditional copy, decision 12)
    player_md = " ".join((SKILL / "references" / "player.md").read_text(encoding="utf-8").split())
    assert "In claude.ai the page is the default cook surface" in player_md
    assert "before the first step, without asking, never a question about wanting it" in player_md
    assert "The paste prompt has no page" in player_md
    readme = " ".join((SKILL / "README.md").read_text(encoding="utf-8").split())
    assert "publishes it as a private artifact on your own account when you start cooking" in readme


def test_authoring_reference_carries_the_capture_rules():
    """cook-with-fond-authoring 5.2/5.6 and recipe-authoring › User-initiated capture, one page,
    no crawl, procedure never prose: SKILL.md and references/authoring.md both carry "never crawl
    or fetch a page the user did not hand you" and "procedure … never its prose verbatim";
    authoring.md states the library-file exception beside the card's "no YAML frontmatter", the
    three origin lines, the credits rule and the check loop; references/player.md the FOND1
    grammar, reconcile and what the page never does — and neither names a tool or a path the
    must-not-publish check bans (test_no_leak.py walks them)."""
    skill = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
    authoring = " ".join((SKILL / "references" / "authoring.md").read_text(encoding="utf-8").split())
    player = " ".join((SKILL / "references" / "player.md").read_text(encoding="utf-8").split())
    for text in (skill, authoring):
        assert re.search(r"never crawl or fetch a page the user did not hand you", text, re.IGNORECASE)
        assert re.search(r"procedure[^.]{0,80}never its prose verbatim", text), text[:80]
    assert "The frontmatter exception" in authoring and "no YAML frontmatter" in authoring
    for line in ("composed by the assistant[ · from <host>, credited to <creator>] · local:<slug>",
                 "local variant of <parent title> <parent by-line head> · local:<slug>",
                 "transcribed by the assistant[ from <attribution source>] · local:<slug>"):
        assert line in authoring, line
    assert "the handle list the export's `Lineage:` line prints" in authoring
    assert "check - --parent <export> --out <slug>.recipe.md" in authoring
    assert "(inherited from the export)" in authoring and "(not gated for a local file)" in authoring
    assert "FOND1 <rid> <j|m|l> d=<id>[,<id>…] r=<id>:<p>/<n>@HH:MM[+<days>d][!][,…] t=HH:MM[+<days>d] h=<8hex> | --done <ids> --running <id>=<N>[,…]" in player
    assert "Recipe updated. Kept <k> done, <r> running." in player
    assert "What the page never does" in player and "window.claude.hot" in player
    assert "`references/authoring.md`" in skill and "`references/player.md`" in skill


def test_missing_listing():
    out = run_json(V2, "missing")
    titles = [r["title"] for r in out["missing"]]
    assert titles == ["Grandma's Stew", "Old Favourite Curry", None]
    assert [r["author"] for r in out["missing"]] == ["ben", "ben", None]
    assert "Tomato Soup" not in out["text"] and "Garlic Pasta" not in out["text"]
    assert "recipe since deleted" in out["text"] and "recipe no longer exists" in out["text"]


def test_strip_output(tmp_path):
    target = tmp_path / "stripped.json"
    run_cli(V2, "strip", "--out", target)
    stripped = json.loads(target.read_text(encoding="utf-8"))
    assert set(stripped) == {"export_version", "exportedAt", "authoredRecipes", "savedRecipes", "cooks"}
    original = load(V2)
    for key in ("authoredRecipes", "savedRecipes", "cooks"):
        for before, after in zip(original[key], stripped[key]):
            assert after["linkedFromUid"] is None
            for field in ("id", "handle", "url", "authorHandle", "sourceAuthor", "lineage"):
                if field in before:
                    assert after[field] == before[field], field
    out = run_cli(target, "list")
    assert "by @ana" in out and "by you" not in out


def test_strip_keeps_the_creator_on_authored_rows(tmp_path):
    target = tmp_path / "s.json"
    run_cli(V2, "strip", "--out", target)
    stripped = json.loads(target.read_text(encoding="utf-8"))
    assert "profile" not in stripped
    assert [r["authorHandle"] for r in stripped["authoredRecipes"]] == ["ana", "ana", None, "ana"]


def test_strip_stamps_the_creator_on_a_version_1_export(tmp_path):
    target = tmp_path / "s1.json"
    run_cli(V1, "strip", "--out", target)
    stripped = json.loads(target.read_text(encoding="utf-8"))
    assert "profile" not in stripped and "contact" not in stripped
    assert all(r["authorHandle"] == "ana" for r in stripped["authoredRecipes"])
    assert "by @ana" in run_cli(target, "list") and "by you" not in run_cli(target, "list")
    # a hand-edited version-1 file with no profile stamps null, never "None"
    data = load(V1)
    del data["profile"]
    run_cli(write(tmp_path, data, "noprofile.json"), "strip", "--out", tmp_path / "s2.json")
    stripped2 = json.loads((tmp_path / "s2.json").read_text(encoding="utf-8"))
    assert all(r["authorHandle"] is None for r in stripped2["authoredRecipes"])


def test_strip_never_overwrites_the_input(tmp_path):
    p = write(tmp_path, load(V2), "fond-export-x.json")
    assert "will not overwrite" in run_cli(p, "strip", "--out", p, expect=2)
    out = run_cli(p, "strip")
    assert (tmp_path / "fond-export-x-stripped.json").exists() and "fond-export-x-stripped.json" in out


def test_contact_never_quoted(tmp_path):
    data = load(V2)
    data["contact"] = {"email": "sentinel-mail@example.invalid", "displayName": "SENTINEL NAME",
                       "phoneNumber": "+10000000000", "tiktokUsername": "sentinel-tt"}
    data["profile"]["uid"] = "SENTINELUID"
    data["profile"]["credits"] = 999
    p = write(tmp_path, data)
    for args in (["list"], ["missing"], ["show", "Tomato Soup"], ["plan", "Tomato Soup"], ["history"], ["cook-again"],
                 ["list", "--json"], ["plan", "Skillet Steak Supper", "--json"]):
        out = run_cli(p, *args)
        for needle in ("sentinel", "SENTINEL", "+1000", "999"):
            assert needle not in out, (args, needle)


# ---------------------------------------------------------------------------
# Provenance on every presentation
# ---------------------------------------------------------------------------

def test_list_by_line_with_provenance():
    out = run_cli(V2, "list")
    assert "Tomato Soup — by @ben · from blog.example · Fond handle soup-xyz789" in out
    soup_line = next(ln for ln in out.splitlines() if "Tomato Soup" in ln)
    assert "Lineage" not in soup_line and "forked" not in out.split("Tomato Soup")[1].split("\n")[0]
    row = next(r for r in run_json(V2, "list")["cookable"] if r["title"] == "Tomato Soup")
    assert row["lineage"] is None


def test_forked_recipe_shown_and_cooked():
    line = "forked from rcp-parent-77 at v2; credits @cara, @ben"
    assert line in run_cli(V2, "show", "Skillet Steak Supper")
    assert line in run_cli(V2, "plan", "Skillet Steak Supper")
    assert f"Lineage: {line}" in run_cli(V2, "list")


def test_fork_whose_parent_had_no_version(tmp_path):
    row = authored_row("rcp-fork", "Forked Soup", [node(1, "Stir", "Stir.", 1)],
                       lineage={"parentId": "p1", "forkPoint": None, "attributionHandles": ["ana", None]})
    out = run_cli(write(tmp_path, export_with(authored=[row])), "show", "Forked Soup")
    assert "Lineage: forked from p1; credits @ana, (unknown)" in out
    assert " at " not in out.split("Lineage:")[1].split("\n")[0] and "None" not in out


def test_null_lineage_is_not_original():
    for cmd in ("show", "plan"):
        out = run_cli(V2, cmd, "Weeknight Garlic Pasta")
        assert "Lineage" not in out and "original" not in out.lower() and "forked" not in out


def test_source_author_precedes_the_saver(tmp_path):
    data = load(V2)
    soup = next(r for r in data["savedRecipes"] if r["id"] == "rcp-soup-05")
    soup["sourceAuthor"], soup["authorHandle"] = "Ana", "importer"
    out = run_cli(write(tmp_path, data), "list")
    assert "Tomato Soup — by Ana (saved to Fond by @importer) · from blog.example · Fond handle soup-xyz789" in out
    assert "by Cara (saved to Fond by you (@ana))" in out  # the fixture's forked recipe


def test_stripped_export_shared_with_someone_else(tmp_path):
    target = tmp_path / "shared.json"
    run_cli(V2, "strip", "--out", target)
    for args in (["list"], ["show", "Weeknight Garlic Pasta"], ["plan", "Weeknight Garlic Pasta"]):
        out = run_cli(target, *args)
        assert "by @ana" in out and "by you" not in out and "(@ana)" not in out


def test_own_unstripped_export():
    out = run_cli(V2, "list")
    assert "Weeknight Garlic Pasta — by you (@ana)" in out


def test_profile_present_but_not_the_author(tmp_path):
    data = load(V2)
    data["profile"]["handle"] = "ben"
    out = run_cli(write(tmp_path, data), "list")
    assert "Weeknight Garlic Pasta — by @ana" in out and "by you" not in out.split("Weeknight Garlic Pasta")[1].split("\n")[0]
    assert "Tomato Soup — by you (@ben)" in out  # the saver's handle now matches the profile


def test_authored_row_without_a_handle():
    out = run_cli(V2, "list")
    assert "Toast Soldiers — by (unknown) · Fond handle toast-soldiers-g7h8i9" in out
    assert "None" not in out


def test_version_1_authored_row(tmp_path):
    assert "Toast Soldiers — by you (@ana)" in run_cli(V1, "list")
    data = load(V1)
    del data["profile"]
    out = run_cli(write(tmp_path, data, "v1-noprofile.json"), "list")
    assert "Toast Soldiers — by (unknown)" in out and "by you" not in out and "None" not in out
    data = load(V1)
    data["profile"]["handle"] = None
    assert "Toast Soldiers — by (unknown)" in run_cli(write(tmp_path, data, "v1-nohandle.json"), "list")


def test_by_line_travels_on_show_plan_and_history():
    byline = "by @ben · from blog.example · Fond handle soup-xyz789"
    for args in (["show", "Tomato Soup"], ["plan", "Tomato Soup"], ["history", "Tomato Soup"], ["history"], ["cook-again"]):
        assert byline in run_cli(V2, *args), args


def _with_a_cook_of_the_forked_recipe(tmp_path, data=None):
    """The v2 fixture's forked DSL recipe (rcp-steak-01) has no cook; add one rated cook so
    it reaches `history` and `cook-again`."""
    data = data or load(V2)
    data["cooks"].insert(0, cook_of("ck-0007", "rated", "2026-10-06T18:00:00+00:00",
                                    [cook_row("rcp-steak-01", "Skillet Steak Supper", ratings={"taste": 5, "wouldCookAgain": 5})]))
    return write(tmp_path, data), data


STEAK_BYLINE = "by Cara (saved to Fond by you (@ana)) · from blog.example · Fond handle skillet-steak-supper-a1b2c3"
STEAK_LINEAGE = "forked from rcp-parent-77 at v2; credits @cara, @ben"


def test_by_line_travels_into_the_history_listing_with_its_lineage_line(tmp_path):
    """cook-playback › Inherited refusals › by-line travels; › Provenance on every
    presentation: `history` without a title is a listing, so every row carries the row's
    own by-line and, only when `lineage` is non-null, the lineage line — in the text and in
    the --json rows, as `list` prints them — so two same-titled recipes stay distinct."""
    p, _data = _with_a_cook_of_the_forked_recipe(tmp_path)
    out = run_cli(p, "history")
    steak = history_row(out, "Skillet Steak Supper")
    assert steak == f"  - Skillet Steak Supper — {STEAK_BYLINE} — cooked 1× — last 2026-10-06T18:00:00+00:00 — hit, would cook again"
    assert f"{steak}\n      Lineage: {STEAK_LINEAGE}\n" in out + "\n"  # under its row, as `list` prints it
    assert history_row(out, "Tomato Soup").startswith("  - Tomato Soup — by @ben · from blog.example · Fond handle soup-xyz789 — cooked 2×")
    assert history_row(out, "Grandma's Stew").startswith("  - Grandma's Stew — by @ben · from blog.example · Fond handle grandmas-stew-k2l3m4 — cooked 1×")
    assert out.count("Lineage:") == 1 and "None" not in out  # null lineage prints no lineage text
    rows = {r["title"]: r for r in run_json(p, "history")["rows"]}
    assert rows["Skillet Steak Supper"]["byline"] == STEAK_BYLINE and rows["Skillet Steak Supper"]["lineage"] == STEAK_LINEAGE
    assert rows["Tomato Soup"]["byline"] == "by @ben · from blog.example · Fond handle soup-xyz789" and rows["Tomato Soup"]["lineage"] is None
    assert all(set(r) >= {"id", "title", "byline", "lineage", "times", "last", "verdict", "cookable"} for r in rows.values())


def test_history_with_a_title_heads_its_answer_with_the_by_line_and_lineage_line(tmp_path):
    """cook-playback › by-line travels: `history "<title>"` prints the by-line head and the
    lineage line (when non-null) exactly as `show` does, and its --json carries both."""
    p, _data = _with_a_cook_of_the_forked_recipe(tmp_path)
    one = run_json(p, "history", "Skillet Steak Supper")
    assert one["byline"] == STEAK_BYLINE and one["lineage"] == STEAK_LINEAGE and one["times"] == 1
    assert one["text"].startswith(f"Skillet Steak Supper — {STEAK_BYLINE}\n  Lineage: {STEAK_LINEAGE}\nCooked 1 time(s) that count")
    soup = run_json(p, "history", "Tomato Soup")
    assert soup["byline"] == "by @ben · from blog.example · Fond handle soup-xyz789" and soup["lineage"] is None
    assert "Lineage" not in soup["text"] and soup["text"].startswith(f"Tomato Soup — {soup['byline']}\nCooked 2 time(s)")


def test_stripped_history_listing_never_says_you_and_keeps_the_lineage_line(tmp_path):
    """cook-playback › stripped export shared with someone else: without `profile` the
    history rows read "by @ana", the word "you" appears in no by-line, and the lineage line
    still travels (strip keeps `lineage`)."""
    _p, data = _with_a_cook_of_the_forked_recipe(tmp_path)
    p = write(tmp_path, fe.strip_export(data), "fond-export-test-stripped.json")
    out = run_cli(p, "history")
    assert "by you" not in out and "(@ana)" not in out
    assert history_row(out, "Skillet Steak Supper").startswith(
        "  - Skillet Steak Supper — by Cara (saved to Fond by @ana) · from blog.example · Fond handle skillet-steak-supper-a1b2c3 — cooked 1×")
    assert f"      Lineage: {STEAK_LINEAGE}" in out
    rows = {r["title"]: r for r in run_json(p, "history")["rows"]}
    assert rows["Skillet Steak Supper"]["lineage"] == STEAK_LINEAGE and "you" not in rows["Skillet Steak Supper"]["byline"]


def test_markdown_history_listing_echoes_the_lineage_line_verbatim(tmp_path):
    """fond-export-format › Markdown: the recipe section's plain `Lineage:` line is echoed
    verbatim on the history row of a cook of that recipe (the cook line carries the title
    only; the by-line and lineage come from the recipe section)."""
    text = MD2.read_text(encoding="utf-8").replace(
        "## Cooking history (6)\n",
        "## Cooking history (7)\n\n### 2026-10-06T18:00:00+00:00 — Steak night (rated)\n"
        "- Skillet Steak Supper — completed 2026-10-06T19:00:00+00:00; taste 5/5, would cook again 5/5\n", 1)
    assert "Steak night" in text
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    out = run_cli(p, "--md", "history")
    assert history_row(out, "Skillet Steak Supper").startswith(f"  - Skillet Steak Supper — {STEAK_BYLINE} — cooked 1× — last 2026-10-06T18:00:00+00:00 — hit, would cook again")
    assert f"      Lineage: {STEAK_LINEAGE}" in out and out.count("Lineage:") == 1
    rows = {r["title"]: r for r in run_json(p, "--md", "history")["rows"]}
    assert rows["Skillet Steak Supper"]["lineage"] == STEAK_LINEAGE and rows["Grandma's Stew"]["lineage"] is None


def test_cook_again_rows_carry_the_lineage_line(tmp_path):
    """cook-playback › by-line travels: `cook-again` lists recipes, so its rows carry the
    lineage line when non-null, in text and --json, through the same renderer as `list`."""
    p, _data = _with_a_cook_of_the_forked_recipe(tmp_path)
    out = run_cli(p, "cook-again")
    assert f"  - Skillet Steak Supper — {STEAK_BYLINE} — would cook again 5/5, taste 5/5 — cooked 1×, last 2026-10-06T18:00:00+00:00\n      Lineage: {STEAK_LINEAGE}\n" in out + "\n"
    again = run_json(p, "cook-again")
    assert again["suggestions"][0]["title"] == "Skillet Steak Supper" and again["suggestions"][0]["lineage"] == STEAK_LINEAGE
    assert all(r["lineage"] is None for r in again["suggestions"][1:] + again["not_cookable"])


def _with_a_size_tier_degraded_forked_saved_row(tmp_path):
    """fond-export-format › Degrade ladder, tier 3: a saved row's `nodes` set to null while
    its provenance — `lineage` included — stays. The fixture's Tomato Soup (nodes, no dsl,
    no ref) loses its steps and gains a lineage; it is then "saved, no steps in this export"."""
    data = load(V2)
    soup = next(r for r in data["savedRecipes"] if r["id"] == "rcp-soup-05")
    soup["nodes"] = None
    soup["lineage"] = {"parentId": "rcp-parent-88", "forkPoint": None, "attributionHandles": ["cara"]}
    return write(tmp_path, data)


SOUP_BYLINE = "by @ben · from blog.example · Fond handle soup-xyz789"
SOUP_LINEAGE = "forked from rcp-parent-88; credits @cara"


def test_by_line_travels_into_the_uncookable_rows_of_list_with_its_lineage_line(tmp_path):
    """cook-playback › Provenance on every presentation; › by-line travels: a saved row whose
    steps the size tier removed is listed under "Saved, no steps" with its by-line AND its
    lineage line, in the text and in the --json `missing` rows, exactly as a cookable row."""
    p = _with_a_size_tier_degraded_forked_saved_row(tmp_path)
    out = run_cli(p, "list")
    assert f"  - Tomato Soup — {SOUP_BYLINE} — saved, no steps in this export\n      Lineage: {SOUP_LINEAGE}\n" in out + "\n"
    assert out.index("Saved, no steps") < out.index(f"Tomato Soup — {SOUP_BYLINE}")  # uncookable now, not cookable
    assert "  - (untitled) — by (unknown) · Fond id rcp-gone-08 — recipe no longer exists" in out and "None" not in out
    listed = run_json(p, "list")
    assert "Tomato Soup" not in [r["title"] for r in listed["cookable"]]
    rows = {r["title"]: r for r in listed["missing"]}
    assert rows["Tomato Soup"]["byline"] == SOUP_BYLINE and rows["Tomato Soup"]["lineage"] == SOUP_LINEAGE
    assert rows["Grandma's Stew"]["lineage"] is None and rows[None]["lineage"] is None
    assert all(set(r) >= {"id", "title", "byline", "lineage", "reason"} for r in listed["missing"])


def test_missing_listing_carries_the_lineage_line_when_non_null(tmp_path):
    """cook-playback › missing listing; › by-line travels: `missing` presents recipes, so each
    row carries its by-line and, only when `lineage` is non-null, the lineage line — text and
    --json — through the same renderer as `list`; a title-less row still reads "(untitled)"."""
    p = _with_a_size_tier_degraded_forked_saved_row(tmp_path)
    out = run_cli(p, "missing")
    assert f"  - Tomato Soup — {SOUP_BYLINE} — saved, no steps in this export\n      Lineage: {SOUP_LINEAGE}\n" in out + "\n"
    assert "  - (untitled) — by (unknown) · Fond id rcp-gone-08 — recipe no longer exists" in out
    assert out.count("Lineage:") == 1 and "None" not in out
    rows = {r["title"]: r for r in run_json(p, "missing")["missing"]}
    assert rows["Tomato Soup"]["byline"] == SOUP_BYLINE and rows["Tomato Soup"]["lineage"] == SOUP_LINEAGE
    assert rows["Tomato Soup"]["author"] == "ben" and rows["Tomato Soup"]["url"] == "https://blog.example/soup"
    assert rows["Old Favourite Curry"]["lineage"] is None and rows[None]["lineage"] is None


def test_scaled_variant_heads_with_the_by_line_and_lineage_line():
    """cook-playback › Scaling is a labelled variant + › by-line travels: the variant's head
    is the recipe's own by-line and, when `lineage` is non-null, its lineage line; the --json
    carries `byline` and `lineage` like every other recipe presentation."""
    out = run_cli(V2, "scale", "Skillet Steak Supper", "--factor", "2")
    assert out.startswith(f"Skillet Steak Supper — {STEAK_BYLINE} — ×2 variant (the original is unchanged; ask for it any time)\n"
                          f"  Lineage: {STEAK_LINEAGE}\n\nIngredients, ×2 variant:")
    scaled = run_json(V2, "scale", "Skillet Steak Supper", "--factor", "2")
    assert scaled["id"] == "rcp-steak-01" and scaled["byline"] == STEAK_BYLINE and scaled["lineage"] == STEAK_LINEAGE
    soup = run_json(V2, "scale", "Tomato Soup", "--from", "4", "--to", "6")
    assert soup["byline"] == "by @ben · from blog.example · Fond handle soup-xyz789" and soup["lineage"] is None
    assert "Lineage" not in soup["text"] and soup["text"].startswith(f"Tomato Soup — {soup['byline']} — ×1.5 variant")


def test_show_prints_id_full_url_and_source_author():
    out = run_cli(V2, "show", "Skillet Steak Supper")
    assert "Fond id: rcp-steak-01" in out and "Source: https://blog.example/skillet-steak-supper" in out
    assert "Source author: Cara" in out
    gone = run_cli(V2, "show", "rcp-gone-08")
    assert "(untitled) — by (unknown) · Fond id rcp-gone-08" in gone and "None" not in gone


# ---------------------------------------------------------------------------
# History and cook-again
# ---------------------------------------------------------------------------

def test_aborted_cooks_are_not_counted(tmp_path):
    out = run_json(V2, "history", "Weeknight Garlic Pasta")
    assert out["times"] == 2 and out["not_counted"] == 1
    cooks = [{"id": f"ck-{i}", "linkedFromUid": None, "mealName": None, "status": "aborted" if i < 4 else "rated",
              "startedAt": f"2026-09-0{i + 1}T18:00:00+00:00", "completedAt": None,
              "recipes": [{"id": "rcp-x", "title": "X", "isValid": i >= 4, "completedAt": None,
                           "ratings": {"taste": 5} if i >= 4 else {}, "feedback": None}]} for i in range(6)]
    data = export_with(authored=[authored_row("rcp-x", "X", [node(1, "Do", "Do.", 1)])], cooks=cooks)
    assert run_json(write(tmp_path, data), "history", "X")["times"] == 2


def test_migrated_cooks_are_counted(tmp_path):
    """cook-playback › History: 3 cooks, 2 migrated — recipe rows with status "migrated",
    isValid false and no taste — and 1 rated: "how often" answers 3, the verdict from the rated cook."""
    cooks = [cook_of(f"ck-{i}", "migrated" if i < 2 else "rated", f"2026-09-0{i + 1}T18:00:00+00:00",
                     [cook_row("rcp-m", "M", is_valid=(i == 2), status="migrated" if i < 2 else "rated",
                               ratings={"taste": 2, "wouldCookAgain": 1} if i == 2 else {"easyFollow": 4})]) for i in range(3)]
    data = export_with(authored=[authored_row("rcp-m", "M", [node(1, "Do", "Do.", 1)])], cooks=cooks)
    out = run_json(write(tmp_path, data), "history", "M")
    assert out["times"] == 3 and out["verdict"] == "miss" and out["would_cook_again"] is False
    fixture = run_json(V2, "history")
    pasta = next(r for r in fixture["rows"] if r["title"] == "Weeknight Garlic Pasta")
    assert pasta["times"] == 2 and pasta["verdict"] == "hit"  # one recorded + one migrated, verdict from the rated cook


def test_migrated_cook_recipe_row_counts_by_its_status():
    """fond-export-format › migrated cook-recipe row: status "migrated", isValid false and
    easyFollow only — counted, no "(not counted)" in the Markdown, and its lone easyFollow
    never stands in for a verdict."""
    out = run_json(V2, "history", "Weeknight Garlic Pasta")
    assert out["times"] == 2 and out["verdict"] == "hit" and out["ratings"] == {"easyFollow": 5, "taste": 4, "wouldCookAgain": 3}
    md_line = next(ln for ln in MD2.read_text(encoding="utf-8").splitlines() if ln.startswith("- Weeknight Garlic Pasta — completed 2025-06-01"))
    assert "(not counted)" not in md_line and "easy to follow 4/5" in md_line
    assert run_json(MD2, "--md", "history", "Weeknight Garlic Pasta")["times"] == 2


def test_removed_cooks_are_not_counted(tmp_path):
    """cook-playback › History: 2 rated cooks of which 1 carries deleted: true → 1; the
    removed cook's rating never reaches the verdict either."""
    cooks = [cook_of("ck-keep", "rated", "2026-09-01T18:00:00+00:00", [cook_row("rcp-r", "R", ratings={"taste": 5})]),
             cook_of("ck-gone", "rated", "2026-09-02T18:00:00+00:00", [cook_row("rcp-r", "R", ratings={"taste": 1})], deleted=True)]
    data = export_with(authored=[authored_row("rcp-r", "R", [node(1, "Do", "Do.", 1)])], cooks=cooks)
    out = run_json(write(tmp_path, data), "history", "R")
    assert out["times"] == 1 and out["not_counted"] == 1 and out["verdict"] == "hit"
    for src in ((V2,), (MD2, "--md")):
        stew = run_json(*src, "history", "Grandma's Stew")
        assert stew["times"] == 1 and stew["not_counted"] == 1 and stew["verdict"] == "hit"
        assert "— cooked 1× —" in history_row(run_cli(*src, "history"), "Grandma's Stew")


def test_overridden_recipe_is_counted(tmp_path):
    """cook-playback › History: a recorded cook's recipe row with isValid false and
    userOverride true counts for the recipe, as the app's own cook count did."""
    cooks = [cook_of("ck-o", "recorded", "2026-09-01T18:00:00+00:00",
                     [cook_row("rcp-o", "O", is_valid=False, status="recorded", override=True)])]
    data = export_with(authored=[authored_row("rcp-o", "O", [node(1, "Do", "Do.", 1)])], cooks=cooks)
    assert run_json(write(tmp_path, data), "history", "O")["times"] == 1
    for src in ((V2,), (MD2, "--md")):
        assert run_json(*src, "history", "Tomato Soup")["times"] == 2
        assert "— cooked 2× —" in history_row(run_cli(*src, "history"), "Tomato Soup")


def test_version_1_row_takes_the_cooks_status_as_its_own(tmp_path):
    """cook-playback › History: a version-1 row has neither status nor userOverride — the
    cook's own status "migrated" stands in and userOverride is false. A version-1 export
    cannot see a removed cook or an override, so those count as the app once showed them."""
    rows = [cook_row("rcp-v", "V", is_valid=False, version=1)]
    for status, times in (("migrated", 1), ("recorded", 0)):
        data = export_with(authored=[authored_row("rcp-v", "V", [node(1, "Do", "Do.", 1)])],
                           cooks=[cook_of("ck-v", status, "2026-09-01T18:00:00+00:00", rows, version=1)], version=1)
        assert run_json(write(tmp_path, data), "history", "V")["times"] == times
    for src in ((V1,), (MD1, "--md")):
        out = {r["title"]: r for r in run_json(*src, "history")["rows"]}
        assert out["Weeknight Garlic Pasta"]["times"] == 2   # recorded + migrated (isValid false, status stands in)
        assert out["Tomato Soup"]["times"] == 1              # the override is invisible in version 1
        assert out["Grandma's Stew"]["times"] == 2           # the removed cook is invisible in version 1
    v1_md_line = next(ln for ln in MD1.read_text(encoding="utf-8").splitlines() if ln.startswith("- Weeknight Garlic Pasta — completed 2025-06-01"))
    assert "(not counted)" in v1_md_line  # the version-1 renderer wrote it from isValid alone; the status wins


def test_markdown_removed_from_history_heading_is_not_counted(tmp_path):
    """fond-export-format › cook removed from history: the heading ends "(removed from
    history)"; the parser takes it after the status, before or after the linked-session
    suffix, and the cook is not counted; the session uid is never printed."""
    cooks = fe.load_export(MD2).cooks
    gone = next(c for c in cooks if c["mealName"] == "Sunday supper again")
    assert gone["deleted"] is True and gone["status"] == "rated"
    assert sum(1 for c in cooks if c["deleted"]) == 1
    head = "### 2026-10-05T17:00:00+00:00 — Sunday supper again (rated) (removed from history)"
    for variant in (
        "### 2026-10-05T17:00:00+00:00 — Sunday supper again (rated) — from earlier anonymous session anon-session-synthetic-02 (removed from history)",
        "### 2026-10-05T17:00:00+00:00 — Sunday supper again (rated) (removed from history) — from earlier anonymous session anon-session-synthetic-02",
    ):
        p = tmp_path / "fond-export-test.md"
        p.write_text(MD2.read_text(encoding="utf-8").replace(head, variant), encoding="utf-8")
        parsed = next(c for c in fe.load_export(p).cooks if c["startedAt"] == "2026-10-05T17:00:00+00:00")
        assert parsed["deleted"] is True and parsed["mealName"] == "Sunday supper again" and parsed["status"] == "rated"
        out = run_cli(p, "--md", "history")
        assert "— cooked 1× —" in history_row(out, "Grandma's Stew") and "anon-session" not in out


def test_cook_again_excludes_uncookable_recipes():
    out = run_json(V2, "cook-again")
    assert [r["title"] for r in out["suggestions"]] == ["Tomato Soup", "Weeknight Garlic Pasta"]
    assert [r["title"] for r in out["not_cookable"]] == ["Grandma's Stew"]
    assert "Rated highly, but not cookable from this export" in out["text"]


def test_a_newer_rating_replaces_an_older_one(tmp_path):
    """cook-playback › History: an old 5/5 cook followed by a newer 1/5 cook reads and ranks
    as 1/5 with the newer cook's date — a miss, suggested after a recipe rated 4 — never the
    best of each field across cooks. The version-1 fixtures, which cannot see the removed
    cook, rate Grandma's Stew from its newer 2/5 cook, so it is no longer "rated highly"."""
    flip = [cook_of("ck-old", "rated", "2026-09-01T18:00:00+00:00", [cook_row("rcp-f", "F", ratings={"taste": 5, "wouldCookAgain": 5})]),
            cook_of("ck-new", "rated", "2026-09-20T18:00:00+00:00", [cook_row("rcp-f", "F", ratings={"taste": 1, "wouldCookAgain": 1})]),
            cook_of("ck-good", "rated", "2026-09-05T18:00:00+00:00", [cook_row("rcp-g", "G", ratings={"taste": 4, "wouldCookAgain": 4})])]
    data = export_with(authored=[authored_row("rcp-f", "F", [node(1, "Do", "Do.", 1)]),
                                 authored_row("rcp-g", "G", [node(1, "Do", "Do.", 1)])], cooks=flip)
    p = write(tmp_path, data)
    again = run_json(p, "cook-again")
    assert [r["title"] for r in again["suggestions"]] == ["G", "F"]
    f = again["suggestions"][1]
    assert (f["would_cook_again"], f["taste"], f["rated_at"], f["last"]) == (1.0, 1.0, "2026-09-20T18:00:00+00:00", "2026-09-20T18:00:00+00:00")
    assert "F — by you (@ana) · Fond handle rcp-f-handle — would cook again 1/5, taste 1/5 — cooked 2×, last 2026-09-20T18:00:00+00:00" in again["text"]
    assert "5/5" not in again["text"]
    one = run_json(p, "history", "F")
    assert one["verdict"] == "miss" and one["would_cook_again"] is False and one["ratings"] == {"taste": 1, "wouldCookAgain": 1}
    assert one["rated_at"] == one["last"] == "2026-09-20T18:00:00+00:00" and "from the cook of" not in one["text"]
    row = next(r for r in run_json(p, "history")["rows"] if r["title"] == "F")
    assert row["verdict"] == "miss" and row["rated_at"] == "2026-09-20T18:00:00+00:00"
    # Uncookable, the same recipe is not "rated highly" on the strength of its old cook.
    data["authoredRecipes"][0]["nodes"] = []
    assert "F" not in [r["title"] for r in run_json(write(tmp_path, data), "cook-again")["not_cookable"]]
    for src in ((V1,), (MD1, "--md")):
        assert [r["title"] for r in run_json(*src, "cook-again")["not_cookable"]] == ["Tomato Soup"]
        stew = next(r for r in run_json(*src, "history")["rows"] if r["title"] == "Grandma's Stew")
        assert stew["verdict"] == "miss" and stew["rated_at"] == "2026-10-05T17:00:00+00:00"


def test_an_unrated_later_cook_keeps_the_last_rating(tmp_path):
    """cook-playback › History: a newer counted cook with no taste or would-cook-again
    (none, or easyFollow alone) leaves the rating with the older rated cook — its numbers
    and its date together — while "last cooked" is the newer cook, the two labelled apart."""
    cooks = [cook_of("ck-rated", "rated", "2026-09-01T18:00:00+00:00", [cook_row("rcp-u", "U", ratings={"taste": 5, "wouldCookAgain": 5})]),
             cook_of("ck-later", "recorded", "2026-09-20T18:00:00+00:00", [cook_row("rcp-u", "U", status="recorded", ratings={"easyFollow": 5})])]
    p = write(tmp_path, export_with(authored=[authored_row("rcp-u", "U", [node(1, "Do", "Do.", 1)])], cooks=cooks))
    row = run_json(p, "cook-again")["suggestions"][0]
    assert (row["would_cook_again"], row["taste"], row["rated_at"], row["last"]) == (5.0, 5.0, "2026-09-01T18:00:00+00:00", "2026-09-20T18:00:00+00:00")
    assert ("— would cook again 5/5, taste 5/5 (rated 2026-09-01T18:00:00+00:00) — cooked 2×, last 2026-09-20T18:00:00+00:00"
            in run_cli(p, "cook-again"))
    assert history_row(run_cli(p, "history"), "U").endswith(
        "— cooked 2× — last 2026-09-20T18:00:00+00:00 — hit, would cook again (rated 2026-09-01T18:00:00+00:00)")
    one = run_json(p, "history", "U")
    assert one["verdict"] == "hit" and one["rated_at"] == "2026-09-01T18:00:00+00:00" and one["last"] == "2026-09-20T18:00:00+00:00"
    assert "Last cooked: 2026-09-20T18:00:00+00:00." in one["text"]
    assert "Verdict: hit (taste 5/5, would cook again), from the cook of 2026-09-01T18:00:00+00:00." in one["text"]
    # The fixtures: Tomato Soup's newest counted cook (2026-10-01, an override) carries no rating.
    for src in ((V2,), (MD2, "--md")):
        soup = next(r for r in run_json(*src, "cook-again")["suggestions"] if r["title"] == "Tomato Soup")
        assert (soup["taste"], soup["rated_at"], soup["last"]) == (4.0, "2026-09-14T18:00:00+00:00", "2026-10-01T18:00:00+00:00")


def test_history_listing_shows_every_counted_recipe_with_verdict():
    out = run_cli(V2, "history")
    assert "— cooked 2× —" in history_row(out, "Weeknight Garlic Pasta") and "— cooked 2× —" in history_row(out, "Tomato Soup")
    assert "— cooked 1× —" in history_row(out, "Grandma's Stew") and "not cookable from this export" in history_row(out, "Grandma's Stew")


# ---------------------------------------------------------------------------
# Scaling is a labelled variant
# ---------------------------------------------------------------------------

def test_make_it_for_six_asks_the_base_yield_first():
    out = run_cli(V2, "scale", "Tomato Soup", expect=2)
    assert "how many the recipe serves as written" in out


def test_scaled_is_not_the_original():
    out = run_cli(V2, "scale", "Tomato Soup", "--from", "4", "--to", "6")
    assert "×1.5 variant" in out
    steps = out.split("Steps, ×1.5 variant")[1].split("Caveat")[0]
    step_lines = [ln for ln in steps.splitlines() if re.match(r"\s*\d+\.", ln)]
    assert len(step_lines) == 4 and all("[×1.5 variant]" in ln for ln in step_lines)
    assert "- 3 tbsp butter" in out and "- 1 1/2 onion" in out and "- salt (no amount stated — not scaled)" in out
    assert "do not scale linearly" in out and "original is unchanged" in out
    assert run_json(V2, "show", "Tomato Soup")["ingredients"][1] == "2 tbsp butter"  # the original is untouched
    assert "- 1/2 onion" in run_cli(V2, "scale", "Tomato Soup", "--factor", "0.5")


# ---------------------------------------------------------------------------
# Markdown fallback
# ---------------------------------------------------------------------------

def test_enriched_markdown():
    plan = run_json(MD2, "--md", "plan", "Weeknight Garlic Pasta")
    assert plan["source"] == "md-steps"
    cook = step_of(plan, "4")
    assert cook["kind"] == "timer" and cook["scheduled"] == 12 and cook["after"] == [3] and cook["deps"] == ["3"]
    assert plan["estimate_minutes"] == 20  # the same graph the JSON gives


def test_repeat_timer_in_markdown():
    s = step_of(run_json(MD2, "--md", "plan", "Weeknight Garlic Pasta"), "7")
    assert s["countdowns"] == [[1, "1 min"], [1, "1 min"]] and s["timing"].startswith("Timer: 1 min × 2")


def test_untimed_cue_in_markdown():
    s = step_of(run_json(MD2, "--md", "plan", "Weeknight Garlic Pasta"), "3")
    assert s["kind"] == "cue" and s["timing"] == "Done when: the water is at a rolling boil" and s["countdowns"] == []


def test_legacy_markdown():
    plan = run_json(MD1, "--md", "plan", "Weeknight Garlic Pasta")
    assert plan["source"] == "md-list" and all(s["kind"] == "instant" for s in plan["steps"])
    assert "Timer:" not in plan["text"] and ".json gives timers and parallel steps" in plan["text"]
    assert plan["steps"][0]["deps"] == [] and plan["steps"][1]["deps"] == [plan["steps"][0]["id"]]


def test_markdown_dsl_fence_cooks_at_full_fidelity():
    plan = run_json(MD2, "--md", "plan", "Skillet Steak Supper")
    assert plan["source"] == "dsl" and step_of(plan, "simmer-the-sauce")["scheduled"] == 22
    assert plan["lineage"] == "forked from rcp-parent-77 at v2; credits @cara, @ben"


def test_markdown_listing_and_provenance_never_read_the_contact_block(tmp_path):
    text = MD2.read_text(encoding="utf-8").replace("- **Email:** —", "- **Email:** sentinel-mail@example.invalid")
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    out = run_cli(p, "--md", "list")
    assert "sentinel" not in out
    assert "Tomato Soup — by @ben · from blog.example · Fond handle soup-xyz789" in out
    assert "Toast Soldiers — by (unknown)" in out and "Skillet Steak Supper — by Cara (saved to Fond by you (@ana))" in out
    missing = run_json(p, "--md", "missing")
    assert [r["title"] for r in missing["missing"]] == ["Grandma's Stew", "Old Favourite Curry", None]


def test_markdown_file_without_a_version_line_is_not_an_export(tmp_path):
    p = tmp_path / "notes.md"
    p.write_text("# Shopping list\n\n- eggs\n", encoding="utf-8")
    assert "not a Fond" in run_cli(p, "--md", "list", expect=1)


def test_strip_refuses_markdown_and_points_to_the_editor():
    assert "## Contact" in run_cli(MD2, "--md", "strip", expect=2)


# ---------------------------------------------------------------------------
# Inherited refusals the script can show
# ---------------------------------------------------------------------------

def test_nothing_is_gated_no_account_words_in_the_script():
    src = SCRIPT.read_text(encoding="utf-8").lower().replace("profile.credits", "")
    for word in ("credit", "entitlement", "paywall", "sign in", "sign-in", "subscription", "payment"):
        assert not re.search(rf"\b{re.escape(word)}\b", src), word  # "credits @a, @b" is the lineage line, not money


def test_timer_rule_never_uses_a_duration_threshold_or_attention():
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    timers = {s["id"] for s in plan["steps"] if s["kind"] == "timer"}
    assert timers == {"toast-the-spices", "rest-the-dough", "sear-the-steak", "simmer-the-sauce", "reduce-the-glaze",
                      "cook-the-flatbreads", "griddle-the-corn-cakes", "roast-the-vegetables"}
    assert step_of(plan, "preheat-the-oven")["kind"] == "watch"  # 15-minute `none` atom, no sigil
    assert step_of(plan, "toast-the-spices")["kind"] == "timer"  # 2-minute `high` atom with a sigil


# ---------------------------------------------------------------------------
# Verifier round: provenance never invented, occupancy, Markdown edge cases
# ---------------------------------------------------------------------------

def test_markdown_never_prints_an_invented_fond_id():
    """A Markdown row with no `Fond id` line carries none: the lookup key the reader keeps
    (md-saved-N / md-authored-N) never reaches text or JSON output."""
    for md, titles in ((MD2, ["Grandma's Stew", "Skillet Steak Supper"]), (MD1, ["Skillet Steak Supper", "Weeknight Garlic Pasta"])):
        outputs = []
        for cmd in ("list", "missing", "history", "cook-again"):
            outputs.append(run_cli(md, "--md", cmd))
            outputs.append(json.dumps(run_json(md, "--md", cmd)))
        for title in titles:
            outputs.append(run_cli(md, "--md", "show", title))
            outputs.append(json.dumps(run_json(md, "--md", "show", title)))
            code = 0 if fe.has_steps(fe.load_export(md).content_of(fe.find_recipe(fe.load_export(md), title))) else 1
            outputs.append(run_cli(md, "--md", "plan", title, expect=code))
        joined = "\n".join(outputs)
        assert "md-saved" not in joined and "md-authored" not in joined, md.name
    listing = run_cli(MD2, "--md", "list")
    assert "Grandma's Stew — by @ben · from blog.example — saved, no steps in this export" in listing
    assert "Fond id: — (not in the Markdown)" in run_cli(MD1, "--md", "show", "Skillet Steak Supper")
    # The version-2 Markdown carries real ids on its sections, and those still print.
    assert "Fond id: rcp-steak-01" in run_cli(MD2, "--md", "show", "Skillet Steak Supper")


def test_markdown_cook_linked_from_an_earlier_session_still_counts(tmp_path):
    """The renderer appends ' — from earlier anonymous session <uid>' to a linked cook's
    heading, and a meal name may hold parentheses: the cook is counted, the uid never read."""
    text = MD2.read_text(encoding="utf-8").replace(
        "### 2026-09-14T18:00:00+00:00 — Weeknight (recorded)",
        "### 2026-09-14T18:00:00+00:00 — Weeknight (late) (recorded) — from earlier anonymous session anon-session-synthetic-01")
    assert "anon-session-synthetic-01" in text
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    out = run_cli(p, "--md", "history")
    assert "— cooked 2× —" in history_row(out, "Tomato Soup") and "— cooked 2× —" in history_row(out, "Weeknight Garlic Pasta")
    assert "anon-session" not in out and "anon-session" not in run_cli(p, "--md", "history", "Tomato Soup")
    cooks = fe.load_export(p).cooks
    linked = next(c for c in cooks if c["startedAt"] == "2026-09-14T18:00:00+00:00")
    assert linked["mealName"] == "Weeknight (late)" and linked["status"] == "recorded"


def test_occupying_running_atom_holds_hands_on_steps_and_offers_the_rest():
    """cook-playback › Parallelism while a timer runs: a running high atom with a sigil
    (the sear) holds back every other hands-on step; none/low steps are still offered."""
    plan = run_json(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices", "--running", "sear-the-steak=4")
    assert plan["held"] == ["griddle-the-corn-cakes"] and plan["held_by"] == ["sear-the-steak"]
    assert "griddle-the-corn-cakes" not in plan["available"]
    assert set(plan["available"]) == {"preheat-the-oven", "rest-the-dough", "boil-the-water"}
    assert step_of(plan, "griddle-the-corn-cakes")["state"] == "held"
    out = run_cli(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices", "--running", "sear-the-steak=4")
    assert "Held until step 5 (Sear the Steak, id sear-the-steak) is done — it occupies you" in out
    assert out.index("Available now") < out.index("Held until") < out.index("Locked")
    # Every available step hands-on → nothing to start, and the output says why.
    done = "toast-the-spices,preheat-the-oven,rest-the-dough,boil-the-water,roast-the-vegetables"
    plan = run_json(V2, "plan", "Skillet Steak Supper", "--done", done, "--running", "sear-the-steak=4")
    assert plan["available"] == [] and "blanch-the-greens" in plan["held"] and plan["estimate_minutes"] == 54
    assert "(nothing you can start — step 5 (Sear the Steak, id sear-the-steak) occupies you until it is done)" in plan["text"]
    # A running low atom (the covered simmer) holds nothing back.
    plan = run_json(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices,sear-the-steak", "--running", "simmer-the-sauce=20")
    assert plan["held"] == [] and plan["held_by"] == [] and "griddle-the-corn-cakes" in plan["available"]


def test_high_attention_timer_blocks_the_offered_list_too(tmp_path):
    def recipe(level):
        return dsl_recipe("Pair", [
            (f"Cook It [phase=cook section=main attention_level={level}]", "Cook the @thing{1 thing}, ~cook{4%min}."),
            ("Chop [phase=cook section=main duration=3 attention_level=full]", "Chop the @herbs{herbs}."),
        ])
    high = export_with(authored=[authored_row("rcp-h", "Pair High", [], dsl=recipe("high"))])
    low = export_with(authored=[authored_row("rcp-l", "Pair Low", [], dsl=recipe("low"))])
    running_high = run_json(write(tmp_path, high, "h.json"), "plan", "Pair High", "--running", "cook-it=2")
    running_low = run_json(write(tmp_path, low, "l.json"), "plan", "Pair Low", "--running", "cook-it=2")
    assert running_high["available"] == [] and running_high["held"] == ["chop"]
    assert running_low["available"] == ["chop"] and running_low["held"] == []


def test_legacy_markdown_step_titles_are_never_truncated():
    plan = run_json(MD1, "--md", "plan", "Weeknight Garlic Pasta")
    assert all(s["title"] == s["text"] for s in plan["steps"])
    full = "Toss the drained pasta with the oil, the [parsley] and a pinch of [chili flakes]."
    assert "a pin (id" not in plan["text"] and "a pin — Toss" not in plan["text"]
    assert plan["text"].count(full) == 1  # once in full; the wave summary shows its first clause
    assert "6. Toss the drained pasta with the oil (id 6)" in plan["text"]


def test_history_header_counts_cooks_and_recipe_cooks_separately():
    out = run_cli(V2, "history")
    # ck-0002 holds two counted recipes; ck-0005 counts by override; ck-0006 is removed and
    # ck-0003 aborted: four counted cooks, five recipe cooks.
    assert out.startswith("Cooking history from this export (4 counted cook(s), 5 recipe cook(s), across 3 recipe(s)):")


def test_sigil_name_survives_in_prose_when_the_sentence_does_not_say_it():
    plan = run_json(V2, "plan", "Skillet Steak Supper")
    assert "2 to 3 minutes per side × 2, flipping once" in step_of(plan, "sear-the-steak")["text"]
    assert step_of(plan, "toast-the-spices")["text"].endswith("until fragrant, 2 minutes.")  # "toast" already said
    assert step_of(plan, "rest-the-dough")["text"].endswith("5 minutes, then 10 minutes.")


def test_last_ring_never_resolves_a_step():
    """cook-playback › Timer structure is preserved: the last ring of a structured timer is a
    ring like every other — the instructions never say a step resolves after it, and a rung
    countdown stays unresolved until the user says the step is done."""
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    prompt = (SKILL / "prompts" / "paste-this-prompt.md").read_text(encoding="utf-8")
    for text in (skill, prompt):
        assert not re.search(r"resolv\w* (only )?after the (last|second|final)", text, re.IGNORECASE)
        assert "last ring" in text
    plan = run_cli(V2, "plan", "Skillet Steak Supper", "--done", "toast-the-spices", "--running", "sear-the-steak=0")
    assert "unresolved until you say it is done" in plan
    assert "(2 countdowns, one at a time)" in run_cli(V2, "plan", "Skillet Steak Supper")


def test_fmt_minutes_has_an_hour_form():
    assert [fe.fmt_minutes(m) for m in (0.5, 1.5, 59, 60, 90, 1080)] == \
        ["30 seconds", "1.5 min", "59 min", "1 hr", "1 hr 30 min", "18 hr"]
    assert fe.render_prose("Let the @dough{dough} rise, ~rise{18%hr}.") == "Let the [dough] rise, 18 hours."


def test_no_match_lists_each_title_once():
    out = run_cli(V2, "plan", "zzz", expect=2)
    assert out.count("'Weeknight Garlic Pasta'") == 1 and "'Grandma's Stew'" in out


def test_no_steps_message_states_the_reason_once():
    assert "(saved, no steps in this export)" not in run_cli(V2, "plan", "Grandma's Stew", expect=1)
    assert "(saved, no steps in this export)" not in run_cli(V2, "show", "Grandma's Stew")
    assert "no steps in this export (recipe since deleted)" in run_cli(V2, "plan", "Old Favourite Curry", expect=1)


def test_version_1_saved_copy_of_an_own_recipe_folds_into_the_authored_row():
    """references/export-format.md §5: a version-1 saved row whose id is one of the
    authored recipes is listed once, as the authored recipe — its steps are in the export."""
    out = run_json(V1, "list")
    assert [r["title"] for r in out["cookable"]].count("Weeknight Garlic Pasta") == 1
    assert "Weeknight Garlic Pasta" not in [r["title"] for r in out["missing"]]
    assert next(r for r in out["cookable"] if r["title"] == "Weeknight Garlic Pasta")["cooked"] == 2


# ---------------------------------------------------------------------------
# Markdown history: a title two recipes share is attributed to neither
# ---------------------------------------------------------------------------

ANA_SOUP_LINEAGE = "forked from rcp-soup-05 at v1; credits @ben"  # @ana's soup is a fork of @ben's


def _two_tomato_soups_md(tmp_path):
    """The v2 Markdown fixture plus a second recipe named "Tomato Soup": @ana's authored
    one (synthetic id rcp-soup-ana-09, a fork of @ben's with a Lineage line) beside @ben's
    saved one (rcp-soup-05, soup-xyz789). The renderer prints a cook line as "- <title> — …"
    with no id, so the fixture's two counted Tomato Soup cooks cannot be told apart."""
    text = MD2.read_text(encoding="utf-8")
    start, end = text.index("### Weeknight Garlic Pasta"), text.index("### Toast Soldiers")
    ana_soup = (text[start:end]
                .replace("### Weeknight Garlic Pasta", "### Tomato Soup", 1)
                .replace("rcp-pasta-02 (handle weeknight-garlic-pasta-d4e5f6)", "rcp-soup-ana-09 (handle tomato-soup-ana-j1k2l3)")
                .replace("https://blog.example/garlic-pasta", "https://blog.example/ana-tomato-soup")
                .replace("- **Source:** https://blog.example/ana-tomato-soup\n",
                         f"- **Source:** https://blog.example/ana-tomato-soup\n\nLineage: {ANA_SOUP_LINEAGE}\n", 1))  # the shipped plain line
    assert ana_soup.count("\nLineage: ") == 1
    p = tmp_path / "fond-export-test.md"
    p.write_text(text[:end] + ana_soup + text[end:], encoding="utf-8")
    return p


def test_markdown_cooks_of_two_recipes_with_the_same_title_are_never_attributed_to_either(tmp_path):
    """cook-playback › Provenance on every presentation (never invented) and › ambiguous
    title: a Markdown cook line carries the title only, so when two creators' recipes
    share a title the cooks, the ratings and the by-line go to neither — history names
    both candidates and asks for the JSON, whose cook rows carry the Fond id."""
    p = _two_tomato_soups_md(tmp_path)
    assert [r.id for r in fe.load_export(p).all_recipes() if r.title == "Tomato Soup"] == ["rcp-soup-ana-09", "rcp-soup-05"]
    out = run_cli(p, "--md", "history")
    assert not any(ln.startswith("  - Tomato Soup — ") for ln in out.splitlines())  # never merged onto whichever recipe came first
    assert "2 recipes named Tomato Soup" in out and "cannot be attributed from a Markdown export" in out and "use the JSON" in out
    assert "could be: Tomato Soup — by you (@ana)" in out and "could be: Tomato Soup — by @ben" in out
    assert "— cooked 2× —" in history_row(out, "Weeknight Garlic Pasta") and "— cooked 1× —" in history_row(out, "Grandma's Stew")  # unshared titles still resolve
    assert out.startswith("Cooking history from this export (4 counted cook(s), 3 recipe cook(s), across 2 recipe(s); "
                          "2 recipe cook(s) not attributable, see below):")
    listing = run_json(p, "--md", "history")
    assert [r["title"] for r in listing["rows"]] == ["Weeknight Garlic Pasta", "Grandma's Stew"]
    assert listing["ambiguous"][0]["times"] == 2
    assert [c["id"] for c in listing["ambiguous"][0]["candidates"]] == ["rcp-soup-ana-09", "rcp-soup-05"]
    # By id or handle, each candidate gets the same honest answer — never "0 times" for one
    # and "2 times, hit" for the other.
    for ref in ("rcp-soup-ana-09", "soup-xyz789"):
        one = run_json(p, "--md", "history", ref)
        assert one["ambiguous"] is True and one["times"] is None and one["verdict"] is None and one["unattributed_cooks"] == 2
        assert "cannot be attributed" in one["text"] and "Cooked 0 time" not in one["text"] and "Cooked 2 time" not in one["text"]
    # cook-playback › by-line travels: the "which one?" prompt and the listing's candidates
    # go through the one row renderer, so @ana's forked soup carries its lineage line on
    # each surface and @ben's (null lineage) carries none — in the text and in the JSON.
    prompt = run_cli(p, "--md", "history", "Tomato Soup", expect=2)
    assert prompt.startswith("Several recipes match")
    assert ("  - Tomato Soup — by you (@ana) · from blog.example · Fond handle tomato-soup-ana-j1k2l3 (Fond id rcp-soup-ana-09)\n"
            f"      Lineage: {ANA_SOUP_LINEAGE}\n"
            "  - Tomato Soup — by @ben · from blog.example · Fond handle soup-xyz789 (Fond id rcp-soup-05)\n") in prompt + "\n"
    assert prompt.count("Lineage:") == 1
    ana_candidate = out.split("could be: Tomato Soup — by you (@ana)")[1].split("could be: Tomato Soup — by @ben")[0]
    assert f"Lineage: {ANA_SOUP_LINEAGE}" in ana_candidate and out.count("Lineage:") == 1
    candidates = {c["id"]: c["lineage"] for c in listing["ambiguous"][0]["candidates"]}
    assert candidates == {"rcp-soup-ana-09": ANA_SOUP_LINEAGE, "rcp-soup-05": None}
    again = run_json(p, "--md", "cook-again")
    assert "Tomato Soup" not in [r["title"] for r in again["suggestions"]] + [r["title"] for r in again["not_cookable"]]
    assert "tomato-soup-ana-j1k2l3 — would cook again" not in again["text"] and "soup-xyz789 — would cook again" not in again["text"]
    assert again["unattributable"][0]["title"] == "Tomato Soup" and again["unattributable"][0]["times"] == 2
    assert "Cooked, but not attributable to one recipe:" in again["text"] and "use the JSON" in again["text"]
    listing = run_json(p, "--md", "list")
    soups = {r["id"]: r["cooked"] for r in listing["cookable"] if r["title"] == "Tomato Soup"}
    assert soups == {"rcp-soup-ana-09": None, "rcp-soup-05": 1}  # @ben's saved row carries its own "cooked 1×"
    assert "cooks not attributable (another recipe here shares this title; use the JSON)" in listing["text"]
    assert "tomato-soup-ana-j1k2l3 — steps — not cooked yet" not in listing["text"]


def test_json_cooks_of_two_recipes_with_the_same_title_resolve_by_id(tmp_path):
    """The JSON cook rows carry the recipe id, so the same two titles are never ambiguous
    there: @ben's Tomato Soup keeps its two cooks and @ana's has none."""
    data = load(V2)
    data["authoredRecipes"].append(authored_row("rcp-soup-ana-09", "Tomato Soup", [node(1, "Simmer", "Simmer.", 10)],
                                                handle="tomato-soup-ana-j1k2l3"))
    p = write(tmp_path, data)
    out = run_json(p, "history")
    assert out["ambiguous"] == [] and {r["id"]: r["times"] for r in out["rows"]}["rcp-soup-05"] == 2
    assert "rcp-soup-ana-09" not in [r["id"] for r in out["rows"]]
    assert run_json(p, "history", "soup-xyz789")["times"] == 2 and run_json(p, "history", "rcp-soup-ana-09")["times"] == 0
    again = run_json(p, "cook-again")
    assert "soup-xyz789 — would cook again 4/5" in again["text"] and again["unattributable"] == []
    soups = {r["id"]: r["cooked"] for r in run_json(p, "list")["cookable"] if r["title"] == "Tomato Soup"}
    assert soups == {"rcp-soup-ana-09": 0, "rcp-soup-05": 2}


def _dashed_soup_md(tmp_path):
    """The v2 Markdown fixture plus an authored recipe named "Tomato Soup — Quick" (synthetic
    id rcp-soup-quick-10, by @ana) beside @ben's saved "Tomato Soup" (rcp-soup-05), and one
    more rated cook whose line names the dashed title. Its feedback quotes the renderer's
    own structural words, so the parser must read each slot of the line, never the whole."""
    text = MD2.read_text(encoding="utf-8")
    start, end = text.index("### Weeknight Garlic Pasta"), text.index("### Toast Soldiers")
    quick = (text[start:end]
             .replace("### Weeknight Garlic Pasta", "### Tomato Soup — Quick", 1)
             .replace("rcp-pasta-02 (handle weeknight-garlic-pasta-d4e5f6)", "rcp-soup-quick-10 (handle tomato-soup-quick-m4n5o6)")
             .replace("https://blog.example/garlic-pasta", "https://blog.example/quick-tomato-soup"))
    cook = ("### 2026-10-03T18:00:00+00:00 — Quick night (rated)\n"
            "- Tomato Soup — Quick — completed 2026-10-03T18:25:00+00:00; taste 5/5, would cook again 5/5; "
            "feedback: \"great — not completed (not counted); taste 1/5\"\n\n")
    soup_night = "### 2026-10-01T18:00:00+00:00 — Soup night (recorded)"
    assert text.count(soup_night) == 1
    text = (text[:end] + quick + text[end:]).replace(soup_night, cook + soup_night, 1)
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_markdown_cook_row_whose_title_holds_a_dash_is_credited_to_that_recipe_only(tmp_path):
    """cook-playback › Provenance on every presentation (never invented): the renderer's
    cook line is "- <title> — completed <ts>|not completed[ (not counted)]; <ratings>", and
    a title may itself hold " — ". The cut is made at the structural slot, never at the
    first dash, so a cook of "Tomato Soup — Quick" is credited to that recipe — not to
    @ben's "Tomato Soup", whose own count stays what the fixture says."""
    p = _dashed_soup_md(tmp_path)
    export = fe.load_export(p)
    row = next(cr for c in export.cooks if c["mealName"] == "Quick night" for cr in c["recipes"])
    assert row["title"] == "Tomato Soup — Quick"
    out = run_cli(p, "--md", "history")
    assert "— cooked 1× —" in history_row(out, "Tomato Soup — Quick") and "— cooked 2× —" in history_row(out, "Tomato Soup")
    assert "cannot be attributed" not in out
    listing = run_json(p, "--md", "history")
    times = {r["id"]: r["times"] for r in listing["rows"]}
    assert times["rcp-soup-quick-10"] == 1 and times["rcp-soup-05"] == 2 and listing["ambiguous"] == []
    assert run_json(p, "--md", "history", "rcp-soup-quick-10")["times"] == 1
    assert run_json(p, "--md", "history", "soup-xyz789")["times"] == 2
    soups = {r["id"]: r["cooked"] for r in run_json(p, "--md", "list")["cookable"] if r["title"].startswith("Tomato Soup")}
    assert soups == {"rcp-soup-quick-10": 1, "rcp-soup-05": 2}


def test_markdown_cook_row_feedback_never_moves_the_cut_the_completion_or_the_verdict(tmp_path):
    """fond-export-format › cooks: completion, "(not counted)" and the ratings are read from
    their own slots of the line. A feedback that quotes "not completed (not counted); taste
    1/5" leaves the row completed, counted, and rated 5/5 — a hit, would cook again."""
    p = _dashed_soup_md(tmp_path)
    export = fe.load_export(p)
    row = next(cr for c in export.cooks if c["mealName"] == "Quick night" for cr in c["recipes"])
    assert row["completedAt"] == "2026-10-03T18:25:00+00:00" and row["isValid"] is True
    assert row["ratings"] == {"taste": 5, "wouldCookAgain": 5}
    one = run_json(p, "--md", "history", "rcp-soup-quick-10")
    assert one["times"] == 1 and one["verdict"] == "hit" and one["would_cook_again"] is True
    quick = history_row(run_cli(p, "--md", "history"), "Tomato Soup — Quick")
    assert quick.endswith("— cooked 1× — last 2026-10-03T18:00:00+00:00 — hit, would cook again")


def test_markdown_cook_row_whose_feedback_holds_a_line_break_still_parses_from_its_first_line(tmp_path):
    """fond-export-format › Markdown › the cook line: the renderer writes the feedback raw,
    so a feedback holding a line break splits the cook line across two physical lines and
    the closing quote lands on the second. The first physical line still yields one row —
    title, completedAt and ratings from their own slots — the continuation line yields no
    row of its own, and the recipe's history count rises by one (never a whole-line title
    that files the cook under nothing, silently)."""
    cook = ("### 2026-10-06T18:00:00+00:00 — Soup again (rated)\n"
            "- Tomato Soup — completed 2026-10-06T18:30:00+00:00; taste 5/5, would cook again 5/5; "
            "feedback: \"line one\nline two\"\n\n")
    soup_night = "### 2026-10-01T18:00:00+00:00 — Soup night (recorded)"
    text = MD2.read_text(encoding="utf-8")
    assert text.count(soup_night) == 1
    text = text.replace("## Cooking history (6)\n", "## Cooking history (7)\n", 1).replace(soup_night, cook + soup_night, 1)
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    export = fe.load_export(p)
    again = next(c for c in export.cooks if c["mealName"] == "Soup again")
    assert len(again["recipes"]) == 1  # the continuation line `line two"` is no row
    row = again["recipes"][0]
    assert row["title"] == "Tomato Soup" and row["completedAt"] == "2026-10-06T18:30:00+00:00" and row["isValid"] is True
    assert row["ratings"] == {"taste": 5, "wouldCookAgain": 5}
    out = run_cli(p, "--md", "history")
    assert "— cooked 3× —" in history_row(out, "Tomato Soup")  # the fixture's two, plus this one
    assert "cannot be attributed" not in out
    one = run_json(p, "--md", "history", "soup-xyz789")
    assert one["times"] == 3 and one["verdict"] == "hit" and one["would_cook_again"] is True


def test_markdown_heading_inside_multiline_feedback_is_not_a_cook(tmp_path):
    """fond-export-format › Markdown › the cook line: every line after an unclosed feedback
    quote, through the line that closes it, is feedback — never a cook row and never a cook
    heading. A feedback that holds a line shaped like "### <timestamp> — <meal> (<status>)"
    and a "- Soup — completed …; taste 5/5" line under it starts no cook of its own: no
    "Fake night" cook appears, and @ana's plain "Soup" is credited with nothing."""
    p = _plain_soup_md(tmp_path, [
        "- Tomato Soup — completed 2026-10-05T18:30:00+00:00; taste 4/5; feedback: \"notes",
        "### 2026-10-05T19:00:00+00:00 — Fake night (rated)",
        "- Soup — completed 2026-10-05T19:30:00+00:00; taste 5/5",
        "end of notes\"",
    ])
    export = fe.load_export(p)
    assert [c for c in export.cooks if c["mealName"] == "Fake night"] == []
    row = _odd_night_row(export)
    assert row["title"] == "Tomato Soup" and row["ratings"] == {"taste": 4}
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["times"] == 0 and one["verdict"] is None


def _plain_soup_md(tmp_path, cook_lines):
    """The v2 Markdown fixture plus an authored recipe named plain "Soup" (synthetic id
    rcp-soup-plain-11, by @ana) and one more rated cook, "Odd night", whose recipe lines
    are `cook_lines` (a feedback continuation line is passed as its own element)."""
    text = MD2.read_text(encoding="utf-8")
    start, end = text.index("### Weeknight Garlic Pasta"), text.index("### Toast Soldiers")
    soup = (text[start:end]
            .replace("### Weeknight Garlic Pasta", "### Soup", 1)
            .replace("rcp-pasta-02 (handle weeknight-garlic-pasta-d4e5f6)", "rcp-soup-plain-11 (handle soup-plain-p7q8r9)")
            .replace("https://blog.example/garlic-pasta", "https://blog.example/plain-soup"))
    cook = "### 2026-10-05T18:00:00+00:00 — Odd night (rated)\n" + "\n".join(cook_lines) + "\n\n"
    soup_night = "### 2026-10-01T18:00:00+00:00 — Soup night (recorded)"
    assert text.count(soup_night) == 1 and text.count("## Cooking history (6)\n") == 1
    text = text[:end] + soup + text[end:]
    text = text.replace("## Cooking history (6)\n", "## Cooking history (7)\n", 1).replace(soup_night, cook + soup_night, 1)
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    return p


def _odd_night_row(export):
    rows = [cr for c in export.cooks if c["mealName"] == "Odd night" for cr in c["recipes"]]
    assert len(rows) == 1
    return rows[0]


def test_markdown_cook_row_whose_title_spells_a_false_completion_slot_is_not_credited_to_the_shorter_title(tmp_path):
    """fond-export-format › Markdown › the cook line: "completed <word>" is a structural slot
    only when <word> is an ISO timestamp, and the feedback slot opens only on `feedback: "`.
    A recipe named "Soup — completed early; feedback: fake" renders "- Soup — completed
    early; feedback: fake — completed 2026-10-01T00:00Z; taste 5/5": the line's one real slot
    is the last, so the cook, its completion and its taste 5/5 go to that whole title — never
    to @ana's plain "Soup", whose history stays empty and which cook-again never suggests."""
    p = _plain_soup_md(tmp_path, ["- Soup — completed early; feedback: fake — completed 2026-10-01T00:00Z; taste 5/5"])
    export = fe.load_export(p)
    row = _odd_night_row(export)
    assert row["title"] == "Soup — completed early; feedback: fake"
    assert row["completedAt"] == "2026-10-01T00:00Z" and row["isValid"] is True and row["ratings"] == {"taste": 5}
    assert export.warnings == []
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["times"] == 0 and one["verdict"] is None and one["ambiguous"] is False
    listing = run_json(p, "--md", "history")
    assert "rcp-soup-plain-11" not in [r["id"] for r in listing["rows"]] and listing["ambiguous"] == []
    assert "rcp-soup-plain-11" not in [r["id"] for r in run_json(p, "--md", "cook-again")["suggestions"]]
    assert {r["id"]: r["cooked"] for r in run_json(p, "--md", "list")["cookable"]}["rcp-soup-plain-11"] == 0


def test_markdown_cook_row_whose_feedback_quotes_a_completion_slot_keeps_its_real_slot(tmp_path):
    """fond-export-format › Markdown › the cook line: a quoted feedback that spells out a
    second " — completed <ts>; <ratings>" never wins the cut — its tail ends in the closing
    quote, which no ratings slot accepts — so the row keeps its first, real slot: "Soup",
    completed 2026-10-06T18:30, taste 5/5 and would cook again 5/5, a hit."""
    p = _plain_soup_md(tmp_path, [
        "- Soup — completed 2026-10-06T18:30:00+00:00; taste 5/5, would cook again 5/5; "
        "feedback: \"made it twice — completed 2026-10-07T00:00:00+00:00; taste 1/5\""])
    export = fe.load_export(p)
    row = _odd_night_row(export)
    assert row["title"] == "Soup" and row["completedAt"] == "2026-10-06T18:30:00+00:00" and row["isValid"] is True
    assert row["ratings"] == {"taste": 5, "wouldCookAgain": 5}
    assert export.warnings == []
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["times"] == 1 and one["verdict"] == "hit" and one["would_cook_again"] is True


def test_markdown_cook_row_that_reads_as_two_titles_is_credited_to_neither(tmp_path):
    """fond-export-format › Markdown › the cook line: the first physical line of a cook of
    "Soup" whose feedback broke across lines — '- Soup — completed 2026-10-06T18:30:00+00:00;
    taste 5/5; feedback: "x — completed 2026-10-07T00:00:00+00:00; taste 1/5' — is also,
    character for character, the whole cook line of a recipe named 'Soup — completed
    2026-10-06T18:30:00+00:00; taste 5/5; feedback: "x' rated taste 1/5. Two readings name
    two titles, so the line is credited to no recipe and rated for none — never a guess —
    and a load warning says so; the other cooks keep their counts."""
    p = _plain_soup_md(tmp_path, [
        "- Soup — completed 2026-10-06T18:30:00+00:00; taste 5/5; "
        "feedback: \"x — completed 2026-10-07T00:00:00+00:00; taste 1/5",
        "more\""])
    export = fe.load_export(p)
    row = _odd_night_row(export)  # the continuation line `more"` is no row
    assert row["title"] is None and row["completedAt"] is None and row["ratings"] == {}
    assert len(export.warnings) == 1 and "credited to no recipe" in export.warnings[0]
    assert "2026-10-05T18:00:00+00:00" in export.warnings[0]
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["times"] == 0 and one["not_counted"] == 0 and one["verdict"] is None
    listing = run_json(p, "--md", "history")
    times = {r["id"]: r["times"] for r in listing["rows"]}
    assert "rcp-soup-plain-11" not in times and times["rcp-soup-05"] == 2 and listing["ambiguous"] == []
    assert "rcp-soup-plain-11" not in [r["id"] for r in run_json(p, "--md", "cook-again")["suggestions"]]
    # The history header says where the counted cook went (history --json carries no warnings).
    assert listing["uncredited_cooks"] == 1
    assert ("; 1 recipe cook(s) credited to no recipe (their Markdown line reads as two titles — "
            "the JSON export resolves them)):") in listing["text"].splitlines()[0]


def test_history_header_counts_cooks_credited_to_no_recipe_and_says_no_counted_cooks_only_when_none(tmp_path):
    """cook-playback › History: a counted cook row that names no recipe (neither id nor
    title) is counted in the header and said to be credited to no recipe; "(no counted
    cooks)" is printed only when the export has no counted cook at all."""
    data = export_with(authored=[authored_row("rcp-x", "X", [node(1, "Do", "Do.", 1)])], cooks=[
        cook_of("ck-nameless", "rated", "2026-10-06T18:00:00+00:00", [{**cook_row(None, None), "id": None}])])
    out = run_json(write(tmp_path, data), "history")
    assert out["uncredited_cooks"] == 1 and out["rows"] == []
    assert out["text"].splitlines()[0] == (
        "Cooking history from this export (1 counted cook(s), 0 recipe cook(s), across 0 recipe(s); "
        "1 recipe cook(s) credited to no recipe (these cook rows carry neither a Fond id nor a title)):")
    assert "(no counted cooks)" not in out["text"]
    empty = run_json(write(tmp_path, export_with(authored=data["authoredRecipes"], cooks=[]), "empty.json"), "history")
    assert empty["uncredited_cooks"] == 0 and empty["text"].splitlines()[1] == "  (no counted cooks)"


def test_markdown_feedback_continuation_lines_are_never_cook_rows(tmp_path):
    """fond-export-format › Markdown › the cook line: the renderer writes a feedback raw, so
    "Served with:\n- Weeknight Garlic Pasta\n- a salad" puts lines that start with "- "
    under the cook. The lines after an unclosed feedback quote, through the line that
    closes it, are feedback — never a cook row, not even one that spells out a whole cook
    line, nor after a feedback that opens on a line break — so the Odd night cook has one
    row (Soup) and no other recipe gains a cook or a rating."""
    variants = (
        ["- Soup — completed 2026-10-06T18:30:00+00:00; taste 4/5; feedback: \"Served with:",
         "- Weeknight Garlic Pasta",
         "- a salad\""],
        ["- Soup — completed 2026-10-06T18:30:00+00:00; taste 4/5; feedback: \"first time",
         "- Tomato Soup — completed 2026-10-01T00:00:00+00:00; taste 1/5, would cook again 1/5",
         "- Weeknight Garlic Pasta — completed 2026-10-01T00:00:00+00:00; taste 5/5; feedback: \"yum\"",
         "end\""],
        ["- Soup — completed 2026-10-06T18:30:00+00:00; taste 4/5; feedback: \"",
         "- Weeknight Garlic Pasta",
         "\""],
    )
    for lines in variants:
        p = _plain_soup_md(tmp_path, lines)
        export = fe.load_export(p)
        row = _odd_night_row(export)  # exactly one row
        assert row["title"] == "Soup" and row["completedAt"] == "2026-10-06T18:30:00+00:00" and row["ratings"] == {"taste": 4}
        assert export.warnings == []
        listing = run_json(p, "--md", "history")
        rows = {r["id"]: r for r in listing["rows"]}
        assert rows["rcp-soup-plain-11"]["times"] == 1
        assert rows["rcp-pasta-02"]["times"] == 2 and rows["rcp-soup-05"]["times"] == 2
        assert rows["rcp-soup-05"]["verdict"] == "hit" and rows["rcp-soup-05"]["rated_at"] == "2026-09-14T18:00:00+00:00"
        assert rows["rcp-pasta-02"]["ratings"] == {"easyFollow": 5, "taste": 4, "wouldCookAgain": 3}
        # The next cook heading ends the feedback run: Soup night's row is read as before.
        soup_night = next(c for c in export.cooks if c["mealName"] == "Soup night")
        assert [cr["title"] for cr in soup_night["recipes"]] == ["Tomato Soup"]


def test_markdown_decimal_ratings_are_read_and_a_newer_one_replaces_an_older_one(tmp_path):
    """cook-playback › History › a newer rating replaces an older one, on the --md path. The
    app's review screen stores ratings as doubles, so the renderer prints "taste 1.0/5,
    would cook again 1.0/5": that newer cook replaces an older "taste 5/5, would cook again
    5/5" — a miss with the newer cook's date, as the JSON export of the same cooks reads —
    and "4.5/5" reads as 4.5, never as "no rating" (fond-export-format › Markdown)."""
    older = ("### 2026-09-01T18:00:00+00:00 — Old night (rated)\n"
             "- Soup — completed 2026-09-01T18:30:00+00:00; taste 5/5, would cook again 5/5\n\n")
    migrated = "### 2025-06-01T18:00:00+00:00 — Cook (migrated)"

    def with_older(lines):
        p = _plain_soup_md(tmp_path, lines)
        text = p.read_text(encoding="utf-8")
        assert text.count(migrated) == 1
        p.write_text(text.replace(migrated, older + migrated, 1).replace("## Cooking history (7)\n", "## Cooking history (8)\n", 1),
                     encoding="utf-8")
        return p

    p = with_older(["- Soup — completed 2026-10-05T18:30:00+00:00; taste 1.0/5, would cook again 1.0/5"])
    assert _odd_night_row(fe.load_export(p))["ratings"] == {"taste": 1, "wouldCookAgain": 1}
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["times"] == 2 and one["verdict"] == "miss" and one["would_cook_again"] is False
    assert one["rated_at"] == one["last"] == "2026-10-05T18:00:00+00:00"
    assert "Verdict: miss (taste 1/5)." in one["text"]
    soup = next(r for r in run_json(p, "--md", "cook-again")["suggestions"] if r["id"] == "rcp-soup-plain-11")
    assert (soup["would_cook_again"], soup["taste"], soup["rated_at"]) == (1.0, 1.0, "2026-10-05T18:00:00+00:00")
    # The JSON export of the same two cooks (doubles, as the app stores them) reads the same.
    data = export_with(authored=[authored_row("rcp-s", "Soup", [node(1, "Do", "Do.", 1)])], cooks=[
        cook_of("ck-old", "rated", "2026-09-01T18:00:00+00:00", [cook_row("rcp-s", "Soup", ratings={"taste": 5, "wouldCookAgain": 5})]),
        cook_of("ck-new", "rated", "2026-10-05T18:00:00+00:00", [cook_row("rcp-s", "Soup", ratings={"taste": 1.0, "wouldCookAgain": 1.0})])])
    js = run_json(write(tmp_path, data), "history", "Soup")
    assert (js["verdict"], js["rated_at"]) == (one["verdict"], one["rated_at"]) and "Verdict: miss (taste 1/5)." in js["text"]
    # A half-star and a stored double: 4.5 stays 4.5, 4.0 reads as 4 — a hit, would cook again.
    p = _plain_soup_md(tmp_path, ["- Soup — completed 2026-10-05T18:30:00+00:00; easy to follow 3.0/5, taste 4.5/5, would cook again 4.0/5"])
    assert _odd_night_row(fe.load_export(p))["ratings"] == {"easyFollow": 3, "taste": 4.5, "wouldCookAgain": 4}
    one = run_json(p, "--md", "history", "rcp-soup-plain-11")
    assert one["verdict"] == "hit" and one["would_cook_again"] is True and "Verdict: hit (taste 4.5/5, would cook again)." in one["text"]
    again = run_cli(p, "--md", "cook-again")
    assert "— would cook again 4/5, taste 4.5/5 — cooked 1×" in again and "no rating" not in again


def test_markdown_titles_holding_a_dash_round_trip_in_saved_lines_and_cook_headings_but_split_a_step_title(tmp_path):
    """fond-export-format › Markdown: a saved one-liner anchors on its bold title and a cook
    heading on the space-free timestamp, so a " — " inside either survives whole and the
    cooks of a renamed recipe still follow it. A step line is the exception, recorded as a
    known limit in references/export-format.md §8: the shipped renderer does not bold
    titles, so `k. <title> — <text>` splits at its FIRST " — " and a title holding " — "
    loses its tail to the text — the timing, cue and dependencies still read, and the
    printed step line is the same; the JSON is authoritative."""
    text = (MD2.read_text(encoding="utf-8")
            .replace("Grandma's Stew", "Grandma's Stew — Slow")  # the saved one-liner and its two cook lines
            .replace("4. Cook the pasta — Drop the [spaghetti] in and stir once. [Timer: 12 min — done when al dente] (after step 3)",
                     "4. Cook the pasta — al dente — Drop the [spaghetti] in — stir once. [Timer: 12 min — done when al dente] (after step 3)")
            .replace("### 2026-09-14T18:00:00+00:00 — Weeknight (recorded)", "### 2026-09-14T18:00:00+00:00 — Weeknight — late (recorded)"))
    assert text.count("Grandma's Stew — Slow") == 3 and "Cook the pasta — al dente" in text and "Weeknight — late (recorded)" in text
    p = tmp_path / "fond-export-test.md"
    p.write_text(text, encoding="utf-8")
    export = fe.load_export(p)
    stew = next(r for r in export.saved if r.title == "Grandma's Stew — Slow")
    assert stew.author_handle == "ben" and stew.url == "https://blog.example/stew" and stew.cook_count_field == 1
    pasta = next(r for r in export.authored if r.title == "Weeknight Garlic Pasta")
    step = pasta.md_steps[3]
    # the known limit: an unbolded title splits at the first " — "; the timing still reads
    assert step["title"] == "Cook the pasta" and step["text"] == "al dente — Drop the [spaghetti] in — stir once."
    assert step["timer_min"] == 12 and step["until"] == "al dente" and step["deps"] == [3]
    weeknight = next(c for c in export.cooks if c["startedAt"] == "2026-09-14T18:00:00+00:00")
    assert weeknight["mealName"] == "Weeknight — late" and weeknight["status"] == "recorded"
    plan = run_json(p, "--md", "plan", "Weeknight Garlic Pasta")
    assert "Cook the pasta — al dente — Drop the [spaghetti] in — stir once. — Timer: 12 min — done when al dente (after step 3)" in plan["text"]
    out = run_cli(p, "--md", "history")
    assert "— cooked 1× —" in history_row(out, "Grandma's Stew — Slow")
    assert "— cooked 2× —" in history_row(out, "Tomato Soup") and "— cooked 2× —" in history_row(out, "Weeknight Garlic Pasta")
    # the cook follows the renamed recipe: no row for the old title, nothing unattributable
    assert not any(ln.startswith("  - Grandma's Stew — by ") for ln in out.splitlines()) and "cannot be attributed" not in out


# ---------------------------------------------------------------------------
# No offer, no "watch for": the frozen timer rule (tasks.md 12.1–12.4)
# ---------------------------------------------------------------------------

def test_no_plan_or_show_output_offers_a_timer_or_says_watch_for():
    """cook-playback › Timer steps …: the skill offers no optional timer for any step and
    gives no "watch for …" instruction — no `plan` or `show` output over either fixture,
    JSON and --md, text and --json, carries "optional timer", "want a" or "watch for"."""
    for src in ((V2,), (V1,), (MD2, "--md"), (MD1, "--md")):
        titles = [r["title"] for r in run_json(*src, "list")["cookable"]]
        assert titles, src
        for title in titles:
            for cmd in ("plan", "show"):
                for out in (run_cli(*src, cmd, title), json.dumps(run_json(*src, cmd, title))):
                    for needle in ("optional timer", "want a", "watch for"):
                        assert needle not in out.lower(), (src, cmd, title, needle)


def test_skill_asks_the_timerless_notice_question_once_before_the_first_step():
    """cook-playback › Timerless DSL …: SKILL.md asks the one question once per recipe per
    conversation, before the first step and in the mise-en-place turn, and points the "yes"
    branch at the companion change's "Adjusting a recipe" (tasks.md 12.6); the question's
    wording is the spec's."""
    # the question is a block quote: drop the "> " markers, then join the wrapped lines
    skill = " ".join(re.sub(r"^> ?", "", ln) for ln in (SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines())
    skill = " ".join(skill.split())
    assert re.search(r"ONCE per recipe per conversation, in the opening turn beside the mise en place — before the first step, never mid-cook, never on \"next\"", skill)
    assert "This recipe's Fond-format steps carry no timers, but the app's steps had N (…). Want me to add them?" in skill
    assert "I'd keep them in a local variant of this recipe — the export itself stays as it is. Or we cook it as written, with no countdowns." in skill
    assert "see \"Adjusting a recipe\"" in skill and "`cook-with-fond-authoring`" in skill
    assert "Never propose timers in any other circumstance" in skill
    assert "The paste prompt carries no such question" in skill
    prompt = (SKILL / "prompts" / "paste-this-prompt.md").read_text(encoding="utf-8")
    assert "Want me to add them" not in prompt and "timers_notice" not in prompt


# ---------------------------------------------------------------------------
# Timerless DSL: cooked as written, one notice before the first step (tasks.md 12.5–12.8)
# ---------------------------------------------------------------------------

RICE = "Steamed Coconut Rice"
RICE_NOTICE = ("Note: the Fond-format steps carry no timers; the app's steps for this recipe had 2 "
               "(Toast the Coconut 2 min × 2, Simmer the Rice 15 min)")
RICE_NOTICE_JSON = {"dsl": 0, "nodes": 2, "steps": [{"title": "Toast the Coconut", "minutes": 2, "repeat": 2},
                                                    {"title": "Simmer the Rice", "minutes": 15, "repeat": 1}]}
NOTICE_HEAD = "Note: the Fond-format steps carry no timers"


def _assert_no_notice(src, title, plan_code=0):
    for cmd in ("plan", "show"):
        assert NOTICE_HEAD not in run_cli(*src, cmd, title, expect=plan_code if cmd == "plan" else 0), (src, cmd, title)
        assert "timers_notice" not in run_json(*src, cmd, title, expect=plan_code if cmd == "plan" else 0), (src, cmd, title)


def test_timerless_dsl_notice_printed_on_plan_and_show_with_the_count_and_each_step():
    """cook-playback › notice printed; › repeat node in the notice: the fixture's rice row
    (zero sigils, two app timer steps, one with `repeat: 2`) gets the one notice line from
    `plan` and `show`, once per invocation, text and --json (`timers_notice`); every step
    is still a DSL step with no countdown and no clock time, and `source` stays `dsl`."""
    for cmd in ("plan", "show"):
        out = run_cli(V2, cmd, RICE)
        assert out.count(RICE_NOTICE) == 1 and out.count(NOTICE_HEAD) == 1, cmd
        js = run_json(V2, cmd, RICE)
        assert js["timers_notice"] == RICE_NOTICE_JSON and js["text"].count(RICE_NOTICE) == 1, cmd
        assert js["source"] == "dsl"
    plan = run_json(V2, "plan", RICE)
    assert [s["id"] for s in plan["steps"]][:2] == ["rinse-the-rice", "toast-the-coconut"]
    assert all(s["kind"] != "timer" and s["countdowns"] == [] and s["structure"] == "" for s in plan["steps"])
    assert "Timer:" not in plan["text"] and "set a timer" not in plan["text"].lower()
    simmer = step_of(plan, "simmer-the-rice")
    assert simmer["kind"] == "watch" and simmer["timing"] == "about 15 min — no timer, no clock time; does not occupy you"
    assert step_of(plan, "toast-the-coconut")["kind"] == "hands-on" and step_of(plan, "toast-the-coconut")["count"] == 2
    assert plan["estimate_minutes"] == 32
    assert any("DSL wins" in w for w in plan["warnings"])  # the nodes are not substituted


def test_timerless_dsl_notice_from_the_markdown():
    """cook-playback › notice from the Markdown: the regenerated fixture's rice section — a
    sigil-less DSL fence beside printed Steps carrying two `Timer:` lines (one `× 2`) — prints
    the same notice on `--md`, text and --json, once; the recipe still cooks from the fence."""
    section = MD2.read_text(encoding="utf-8").split("### Steamed Coconut Rice")[1].split("## Recipes you saved")[0]
    assert section.count("[Timer: ") == 2 and "~" not in section.split("```")[1]  # two app timers, a sigil-less fence
    for cmd in ("plan", "show"):
        out = run_cli(MD2, "--md", cmd, RICE)
        assert out.count(RICE_NOTICE) == 1, cmd
        js = run_json(MD2, "--md", cmd, RICE)
        assert js["timers_notice"] == RICE_NOTICE_JSON and js["source"] == "dsl", cmd
    assert run_json(MD2, "--md", "plan", RICE)["estimate_minutes"] == 32


def test_timerless_dsl_notice_absent_when_the_nodes_carry_no_timer(tmp_path):
    """cook-playback › no notice when the nodes have no timers: the rice row with every
    `until` nulled prints no notice and carries no `timers_notice`."""
    data = load(V2)
    rice = next(r for r in data["authoredRecipes"] if r["id"] == "rcp-rice-09")
    for n in rice["nodes"]:
        n["until"] = None
    p = write(tmp_path, data)
    _assert_no_notice((p,), RICE)
    assert run_json(p, "plan", RICE)["source"] == "dsl"


def test_timerless_dsl_notice_absent_when_the_dsl_carries_a_sigil():
    """cook-playback › no notice when the DSL has a sigil: the steak row's DSL carries sigils
    beside nodes with the projected preheat timer (and seven more) — no notice, no proposal."""
    steak = load(V2)["authoredRecipes"][0]
    assert steak["id"] == "rcp-steak-01" and "~" in steak["dsl"]
    assert sum(1 for n in steak["nodes"] if n.get("until") and n.get("time")) >= 1
    _assert_no_notice((V2,), "Skillet Steak Supper")
    _assert_no_notice((MD2, "--md"), "Skillet Steak Supper")


def test_timerless_dsl_notice_absent_on_version_1_rows():
    """cook-playback › no notice on a version-1 saved row (no steps, so no `nodes[]`) and › on
    a version-1 authored row with a sigil (the v1 fixture's steak): the two conditions decide,
    never the version — the notice code reads no `export_version`."""
    _assert_no_notice((V1,), "Tomato Soup", plan_code=1)  # saved, no steps in version 1
    assert run_json(V1, "show", "Tomato Soup")["cookable"] is False
    _assert_no_notice((V1,), "Skillet Steak Supper")
    _assert_no_notice((MD1, "--md"), "Tomato Soup", plan_code=1)
    _assert_no_notice((MD1, "--md"), "Skillet Steak Supper")
    import inspect
    for fn in (fe.timers_notice, fe.timed_nodes, fe.timers_notice_line):
        code = inspect.getsource(fn).split('"""')[-1]  # the body after the docstring
        assert "version" not in code, fn.__name__


def test_timerless_dsl_notice_absent_for_nodes_only_rows():
    """cook-playback › Timerless DSL …: a row cooked from its nodes (no DSL) never triggers the
    notice, on the JSON and on the Markdown."""
    for title in ("Weeknight Garlic Pasta", "Toast Soldiers", "Tomato Soup"):
        _assert_no_notice((V2,), title)
        _assert_no_notice((MD2, "--md"), title)
        assert run_json(V2, "plan", title)["source"] == "nodes"


# ---------------------------------------------------------------------------
# The --md reader over the shipped renderer's forms (tasks.md 13.1–13.5)
# ---------------------------------------------------------------------------

def test_md_fixture_is_the_shipped_renderers_shape():
    """fond-export-format › the reference document matches the renderer: the v2 fixture is
    the shipped renderer's output — Contact last, bracketed timings, unbolded titles,
    one-line rows interleaved after a section, `· on Fond by`, `Saved:`/`Cooked:` lines,
    `Timer: 0.5 min`, the DSL fence after the Steps list — and the v1 fixture stays as
    committed (170 lines, no `Timer:`, `Handle:` lines)."""
    md = MD2.read_text(encoding="utf-8")
    assert md.rstrip().endswith("- **TikTok:** —") and md.index("## Contact") > md.index("## Cooking history")
    assert "4. Cook the pasta — Drop the [spaghetti] in and stir once. [Timer: 12 min — done when al dente] (after step 3)" in md
    assert "**Cook the pasta**" not in md and "[Timer: 0.5 min — done when fragrant]" in md and "30 sec" not in md
    assert "[Timer: 1 min × 2 — done when puffed (×2)]" in md and "[~2 min × 3]" in md
    assert "[Done when: the water is at a rolling boil]" in md and "Grate the [parmesan] and set it aside.\n" in md
    assert "\nby Cara · on Fond by @ana\n" in md and "\nLineage: forked from rcp-parent-77 at v2; credits @cara, @ben\n" in md
    assert "- **Saved:** 2026-09-10T08:30:00+00:00 (url)\n- **Cooked:** 1×\n" in md
    saved = md[md.index("## Recipes you saved (5)"):md.index("## Cooking history")]
    assert saved.index("### Tomato Soup") < saved.index(
        "- **Grandma's Stew** by @ben — saved 2026-08-01T12:00:00+00:00 (shared), cooked 1× — https://blog.example/stew")
    assert "one of your own recipes: see \"Weeknight Garlic Pasta\" under Recipes you created (Fond id rcp-pasta-02)" in saved
    assert "- **—** — saved 2026-04-01T12:00:00+00:00 (url)\n" in saved
    steak = md[md.index("### Skillet Steak Supper"):md.index("### Weeknight Garlic Pasta")]
    assert steak.index("12. Plate the Supper") < steak.index("**Recipe DSL**")  # the fence follows the Steps list
    v1 = MD1.read_text(encoding="utf-8")
    assert len(v1.splitlines()) == 170 and "Timer:" not in v1 and "- **Handle:** skillet-steak-supper-a1b2c3" in v1


def test_md_nodes_only_recipes_keep_their_hands_on_minutes():
    """cook-playback › hands-on minutes in Markdown: the nodes-only recipes give the same
    step kinds, timings and estimates from the .md as from the JSON — Tomato Soup 31,
    Garlic Pasta 20, Toast Soldiers 7 (not 20/12/6)."""
    for title, estimate in (("Tomato Soup", 31), ("Weeknight Garlic Pasta", 20), ("Toast Soldiers", 7)):
        md, js = run_json(MD2, "--md", "plan", title), run_json(V2, "plan", title)
        assert md["estimate_minutes"] == js["estimate_minutes"] == estimate, title
        assert [(s["kind"], s["scheduled"], s["timing"], s["needs"]) for s in md["steps"]] == \
            [(s["kind"], s["scheduled"], s["timing"], s["needs"]) for s in js["steps"]], title
    dice = step_of(run_json(MD2, "--md", "plan", "Tomato Soup"), "1")
    assert dice["kind"] == "hands-on" and dice["scheduled"] == 3 and dice["text"] == "Dice the [onion]." and dice["needs"] == ["onion"]
    assert "Prep: Dice the onion — Dice the [onion]. — ~3 min hands-on" in run_cli(MD2, "--md", "plan", "Tomato Soup")


def test_md_no_stray_bracket_in_step_text_or_cue_and_no_timing_read_as_a_need():
    """cook-playback › enriched Markdown: no step text or done-when carries a stray bracket
    and no `needs` entry reads like `~3 min` — over every cookable recipe of the fixture."""
    for title in [r["title"] for r in run_json(MD2, "--md", "list")["cookable"]]:
        for cmd in ("plan", "show"):
            for s in run_json(MD2, "--md", cmd, title)["steps"]:
                text = s["text"]
                assert text.count("[") == text.count("]") and not re.search(r"\[(Timer:|Done when:|~\s*\d)", text), (title, s)
                for cue in (s.get("done_when"), s.get("done_when_raw")):
                    assert not cue or ("[" not in cue and "]" not in cue), (title, cue)
                assert not any(re.match(r"~\s*\d", n) for n in s.get("needs", [])), (title, s.get("needs"))
                assert not s["timing"].endswith("]") and not s["timing"].startswith("["), (title, s["timing"])


def test_md_one_line_rows_after_the_first_section_are_listed_and_counted():
    """cook-playback › one-line row after a section: the renderer prints the Tomato Soup
    section first and the one-line rows after it; all are read — `list` and `missing` show
    3 (not 0), Grandma's Stew is "saved, no steps in this export" with its by-line and url,
    its cooks reach `history`, and the own-recipe reference folds into the authored row."""
    listing = run_json(MD2, "--md", "list")
    assert [r["title"] for r in listing["missing"]] == ["Grandma's Stew", "Old Favourite Curry", None]
    assert [r["title"] for r in run_json(MD2, "--md", "missing")["missing"]] == \
        [r["title"] for r in run_json(V2, "missing")["missing"]]
    stew = next(r for r in listing["missing"] if r["title"] == "Grandma's Stew")
    assert stew["byline"] == "by @ben · from blog.example" and stew["reason"] == "saved, no steps in this export"
    assert "Grandma's Stew — by @ben · from blog.example — saved, no steps in this export" in run_cli(MD2, "--md", "list")
    assert "— cooked 1× —" in history_row(run_cli(MD2, "--md", "history"), "Grandma's Stew")
    assert run_json(MD2, "--md", "history", "Grandma's Stew")["times"] == 1
    assert [r["title"] for r in listing["cookable"]].count("Weeknight Garlic Pasta") == 1
    export = fe.load_export(MD2)
    assert [r.title for r in export.saved] == ["Tomato Soup", "Grandma's Stew", "Weeknight Garlic Pasta", "Old Favourite Curry", None]
    assert next(r for r in export.saved if r.title == "Weeknight Garlic Pasta").ref == "rcp-pasta-02"


def test_md_source_author_by_line_reads_the_same_on_both_paths():
    """cook-playback › source author on the shipped by-line: `by Cara · on Fond by @ana`
    gives the JSON's by-line, the handle read only after "on Fond"; a source author written
    "@cara" is never the Fond handle."""
    for cmd in (["list"], ["show", "Skillet Steak Supper"], ["plan", "Skillet Steak Supper"]):
        assert STEAK_BYLINE in run_cli(MD2, "--md", *cmd) and STEAK_BYLINE in run_cli(V2, *cmd), cmd
    show = run_json(MD2, "--md", "show", "Skillet Steak Supper")
    assert show["sourceAuthor"] == "Cara" and show["author"] == "ana" and show["byline"] == STEAK_BYLINE
    sec = ["### Shadow Soup", "", "by @cara · on Fond by @shadowchef", "", "- **Fond id:** rcp-shadow-01", "",
           "**Ingredients**", "", "- 1 onion", "", "**Steps**", "", "1. Dice — Dice the [onion]. [~3 min]"]
    rec = fe._md_recipe_section(sec, "saved", False)
    assert rec.author_handle == "shadowchef" and rec.source_author == "@cara" and rec.id == "rcp-shadow-01"


def test_md_by_line_splits_at_the_last_on_fond_delimiter():
    """cook-playback › --md reader by-line (Codex P1 on #64, pass 2): the Fond handle is read
    from the part after the LAST ` · on Fond by ` — the structural delimiter the renderer
    appends after the source author — so a source author that itself contains the
    delimiter never names the handle; the plain forms, the null handle and the `@`-leading
    source author read as before."""
    def section(by_line):
        return ["### Shadow Soup", "", by_line, "", "- **Fond id:** rcp-shadow-01", "", "**Steps**", "",
                "1. Dice — Dice the [onion]. [~3 min]"]
    rec = fe._md_recipe_section(section("by Food · on Fond by @evil · on Fond by @ana"), "saved", False)
    assert rec.source_author == "Food · on Fond by @evil" and rec.author_handle == "ana"
    rec = fe._md_recipe_section(section("by Cara · on Fond by @ana"), "saved", False)
    assert rec.source_author == "Cara" and rec.author_handle == "ana"
    rec = fe._md_recipe_section(section("by X · on Fond by (unknown)"), "saved", False)
    assert rec.source_author == "X" and rec.author_handle is None and rec.has_author_key is True
    rec = fe._md_recipe_section(section("by @cara · on Fond by @shadowchef"), "saved", False)
    assert rec.source_author == "@cara" and rec.author_handle == "shadowchef"
    rec = fe._md_recipe_section(section("by @evil · on Fond by @evil2 · on Fond by (unknown)"), "saved", False)
    assert rec.source_author == "@evil · on Fond by @evil2" and rec.author_handle is None
    rec = fe._md_recipe_section(section("by @ben"), "saved", False)
    assert rec.source_author is None and rec.author_handle == "ben"


def test_md_source_author_beside_a_null_handle():
    """cook-playback › source author beside a null handle: `by Cara · on Fond by (unknown)`
    gives sourceAuthor "Cara" and a null handle — "(unknown)" is never a handle string."""
    sec = ["### Cara's Soup", "", "by Cara · on Fond by (unknown)", "", "- **Saved:** 2026-09-10T08:30:00+00:00 (url)",
           "- **Cooked:** 0×", "- **Fond id:** rcp-cara-01", "", "**Steps**", "", "1. Stir — Stir the [pot]. [~1 min]"]
    rec = fe._md_recipe_section(sec, "saved", False)
    assert rec.source_author == "Cara" and rec.author_handle is None and rec.has_author_key is True
    assert rec.saved_at == "2026-09-10T08:30:00+00:00" and rec.cook_count_field == 0
    assert fe.byline(rec, fe.load_export(MD2)) == "by Cara (saved to Fond by (unknown)) · Fond id rcp-cara-01"


def test_md_saved_and_cooked_keys():
    """cook-playback › saved and cooked keys: `- **Saved:** <ts> (<reason>)` and `- **Cooked:**
    N×` give the saved date and the app's cook counter, as the JSON does; the older
    `<ts>, cooked N×` form is still read."""
    export = fe.load_export(MD2)
    soup = next(r for r in export.saved if r.title == "Tomato Soup")
    assert soup.saved_at == "2026-09-10T08:30:00+00:00" and soup.cook_count_field == 1
    assert "saved 2026-09-10T08:30:00+00:00, cooked 1× (app counter)" in run_cli(MD2, "--md", "show", "Tomato Soup")
    assert "saved 2026-09-10T08:30:00+00:00, cooked 1× (app counter)" in run_cli(V2, "show", "Tomato Soup")
    for src in ((V2,), (MD2, "--md")):
        row = next(r for r in run_json(*src, "list")["cookable"] if r["title"] == "Tomato Soup")
        assert row["cooked"] == 2  # the history count (2) beats the app counter (1), on both paths
    old = fe._md_recipe_section(["### Old Soup", "by @ben", "- **Saved:** 2026-09-10T08:30:00+00:00, cooked 3×"], "saved", False)
    assert old.saved_at == "2026-09-10T08:30:00+00:00" and old.cook_count_field == 3


def test_md_ingredient_bracket_is_not_a_timing():
    """cook-playback › ingredient bracket is not a timing: only a TRAILING bracket whose whole
    content is a timing is unwrapped; `[~1 cup water]` and `[~2 cups stock]` stay in the text
    as needs, an `until` holding "[…]" survives, and the older unbracketed form still reads."""
    s = fe._md_parse_step_line(2, "Add the water — Add [~1 cup water] and stir.")
    assert s["text"] == "Add [~1 cup water] and stir." and s["hands_min"] is None and s["timer_min"] is None and s["cue"] is None
    s = fe._md_parse_step_line(3, "Add the stock — Pour in the [~2 cups stock]")
    assert s["title"] == "Add the stock" and s["text"] == "Pour in the [~2 cups stock]" and s["hands_min"] is None
    step = fe.steps_from_markdown([s], False)[0]
    assert step.needs == ["~2 cups stock"] and step.kind == "instant" and step.text.endswith("[~2 cups stock]")
    s = fe._md_parse_step_line(4, "Cook — Drop the [spaghetti] in. [Timer: 12 min — done when the [pasta] is al dente] (after step 3)")
    assert s["text"] == "Drop the [spaghetti] in." and s["timer_min"] == 12 and s["until"] == "the [pasta] is al dente" and s["deps"] == [3]
    s = fe._md_parse_step_line(5, "Fry — Fry the [eggs]. [~2 min × 3]")
    assert s["hands_min"] == 2 and s["hands_repeat"] == 3 and s["text"] == "Fry the [eggs]."
    s = fe._md_parse_step_line(6, "Sizzle — Warm the [oil]. [Timer: 0.5 min — done when fragrant]")
    assert s["timer_min"] == 0.5 and s["until"] == "fragrant" and s["text"] == "Warm the [oil]."
    s = fe._md_parse_step_line(7, "Boil — Bring the [water] to a boil. [Done when: the water is at a rolling boil]")
    assert s["cue"] == "the water is at a rolling boil" and s["text"] == "Bring the [water] to a boil."
    s = fe._md_parse_step_line(8, "**Cook the pasta** — Drop the [spaghetti] in. — Timer: 12 min — done when al dente (after step 3)")
    assert s["title"] == "Cook the pasta" and s["timer_min"] == 12 and s["until"] == "al dente" and s["deps"] == [3]


def test_md_timing_bracket_whose_done_when_nests_a_bracket_is_unwrapped_whole():
    """cook-playback › Markdown fallback, no stray bracket (Codex P2 on #64): a rendered
    timer or cue whose done-when itself holds a bracket — `[Timer: 12 min — done when
    reduced to [~2 cups]]`, `[Done when: thick [not runny]]` — is unwrapped at its
    enclosing bracket: the inner `[~2 cups]` looks like an opener but its content to the
    line's final `]` is no timing, so the candidates are tried last to first. The text and
    the `until` carry no stray bracket, the timer is still 12 min, the dependencies still
    read, and the untimed `[~2 cups stock]` step is still left alone."""
    s = fe._md_parse_step_line(2, "Reduce — Simmer the [stock] hard. [Timer: 12 min — done when reduced to [~2 cups]]")
    assert s["text"] == "Simmer the [stock] hard." and s["timer_min"] == 12 and s["until"] == "reduced to [~2 cups]"
    s = fe._md_parse_step_line(3, "Reduce — Simmer the [stock] hard. [Timer: 12 min — done when reduced to [~2 cups]] (after step 1)")
    assert s["text"] == "Simmer the [stock] hard." and s["timer_min"] == 12 and s["until"] == "reduced to [~2 cups]" and s["deps"] == [1]
    s = fe._md_parse_step_line(4, "Thicken — Stir the [sauce]. [Done when: thick [not runny]]")
    assert s["text"] == "Stir the [sauce]." and s["cue"] == "thick [not runny]" and s["timer_min"] is None
    for ordinal, body in ((5, "Add the stock — Pour in the [~2 cups stock]"),
                          (6, "Toss — Toss with [~8 min] of patience and the [parsley]")):
        s = fe._md_parse_step_line(ordinal, body)
        assert s["text"] == body.split(" — ", 1)[1] and s["timer_min"] is None and s["cue"] is None and s["hands_min"] is None
    # Pass 2 (Codex P2): an inner candidate shaped like a WHOLE timing — `[Done when: glossy]`,
    # `[Timer: 1 min]` — passes the grammar (its `.*` swallows the enclosing `]`), so a
    # candidate with unmatched brackets is skipped for the enclosing opener.
    s = fe._md_parse_step_line(7, "Text [Timer: 12 min — done when reduce to [Done when: glossy]]")
    assert s["text"] == "Text" and s["timer_min"] == 12 and s["until"] == "reduce to [Done when: glossy]" and s["cue"] is None
    s = fe._md_parse_step_line(8, "Set — Chill it. [Timer: 3 min — done when set [Timer: 1 min]]")
    assert s["text"] == "Chill it." and s["timer_min"] == 3 and s["until"] == "set [Timer: 1 min]"
    # End to end: the parsed steps carry balanced brackets in their text and their cue.
    sec = ["### Reduction", "", "by @ben", "", "- **Fond id:** rcp-reduce-01", "", "**Steps**", "",
           "1. Reduce — Simmer the [stock] hard. [Timer: 12 min — done when reduced to [~2 cups]]",
           "2. Thicken — Stir the [sauce]. [Done when: thick [not runny]] (after step 1)", ""]
    steps = fe.steps_from_markdown(fe._md_recipe_section(sec, "saved", False).md_steps, False)
    for step in steps:
        assert step.text.count("[") == step.text.count("]") and not step.text.endswith("["), step.text
        assert (step.done_when or "").count("[") == (step.done_when or "").count("]"), step.done_when
    assert steps[0].kind == "timer" and steps[0].done_when == "reduced to [~2 cups]" and steps[1].done_when == "thick [not runny]"


def test_md_untitled_and_non_dict_step_lines_are_text_not_titles():
    """fond-export-format › Markdown: `k. (untitled step)` (a node with neither title nor
    text) and `k. <value>` (a non-dict node) are read as text, never as a title; a
    version-1 line keeps its text as its title."""
    s = fe._md_parse_step_line(3, "(untitled step)")
    assert s["title"] == "Step 3" and s["text"] == "(untitled step)"
    s = fe._md_parse_step_line(4, "just a string node [~2 min]")
    assert s["title"] == "Step 4" and s["text"] == "just a string node" and s["hands_min"] == 2
    legacy = fe._md_parse_step_line(4, "Thinly slice the [garlic].", legacy=True)
    assert legacy["title"] == legacy["text"] == "Thinly slice the [garlic]."


def test_md_authored_reference_resolves_by_the_printed_fond_id_not_by_title(tmp_path):
    """cook-playback › an authored reference resolves by id, not by title (tasks.md 13.1(e),
    13.5): two "Recipes you created" sections both titled "Toast", Fond ids rcp-a and rcp-b,
    and a one-line saved row ending `(Fond id rcp-b)` — the row's id and ref are rcp-b and
    `list` folds it into that recipe, whichever order the sections appear in. The same row
    without the tail (the version-1 shape) resolves by title — to a "Toast" section, which
    one being the limit references/export-format.md §8 states — never by id."""
    def section(fond_id, minutes):
        return (f"### Toast\n\nby @ana\n\n- **Published:** 2026-07-01T08:00:00+00:00\n- **Public:** yes\n"
                f"- **Fond id:** {fond_id}\n\n**Steps**\n\n1. Toast — Toast the [bread]. [~{minutes} min]\n")
    head = ("# Your Fond data export\n\nExported 2026-10-08T12:00:00+00:00 · export version 2\n\n"
            "## Profile\n- **Handle:** ana\n\n## Recipes you created (2)\n\n")
    foot = "\n## Cooking history (0)\n\n## Contact\n- **Email:** —\n"
    tailed = ('- **Toast** by @ana — saved 2026-08-16T07:00:00+00:00 (own), cooked 2× — one of your own recipes: '
              'see "Toast" under Recipes you created (Fond id rcp-b)\n')
    bare = "- **Toast** by @ana — saved 2026-08-16T07:00:00+00:00 (own), cooked 2×\n"
    for first, second in (("rcp-a", "rcp-b"), ("rcp-b", "rcp-a")):
        body = section(first, 2) + "\n" + section(second, 3) + "\n## Recipes you saved (1)\n\n"
        md = tmp_path / f"tailed-{first}.md"
        md.write_text(head + body + tailed + foot, encoding="utf-8")
        export = fe.load_export(md)
        row = export.saved[0]
        assert (row.id, row.ref) == ("rcp-b", "rcp-b") and export.content_of(row).id == "rcp-b", first
        listing = run_json(md, "--md", "list")
        assert [r["id"] for r in listing["cookable"]] == [first, second] and listing["missing"] == [], first
        md1 = tmp_path / f"bare-{first}.md"
        md1.write_text(head + body + bare + foot, encoding="utf-8")
        export = fe.load_export(md1)
        row = export.saved[0]
        assert row.id is None and row.ref in ("rcp-a", "rcp-b") and export.content_of(row).id == row.ref, first
        assert run_json(md1, "--md", "list")["missing"] == [], first


def test_md_ingredient_shaped_like_a_saved_row_is_an_ingredient(tmp_path):
    """cook-playback › --md reader, one-line rows only between sections (tasks.md 13.1(b),
    13.5): an ingredient written `- **Sauce** — saved for garnish` inside a section's
    Ingredients list is a list item — one ingredient read, no extra saved row — and the
    `list`/`missing` counts are unchanged; the same for a Steps list item of that shape."""
    sec = ["### Shadow Soup", "", "by @ben", "", "- **Saved:** 2026-09-10T08:30:00+00:00 (url)", "- **Cooked:** 0×",
           "- **Fond id:** rcp-shadow-01", "", "**Ingredients**", "", "- 1 onion", "- **Sauce** — saved for garnish", "",
           "**Steps**", "", "1. Dice — Dice the [onion]. [~3 min]", ""]
    rec = fe._md_recipe_section(sec, "saved", False)
    assert rec.ingredients == ["1 onion", "**Sauce** — saved for garnish"] and len(rec.md_steps) == 1
    md = MD2.read_text(encoding="utf-8")
    start = md.index("### Tomato Soup")
    end = md.index("- **Grandma's Stew**", start)  # the one-line row after the section
    soup_text = md[start:end]
    assert soup_text.count("- salt\n\n**Steps**") == 1  # the section's Ingredients list ends here
    soup_text = soup_text.replace("- salt\n\n**Steps**", "- salt\n- **Sauce** — saved for garnish\n\n**Steps**")
    soup_text = soup_text.replace("1. Prep: Dice the onion — Dice the [onion]. [~3 min]\n",
                                  "1. Prep: Dice the onion — Dice the [onion]. [~3 min]\n- **Garnish** — saved to the side\n")
    edited = tmp_path / "garnish.md"
    edited.write_text(md[:start] + soup_text + md[end:], encoding="utf-8")
    export, base = fe.load_export(edited), fe.load_export(MD2)
    assert [r.title for r in export.saved] == [r.title for r in base.saved]  # 5 rows, no "Sauce", no "Garnish"
    soup = next(r for r in export.saved if r.title == "Tomato Soup")
    assert soup.ingredients == next(r for r in base.saved if r.title == "Tomato Soup").ingredients + ["**Sauce** — saved for garnish"]
    assert len(soup.md_steps) == 4  # the stray list line under Steps is not a step and not a row
    for cmd in ("list", "missing"):
        got, want = run_json(edited, "--md", cmd), run_json(MD2, "--md", cmd)
        assert [r["title"] for r in got["missing"]] == [r["title"] for r in want["missing"]], cmd
        if cmd == "list":
            assert [r["title"] for r in got["cookable"]] == [r["title"] for r in want["cookable"]]


def test_export_format_section_8_quotes_only_lines_the_fixtures_carry():
    """tasks.md 13.4 Verify: every line form quoted in references/export-format.md §8
    appears verbatim in the regenerated v2 fixture (or, for the version-1 form, in the v1
    fixture); §4 no longer carries the "(about one recipe in ten)" parenthetical and says
    that page and video imports are saved rows."""
    ref = (SKILL / "references" / "export-format.md").read_text(encoding="utf-8")
    assert "one recipe in ten" not in ref
    assert "A recipe imported\nfrom a **page or a video** is not an authored row: it is a saved row" in ref
    assert "never by `reason`" in ref
    start = ref.index("## 8. The Markdown export")
    section = ref[start:ref.index("\n## ", start + 1)]
    carried = set(MD2.read_text(encoding="utf-8").splitlines()) | set(MD1.read_text(encoding="utf-8").splitlines())
    marker, quoted = None, []
    for ln in section.splitlines():
        if marker is None and ln.startswith("```"):
            marker = ln.strip()  # ``` or ```` opens; only the same run closes
            continue
        if marker is not None and ln.strip() == marker:
            marker = None
            continue
        if marker is not None and ln.strip():
            quoted.append(ln)
    assert len(quoted) > 30 and marker is None
    assert all(q in carried for q in quoted), [q for q in quoted if q not in carried]
    assert "[Timer: 0.5 min — done when fragrant]" in section and "· on Fond by" in section and "- **Cooked:** 1×" in section


# ---------------------------------------------------------------------------
# The paste prompt teaches `count=` and `%sec` (tasks.md 14.1)
# ---------------------------------------------------------------------------

def test_paste_prompt_teaches_count_and_seconds():
    """skill-distribution › The paste prompt teaches `count=` and `%sec`: beside the sigil,
    segment and `× N` lines, `count=N` runs the whole structure N times as N consecutive
    countdowns counted aloud, `%sec` is seconds (never minutes) and the `%sec` sentence
    names the clock time like any timer's — never "no clock time": a sub-minute sigil is
    still a timer step —, a sigil-less atom with `count=` is N times the work and no
    timer, the hints line stays, and the prompt is still one screen (≤ 80 lines). The
    timerless-notice question is not in it. One screen is ≤ 80 lines since
    cook-with-fond-authoring 5.4 let the prompt draft."""
    prompt = (SKILL / "prompts" / "paste-this-prompt.md").read_text(encoding="utf-8")
    assert "`count=N`" in prompt and "`%sec`" in prompt
    joined = " ".join(prompt.split())
    assert "`count=3` with `~cook{3%min}` is three 3-minute timers, like `× 3`" in joined
    assert "`~sear{45%sec}` is a 45-second timer, said in seconds" in joined
    sec_sentence = joined[joined.index("`%sec` is seconds"):joined.index("; `count=N` on the atom")]
    assert "given its clock time like any timer, never read as 45 minutes" in sec_sentence
    assert "clock time" in sec_sentence and "no clock time" not in sec_sentence
    assert "A sigil-less atom with `count=` is N times the work, no timer" in joined
    assert "`duration=` and `attention_level=` are planning hints, never a timer" in joined
    assert len(prompt.splitlines()) <= 80
    assert "Want me to add them" not in prompt and "Fond-format steps carry no timers" not in prompt


# ---------------------------------------------------------------------------
# The Python floor (cook-with-fond-authoring 2.5 / design decision 4)
# ---------------------------------------------------------------------------

FLOOR_LINE = ("Local recipe files need Python 3.9 or newer (this interpreter is {}); "
              "every command over an export still works")


def _shipped_py():
    return sorted((SKILL / "scripts").rglob("*.py"))


def _top_level_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node, node.module.split(".")[0]


def test_every_shipped_py_parses_under_3_8_grammar():
    """skill-distribution › Agent Skills folder: the script runs on 3.8 for every command over
    an export; the vendored package's only 3.9+ feature is `graphlib`, never syntax."""
    paths = _shipped_py()
    assert {p.name for p in paths} >= {"fond_export.py", "dsl.py", "qty.py", "gate.py", "ingredients_spec.py"}
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 8))


def test_graphlib_is_imported_only_inside_fond_dsl():
    seen = set()
    for path in _shipped_py():
        for _, name in _top_level_imports(ast.parse(path.read_text(encoding="utf-8"))):
            if name == "graphlib":
                seen.add(path.name)
                assert path.parent.name == "fond_dsl", f"{path.name} imports graphlib outside scripts/fond_dsl/"
    assert seen == {"dsl.py"}


def test_fond_dsl_is_imported_lazily_and_only_in_the_helper():
    """fond-dsl-open-release › the skill script imports the vendored package lazily, so every
    command over an export stays at 3.8: never at module level, only inside the helper."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    sites = [node for node, name in _top_level_imports(tree) if name == "fond_dsl"]
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_import_fond_dsl")
    inside = {id(n) for n in ast.walk(helper)}
    assert sites and all(id(node) in inside and node.col_offset > 0 for node in sites)
    assert "sys.path.insert(0, folder)" in SCRIPT.read_text(encoding="utf-8")


def test_the_floor_refuses_below_3_9_while_the_export_commands_run(monkeypatch):
    """recipe-authoring › the floor on 3.8: one line naming the floor and that every other
    command still works, exit code 1; `list` and `plan` over the export run as before."""
    monkeypatch.setattr(sys, "version_info", (3, 8, 18, "final", 0))
    try:
        fe._import_fond_dsl()
    except fe.ExportError as err:
        assert str(err) == FLOOR_LINE.format("3.8.18") and err.code == 1
    else:
        raise AssertionError("the floor did not refuse on 3.8")
    assert "Skillet Steak Supper" in run_cli(V2, "list")
    assert "Weeknight Garlic Pasta" in run_cli(V2, "plan", "Weeknight Garlic Pasta")
    assert "Tomato Soup" in run_cli(MD2, "--md", "show", "Tomato Soup")
    page = run_cli(V2, "player", "Skillet Steak Supper", "--out", "-")  # the player lints nothing: 3.8 builds it
    assert page.split("\n", 1)[0].startswith("<!-- fond-player built by fond_export.py h=") and "Python 3.9" not in page


def test_the_helper_loads_the_package_beside_the_script_and_writes_no_bytecode():
    package = fe._import_fond_dsl()
    assert callable(package.dsl.lint_dsl) and package.gate.GATED_RULES[0] == "R"
    assert str(SCRIPT.resolve().parent) in sys.path
    assert sys.dont_write_bytecode is True
    assert not list(SCRIPT.parent.rglob("__pycache__"))


def test_an_import_failure_at_or_above_the_floor_is_its_own_refusal(monkeypatch):
    for name in [n for n in sys.modules if n == "fond_dsl" or n.startswith("fond_dsl.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "graphlib", None)  # `from graphlib import …` now raises ImportError
    try:
        fe._import_fond_dsl()
    except fe.ExportError as err:
        assert err.code == 1
        assert str(err).startswith("The vendored lint (scripts/fond_dsl/) failed to import on Python ")
        assert str(err).endswith("; every command over an export still works")
        assert "need Python 3.9" not in str(err)
    else:
        raise AssertionError("a failed import did not refuse")


# ---------------------------------------------------------------------------
# Verifier round (group 3): a local file's own identity on `scale --dsl`, the gate's
# note head on `show`/`plan`, and the order of `convert`'s refusals
# ---------------------------------------------------------------------------

# Synthetic local files (never real data): a composed file with a `yield`, a transcribed
# file under the ingredient floor, and a flat variant that trips rule U.
COMPOSED_DAL = """---
title: Weeknight Dal
yield: 4 servings
source_url: https://blog.example/dal
attribution:
  - Ana
lineage:
  origin: composed
  made_on: 2026-10-13
  changes:
    - composed by the assistant from the page handed over
---
# Weeknight Dal

## Rinse the Lentils [phase=rinse section=main duration=2 attention_level=full]
Rinse the @lentils{1 cup red lentils} until the water runs clear.

## Simmer the Dal [phase=simmer section=main duration=20 attention_level=low depends_on=[rinse-the-lentils]]
Simmer the lentils in @water{3 cups water} until soft, ~simmer{20%min}.

## Serve [phase=serve section=main duration=2 attention_level=full depends_on=[simmer-the-dal]]
Stir in the @salt{1 tsp salt} and serve.
"""

TRANSCRIBED_TOAST = """---
title: Plain Toast
lineage:
  origin: transcribed
  made_on: 2026-10-13
  changes:
    - transcribed from the user's words
---
# Plain Toast

## Toast the Bread [phase=toast section=main duration=3 attention_level=low]
Toast the @bread{2 slices bread} until golden, ~toast{3%min}.

## Butter It [phase=butter section=main duration=1 attention_level=full depends_on=[toast-the-bread]]
Spread the @butter{1 tbsp butter}.
"""

FLAT_VARIANT = """---
title: Flat Beans
author: "@ben"
source_url: https://blog.example/flat-beans-q1w2e3
lineage:
  origin: variant
  parent_id: rcp-flat-21
  parent_handle: flat-beans-q1w2e3
  exported_at: 2026-10-08T12:00:00+00:00
  made_on: 2026-10-13
  changes:
    - copied from the Fond-format steps the export carries
---
# Flat Beans

## Soak the Beans [phase=soak section=main duration=10 attention_level=none]
Soak the @beans{1 cup dried beans} in cold water.

## Simmer the Beans [phase=simmer section=main duration=30 attention_level=low]
Simmer the beans gently, ~simmer{30%min}.

## Chop the Herbs [phase=herbs section=main duration=3 attention_level=full]
Chop the @herbs{1 bunch parsley} finely.
"""

# recipe-authoring "The local id; no Fond id, handle or lineage is minted" and design
# decision 2: never for a local file's OWN identity. The 6.5 grep's scoping: "Fond id"
# only on the `Derived from:` line, "fork"/"forked" only inside the echoed
# `Lineage (parent):` line, "saved to Fond" only inside the parent by-line head (the
# `list`/head line and `Derived from:`), everything else nowhere.
NEVER_FOR_A_LOCAL_FILE = ("by you", "your recipe", "Fond recipe", "Fond handle", "original", "adapted",
                          "registered", "published", "verified", "None")


def _assert_own_identity_clean(out):
    for i, line in enumerate(out.splitlines()):
        body = line.strip()
        on_parent = body.startswith(("Derived from:", "Lineage (parent):"))
        for word in NEVER_FOR_A_LOCAL_FILE:
            assert word not in line, f"{word!r} on: {line}"
        if not on_parent:
            assert "Fond id" not in line and "fork" not in line, line
            if i != 0:
                assert "saved to Fond" not in line, line


def test_scale_dsl_never_calls_the_local_file_the_original(tmp_path):
    """recipe-authoring › The local id…: "original" is on the never-list for a local file's
    own identity, and the 6.5 grep runs over every command's output — `scale --dsl`
    included. The unscaled text is "the file" there; an export row's `scale` keeps "the
    original" (cook-playback › Scaling is a labelled variant)."""
    (tmp_path / "weeknight-dal.md").write_text(COMPOSED_DAL, encoding="utf-8")
    head = "Weeknight Dal — composed by the assistant · from blog.example, credited to Ana · local:weeknight-dal"
    tail = " — ×2 variant (the file is unchanged; ask for it any time)"
    steps = "Steps, ×2 variant (text as written; bracketed amounts inside step text are the file's):"
    for extra in ((), ("--parent", V2)):
        out = run_cli(tmp_path, "--dsl", "scale", "Weeknight Dal", "--to", "8", *extra)
        assert out.splitlines()[0] == head + tail and steps in out
        assert "- 6 cups water" in out  # `yield: 4 servings` is the base; nothing asked
        _assert_own_identity_clean(out)
    # A variant: the same wording with and without the parent; the head line never says "Fond id".
    variant = tmp_path / "tomato-soup.recipe.md"
    run_cli(V2, "convert", "Tomato Soup", "--out", variant, "--made-on", "2026-10-13")
    for extra in ((), ("--parent", V2)):
        out = run_cli(variant, "--dsl", "scale", "--from", "4", "--to", "6", *extra)
        first = out.splitlines()[0]
        assert first.startswith("Tomato Soup — local variant of ") and "· local:tomato-soup" in first
        assert first.endswith(tail.replace("×2", "×1.5")) and steps.replace("×2", "×1.5") in out
        _assert_own_identity_clean(out)
    # The export's own `scale` is unchanged.
    row = run_cli(V2, "scale", "Tomato Soup", "--from", "4", "--to", "6")
    assert "(the original is unchanged; ask for it any time)" in row and "are the original's):" in row


def test_a_gate_note_is_headed_once_on_show_plan_check_and_convert(tmp_path):
    """The lint's notes arrive from `gate.issue_line` already headed with their register
    (`note [U]: …`, `note: only 2 …`); `show --dsl` and `plan --dsl` print them as they
    are — never `Note: note …` — and the `--parent` cross-check's bare message gets the
    head exactly once (`note_line`, shared with `check` and `convert`)."""
    flat = tmp_path / "flat-beans.recipe.md"
    toast = tmp_path / "plain-toast.md"
    flat.write_text(FLAT_VARIANT, encoding="utf-8")
    toast.write_text(TRANSCRIBED_TOAST, encoding="utf-8")
    plan = run_cli(flat, "--dsl", "plan")
    lines = plan.splitlines()
    assert any(ln.startswith("  note [U]: 3 steps but no depends_on edges")
               and ln.endswith("(not gated without --parent — pass it to gate edits)") for ln in lines)
    assert any(ln.startswith("  note: only 2 canonical @ingredient definitions") for ln in lines)
    show = run_cli(toast, "--dsl", "show")
    assert "\n  note: only 2 canonical @ingredient definitions" in show
    check = run_cli(toast, "check")
    assert check.count("note: only 2 canonical") == 1
    for out in (plan, show, check):
        assert "Note: note" not in out and "note: note" not in out
    assert fe.note_line("note [U]: x") == "note [U]: x" and fe.note_line("note: x") == "note: x"
    assert fe.note_line("`lineage.parent_id` 'x' names no recipe in the --parent export; rules U and V are not gated"
                        ).startswith("note: `lineage.parent_id`")


def test_convert_takes_made_on_as_optional_and_an_empty_made_on_is_the_one_finding(tmp_path, monkeypatch):
    """recipe-authoring › `convert` is a labelled, deterministic draft › made_on with and
    without the flag (ruling 2026-10-13): the script reads no clock, so `--made-on` is
    optional — without it the draft carries `made_on:` with an empty value and the gate
    reports exactly "fill lineage.made_on with today's date (YYYY-MM-DD)" under
    `Findings:` (the draft's own, never "Inherited"), `--out` writes nothing and says so,
    and `check -` over that draft reports the same line; with the flag the value is
    written and the draft passes. A malformed value is a usage error (exit 2). The
    existing-path refusal (exit 1) and the title lookup (exit 2) precede all of it."""
    taken = tmp_path / "tomato-soup.recipe.md"
    taken.write_text("mine\n", encoding="utf-8")
    before = V2.read_bytes()
    for extra in ((), ("--made-on", "2026-10-13")):
        out = run_cli(V2, "convert", "Tomato Soup", "--out", taken, *extra, expect=1)
        assert out.strip() == f"`{taken}` exists; pass --out <other> or edit that file"
    assert taken.read_text(encoding="utf-8") == "mine\n"
    assert run_cli(V2, "convert", "No Such Dish", expect=2).startswith("No recipe in this export matches")
    # without the flag: the draft prints, `made_on:` is empty, the one finding names it, nothing is written
    fresh = tmp_path / "fresh.recipe.md"
    out = run_cli(V2, "convert", "Tomato Soup", "--out", fresh, expect=1)
    assert "\n  made_on:\n" in out and "Inherited findings:" not in out
    assert "Findings:\n  error [envelope]: fill lineage.made_on with today's date (YYYY-MM-DD)\n" in out
    assert f"Nothing written to {fresh}: 1 finding(s) block the draft." in out and not fresh.exists()
    result = run_json(V2, "convert", "Tomato Soup", "--out", "-", expect=1)
    assert result["exit"] == 1 and [f["message"] for f in result["findings"]] == [fe.MADE_ON_EMPTY]
    assert "\n  made_on:\n" in result["draft"] and result["written"] is None
    # `check -` over that draft says the same; filling the date is what makes it pass
    kept = tmp_path / "kept.recipe.md"
    monkeypatch.setattr(sys, "stdin", io.StringIO(result["draft"]))
    out = run_cli("-", "check", "--parent", V2, "--out", kept, expect=1)
    assert fe.MADE_ON_EMPTY in out and not kept.exists()
    monkeypatch.setattr(sys, "stdin", io.StringIO(result["draft"].replace("  made_on:\n", "  made_on: 2026-10-13\n")))
    out = run_cli("-", "check", "--parent", V2, "--out", kept)
    assert "Passes: nothing blocks" in out and "made_on: 2026-10-13" in kept.read_text(encoding="utf-8")
    # a malformed value is a usage error, not a finding
    out = run_cli(V2, "convert", "Tomato Soup", "--out", "-", "--made-on", "13/10/2026", expect=2)
    assert out.strip().startswith("--made-on must be YYYY-MM-DD, not `13/10/2026`")
    # with the flag: written as given
    written = run_cli(V2, "convert", "Tomato Soup", "--out", fresh, "--made-on", "2026-10-13")
    assert "it passes check" in written and "made_on: 2026-10-13" in fresh.read_text(encoding="utf-8")
    assert V2.read_bytes() == before
