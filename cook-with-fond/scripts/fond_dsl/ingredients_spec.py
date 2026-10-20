# MIT License — Copyright (c) 2026 Deglaze Corp. See LICENSE in the skill folder.
"""Stub for lint rule AH — the one semantic patch in the vendored closure (PATCHES.md).

The reference lint resolves an explicit prep slot through an ingredient-spec module that
needs pydantic and is not vendored. This stub keeps rule AH evaluating and silent: the
pattern never matches (`.search()` is called on it, so an empty tuple would raise) and
`_detect` returns a non-None sentinel (a `None` return would flag every prep slot).
"""

import re

_SKIP_MARKERS = re.compile(r"(?!)")


def _detect(phrase):
    return True
