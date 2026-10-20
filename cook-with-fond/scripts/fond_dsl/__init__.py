# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""fond_dsl — the Fond DSL lint closure, vendored into the Cook-with-Fond skill.

`dsl.py`, `qty.py` and `authoring_guidance.py` (the authoring card alone) are copies of the
reference implementation's modules, taken from fond-mono at commit 4e81b4ddddef85165d40acdc20c105682705aea9 (recorded in
`VERSION` beside this file) with the patch set `PATCHES.md` records: an MIT header, the
package rename on import lines, the card-only reduction, and `ingredients_spec.py`, a
stub that keeps lint rule AH silent. `gate.py` is the skill's own. These are copies: edit
the source in fond-mono and re-vendor (`python apps/skill/revendor.py`); never edit them by hand.
Standard library only; `dsl.py` needs Python 3.9 (`graphlib`). `fond_export.py` imports
this package lazily, so every command over an export runs without it.
"""
