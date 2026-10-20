# Patches on the vendored lint closure

`dsl.py`, `qty.py` and `authoring_guidance.py` are copies of the Fond reference
implementation's modules of the same name, taken from fond-mono at the commit `VERSION`
records. `apps/skill/revendor.py` makes the copies and applies the patches below, in this
order; fond-mono's drift test applies the same transform to the current sources and fails
until the copies are re-vendored, so only undocumented drift fails — these patches never
do. The four lines of `dsl.py` that the must-not-publish check catches (a reference-tree
path in the module docstring, a registered tool name in the rule-M message and in two
comments) were reworded upstream before the first copy; no patch redacts them.

1. **The MIT header**, on every file in this folder:
   `# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.`
   (the licence line the skill's grant requires; recorded here so the drift test does not
   fail on every file).
2. **The package rename**, `dsl.py` only: `services.` → `fond_dsl.` on its three import
   statements — the card import at the top, the lazy ingredient-spec import inside the
   rule-AH block, and the lazy `qty` import inside the rule-D block. Comments that mention
   `services.` keep their text: the transform rewrites `from`/`import` statements only.
3. **The card-only reduction**, `authoring_guidance.py`: the copy is the MIT header, a
   one-line docstring and the `AUTHORING_CARD_V1` assignment verbatim. The source's module
   docstring (it names the registered tool names) and its conversion-prompt constants are
   dropped.
4. **The stub import line**, `dsl.py`: after the rename, the lazy
   `from fond_dsl.ingredients.spec import _SKIP_MARKERS, _detect` becomes
   `from fond_dsl.ingredients_spec import _SKIP_MARKERS, _detect` — the source module needs
   pydantic and is not vendored.
5. **The rule-AH stub**, `ingredients_spec.py` — the one semantic patch: `import re`,
   `_SKIP_MARKERS = re.compile(r"(?!)")` (a never-matching pattern; the lint calls
   `.search()` on it, so an empty tuple would raise) and `def _detect(phrase): return True`
   (a non-None sentinel; the lint fires AH on a `None` return, which would flag every prep
   slot). Rule AH therefore evaluates and reports nothing; it is a suggestion, not a gated
   rule, so the gate is unchanged.

Skill-owned, not a copy: `gate.py` (the `GATED_RULES` and `MIN_INGREDIENTS` mirror plus
the local-file baseline), this file, and `__init__.py` (written by the re-vendor script
from a template; no source counterpart). `VERSION` is provenance only and is never a test
input.
