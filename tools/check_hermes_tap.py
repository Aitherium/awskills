#!/usr/bin/env python3
"""Make this repo a valid skills tap for Hermes Agent (and any agentskills.io reader).

Hermes (Nous Research) treats a GitHub repo as a skills source ("tap"):

    hermes skills tap add Aitherium/awskills
    hermes skills install Aitherium/awskills/<skill>

It lists every SUBDIRECTORY of the tap path (default ``skills/``) and reads
``<dir>/SKILL.md`` whose frontmatter follows agentskills.io: ``name`` (lowercase,
digits, ``-``/``_``; must equal the folder), ``description`` (non-empty, <= 1024
chars), optional ``version``, ``author``, ``platforms`` (list) and
``metadata.hermes`` (``category`` string, ``tags`` list).

This repo ships FLAT ``skills/<name>.md`` (one file you copy into any agent), so:

  check_hermes_tap.py                 judge every skills/*.md frontmatter (rules below)
  check_hermes_tap.py --build DIR     write DIR/<name>/SKILL.md for every skills/*.md in
                                      DIR -- the public mirror runs this AFTER internal
                                      skills are removed, so the tap layout never carries
                                      one; the flat files stay where every installer
                                      and count expects them
  check_hermes_tap.py --self-test     prove every rule can still fail

Rules:
  HT001  no YAML frontmatter, or it does not parse
  HT002  ``name`` missing, not ``^[a-z][a-z0-9_-]{0,63}$``, or not the file's stem
  HT003  ``description`` missing/empty or over 1024 characters
  HT004  an optional field with the wrong type (``version`` not a string/number,
         ``platforms`` not a list, ``metadata.hermes.category`` not a string,
         ``metadata.hermes.tags`` not a list)

Exit 0 clean, 1 a violation, 2 could not judge (no skills/ dir, or no *.md in it --
an empty tap and a clean one must not look the same).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)
MAX_DESCRIPTION = 1024


def _yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover - pyyaml is in every env this runs in
        return None
    return yaml


def frontmatter(text: str) -> "tuple[dict | None, str]":
    """(parsed frontmatter, error). None + reason when absent or unparseable."""
    m = FRONT_RE.match(text)
    if not m:
        return None, "no YAML frontmatter (--- ... ---) at the top of the file"
    yaml = _yaml()
    if yaml is None:
        return None, "pyyaml is not installed; cannot parse frontmatter"
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        return None, f"frontmatter does not parse: {str(exc).splitlines()[0]}"
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, ""


def judge(path: Path) -> "list[str]":
    """Every rule *path* breaks, as ``HTxxx message`` lines."""
    out: "list[str]" = []
    data, err = frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    if data is None:
        return [f"HT001 {path.name}: {err}"]
    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        out.append(f"HT002 {path.name}: name {name!r} must match {NAME_RE.pattern}")
    elif name != path.stem:
        out.append(f"HT002 {path.name}: name {name!r} must equal the file stem {path.stem!r}")
    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        out.append(f"HT003 {path.name}: description missing or empty")
    elif len(desc) > MAX_DESCRIPTION:
        out.append(f"HT003 {path.name}: description is {len(desc)} chars (max "
                   f"{MAX_DESCRIPTION})")
    if "version" in data and not isinstance(data["version"], (str, int, float)):
        out.append(f"HT004 {path.name}: version must be a string")
    if "platforms" in data and not isinstance(data["platforms"], list):
        out.append(f"HT004 {path.name}: platforms must be a list")
    hermes = ((data.get("metadata") or {}) if isinstance(data.get("metadata"), dict)
              else {}).get("hermes")
    if isinstance(hermes, dict):
        if "category" in hermes and not isinstance(hermes["category"], str):
            out.append(f"HT004 {path.name}: metadata.hermes.category must be a string")
        if "tags" in hermes and not isinstance(hermes["tags"], list):
            out.append(f"HT004 {path.name}: metadata.hermes.tags must be a list")
    return out


def skill_files(skills_dir: Path) -> "list[Path]":
    return sorted(p for p in skills_dir.glob("*.md") if p.name.lower() != "readme.md")


def check(skills_dir: Path) -> int:
    if not skills_dir.is_dir():
        print(f"check_hermes_tap: {skills_dir} is not a directory (cannot judge)")
        return 2
    files = skill_files(skills_dir)
    if not files:
        print(f"check_hermes_tap: no *.md under {skills_dir} (cannot judge)")
        return 2
    findings = [f for p in files for f in judge(p)]
    for f in findings:
        print(f)
    print(f"check_hermes_tap: {len(files)} skill(s), {len(findings)} violation(s)")
    return 1 if findings else 0


def build(skills_dir: Path) -> int:
    """Write ``<skills_dir>/<stem>/SKILL.md`` (byte-identical) for every flat skill.

    Refuses (1) when any skill fails :func:`judge` -- a tap entry Hermes cannot read is
    worse than no entry -- and when a ``<stem>/`` dir already holds something else.
    """
    rc = check(skills_dir)
    if rc:
        return rc
    for p in skill_files(skills_dir):
        dest_dir = skills_dir / p.stem
        dest = dest_dir / "SKILL.md"
        if dest_dir.exists() and not (dest.is_file() and len(list(dest_dir.iterdir())) == 1):
            print(f"check_hermes_tap: {dest_dir} exists and is not a generated tap entry")
            return 1
        dest_dir.mkdir(exist_ok=True)
        dest.write_bytes(p.read_bytes())
    print(f"check_hermes_tap: wrote {len(skill_files(skills_dir))} tap entries under "
          f"{skills_dir}")
    return 0


def self_test() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="hermes-tap-st-"))
    try:
        d = tmp / "skills"
        d.mkdir()
        assert check(d) == 2, "an empty skills dir must exit 2"
        good = "---\nname: good-one\ndescription: does a thing\nversion: 1.0.0\n---\n# x\n"
        (d / "good-one.md").write_text(good, encoding="utf-8")
        assert check(d) == 0, "a valid skill must pass"
        cases = {
            "nofront.md": ("# no frontmatter\n", "HT001"),
            "badyaml.md": ("---\nname: [unclosed\n---\n", "HT001"),
            "Upper.md": ("---\nname: Upper\ndescription: x\n---\n", "HT002"),
            "stem.md": ("---\nname: other\ndescription: x\n---\n", "HT002"),
            "nodesc.md": ("---\nname: nodesc\n---\n", "HT003"),
            "longdesc.md": ("---\nname: longdesc\ndescription: " + "x" * 1100 + "\n---\n",
                            "HT003"),
            "plat.md": ("---\nname: plat\ndescription: x\nplatforms: linux\n---\n", "HT004"),
            "cat.md": ("---\nname: cat\ndescription: x\nmetadata:\n  hermes:\n"
                       "    category: [a]\n---\n", "HT004"),
        }
        for fname, (text, code) in cases.items():
            p = d / fname
            p.write_text(text, encoding="utf-8")
            got = judge(p)
            assert any(g.startswith(code) for g in got), f"{fname}: wanted {code}, got {got}"
            assert check(d) == 1, f"{fname} must fail the run"
            p.unlink()
        assert build(d) == 0 and (d / "good-one" / "SKILL.md").read_text(
            encoding="utf-8") == good, "build must write a byte-identical SKILL.md"
        assert build(d) == 0, "a rebuild over its own output must succeed"
        (d / "good-one" / "notes.txt").write_text("hand-made", encoding="utf-8")
        assert build(d) == 1, "build must not overwrite a dir it did not generate"
        print("check_hermes_tap self-test: every rule fires, empty exits 2, build is safe")
        return 0
    except AssertionError as exc:
        print(f"check_hermes_tap self-test FAILED: {exc}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("skills_dir", nargs="?",
                    default=str(Path(__file__).resolve().parent.parent / "skills"))
    ap.add_argument("--build", action="store_true",
                    help="write <skills_dir>/<name>/SKILL.md tap entries (mirror step)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    return build(Path(a.skills_dir)) if a.build else check(Path(a.skills_dir))


if __name__ == "__main__":
    sys.exit(main())
