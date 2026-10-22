#!/usr/bin/env python3
import re
import unicodedata
from pathlib import Path


def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-zA-Z0-9]+\s*", "-", name).strip("-").lower()
    name = re.sub(r"-{2,}", "-", name)
    return name


def split_file(src: Path, out_dir: Path, prefix: str) -> list[tuple[str, str]]:
    lines = src.read_text(encoding="utf-8").splitlines()
    h1 = lines[0] if lines and lines[0].startswith("# ") else ""
    sections: list[tuple[str | None, list[str]]] = []
    current_title: str | None = None
    current: list[str] = []
    preamble: list[str] = []
    seen_heading = False
    for line in lines[1:]:
        m = re.match(r"^## \s*(.+)$", line)
        if m:
            seen_heading = True
            if current_title is not None:
                sections.append((current_title, current))
            current_title = m.group(1).strip()
            current = [line]
        elif seen_heading:
            current.append(line)
        else:
            # content before the first H2 heading -> preamble
            preamble.append(line)
    if current_title is not None:
        sections.append((current_title, current))

    final: list[tuple[str | None, list[str]]] = []
    if preamble:
        final.append((None, [h1] + [""] + preamble) if h1 else (None, preamble))
    for title, body in sections:
        if h1:
            body.insert(0, h1)
            body.insert(1, "")
        final.append((title, body))

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, str]] = []
    # index 0 reserved for the optional preamble (introduction)
    for i, (title, body) in enumerate(final, start=1):
        if title is None:
            slug = "introduction"
            display = "Introduction"
        else:
            slug = slugify(title)
            display = title
        fname = f"{prefix}-{i:02d}-{slug}.md"
        out = out_dir / fname
        out.write_text("\n".join(body) + "\n", encoding="utf-8")
        written.append((display, str(out.relative_to(Path.cwd()))))
    return written


base = Path(__file__).resolve().parent  # the chapters/ directory

print("=== TECHSPEC ===")
tech = split_file(base.parent / "TECHSPEC.md", base / "techspec", "techspec")
for title, path in tech:
    print(f"{title!r:55} -> {path}")

print("\n=== APPENDIX ===")
appx = split_file(base.parent / "APPENDIX.md", base / "appendix", "appendix")
for title, path in appx:
    print(f"{title!r:55} -> {path}")
