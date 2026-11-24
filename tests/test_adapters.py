#!/usr/bin/env python3
"""Adapter round-trips: place → readback → remove must be byte-exact.

Run: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from persona_stack.adapters import get_adapter  # noqa: E402

PID, H = "t", "abc1234567890abc"

FILES = {
    "AGENTS.md": b"---\ntitle: AGENTS\n---\n\n# AGENTS\n\npolicy\n",
    "IDENTITY.md": b"---\ntitle: IDENTITY\n---\n\n# IDENTITY\n\nname\n",
    "SOUL.md": b"---\ntitle: SOUL\n---\n\n# SOUL\n\nvoice\n",
    "TOOLS.md": b"# TOOLS\n\nsteps\n",
    "CONTEXT.md": b"# CONTEXT\n\nterms\n",
}
LOADS = {
    "AGENTS.md": "always-on",
    "IDENTITY.md": "session-start",
    "SOUL.md": "session-start",
    "TOOLS.md": "on-demand",
    "CONTEXT.md": "on-demand",
}
IN_PREFIX = ["AGENTS.md", "IDENTITY.md", "SOUL.md"]


class FileAdapterTest(unittest.TestCase):
    """openclaw: one file per source file, each in an envelope."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "host"
        self.a = get_adapter("file")

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        got = self.a.readback(self.root, PID, list(FILES), LOADS)
        self.assertEqual(got, FILES)

    def test_replace_selection_removes_excluded_blocks(self):
        self.root.mkdir(parents=True)
        host = b"host notes\n\n\nsecond section\n\n"
        (self.root / "TOOLS.md").write_bytes(host)
        self.a.place(self.root, PID, H, FILES, {})
        selected = {"SOUL.md": FILES["SOUL.md"]}
        self.a.place(self.root, PID, H, selected, {})
        self.assertEqual(self.a.readback(self.root, PID, list(selected), {}), selected)
        self.assertEqual((self.root / "TOOLS.md").read_bytes(), host)
        self.assertCountEqual([p.name for p in self.root.iterdir()], ["SOUL.md", "TOOLS.md"])

    def test_remove_restores_empty_dir(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        self.a.remove(self.root, PID, FILES, LOADS)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_host_content_survives(self):
        self.root.mkdir(parents=True)
        host = b"# project rules\n\nkeep me\n"
        (self.root / "AGENTS.md").write_bytes(host)
        self.a.place(self.root, PID, H, FILES, LOADS)
        self.assertTrue((self.root / "AGENTS.md").read_bytes().startswith(host.rstrip(b"\n")))
        self.a.remove(self.root, PID, FILES, LOADS)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), host)


class DshAdapterTest(unittest.TestCase):
    """DSH composition and legacy snapshot rollback."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "ws"
        self.a = get_adapter("dsh")

    def tearDown(self):
        self._tmp.cleanup()

    def test_modules_can_be_used_alone_or_composed(self):
        modules = {name: body for name, body in FILES.items() if name != "CONTEXT.md"}
        for selected in ({"TOOLS.md": modules["TOOLS.md"]}, modules):
            with self.subTest(names=list(selected)):
                self.a.place(self.root, PID, H, selected, {})
                self.assertEqual(self.a.readback(self.root, PID, list(selected), {}), selected)
                self.assertEqual([p.name for p in self.root.iterdir()], ["persona.prefix.txt"])
                self.assertEqual(self.a.remove(self.root, PID, selected, {}), [])

    def test_placement_shape(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        self.assertTrue((self.root / "persona.prefix.txt").is_file())
        for name in ("TOOLS.md", "CONTEXT.md"):
            self.assertEqual((self.root / name).read_bytes(), FILES[name])
        for name in IN_PREFIX:
            self.assertFalse((self.root / name).exists())

    def test_roundtrip(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        self.assertEqual(self.a.readback(self.root, PID, list(FILES), LOADS), FILES)

    def test_remove_cleans_on_demand_copies(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        self.assertEqual(self.a.remove(self.root, PID, FILES, LOADS), [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_remove_keeps_host_edited_copy(self):
        self.a.place(self.root, PID, H, FILES, LOADS)
        (self.root / "TOOLS.md").write_bytes(b"# TOOLS\n\nhost edit\n")
        notes = self.a.remove(self.root, PID, FILES, LOADS)
        self.assertTrue((self.root / "TOOLS.md").exists())
        self.assertEqual(len(notes), 1)
        self.assertIn("TOOLS.md", notes[0])


class CodexAdapterTest(unittest.TestCase):
    """codex: one file the host already owns; persona lives in one envelope."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "AGENTS.md"
        self.a = get_adapter("codex")

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip(self):
        sub = {"IDENTITY.md": FILES["IDENTITY.md"], "SOUL.md": FILES["SOUL.md"]}
        self.a.place(self.path, PID, H, sub, LOADS)
        self.assertEqual(self.a.readback(self.path, PID, list(sub), LOADS), sub)

    def test_single_module_preserves_trailing_blank_line(self):
        selected = {"TOOLS.md": b"# Tool use\n\nRun only authorized tools.\n\n"}
        self.a.place(self.path, PID, H, selected, {})
        self.assertEqual(self.a.readback(self.path, PID, list(selected), {}), selected)

    def test_host_block_preserved_and_restored(self):
        host = b"<!-- other-tool:begin -->\n# other\n<!-- other-tool:end -->\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(host)
        sub = {"IDENTITY.md": FILES["IDENTITY.md"], "SOUL.md": FILES["SOUL.md"]}
        self.a.place(self.path, PID, H, sub, LOADS)
        self.assertTrue(self.path.read_bytes().startswith(host.rstrip(b"\n")))
        self.assertEqual(self.a.remove(self.path, PID, FILES, LOADS), [])
        self.assertEqual(self.path.read_bytes(), host)

    def test_remove_without_block_reports(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"# nothing here\n")
        notes = self.a.remove(self.path, PID, FILES, LOADS)
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.path.read_bytes(), b"# nothing here\n")

    def test_place_is_idempotent(self):
        sub = {"IDENTITY.md": FILES["IDENTITY.md"], "SOUL.md": FILES["SOUL.md"]}
        self.a.place(self.path, PID, H, sub, LOADS)
        once = self.path.read_bytes()
        self.a.place(self.path, PID, H, sub, LOADS)
        self.assertEqual(self.path.read_bytes(), once)


if __name__ == "__main__":
    unittest.main()
