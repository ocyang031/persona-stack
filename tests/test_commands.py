"""Command-level regressions: version gate, portable targets, pinned revert.

Run: python -m unittest discover -s tests
"""
import argparse
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import persona_stack.commands as commands  # noqa: E402
import persona_stack.registry as registry  # noqa: E402
import persona_stack.state as state  # noqa: E402


class CommandTestBase(unittest.TestCase):
    """Point every path constant at a throwaway repo replica."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bundles = self.root / "bundles"
        self.sources = self.root / "sources"
        self.receipts = self.root / "receipts"
        self.bindings = self.root / "bindings.json"
        self.targets = self.root / "targets.local.json"
        self._patches = [
            mock.patch.object(commands, "REPO", self.root),
            mock.patch.object(commands, "BUNDLES_DIR", self.bundles),
            mock.patch.object(commands, "SOURCES_DIR", self.sources),
            mock.patch.object(commands, "TARGETS_FILE", self.targets),
            mock.patch.object(registry, "BUNDLES_DIR", self.bundles),
            mock.patch.object(state, "BINDINGS_FILE", self.bindings),
            mock.patch.object(state, "TARGETS_FILE", self.targets),
            mock.patch.object(state, "RECEIPTS_DIR", self.receipts),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    @contextlib.contextmanager
    def quiet(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield out, err

    def write_source(self, version: str, body: bytes) -> Path:
        src = self.sources / "x"
        src.mkdir(parents=True, exist_ok=True)
        (src / "persona.yaml").write_bytes(
            f"id: x\nversion: {version}\nfiles:\n  - name: SOUL.md\n".encode("utf-8")
        )
        (src / "SOUL.md").write_bytes(body)
        return src

    def pack(self, version: str, body: bytes) -> str:
        src = self.write_source(version, body)
        with self.quiet():
            commands.cmd_pack(argparse.Namespace(source=str(src)))
        idx = json.loads((self.bundles / "x" / "index.json").read_text(encoding="utf-8"))
        return idx["bundles"][-1]["hash"]

    def bind(self, h: str, target: Path, pin: bool = False) -> None:
        with self.quiet():
            commands.cmd_bind(argparse.Namespace(
                slot="s", ref=f"x@{h}", host="dsh", target=str(target),
                var=[], include="", pin=pin, device="win-dsh",
            ))


class PackVersionGateTest(CommandTestBase):
    def test_refuses_content_change_without_version_bump(self):
        self.pack("1.0.0", b"voice one\n")
        src = self.write_source("1.0.0", b"voice two\n")

        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as raised:
            commands.cmd_pack(argparse.Namespace(source=str(src)))

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("content changed without a version bump", stderr.getvalue())
        published = [p for p in (self.bundles / "x").iterdir() if p.is_dir()]
        self.assertEqual(len(published), 1)

    def test_accepts_version_bump(self):
        self.pack("1.0.0", b"voice one\n")
        self.pack("1.1.0", b"voice two\n")

        idx = json.loads((self.bundles / "x" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([b["version"] for b in idx["bundles"]], ["1.0.0", "1.1.0"])

    def test_index_source_is_repo_relative(self):
        self.pack("1.0.0", b"voice one\n")

        idx = json.loads((self.bundles / "x" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["bundles"][0]["source"], "sources/x")


class PortableTargetTest(CommandTestBase):
    def test_bind_keeps_host_path_out_of_authoritative_table(self):
        h = self.pack("1.0.0", b"voice one\n")
        host = self.root / "host"
        self.bind(h, host)

        committed = self.bindings.read_text(encoding="utf-8")
        entry = json.loads(committed)["bindings"][0]
        self.assertNotIn("target", entry)
        self.assertNotIn(str(self.root), committed)

        local = json.loads(self.targets.read_text(encoding="utf-8"))
        self.assertEqual(local["s"], str(host))


    def test_status_reports_unconfigured_without_local_target(self):
        h = self.pack("1.0.0", b"voice one\n")
        self.bind(h, self.root / "host")
        self.targets.unlink()

        with self.quiet() as (out, _):
            rc = commands.cmd_status(argparse.Namespace(slot="s", device=None))

        self.assertEqual(rc, 2)
        self.assertIn("unconfigured", out.getvalue())

    def test_reconcile_fails_when_target_missing(self):
        h = self.pack("1.0.0", b"voice one\n")
        self.bind(h, self.root / "host")
        self.targets.unlink()

        with self.quiet() as (out, _):
            rc = commands.cmd_reconcile(
                argparse.Namespace(slot="s", device=None, pull=False)
            )

        self.assertEqual(rc, 2)
        self.assertIn("no machine-local target", out.getvalue())

    def test_unbind_clears_local_target(self):
        h = self.pack("1.0.0", b"voice one\n")
        host = self.root / "host"
        self.bind(h, host)

        with self.quiet():
            commands.cmd_unbind(argparse.Namespace(slot="s", yes=True))

        self.assertEqual(json.loads(self.bindings.read_text(encoding="utf-8"))["bindings"], [])
        self.assertEqual(json.loads(self.targets.read_text(encoding="utf-8")), {})
        self.assertFalse((host / "persona.prefix.txt").exists())


class PinnedRevertTest(CommandTestBase):
    def test_revert_converges_even_when_slot_is_pinned(self):
        older = self.pack("1.0.0", b"older voice\n")
        newer = self.pack("2.0.0", b"newer voice\n")
        host = self.root / "host"
        self.bind(newer, host)
        with self.quiet():
            self.assertEqual(commands.cmd_reconcile(
                argparse.Namespace(slot="s", device=None, pull=False)), 0)
        self.bind(newer, host, pin=True)  # host already holds the newer bundle

        with self.quiet() as (out, _):
            rc = commands.cmd_revert(argparse.Namespace(slot="s"))

        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn(b"older voice", (host / "persona.prefix.txt").read_bytes())
        entry = json.loads(self.bindings.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual(entry["hash"], older)
        self.assertTrue(entry["pin"])


if __name__ == "__main__":
    unittest.main()
