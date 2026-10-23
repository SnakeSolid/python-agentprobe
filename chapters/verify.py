#!/usr/bin/env python3
from pathlib import Path

base = Path(__file__).resolve().parent

for name, prefix, sub in [
    ("TECHSPEC.md", "techspec", "techspec"),
    ("APPENDIX1.md", "appendix1", "appendix1"),
    ("APPENDIX2.md", "appendix2", "appendix2"),
]:
    src = base.parent / name
    if not src.exists():
        print(f"SKIP {name}: source file not present")
        continue
    src_lines = src.read_text(encoding="utf-8").splitlines()
    files = sorted((base / sub).glob(f"{prefix}-*.md"))

    # Reconstruct from chapter files, removing the prepended H1 line and blank.
    cat: list[str] = []
    for f in files:
        ls = f.read_text(encoding="utf-8").splitlines()
        body = ls[2:] if ls and ls[0].startswith("# ") else ls
        # drop one trailing blank caused by the final newline
        if body and body[-1] == "":
            body = body[:-1]
        cat.extend(body)

    # Compare ignoring blank lines (want no content loss)
    src_nb = [l for l in src_lines if l.strip()]
    cat_nb = [l for l in cat if l.strip()]
    if src_nb == cat_nb:
        print(f"OK   {name}: {len(files)} files, all {len(src_nb)} non-blank lines preserved")
    else:
        print(f"DIFF {name}: src_nonblank={len(src_nb)} cat_nonblank={len(cat_nb)}")
        import difflib
        for i, d in enumerate(difflib.unified_diff(src_nb, cat_nb, lineterm=""), start=1):
            if i > 40:
                break
            print(d)
