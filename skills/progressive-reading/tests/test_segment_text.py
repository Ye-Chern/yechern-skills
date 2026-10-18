import importlib.util
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "segment_text.py"
spec = importlib.util.spec_from_file_location("segment_text", MODULE)
seg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seg)


class SegmentTextTests(unittest.TestCase):
    def test_exact_reconstruction_with_chapters(self):
        book = "".join(f"第{i}章\n" + ("风从城外吹来。" * 160) + "\n\n" for i in range(1, 11))
        spans = seg.segment_spans(book, 1000)
        self.assertGreater(len(spans), 1)
        self.assertEqual("".join(book[a:b] for a, b in spans), book)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], len(book))
        self.assertTrue(all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1)))

    def test_write_and_status_not_mislabeled(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "novel.txt"
            out = Path(td) / "read"
            novel = ("第1章\r\n情节甲。\r\n\r\n" * 75) + ("第2章\n情节乙。\n\n" * 75)
            source.write_bytes(novel.encode("utf-8"))
            m = seg.write_project(source, out, 500, 35)
            self.assertGreaterEqual(m["segments_count"], 2)
            assembled = "".join((out / s["file"]).read_bytes().decode("utf-8") for s in m["segments"])
            self.assertEqual(assembled, novel)
            self.assertTrue(all(s["reading_status"] == "unread" for s in m["segments"]))
            self.assertIn("不代表完成任何片段的精读", (out / "scout.txt").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((out / "manifest.json").read_text(encoding="utf-8"))["segments_count"], m["segments_count"])
            with self.assertRaises(FileExistsError):
                seg.write_project(source, out, 500, 35)

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            seg.segment_spans("abc", 50)

    def test_unicode_offsets_preserve_source_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "novel.txt"
            out = Path(td) / "read"
            raw = ("\ufeff第1章\r\n" + "山风🌙e\u0301。\r\n" * 100).encode("utf-8")
            source.write_bytes(raw)
            m = seg.write_project(source, out, 250, 20)
            text = raw.decode("utf-8")
            self.assertEqual(m["source_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(m["source_utf8_character_count"], len(text))
            for s in m["segments"]:
                piece = (out / s["file"]).read_bytes().decode("utf-8")
                self.assertEqual(piece, text[s["start_char_inclusive"]:s["end_char_exclusive"]])
            self.assertEqual(b"".join((out / s["file"]).read_bytes() for s in m["segments"]), raw)

    def test_no_scout_cli(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "novel.txt"
            out = Path(td) / "read"
            source.write_text("第1章 起点\n开篇。\n第2章 秘密身份\n后文。", encoding="utf-8")
            run = subprocess.run([sys.executable, str(MODULE), str(source), "--out", str(out), "--no-scout"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse((out / "scout.txt").exists())
            m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(m["segments"])
            self.assertTrue(all(s["reading_status"] == "unread" for s in m["segments"]))
            self.assertTrue(all(not s["chapter_headings_excerpt"] for s in m["segments"]))
            self.assertNotIn("秘密身份", (out / "manifest.json").read_text(encoding="utf-8"))

    def test_blank_input_and_invalid_utf8_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "novel.txt"
            out = Path(td) / "read"
            for raw in (b"", "\ufeff \r\n\t".encode("utf-8"), b"\xff\xfe"):
                source.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeDecodeError)):
                    seg.write_project(source, out, 250, 20)
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
