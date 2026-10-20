"""pytest reads this before it imports any suite in this folder.

Every suite executes `cook-with-fond/scripts/fond_export.py` with `importlib` (the script
is not a package), and the standard loader caches what it executes under
`scripts/__pycache__/` — inside the published folder — unless this flag is set first.
`test_fond_export.py` asserts that folder stays clean, both CIs run pytest without `-B`,
and `publish.sh` mirrors this file with the suites, so the public mirror's matrix carries
the same guard. `python3 tests/test_no_leak.py` does not pass through here: its
`_load_script` sets the flag itself.
"""

import sys

sys.dont_write_bytecode = True
