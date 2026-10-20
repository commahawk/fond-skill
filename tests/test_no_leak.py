"""Must-not-publish check for the Cook-with-Fond skill.

The published folder (`cook-with-fond/`, the tests next to it and a CI workflow when one
exists — exactly what `publish.sh` mirrors — and `plugin/`, the manifest source it zips into
`cook-with-fond-plugin.zip`) must never contain: a file or basename from
the service's private reference tree (every recipe-corpus basename included — kept here
as SHA-256 digests, so this file names none of them), anything from
the excluded list (`BACKLOG.md`, `docs/`, `services/identity`, `refusal.py`, `auth/`,
`data/`, `eval/`, `.env`), a DSL_SPEC section 9-12 heading, a service-API tool name, a
real export (a 28-character account id, a non-empty `contact` value, an e-mail address
that is not the company's or a documentation domain), a secret, or a patent / filing
notice. The synthetic fixtures pass because their `contact` values are empty and their
ids are invented. The player (recipe-authoring "The player") is scanned too: over
`scripts/player.template.html` and every page built from the fixtures, no network-capable
position (`NET_RE`), no `window.claude.*` but the `hot` snapshot hook, an 8-hex `h` on
every payload row, a URL only under the payload keys that carry one as data, the payload
element intact on the adversarial fixture, and the FOND1 grammar.

Runs two ways so the same check gates fond-mono CI, `publish.sh` and the public
repository's CI:

    python -m pytest -q tests/test_no_leak.py     # as a test module
    python3 tests/test_no_leak.py                 # as a script: prints findings, exit 1 on any

Both ways execute the script with importlib after setting `sys.dont_write_bytecode`
(`conftest.py` under pytest, `_load_script` here), so neither writes a `__pycache__` under
the published `scripts/` folder; a cache found there after the page builds is a finding.

Standard library only. Paths are resolved relative to this file, so the layout
`<root>/cook-with-fond` + `<root>/tests` works both in fond-mono (`apps/skill/`) and in
the public mirror (the repository root). When the file sits inside fond-mono (DSL_SPEC.md
and the private reference tree reachable), three extra checks run: the spec extract is
diffed against its source, no published file may equal a file under the reference tree,
and the digest set below must still match that tree's corpus basenames.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

try:
    import pytest
except ImportError:  # the script entry point needs no pytest
    pytest = None

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent                      # apps/skill in fond-mono; the repo root in the public mirror
SKILL_DIR = SKILL_ROOT / "cook-with-fond"     # the Agent Skills folder
# What publish.sh mirrors or zips, and therefore what is scanned: plugin/ holds the
# plugin.json source that rides in cook-with-fond-plugin.zip (not mirrored, so absent — and
# skipped — in the public repository).
PUBLISHED_DIRS = [SKILL_DIR, SKILL_ROOT / "tests", SKILL_ROOT / ".github", SKILL_ROOT / "plugin"]


# The private reference tree and its recipe corpus, relative to the fond-mono root. Built
# from parts so the path string itself is not in this (published) file.
_PRIVATE_TREE_PARTS = ("apps", "mcp", "reference")
_CORPUS_PARTS = _PRIVATE_TREE_PARTS + ("corpus",)


def _fond_mono_root() -> Optional[Path]:
    """The fond-mono checkout this file lives in, or None in the public mirror."""
    for parent in SKILL_ROOT.parents:
        if (parent / "DSL_SPEC.md").is_file() and (parent / "apps" / "mcp").is_dir():
            return parent
    return None


def _digest(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


# --- what is skipped on the way through the tree ------------------------------------
SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", ".venv", "node_modules"}
SKIP_FILE_NAMES = {".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip"}
CHECKER_NAME = Path(__file__).name   # content checks skip the checker itself (see check_contents)

# --- file-name rules -------------------------------------------------------------------
# SHA-256 of every basename (the part before the first dot) in the private recipe corpus.
# The names themselves are on the must-not-publish list, so only their digests live here;
# inside fond-mono, test_corpus_digests_match_the_private_tree keeps the set current.
CORPUS_BASENAME_DIGESTS = frozenset({
    "38191a8394c583c8ea13a92061c966d47156bb400a9a3fb4044aae853ef5865a",
    "63dee0173b9cfc1d803ff07bd6e52ada01d3ecec0feeaf4bd4866923dc23d5ea",
    "c60ef5828cde2623b8080a41853fdff766df05242788c2bdb743bddc4a87af79",
    "2cef1d317d730c4a0f753d0aff25bac3ddc0b0499a3e263aaeb33b91aac24b4a",
    "7c3fa7c686886cd61d8fca2fe0a78e2b697a00e10e0efa02f79ae16b17f31b5f",
    "9e5f8d33580b4442fd54050d653dd0e13b939929d216f149c51abf9fb4b7065a",
    "783b5307a0743408fca28520b165ee86d31aa5c430a11cd2c78cca0e679f33b9",
    "44762fde5061662d0a0909d187a3a37170cea71a0d76568a13aa6f53e2ef71ab",
    "e38f98b5179b762a9410e6e7336660708778a59619d8100ebe87b5d5c2a9deb2",
    "e3559f3020e0562fa903ed179930ab3ad8e9969471086051ea578c311c2d6c58",
})
# A token shaped like a corpus basename (lower-case words joined by underscores): each one
# found in a text file is digested and looked up, so a name is caught without being spelt.
CORPUS_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9_])")
# The excluded list, as file names (anywhere under the published folders).
FORBIDDEN_FILE_NAMES = {"BACKLOG.md", "refusal.py", "testscript.py", "fond-flutter.json",
                        "GoogleService-Info.plist", "google-services.json"}
# The excluded list, as directory names (any path component).
FORBIDDEN_DIR_NAMES = {"docs", "identity", "auth", "data", "eval", "reference", "corpus",
                       "ingredient_parse", "source docs"}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".key", ".jks", ".keystore"}
# A real export is named fond-export-<date>.json/.md; fixtures are sample-export*.json.
REAL_EXPORT_NAME = re.compile(r"^fond-export-.*\.(json|md)$")

# --- content rules ---------------------------------------------------------------------
# A Firebase account id: 28 characters of [A-Za-z0-9], not embedded in a longer word.
UID_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9]{28}(?![A-Za-z0-9_])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Company addresses and the documentation domains (RFC 2606 / 6761) are not personal data.
ALLOWED_EMAIL_DOMAINS = re.compile(r"(^|\.)(getfond\.com|example\.(com|org|net)|example|invalid|test|localhost)$", re.I)
SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google API key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "sk- API key"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\s*=\s*\S{8,}", re.M), "dotenv-style secret assignment"),
]
# Keys that never leave the service (the export whitelists its fields; these are the known
# private ones) — forbidden as JSON keys anywhere in a published JSON file.
SECRET_JSON_KEYS = {"access_token", "refresh_token", "open_id", "error_technical", "seen_urls",
                    "fcmTokens", "private_key", "client_secret", "previousAnonymousId"}
# Third-party expressive text never rides on saved rows.
FORBIDDEN_SAVED_ROW_KEYS = {"oginstructions", "ogingredients", "description"}
# DSL_SPEC sections 9-12 are not published: their heading text must not appear — a heading
# carrying one of the four titles, or a numbered `12.x` sub-heading (the tool signatures).
# A bare `## 9.` is NOT enough: any long document numbers its sections past eight.
SPEC_PRIVATE_HEADING_NUMBER = re.compile(r"^#{1,6}\s+(9|10|11|12)\.(\d+)?\s")
SPEC_PRIVATE_HEADING_TITLES = ("Not yet implemented", "Tooling map", "Empirical results", "MCP surface")
# The service-API tool names (dotted and registered forms) — the spec extract's "no MCP
# surface" scenario, applied to every published text file.
TOOL_NAMES = (
    "recipes.save", "recipes_save", "recipes.evaluate", "recipes_evaluate", "recipes.get", "recipes_get",
    "recipes.plan_meal", "recipes_plan_meal", "recipes.lint", "recipes_lint", "recipes.parse", "recipes_parse",
    "recipes.import_url", "recipes_import_url", "cooks.list", "cooks_list",
)
TOOL_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(t) for t in TOOL_NAMES) + r")(?![A-Za-z0-9_])")
# The spec's own grep over the extract (fond-dsl-open-release, "no MCP surface").
SPEC_EXTRACT_GREP = re.compile(r"(recipes|cooks)[._][a-z_]+|credits")
REFERENCE_PATH_RE = re.compile(re.escape("/".join(_PRIVATE_TREE_PARTS)) + "|" + re.escape("/".join(_CORPUS_PARTS[2:])))
PATENT_NOTICE_RE = re.compile(r"patent[- ]pending|provisional\s+(patent|application|filing)|filing[- ]dependent", re.I)

# --- the player: no network, one host hook, h on every row, the FOND1 grammar --------
# Load-bearing positions, not the string `http`: the payload's `url`/`source_url` and the
# `Source:` provenance line carry `https://blog.example/…` as data and the page renders
# them as text (tasks 4.5; the analytics-steward's record of 2026-10-12).
NET_RE = re.compile(r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket|EventSource|importScripts|serviceWorker|new Image\(|"
                    r"<img\b|<iframe\b|<link\b|<script\b[^>]*\bsrc=|\bimport\(|@import\b|url\(|https?://")
# The artifact host's hot-reload snapshot is the one host hook the page calls.
HOST_HOOK_RE = re.compile(r"\bwindow\.claude\.(?!hot\b)(\w+)?")
PLAYER_TEMPLATE_NAME = "player.template.html"
PAYLOAD_PLACEHOLDER = "__FOND_PAYLOAD__"
PAYLOAD_LINE_RE = re.compile(r"^const DATA = (.*);$", re.M)   # the payload sits on one line
PAYLOAD_URL_KEYS = frozenset({"url", "source_url", "provenance_lines"})
PLAYER_SCHEMA = "fond-player/1"
PLAYER_H_RE = re.compile(r"[0-9a-f]{8}")
PLAYER_MARKER_RE = re.compile(r"^<!-- fond-player built by fond_export\.py h=[0-9a-f]{8} id=\S+ -->$")
# The FOND1 line (recipe-authoring "The FOND1 line carries h="):
#   FOND1 <rid> <j|m|l> d=<id>[,<id>…] r=<id>:<p>/<n>@HH:MM[+<days>d][!][,…] t=HH:MM[+<days>d] h=<8hex> | --done <ids> --running <id>=<N>[,…]
FOND1_RE = re.compile(
    r"FOND1 (?P<rid>\S+) (?P<mode>[jml]) d=(?P<done>[^\s,]+(?:,[^\s,]+)*)? "
    r"r=(?P<run>[^\s,@]+:\d+/\d+@\d{2}:\d{2}(?:\+\d+d)?!?(?:,[^\s,@]+:\d+/\d+@\d{2}:\d{2}(?:\+\d+d)?!?)*)? "
    r"t=\d{2}:\d{2}(?:\+\d+d)? h=(?P<h>[0-9a-f]{8})(?: \| (?:--done \S+)?(?: ?--running \S+)?)?")

# --- the spec extract: DSL_SPEC.md sections 1-8 with exactly five in-text edits -------
# The cut is the `## 9.` heading, less the horizontal rule and blank lines before it (every
# numbered section of DSL_SPEC.md is preceded by `---`), so a line added to §1-§8 moves
# the boundary with it instead of failing the check.
SECTION_9_HEADING = re.compile(r"^## 9\. ")
EXTRACT_HEADER = "Fond DSL, © 2026 Deglaze Corp., CC BY 4.0\n\n"
EXTRACT_TRAILER_RE = re.compile(r"\n<!-- Copied from fond-mono DSL_SPEC\.md sections 1-8 at commit [0-9a-f]{40}[^\n]*-->\n$")
# Task 4.1: the comment also discloses that the two implementation pointers kept verbatim in
# the body (the preamble's file-name sentence and section 6's "Implemented in `lint.py`") name
# files that are not published. Checked as a substring of the comment, verbatim from the task.
EXTRACT_TRAILER_DISCLOSURE = ("file names in the preamble and §6 (`lint.py`, `schedule.py`, `testscript.py`, "
                              "`qty.py`, `render_classic.py`) refer to Fond's internal reference implementation, "
                              "not included in this release")
EXTRACT_EDITS = [
    ("Rule D uses `pint` for unit arithmetic, with custom recipe units",
     "Rule D uses a dependency-free quantity parser (Python `fractions`, a small unit factor table and no unit library) for unit arithmetic, with custom recipe units"),
    ("stored alongside the document at `recipes.save` time",
     "stored alongside the document when the recipe is saved"),
    ("The meal-plan tool (`recipes.plan_meal`) is the natural consumer",
     "A meal planner is the natural consumer"),
    ("existence checks against the corpus happen in `recipes.save` and `recipes.plan_meal`, not in `recipes.lint` (the single-document linter can't see other recipes)",
     "existence checks against the corpus happen when the recipe is saved or a meal is planned, not in the single-document linter (which can't see other recipes)"),
    ("Gated (blocks submit and `recipes_save`)",
     "Gated (blocks submit and saving to the corpus)"),
]


# ---------------------------------------------------------------------------------------
# Walking
# ---------------------------------------------------------------------------------------


def iter_files(roots: Iterable[Path]) -> List[Path]:
    out: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts[:-1]):
                continue
            if path.is_file() and path.name not in SKIP_FILE_NAMES and path.suffix not in SKIP_SUFFIXES:
                out.append(path)
    return out


def read_text(path: Path) -> Optional[str]:
    """The file as UTF-8 text, or None when it is not text (binary files are not scanned)."""
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def _rel(path: Path, roots: Iterable[Path]) -> str:
    for root in roots:
        try:
            return str(path.relative_to(root.parent))
        except ValueError:
            continue
    return str(path)


# ---------------------------------------------------------------------------------------
# Checks — each returns a list of findings (strings); empty means clean
# ---------------------------------------------------------------------------------------


def check_file_names(files: List[Path], roots: Iterable[Path]) -> List[str]:
    findings = []
    for path in files:
        rel = _rel(path, roots)
        name = path.name
        stem = name.split(".")[0]
        if name.endswith(".recipe.md"):
            findings.append(f"{rel}: a *.recipe.md file (the private corpus) must not be published")
        if _digest(stem) in CORPUS_BASENAME_DIGESTS:
            findings.append(f"{rel}: basename {stem!r} is a private recipe-corpus file")
        if name in FORBIDDEN_FILE_NAMES:
            findings.append(f"{rel}: {name!r} is on the must-not-publish list")
        if name == ".env" or name.startswith(".env."):
            findings.append(f"{rel}: a .env file must not be published")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or name.lower().startswith("serviceaccount"):
            findings.append(f"{rel}: looks like a key or credential file")
        if REAL_EXPORT_NAME.match(name):
            findings.append(f"{rel}: named like a real export (fond-export-*); fixtures are sample-export*.json")
        # Only the path below the published root counts: a checkout under ~/data/ is fine.
        for part in Path(rel).parts[:-1]:
            if part in FORBIDDEN_DIR_NAMES and part not in {r.name for r in roots}:
                findings.append(f"{rel}: directory {part!r} is on the must-not-publish list")
                break
    return findings


def check_text(path: Path, text: str, rel: str) -> List[str]:
    findings = []
    for m in UID_RE.finditer(text):
        findings.append(f"{rel}: 28-character account-id-shaped token {m.group(0)[:6]}… at offset {m.start()}")
    for m in EMAIL_RE.finditer(text):
        domain = m.group(0).rsplit("@", 1)[1]
        if not ALLOWED_EMAIL_DOMAINS.search(domain):
            findings.append(f"{rel}: e-mail address at offset {m.start()} (domain {domain})")
    for pattern, label in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            findings.append(f"{rel}: {label} at offset {m.start()}")
    for m in REFERENCE_PATH_RE.finditer(text):
        findings.append(f"{rel}: references the private reference tree ({m.group(0)!r}) at offset {m.start()}")
    for m in CORPUS_TOKEN_RE.finditer(text):
        if _digest(m.group(0)) in CORPUS_BASENAME_DIGESTS:
            findings.append(f"{rel}: names the corpus file {m.group(0)!r} at offset {m.start()}")
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        m = SPEC_PRIVATE_HEADING_NUMBER.match(line)
        titled = any(t.lower() in line.lower() for t in SPEC_PRIVATE_HEADING_TITLES)
        if titled or (m and m.group(1) == "12" and m.group(2)):
            findings.append(f"{rel}: DSL_SPEC section {m.group(1) if m else '9-12'} heading text: {line.strip()!r}")
    for m in TOOL_NAME_RE.finditer(text):
        findings.append(f"{rel}: service-API tool name {m.group(1)!r} at offset {m.start()}")
    for m in PATENT_NOTICE_RE.finditer(text):
        findings.append(f"{rel}: patent / filing notice {m.group(0)!r} at offset {m.start()}")
    return findings


def _walk_json(value, visit: Callable[[Dict], None]) -> None:
    if isinstance(value, dict):
        visit(value)
        for v in value.values():
            _walk_json(v, visit)
    elif isinstance(value, list):
        for v in value:
            _walk_json(v, visit)


def _non_empty_leaves(value) -> List[str]:
    if value is None or value == "" or value == [] or value == {}:
        return []
    if isinstance(value, dict):
        return [leaf for v in value.values() for leaf in _non_empty_leaves(v)]
    if isinstance(value, list):
        return [leaf for v in value for leaf in _non_empty_leaves(v)]
    return [repr(value)[:40]]


def check_json(path: Path, text: str, rel: str) -> List[str]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [f"{rel}: not valid JSON ({exc})"]
    findings: List[str] = []

    def visit(obj: Dict) -> None:
        contact = obj.get("contact")
        if isinstance(contact, dict):
            for leaf in _non_empty_leaves(contact):
                findings.append(f"{rel}: non-empty contact value {leaf} (a real export?)")
        for key in obj:
            if key in SECRET_JSON_KEYS:
                findings.append(f"{rel}: private key {key!r} present")
        saved = obj.get("savedRecipes")
        if isinstance(saved, list):
            for i, row in enumerate(saved):
                if isinstance(row, dict):
                    for key in FORBIDDEN_SAVED_ROW_KEYS & set(row):
                        findings.append(f"{rel}: savedRecipes[{i}] carries third-party text field {key!r}")

    _walk_json(data, visit)
    return findings


def check_markdown_contact(path: Path, text: str, rel: str) -> List[str]:
    """In a Markdown export, the `## Contact` block must carry no values (the renderer's
    empty marker is an em dash)."""
    findings = []
    in_contact = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_contact = line.strip() == "## Contact"
            continue
        if in_contact:
            m = re.match(r"- \*\*([^*]+):\*\*\s*(.*)$", line)
            if m and m.group(2).strip() not in ("", "—"):
                findings.append(f"{rel}: Contact block has a value for {m.group(1)}")
    return findings


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def check_network_positions(text: str, rel: str) -> List[str]:
    """`NET_RE` and the host-hook rule over a template or a built page (its payload JSON
    already cut out): every hit is named with its line."""
    findings = []
    for m in NET_RE.finditer(text):
        findings.append(f"{rel}: network-capable position {m.group(0)!r} at line {_line_of(text, m.start())}")
    for m in HOST_HOOK_RE.finditer(text):
        hook = "window.claude." + (m.group(1) or "")
        findings.append(f"{rel}: host hook {hook!r} at line {_line_of(text, m.start())} — only window.claude.hot is allowed")
    return findings


def check_player_template(text: str, rel: str) -> List[str]:
    """The template: no network-capable position, the one host hook, the marker placeholder
    on its first line and the payload placeholder exactly once."""
    findings = check_network_positions(text, rel)
    first, _, rest = text.partition("\n")
    if "h=__FOND_H__" not in first or not first.startswith("<!-- fond-player built by fond_export.py "):
        findings.append(f"{rel}: the first line must be the player marker placeholder")
    if rest.count(PAYLOAD_PLACEHOLDER) != 1:
        findings.append(f"{rel}: the payload placeholder must appear exactly once below the first line")
    return findings


def split_player_page(page: str) -> Tuple[str, Optional[str], List[str]]:
    """(the page with the payload JSON cut out, the payload JSON, findings)."""
    hits = PAYLOAD_LINE_RE.findall(page)
    if len(hits) != 1:
        return page, None, [f"expected exactly one `const DATA = …;` line in the page, found {len(hits)}"]
    return page.replace(hits[0], "", 1), hits[0], []


def check_player_page(page: str, rel: str, template: Optional[str] = None) -> List[str]:
    """A built page: the marker first, the payload on one line and embedded HTML-safe (no
    raw <, >, & or line separator inside the JSON), `NET_RE` and the host-hook rule over
    the page with the payload cut out, a URL only under `PAYLOAD_URL_KEYS`, an 8-hex `h`
    on every row, and — against the template — the payload element intact (one `<script`
    opener, the closing tag only where the template puts it, no extra comment close)."""
    findings = []
    if not PLAYER_MARKER_RE.match(page.split("\n", 1)[0]):
        findings.append(f"{rel}: the first line is not the player marker")
    rest, json_text, split_findings = split_player_page(page)
    findings += [f"{rel}: {f}" for f in split_findings]
    findings += check_network_positions(rest, rel)
    if json_text is not None:
        if re.search("[<>&\u2028\u2029]", json_text):
            findings.append(f"{rel}: the payload JSON carries a raw <, >, & or line separator (not HTML-safe)")
        try:
            payload = json.loads(json_text)
        except ValueError as exc:
            return findings + [f"{rel}: the payload is not JSON ({exc})"]
        if not isinstance(payload, dict) or payload.get("schema") != PLAYER_SCHEMA:
            findings.append(f"{rel}: payload schema is not {PLAYER_SCHEMA!r}")
        for i, row in enumerate(payload.get("recipes") or [] if isinstance(payload, dict) else []):
            if not isinstance(row, dict):
                findings.append(f"{rel}: recipe {i} is not an object")
                continue
            h = row.get("h")
            if not isinstance(h, str) or not PLAYER_H_RE.fullmatch(h):
                findings.append(f"{rel}: recipe {i} ({row.get('id')!r}) carries no 8-hex h: {h!r}")
            for key, value in row.items():
                if key in PAYLOAD_URL_KEYS:
                    continue
                if re.search(r"https?://", json.dumps(value, ensure_ascii=False)):
                    findings.append(f"{rel}: recipe {row.get('id')!r} key {key!r} carries a URL; only "
                                    f"{sorted(PAYLOAD_URL_KEYS)} may hold one")
    if template is not None:
        for tag in ("<script", "</script>", "-->"):
            if page.count(tag) != template.count(tag):
                findings.append(f"{rel}: {tag!r} appears {page.count(tag)} time(s), the template has {template.count(tag)} "
                                "— the payload element is not intact")
    return findings


def fond1_line_from_plan(plan: Dict, mode: str = "j") -> str:
    """A FOND1 line assembled from a `plan --json` answer, the way the page writes one: the
    resolved ids under d=, every running id as `<id>:<p>/<n>@HH:MM`, t=, h= and the replay
    tail. For the grammar check only — the page's own lines are checked by the node tests."""
    done = ",".join(plan["done"])
    runs = []
    for sid in plan["running"]:
        step = next(s for s in plan["steps"] if s["id"] == sid)
        n = max(1, len(step["countdowns"]) * max(1, step["count"]))
        runs.append(f"{sid}:1/{n}@18:04")
    replay = " ".join(x for x in [f"--done {done}" if done else "",
                                 "--running " + ",".join(f"{k}={v}" for k, v in plan["running"].items()) if plan["running"] else ""] if x)
    return (f"FOND1 {plan['id']} {mode} d={done} r={','.join(runs)} t=18:00 h={plan['h']}" + (f" | {replay}" if replay else ""))


def _load_script(skill_dir: Path):
    """Execute `scripts/fond_export.py` as a module for the page builds. The flag goes first:
    the standard loader would otherwise cache the script under `scripts/__pycache__/` — in
    the published folder — and `test_fond_export.py` asserts that folder stays clean (a plain
    `python3 tests/test_no_leak.py` once seeded that failure for the next pytest run). Under
    pytest `conftest.py` has set it already; the script entry point has no conftest."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("fond_export_for_no_leak", skill_dir / "scripts" / "fond_export.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script(module, *args) -> Tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = module.run([str(a) for a in args])
    return code, buf.getvalue()


def player_page_builds(skill_dir: Path) -> List[Tuple[str, List[str]]]:
    """What is built and scanned: every fixture export as a whole page, the variant file
    with its parent, and each local fixture file (the adversarial one among them)."""
    fixtures = skill_dir / "fixtures"
    builds = [("built:sample-export.json", [fixtures / "sample-export.json", "player"]),
              ("built:sample-export-v1.json", [fixtures / "sample-export-v1.json", "player"]),
              ("built:sample-export.md", [fixtures / "sample-export.md", "--md", "player"])]
    local = fixtures / "local"
    if local.is_dir():
        for path in sorted(local.glob("*.md")):
            args = [path, "--dsl", "player"]
            if "variant" in path.name:
                args += ["--parent", fixtures / "sample-export.json"]
            builds.append((f"built:local/{path.name}", args))
    return builds


def check_player_pages(skill_dir: Path) -> List[str]:
    """Build a page from each fixture with the script and scan it: the page checks above
    and the content checks every published file gets (a planted uid, e-mail, tool name or
    corpus token in a page fails here). Nothing is written: `--out -` only."""
    template_path = skill_dir / "scripts" / PLAYER_TEMPLATE_NAME
    if not template_path.is_file():
        return [f"scripts/{PLAYER_TEMPLATE_NAME}: missing"]
    template = template_path.read_text(encoding="utf-8")
    findings = check_player_template(template, f"scripts/{PLAYER_TEMPLATE_NAME}")
    try:
        module = _load_script(skill_dir)
    except Exception as exc:  # noqa: BLE001 — the check must report, not crash
        return findings + [f"scripts/fond_export.py: cannot import ({exc})"]
    for rel, args in player_page_builds(skill_dir):
        try:
            code, page = _run_script(module, *args, "--out", "-")
        except Exception as exc:  # noqa: BLE001
            findings.append(f"{rel}: the build raised {exc!r}")
            continue
        if code != 0:
            findings.append(f"{rel}: the build exited {code}: {page.strip()[:200]}")
            continue
        findings += check_player_page(page, rel, template)
        findings += check_text(Path(rel), page, rel)
    # The FOND1 grammar over a line built from a fixture cook.
    try:
        code, out = _run_script(module, skill_dir / "fixtures" / "sample-export.json", "plan", "Skillet Steak Supper",
                                "--done", "toast-the-spices", "--running", "rest-the-dough=12", "--json")
        plan = json.loads(out)
        line = fond1_line_from_plan(plan)
        if not FOND1_RE.fullmatch(line):
            findings.append(f"FOND1 grammar: a line built from a fixture cook does not match: {line!r}")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"FOND1 grammar: could not build a line from the fixture ({exc!r})")
    # The builds executed the script with importlib; a cache under scripts/ means a loader
    # wrote bytecode into the published folder (the suites assert it stays clean).
    for cache in sorted((skill_dir / "scripts").rglob("__pycache__")):
        findings.append(f"scripts/{cache.relative_to(skill_dir / 'scripts')}: a bytecode cache under the published "
                        "folder — remove it; nothing that loads the script may write one")
    return findings


def check_contents(files: List[Path], roots: Iterable[Path]) -> List[str]:
    findings = []
    for path in files:
        if path.name == CHECKER_NAME:
            continue  # this file carries every pattern it hunts; its name is still checked above
        text = read_text(path)
        if text is None:
            continue
        rel = _rel(path, roots)
        findings += check_text(path, text, rel)
        if path.suffix == ".json":
            findings += check_json(path, text, rel)
        if path.suffix == ".md":
            findings += check_markdown_contact(path, text, rel)
        if path.name == PLAYER_TEMPLATE_NAME:
            findings += check_player_template(text, rel)
        elif path.suffix == ".html":
            findings += check_network_positions(text, rel)
    return findings


def spec_sections_1_to_8(source_lines: List[str]) -> Optional[List[str]]:
    """DSL_SPEC.md up to (not including) the `---` rule and blank lines before `## 9.`;
    None when the heading is missing."""
    cut = next((i for i, line in enumerate(source_lines) if SECTION_9_HEADING.match(line)), None)
    if cut is None:
        return None
    while cut > 0 and source_lines[cut - 1].strip() in ("", "---"):
        cut -= 1
    return source_lines[:cut]


def check_spec_extract(skill_dir: Path, fond_mono_root: Optional[Path]) -> List[str]:
    """references/dsl-spec.md is DSL_SPEC.md sections 1-8 by copy, plus the licence line, the
    trailing commit comment (which also discloses the unpublished file names, task 4.1) and
    exactly the five permitted edits — and carries no tool name.
    An edit whose replacement text is already on main (the root doc fixed in place) counts
    as applied; any other difference is a finding."""
    extract_path = skill_dir / "references" / "dsl-spec.md"
    if not extract_path.is_file():
        return [f"{extract_path.name}: missing (references/dsl-spec.md)"]
    text = extract_path.read_text(encoding="utf-8")
    findings = []
    if not text.startswith(EXTRACT_HEADER):
        findings.append("references/dsl-spec.md: must start with the line 'Fond DSL, © 2026 Deglaze Corp., CC BY 4.0'")
    trailer = EXTRACT_TRAILER_RE.search(text)
    if trailer is None:
        findings.append("references/dsl-spec.md: must end with the trailing comment naming the source commit")
    elif EXTRACT_TRAILER_DISCLOSURE not in trailer.group(0):
        findings.append("references/dsl-spec.md: the trailing comment must say that the preamble/§6 file names "
                        "refer to Fond's internal reference implementation, not included in this release (task 4.1)")
    for m in SPEC_EXTRACT_GREP.finditer(text):
        findings.append(f"references/dsl-spec.md: spec grep hit {m.group(0)!r} at offset {m.start()}")
    if "pint" in text:
        findings.append("references/dsl-spec.md: the stale `pint` note survived (edit 1)")
    if fond_mono_root is not None:
        source = (fond_mono_root / "DSL_SPEC.md").read_text(encoding="utf-8").split("\n")
        kept = spec_sections_1_to_8(source)
        if kept is None:
            return findings + ["DSL_SPEC.md: no `## 9.` heading — cannot locate the end of section 8"]
        expected = "\n".join(kept).rstrip("\n") + "\n"
        for old, new in EXTRACT_EDITS:
            if expected.count(old) == 1:
                expected = expected.replace(old, new)
            elif expected.count(old) == 0 and expected.count(new) == 1:
                continue  # the root document already carries this edit (tasks 8.4)
            else:
                findings.append(f"DSL_SPEC.md: edit site not found exactly once: {old[:50]!r} — re-locate the five edits")
        body = EXTRACT_TRAILER_RE.sub("\n", text)
        if body.startswith(EXTRACT_HEADER):
            body = body[len(EXTRACT_HEADER):]
        body = body.rstrip("\n") + "\n"
        if body != expected:
            got, want = body.split("\n"), expected.split("\n")
            first = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            findings.append(
                f"references/dsl-spec.md drifts from DSL_SPEC.md sections 1-8 + the five edits "
                f"(first difference at extract line {first + 3}: {got[first][:80] if first < len(got) else '<eof>'!r})")
    return findings


def check_reference_copies(files: List[Path], roots: Iterable[Path], fond_mono_root: Optional[Path]) -> List[str]:
    """No published file may be a byte copy of anything under the private reference tree
    (fond-mono only)."""
    if fond_mono_root is None:
        return []
    reference = fond_mono_root.joinpath(*_PRIVATE_TREE_PARTS)
    if not reference.is_dir():
        return []
    digests = {}
    for path in reference.rglob("*"):
        if path.is_file() and path.name != "README.md":
            digests[hashlib.sha256(path.read_bytes()).hexdigest()] = path.relative_to(fond_mono_root)
    findings = []
    for path in files:
        hit = digests.get(hashlib.sha256(path.read_bytes()).hexdigest())
        if hit is not None:
            findings.append(f"{_rel(path, roots)}: byte copy of {hit}")
    return findings


def check_licences(skill_dir: Path) -> List[str]:
    findings = []
    lic = skill_dir / "LICENSE"
    spec = skill_dir / "LICENSE-SPEC"
    skill = skill_dir / "SKILL.md"
    if not lic.is_file():
        findings.append("LICENSE: missing")
    else:
        text = lic.read_text(encoding="utf-8")
        if "MIT License" not in text or "Copyright (c) 2026 Deglaze Corp." not in text:
            findings.append("LICENSE: must be the MIT text naming 'Copyright (c) 2026 Deglaze Corp.'")
    if not spec.is_file():
        findings.append("LICENSE-SPEC: missing")
    else:
        text = spec.read_text(encoding="utf-8")
        if "CC BY 4.0" not in text or "Deglaze Corp." not in text or "references/dsl-spec.md" not in text:
            findings.append("LICENSE-SPEC: must name CC BY 4.0, Deglaze Corp. and references/dsl-spec.md")
    if skill.is_file():
        head = skill.read_text(encoding="utf-8").split("---", 2)
        if len(head) < 3 or not re.search(r"^license:\s*MIT\s*$", head[1], re.M):
            findings.append("SKILL.md: frontmatter must carry `license: MIT`")
    return findings


def scan(roots: List[Path], fond_mono_root: Optional[Path] = None, skill_dir: Optional[Path] = None) -> List[str]:
    """Every check over the given published roots; the list of findings (empty = clean)."""
    files = iter_files(roots)
    findings = check_file_names(files, roots) + check_contents(files, roots)
    findings += check_reference_copies(files, roots, fond_mono_root)
    if skill_dir is not None:
        findings += check_spec_extract(skill_dir, fond_mono_root)
        findings += check_licences(skill_dir)
    return findings


# ---------------------------------------------------------------------------------------
# pytest entry points
# ---------------------------------------------------------------------------------------


def test_skill_folder_exists():
    assert (SKILL_DIR / "SKILL.md").is_file(), f"{SKILL_DIR} must hold SKILL.md"


def test_no_forbidden_file_names():
    files = iter_files(PUBLISHED_DIRS)
    assert check_file_names(files, PUBLISHED_DIRS) == []


def test_no_leaking_content():
    files = iter_files(PUBLISHED_DIRS)
    assert check_contents(files, PUBLISHED_DIRS) == []


def test_no_reference_tree_copies():
    files = iter_files(PUBLISHED_DIRS)
    assert check_reference_copies(files, PUBLISHED_DIRS, _fond_mono_root()) == []


def test_plugin_manifest_source_is_scanned():
    """publish.sh zips plugin/plugin.json into cook-with-fond-plugin.zip, so the walk covers
    it wherever it exists (fond-mono); the public mirror carries no plugin/ folder."""
    manifest = SKILL_ROOT / "plugin" / "plugin.json"
    assert SKILL_ROOT / "plugin" in PUBLISHED_DIRS
    if manifest.is_file():
        assert manifest in iter_files(PUBLISHED_DIRS)


def test_spec_extract_is_sections_1_to_8_with_five_edits():
    assert check_spec_extract(SKILL_DIR, _fond_mono_root()) == []


def test_spec_extract_boundary_is_found_by_the_section_9_heading():
    lines = ["# Spec", "", "## 8. Last public", "text", "", "---", "", "## 9. Private", "more"]
    assert spec_sections_1_to_8(lines) == ["# Spec", "", "## 8. Last public", "text"]
    assert spec_sections_1_to_8(["# Spec", "## 8. Only"]) is None


def test_spec_extract_trailing_comment_discloses_the_unpublished_file_names(tmp_path):
    """Task 4.1: the trailing comment says that the preamble/§6 file names refer to Fond's
    internal reference implementation, not included in this release — and the check reports
    a comment that names the commit but lacks that sentence."""
    text = (SKILL_DIR / "references" / "dsl-spec.md").read_text(encoding="utf-8")
    trailer = EXTRACT_TRAILER_RE.search(text)
    assert trailer is not None and EXTRACT_TRAILER_DISCLOSURE in trailer.group(0)
    folder = tmp_path / "cook-with-fond" / "references"
    folder.mkdir(parents=True)
    (folder / "dsl-spec.md").write_text(
        EXTRACT_HEADER + "# Fond DSL\n\nbody\n\n<!-- Copied from fond-mono DSL_SPEC.md sections 1-8 at commit "
        + "0" * 40 + " -->\n", encoding="utf-8")
    found = check_spec_extract(tmp_path / "cook-with-fond", None)
    assert len(found) == 1 and "trailing comment must say" in found[0]


def test_corpus_digests_match_the_private_tree():
    """Inside fond-mono the digest set must name exactly the corpus basenames; in the public
    mirror there is nothing to compare against."""
    root = _fond_mono_root()
    if root is None:
        pytest.skip("not inside fond-mono")
    corpus = root.joinpath(*_CORPUS_PARTS)
    assert corpus.is_dir()
    live = {_digest(p.name.split(".")[0]) for p in corpus.iterdir() if p.name.endswith(".recipe.md")}
    assert live == set(CORPUS_BASENAME_DIGESTS), "update CORPUS_BASENAME_DIGESTS (sha256 of each basename)"


def test_licence_files():
    assert check_licences(SKILL_DIR) == []


# --- the player (tasks 4.5) --------------------------------------------------------------


def test_player_template_has_no_network_position_and_one_host_hook():
    text = (SKILL_DIR / "scripts" / PLAYER_TEMPLATE_NAME).read_text(encoding="utf-8")
    assert check_player_template(text, PLAYER_TEMPLATE_NAME) == []
    assert "window.claude.hot" in text   # the one host hook, called by name


def test_built_pages_are_self_contained_and_stamped():
    """Every page built from a fixture — both exports, the Markdown export, the variant with
    its parent, the adversarial and the reconcile files — passes the page scan and the
    content checks; a FOND1 line built from a fixture cook matches the grammar."""
    assert check_player_pages(SKILL_DIR) == []


def test_loading_the_script_for_the_check_writes_no_bytecode(monkeypatch):
    """`python3 tests/test_no_leak.py` runs without conftest.py: `_load_script` must set the
    flag itself before executing the script, or the loader caches it under the published
    `scripts/` folder and the next pytest run fails `test_fond_export.py`'s clean-folder
    assertions. Exercised with the flag cleared, the way a plain interpreter starts."""
    scripts = SKILL_DIR / "scripts"
    before = set(scripts.rglob("__pycache__"))
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    try:
        _load_script(SKILL_DIR)
        assert sys.dont_write_bytecode is True
        assert not list(scripts.rglob("__pycache__"))
    finally:
        for cache in set(scripts.rglob("__pycache__")) - before:
            shutil.rmtree(cache, ignore_errors=True)   # never leave behind what this test caused


def test_adversarial_page_keeps_the_payload_intact():
    """The title, step text, source_url and author label carrying `</script><script>fetch(`
    and `-->` reach the page only as escaped JSON: one `<script` opener, the closing tag
    where the template puts it, no load-bearing position (recipe-authoring "an adversarial
    recipe cannot break out of the payload")."""
    module = _load_script(SKILL_DIR)
    template = (SKILL_DIR / "scripts" / PLAYER_TEMPLATE_NAME).read_text(encoding="utf-8")
    code, page = _run_script(module, SKILL_DIR / "fixtures" / "local" / "sample-adversarial.md", "--dsl", "player", "--out", "-")
    assert code == 0, page
    assert check_player_page(page, "built:local/sample-adversarial.md", template) == []
    assert page.count("<script") == 1 and page.count("</script>") == 1 and page.count("-->") == template.count("-->")
    assert "</script><script>" not in page and "fetch(" not in split_player_page(page)[0]
    assert "\\u003c/script\\u003e\\u003cscript\\u003efetch( --\\u003e" in page
    row = json.loads(split_player_page(page)[1])["recipes"][0]
    assert "</script><script>fetch( -->" in row["title"] and "</script><script>fetch( -->" in row["steps"][0]["text"]


def test_fond1_line_from_a_fixture_cook_matches_the_grammar():
    module = _load_script(SKILL_DIR)
    code, out = _run_script(module, SKILL_DIR / "fixtures" / "sample-export.json", "plan", "Skillet Steak Supper",
                            "--done", "toast-the-spices", "--running", "rest-the-dough=12", "--json")
    assert code == 0
    line = fond1_line_from_plan(json.loads(out))
    assert FOND1_RE.fullmatch(line), line
    assert line.startswith("FOND1 rcp-steak-01 j d=toast-the-spices r=rest-the-dough:1/2@18:04 t=18:00 h=")
    for good in ("FOND1 rcp-pasta-02 j d=1,2 r=5:1/1@18:30! t=18:12 h=1a2b3c4d | --done 1,2 --running 5=18",
                 "FOND1 local:dal l d= r= t=09:05 h=deadbeef",
                 "FOND1 rcp-x m d=a r=b:2/3@07:00,c:1/1@07:10 t=06:59 h=00000000 | --running b=4,c=10"):
        assert FOND1_RE.fullmatch(good), good
    for bad in ("FOND1 rcp-x j d= r= t=18:00",                      # no h=
                "FOND1 rcp-x j d= r=b:o@18:30 t=18:00 h=1a2b3c4d",  # the retired optional form
                "FOND1 rcp-x q d= r= t=18:00 h=1a2b3c4d",           # not a mode letter
                "FOND1 rcp-x j d= r= t=18:00 h=xyz"):
        assert not FOND1_RE.fullmatch(bad), bad


def test_player_scan_detects_planted_positions(tmp_path, monkeypatch):
    """A scratch template with one `fetch(` fails naming the line; one with
    `window.claude.state` fails naming the hook; a page built with the escape turned off
    fails on the opener count."""
    template = (SKILL_DIR / "scripts" / PLAYER_TEMPLATE_NAME).read_text(encoding="utf-8")
    lines = template.split("\n")
    planted = lines[:] ; planted.insert(20, "const probe = fetch('/x');")
    found = check_player_template("\n".join(planted), "scratch")
    assert len(found) == 1 and "'fetch('" in found[0] and "at line 21" in found[0], found
    hooked = lines[:] ; hooked.insert(30, "window.claude.state.read();")
    found = check_player_template("\n".join(hooked), "scratch")
    assert len(found) == 1 and "'window.claude.state'" in found[0] and "at line 31" in found[0], found
    for position in ("<img src=x>", "<link rel=stylesheet href=x>", "new Image()", "navigator.sendBeacon(u)",
                     "import('x')", "@import 'x';", "background: url(x)", "<script src=x></script>", "https://x.example/"):
        assert check_player_template(template.replace("<title>", position + "<title>", 1), "scratch"), position
    module = _load_script(SKILL_DIR)
    monkeypatch.setattr(module, "html_safe_json", lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    code, page = _run_script(module, SKILL_DIR / "fixtures" / "local" / "sample-adversarial.md", "--dsl", "player", "--out", "-")
    assert code == 0
    found = check_player_page(page, "unescaped", template)
    assert any("'<script' appears" in f and "not intact" in f for f in found), found
    assert any("not HTML-safe" in f for f in found), found
    # a page whose payload lost its h, and one whose step text smuggles a URL
    ok_code, ok_page = _run_script(module, SKILL_DIR / "fixtures" / "sample-export.json", "player", "Toast Soldiers", "--out", "-")
    rest, json_text, _ = split_player_page(ok_page)
    payload = json.loads(json_text)
    payload["recipes"][0]["h"] = "undefined"
    payload["recipes"][0]["steps"][0]["text"] = "see https://x.example/"
    broken = ok_page.replace(json_text, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"), 1)
    found = check_player_page(broken, "broken", template)
    assert any("carries no 8-hex h" in f for f in found) and any("carries a URL" in f for f in found), found


def test_detects_planted_leaks(tmp_path, monkeypatch):
    """The check itself catches the spec's scenarios: a *.recipe.md file, a corpus basename
    (through its digest — a synthetic name is registered for the test, so no real one is
    spelt here), a real export (non-empty contact e-mail, an account-id-shaped token), a
    tool name, a private heading."""
    planted = "planted_corpus_name"
    monkeypatch.setattr(sys.modules[__name__], "CORPUS_BASENAME_DIGESTS",
                        CORPUS_BASENAME_DIGESTS | {_digest(planted)})
    folder = tmp_path / "cook-with-fond"
    folder.mkdir()
    (folder / "x.recipe.md").write_text("# nope\n", encoding="utf-8")
    (folder / f"{planted}.md").write_text("# nope\n", encoding="utf-8")
    (folder / "mentions.md").write_text(f"see {planted} and {'/'.join(_CORPUS_PARTS[2:])}\n", encoding="utf-8")
    uid = "A" * 14 + "b" * 14                       # built, not pasted: 28 account-id characters
    email = "someone" + "@" + "mail-provider.net"   # a non-allowlisted address, assembled
    (folder / "fond-export-2026-10-16.json").write_text(json.dumps({
        "export_version": 1, "profile": {"uid": uid},
        "contact": {"email": email, "displayName": "", "phoneNumber": None},
        "savedRecipes": [{"id": "s1", "oginstructions": ["raw"]}],
        "tiktok": {"access_token": "x"},
    }), encoding="utf-8")
    (folder / "notes.md").write_text("## 12. MCP surface\n\nuse recipes_save here\n", encoding="utf-8")
    (folder / ".env").write_text("API_KEY=abcdefghijkl\n", encoding="utf-8")
    found = "\n".join(scan([folder]))
    for needle in ("*.recipe.md", f"basename '{planted}' is a private recipe-corpus file",
                   f"names the corpus file '{planted}'", "references the private reference tree",
                   "named like a real export",
                   "account-id-shaped", "e-mail address", "non-empty contact value", "oginstructions",
                   "access_token", "section 12 heading", "MCP surface", "recipes_save",
                   ".env file", "dotenv-style secret"):
        assert needle in found, f"{needle!r} not detected:\n{found}"


def test_synthetic_fixture_passes(tmp_path):
    """An export whose contact values are empty and whose ids are synthetic is clean."""
    folder = tmp_path / "cook-with-fond"
    (folder / "fixtures").mkdir(parents=True)
    (folder / "fixtures" / "sample-export.json").write_text(json.dumps({
        "export_version": 2, "exportedAt": "2026-10-16T09:00:00+00:00",
        "profile": {"uid": "uid-ana-synthetic", "handle": "ana", "linkedAnonymousUids": []},
        "contact": {"email": "", "displayName": "", "phoneNumber": None, "tiktokUsername": ""},
        "authoredRecipes": [{"id": "rcp-synthetic-01", "handle": "soup-xyz789", "authorHandle": "ana", "lineage": None}],
        "savedRecipes": [{"id": "rcp-synthetic-02", "authorHandle": "ben", "url": "https://blog.example/soup"}],
        "cooks": [],
    }), encoding="utf-8")
    (folder / "fixtures" / "sample-export.md").write_text(
        "# Your Fond data export\n\n## Contact\n- **Email:** —\n- **Name:** —\n\n## Recipes you created (1)\n",
        encoding="utf-8")
    assert scan([folder]) == []


# ---------------------------------------------------------------------------------------
# Script entry point (publish.sh and the public repository's CI)
# ---------------------------------------------------------------------------------------


def main() -> int:
    findings = scan(PUBLISHED_DIRS, _fond_mono_root(), SKILL_DIR)
    findings += check_player_pages(SKILL_DIR)
    if not (SKILL_DIR / "SKILL.md").is_file():
        findings.insert(0, f"{SKILL_DIR}: SKILL.md missing")
    if findings:
        print("must-not-publish check FAILED:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"must-not-publish check passed over {len(iter_files(PUBLISHED_DIRS))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
