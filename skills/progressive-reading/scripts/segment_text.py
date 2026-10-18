#!/usr/bin/env python3
"""Optional, stdlib-only UTF-8 plain-text segmenter for progressive-reading.

This utility splits a source deterministically and optionally creates a tiny
scouting preview. It does not analyze or read the book on behalf of an LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

CHAPTER = re.compile(
    r"(?im)^[ \t]*(?:第[一二三四五六七八九十百千万零〇0-9]+[章节回卷部篇]"
    r"|chapter[ \t]+[0-9IVXLCDM]+)[^\r\n]{0,65}"
)
PARAGRAPH = re.compile(r"\r?\n[ \t]*\r?\n")
NEWLINE = re.compile(r"\r?\n")


def _nearest_break(text: str, start: int, size: int) -> int:
    total = len(text)
    if total - start <= round(size * 1.30):
        return total
    center = start + size
    left = min(total, start + max(1, round(size * 0.65)))
    right = min(total, start + max(2, round(size * 1.30)))
    for regex in (CHAPTER, PARAGRAPH, NEWLINE):
        if regex is CHAPTER:
            points = [m.start() for m in regex.finditer(text, left, right)]
        else:
            points = [m.end() for m in regex.finditer(text, left, right)]
        points = [p for p in points if p > start and p < total]
        if points:
            return min(points, key=lambda p: (abs(p - center), p))
    return min(center, total)


def segment_spans(text: str, size: int) -> list[tuple[int, int]]:
    if size < 100:
        raise ValueError("--size must be at least 100 characters")
    result: list[tuple[int, int]] = []
    pos = 0
    while pos < len(text):
        cut = _nearest_break(text, pos, size)
        if cut <= pos:
            raise RuntimeError("segmenter failed to advance")
        result.append((pos, cut))
        pos = cut
    assert "".join(text[a:b] for a, b in result) == text
    return result


def write_project(input_path: Path, out_dir: Path, size: int, preview: int, scout: bool = True) -> dict:
    if input_path.suffix.lower() not in (".txt", ".md", ".markdown"):
        raise ValueError("Only UTF-8 .txt/.md/.markdown source files are supported")
    raw = input_path.read_bytes()
    text = raw.decode("utf-8")  # Preserve CRLF and even a BOM as written, if present.
    if not text.lstrip("\ufeff").strip():
        raise ValueError("Source contains no readable text")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {out_dir}")
    spans = segment_spans(text, size)
    if preview < 0:
        raise ValueError("--preview must be nonnegative")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "segments").mkdir(exist_ok=True)
    segments = []
    preview_parts = ["# I0 稀疏侦察材料\n", "注意：这里只包含节选，不代表完成任何片段的精读。\n"]
    for i, (start, end) in enumerate(spans, 1):
        ident = f"S{i:03d}"
        piece = text[start:end]
        relpath = f"segments/{ident}.txt"
        (out_dir / relpath).write_bytes(piece.encode("utf-8"))
        headings = [m.group(0).strip() for m in list(CHAPTER.finditer(piece))[:8]] if scout else []
        segments.append({
            "id": ident,
            "start_char_inclusive": start,
            "end_char_exclusive": end,
            "characters": len(piece),
            "file": relpath,
            "reading_status": "unread",
            "chapter_headings_excerpt": headings,
        })
        if scout:
            excerpt = piece[:preview].replace("\x00", "")
            preview_parts.extend((
                f"\n## {ident} | 源文本字符 [{start}, {end}) | 阅读状态：未读\n",
                f"标题样本：{' / '.join(headings) if headings else '无显式章标题'}\n",
                f"开头节选（至多 {preview} 字符）：\n{excerpt}\n",
            ))
    manifest = {
        "source_file_name": input_path.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_utf8_character_count": len(text),
        "target_segment_chars": size,
        "segments_count": len(segments),
        "explanation": "Offsets are Python Unicode character indices in the original UTF-8-decoded file; end exclusive. Scouting never counts as full reading.",
        "segments": segments,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if scout:
        (out_dir / "scout.txt").write_text("".join(preview_parts), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 novel .txt or .md")
    parser.add_argument("--out", type=Path, required=True, help="New or empty output directory")
    parser.add_argument("--size", type=int, default=20000, help="Target Unicode characters per segment")
    parser.add_argument("--preview", type=int, default=250, help="First characters per segment for I0 scouting")
    parser.add_argument("--no-scout", action="store_true", help="Do not create a cross-book preview")
    args = parser.parse_args()
    result = write_project(args.input, args.out, args.size, args.preview, scout=not args.no_scout)
    print(f"Created {result['segments_count']} contiguous segments; total characters: {result['source_utf8_character_count']}")
    if args.no_scout:
        print("No scouting preview created; read segment files in order.")
    else:
        print("Please read scout.txt for I0 only; full segment files are needed for actual reading.")


if __name__ == "__main__":
    main()
