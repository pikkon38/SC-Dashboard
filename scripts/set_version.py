"""Stamp the release version into the companion: python scripts/set_version.py v1.2.3"""
import pathlib
import re
import sys

version = sys.argv[1].lstrip("v")
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    sys.exit(f"not a version: {sys.argv[1]}")
path = pathlib.Path(__file__).resolve().parent.parent / "companion" / "sc_companion.py"
src = path.read_text(encoding="utf-8")
new, n = re.subn(r'^VERSION = "[^"]*"', f'VERSION = "{version}"', src, count=1, flags=re.M)
if n != 1:
    sys.exit("VERSION line not found")
path.write_text(new, encoding="utf-8")
print("version", version)
