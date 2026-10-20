"""The vendored lint closure (`scripts/fond_dsl/`): imports under isolation, the AH stub, the gate.

Hermetic. The copies themselves are compared with their sources by a test in fond-mono
(it needs the sources); here the package is exercised as the skill script uses it: imported
from the script's folder on a bare interpreter, the stub silent, `gate.py` applying the
registry's bar with the local-file baseline (recipe-authoring "`check` gates keeping and
cooking"). Python 3.9 or newer: `dsl.py` imports `graphlib`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "cook-with-fond"
SCRIPTS = SKILL / "scripts"

sys.dont_write_bytecode = True  # nothing under scripts/ gets a __pycache__ from this suite
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fond_dsl import gate  # noqa: E402
from fond_dsl.dsl import lint_dsl  # noqa: E402
from fond_dsl.ingredients_spec import _SKIP_MARKERS, _detect  # noqa: E402

FLAT = """# Flat

## Simmer the Base [phase=p section=main duration=25 attention_level=low]
Simmer the @stock{1 cup stock} for about 20 minutes.

## Stir the Beans [phase=p section=main duration=5 attention_level=low]
Stir in @beans{1 cup beans}.

## Add the Greens [phase=p section=main duration=5 attention_level=low]
Add @greens{1 cup greens}.
"""

AH_PROBE = """# Probe

## Mince the Garlic [phase=prep section=main duration=3 attention_level=full]
Take @garlic{3 cloves garlic}(zorbled) and @onion{1 onion}(diced) and @oil{2 Tbsp oil}.

## Cook [phase=cook section=main duration=5 attention_level=high depends_on=[mince-the-garlic]]
Cook the @garlic and @onion in @oil.
"""


def _lint_result(**pools):
    return {"errors": pools.get("errors", []), "warnings": pools.get("warnings", []),
            "suggestions": pools.get("suggestions", [])}


def _keys(findings, *, gated=None, kind=None):
    return [(f["rule"], f["step"]) for f in findings
            if (gated is None or f["gated"] is gated) and (kind is None or f["kind"] == kind)]


# --- the package --------------------------------------------------------------------------


def test_imports_on_a_bare_interpreter_with_only_the_standard_library():
    """fond-dsl-open-release › stdlib only, on the 3.9 floor: `-I -S` drops the working
    directory and site-packages, so the insert stands in for the script's own."""
    code = (
        "import sys, sysconfig\n"
        "before = set(sys.modules)\n"
        "sys.path.insert(0, 'scripts')\n"
        "import fond_dsl.dsl, fond_dsl.qty, fond_dsl.gate, fond_dsl.ingredients_spec, fond_dsl.authoring_guidance\n"
        "stdlib = sysconfig.get_paths()['stdlib']\n"
        "outside = [n for n in set(sys.modules) - before if getattr(sys.modules[n], '__file__', None)\n"
        "           and not sys.modules[n].__file__.startswith(stdlib) and 'fond_dsl' not in sys.modules[n].__file__]\n"
        "print(sorted(outside))\n"
        "print(fond_dsl.dsl.lint_summary(fond_dsl.dsl.lint_dsl('# T\\n\\n## A [phase=p section=main duration=1 attention_level=low]\\nStir @a{1 cup apples}.\\n')))\n"
    )
    proc = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code], cwd=str(SKILL), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["[]", "✓ clean"]


def test_the_stub_keeps_rule_ah_silent():
    """fond-dsl-open-release › rule AH is a no-op: a never-matching pattern and a non-None sentinel."""
    assert _SKIP_MARKERS.search("optional, divided, garnish") is None
    assert _SKIP_MARKERS.search("") is None
    assert _detect("3 cloves garlic, zorbled") is not None
    result = lint_dsl(AH_PROBE)
    assert [i["rule"] for pool in result.values() for i in pool] == []


def test_the_card_is_the_one_in_skill_md():
    from fond_dsl.authoring_guidance import AUTHORING_CARD_V1

    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    body = AUTHORING_CARD_V1.split("\n", 1)[1].strip()  # the card's lines after its own heading
    assert body in skill_md


# --- the gate -------------------------------------------------------------------------------


def test_the_mirror_is_the_registry_bar():
    assert gate.GATED_RULES == ("R", "S", "T", "U", "V", "W", "X", "Y", "AA", "AB", "AC", "AD", "AE")
    assert gate.MIN_INGREDIENTS == 3


def test_errors_and_gated_rules_gate_and_the_rest_inform():
    result = _lint_result(
        errors=[{"rule": "A", "step": "x", "message": "bad"}],
        warnings=[{"rule": "AA", "step": "y", "message": "timer exceeds duration"},
                  {"rule": "D", "step": "z", "message": "partition sum"}],
        suggestions=[{"rule": "T", "step": "w", "message": "un-sigiled minutes"},
                     {"rule": "AH", "step": "v", "message": "prep slot"}],
    )
    findings = gate.gate_findings(result, 5, "composed")
    assert _keys(findings, gated=True) == [("A", "x"), ("AA", "y"), ("T", "w")]
    assert _keys(findings, gated=False) == [("D", "z"), ("AH", "v")]
    assert [f["line"] for f in findings][:2] == ["error [A] @x: bad", "warning [AA] @y: timer exceeds duration"]
    assert gate.gated_lines(findings) == ["error [A] @x: bad", "warning [AA] @y: timer exceeds duration",
                                          "suggestion [T] @w: un-sigiled minutes"]
    assert gate.note_lines(findings) == []


def test_a_flat_file_gates_on_u_when_composed_or_transcribed():
    result = lint_dsl(FLAT)
    assert ("U", None) in _keys(gate.gate_findings(result, 3, "composed"), gated=True)
    assert ("U", None) in _keys(gate.gate_findings(result, 3, "transcribed"), gated=True)
    assert ("T", "simmer-the-base") in _keys(gate.gate_findings(result, 3, "composed"), gated=True)


def test_a_variant_without_the_parent_prints_u_and_v_as_notes_and_gates_the_rest():
    findings = gate.gate_findings(lint_dsl(FLAT), 3, "variant")
    u = [f for f in findings if f["rule"] == "U"][0]
    assert u["kind"] == "note" and u["gated"] is False
    assert u["line"].startswith("note [U]: ") and u["line"].endswith(gate.NO_PARENT_SUFFIX)
    assert ("T", "simmer-the-base") in _keys(findings, gated=True)  # the next finding keeps its own kind
    assert [f["kind"] for f in findings if f["rule"] == "T"] == ["suggestion"]


def test_a_variant_inherits_u_and_v_from_the_parent_baseline_and_gates_an_introduced_one():
    result = lint_dsl(FLAT)
    inherited = gate.gate_findings(result, 3, "variant", baseline=result)
    u = [f for f in inherited if f["rule"] == "U"][0]
    assert u["kind"] == "note" and u["gated"] is False and u["line"].endswith(gate.INHERITED_SUFFIX)
    assert ("T", "simmer-the-base") in _keys(inherited, gated=True)
    # The parent carried edges (no U): the variant's U was introduced by an edit and gates.
    introduced = gate.gate_findings(result, 3, "variant", baseline=_lint_result())
    assert ("U", None) in _keys(introduced, gated=True)
    # A baseline may also be the (rule, step) pairs the caller computed.
    assert ("U", None) not in _keys(gate.gate_findings(result, 3, "variant", baseline=[("U", None)]), gated=True)
    assert gate.baseline_keys(result) == {("U", None)}
    assert gate.baseline_keys(None) == set()


def test_the_ingredient_floor_is_a_note_that_never_gates():
    findings = gate.gate_findings(_lint_result(), 2, "transcribed")
    assert [f["gated"] for f in findings] == [False]
    assert findings[0]["kind"] == "note" and findings[0]["rule"] is None
    assert findings[0]["line"] == ("note: only 2 canonical @ingredient definitions — tag every ingredient "
                                   "(≥3 expected for a real recipe) (not gated for a local file)")
    assert gate.gate_findings(_lint_result(), 3, "transcribed") == []
    assert gate.gate_findings(_lint_result(), None, "transcribed") == []


@pytest.mark.parametrize("origin", ["composed", "transcribed", None])
def test_the_baseline_is_ignored_outside_a_variant(origin):
    result = lint_dsl(FLAT)
    assert ("U", None) in _keys(gate.gate_findings(result, 3, origin, baseline=result), gated=True)
