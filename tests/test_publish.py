"""publish.sh builds the two release zips (skill-distribution "zip layout" and "the ChatGPT
plugin package"; founder ruling R-C10, 2026-10-16).

publish.sh runs once into a scratch git-init directory and both zips are read back:
`cook-with-fond.zip` holds one top-level folder, `cook-with-fond/`, file for file the source
folder; `cook-with-fond-plugin.zip` holds one, `cook-with-fond-plugin/`, with `plugin.json`,
`LICENSE` and `LICENSE-SPEC` at its root and the skill at `skills/cook-with-fond/` — file for
file and byte for byte the tree in the first zip. Neither carries a cache, a `*.pyc` or a
dotfile. A `plugin.json` whose version is not SKILL.md's `metadata.version` is refused before
the target is touched.

publish.sh and `plugin/` are not mirrored, so in the public repository this module skips.
Standard library and pytest only; publish.sh itself needs `sh` and `python3` on PATH.
"""

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
SKILL_DIR = SKILL_ROOT / "cook-with-fond"
PUBLISH = SKILL_ROOT / "publish.sh"
MANIFEST = SKILL_ROOT / "plugin" / "plugin.json"
PLUGIN_TOP = "cook-with-fond-plugin/"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
CACHE_PARTS = {"__pycache__", ".pytest_cache"}

pytestmark = pytest.mark.skipif(not PUBLISH.is_file(), reason="publish.sh is not mirrored (public repository)")


def skill_version(skill_md: Path) -> str:
    """SKILL.md's `metadata.version`: the indented `version:` under the top-level `metadata:`."""
    lines = skill_md.read_text(encoding="utf-8").split("\n")
    in_metadata = False
    for line in lines[1:lines.index("---", 1)]:
        if line and not line[0].isspace():
            in_metadata = line.split(":", 1)[0] == "metadata"
        elif in_metadata and line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise AssertionError("SKILL.md carries no metadata.version")


def scratch_clone(path: Path) -> Path:
    """A fresh target: `git init` when git is installed, else an empty directory (publish.sh
    accepts both, and testing for `.git` is all it does with git)."""
    path.mkdir(parents=True)
    if shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def run_publish(publish: Path, target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(publish), str(target)], capture_output=True, text=True, timeout=600)


def file_map(zf: zipfile.ZipFile, prefix: str = "") -> dict:
    """{path below prefix: bytes} for every file entry under prefix."""
    return {n[len(prefix):]: zf.read(n) for n in zf.namelist() if n.startswith(prefix) and not n.endswith("/")}


def top_level(zf: zipfile.ZipFile) -> list:
    return sorted({n.split("/", 1)[0] for n in zf.namelist()})


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    target = scratch_clone(tmp_path_factory.mktemp("publish") / "clone")
    result = run_publish(PUBLISH, target)
    assert result.returncode == 0, result.stderr + result.stdout
    with zipfile.ZipFile(target / "cook-with-fond.zip") as skill_zip, \
            zipfile.ZipFile(target / "cook-with-fond-plugin.zip") as plugin_zip:
        yield {"target": target, "skill": skill_zip, "plugin": plugin_zip}


def test_skill_zip_is_the_source_folder_under_one_top_level_folder(published):
    """skill-distribution "zip layout": `cook-with-fond/` is the only top-level entry and
    holds exactly the source folder's files (caches and dotfiles aside), byte for byte."""
    zf = published["skill"]
    assert top_level(zf) == ["cook-with-fond"]
    assert "cook-with-fond/SKILL.md" in zf.namelist()
    source = {}
    for path in sorted(SKILL_DIR.rglob("*")):
        rel = path.relative_to(SKILL_DIR)
        if path.is_file() and not any(p in CACHE_PARTS or p.startswith(".") for p in rel.parts) \
                and path.suffix != ".pyc":
            source["cook-with-fond/" + rel.as_posix()] = path.read_bytes()
    assert file_map(zf) == source


def test_plugin_zip_layout(published):
    """skill-distribution "the ChatGPT plugin package": one top-level folder holding
    plugin.json, LICENSE and LICENSE-SPEC at its root and the skill under skills/."""
    zf = published["plugin"]
    assert top_level(zf) == [PLUGIN_TOP.rstrip("/")]
    root_entries = {n[len(PLUGIN_TOP):].split("/", 1)[0] for n in zf.namelist() if n != PLUGIN_TOP}
    assert root_entries == {"plugin.json", "LICENSE", "LICENSE-SPEC", "skills"}
    assert PLUGIN_TOP + "skills/cook-with-fond/SKILL.md" in zf.namelist()
    skills = {n[len(PLUGIN_TOP + "skills/"):].split("/", 1)[0] for n in zf.namelist()
              if n.startswith(PLUGIN_TOP + "skills/") and n != PLUGIN_TOP + "skills/"}
    assert skills == {"cook-with-fond"}
    assert zf.read(PLUGIN_TOP + "LICENSE") == (SKILL_DIR / "LICENSE").read_bytes()
    assert zf.read(PLUGIN_TOP + "LICENSE-SPEC") == (SKILL_DIR / "LICENSE-SPEC").read_bytes()


def test_plugin_manifest_fields_and_version(published):
    """plugin.json is the committed source byte for byte, valid JSON with the Agent Plugins
    fields of the package tested in ChatGPT, and its version is SKILL.md's metadata.version."""
    raw = published["plugin"].read(PLUGIN_TOP + "plugin.json")
    assert raw == MANIFEST.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert manifest["name"] == "cook-with-fond"
    assert manifest["version"] == skill_version(SKILL_DIR / "SKILL.md")
    assert isinstance(manifest["description"], str) and manifest["description"].strip()
    assert manifest["license"] == "MIT"
    assert manifest["author"] == {"name": "Deglaze Corp."}
    assert manifest["repository"] == "https://github.com/commahawk/fond-skill"


def test_plugin_skill_tree_is_the_skill_zip_tree(published):
    """The skill inside the plugin is unchanged: skills/cook-with-fond/ equals the tree in
    cook-with-fond.zip file for file and byte for byte."""
    inside = file_map(published["plugin"], PLUGIN_TOP + "skills/")
    assert inside and inside == file_map(published["skill"])


def test_no_cache_or_dotfile_in_either_zip(published):
    for zf in (published["skill"], published["plugin"]):
        for name in zf.namelist():
            parts = [p for p in name.split("/") if p]
            assert not any(p in CACHE_PARTS or p.startswith(".") for p in parts), name
            assert not name.endswith((".pyc", ".pyo")), name


def test_version_mismatch_is_refused_before_the_target_is_touched(tmp_path):
    """A plugin.json whose version differs from SKILL.md's metadata.version stops publish.sh
    before the must-not-publish check and before anything in the target is removed."""
    source = tmp_path / "skill"
    (source / "plugin").mkdir(parents=True)
    shutil.copy2(PUBLISH, source / "publish.sh")
    shutil.copytree(SKILL_DIR, source / "cook-with-fond", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["version"] = skill_version(SKILL_DIR / "SKILL.md") + ".1"
    (source / "plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    target = scratch_clone(tmp_path / "clone")
    (target / "cook-with-fond").mkdir()
    (target / "cook-with-fond" / "kept.txt").write_text("a prior mirror\n", encoding="utf-8")
    result = run_publish(source / "publish.sh", target)
    assert result.returncode != 0
    assert "differs from SKILL.md metadata.version" in result.stderr, result.stderr
    assert "must-not-publish check" not in result.stdout
    assert (target / "cook-with-fond" / "kept.txt").is_file()
    assert not (target / "cook-with-fond.zip").exists() and not (target / "cook-with-fond-plugin.zip").exists()
