"""verify.py portability gates: absolute paths must not enter the registry."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verify  # noqa: E402


class LooksAbsoluteTest(unittest.TestCase):
    def test_recognises_every_machine_path_form(self):
        for value in (r"D:\work\slot", "D:/work/slot", r"\\server\share",
                      "/workspace/persona", str(Path(sys.executable).resolve().parent)):
            self.assertTrue(verify.looks_absolute(value), value)

    def test_accepts_portable_forms(self):
        for value in ("sources/x", "bundles/x/abc", "external", "draft/slot"):
            self.assertFalse(verify.looks_absolute(value), value)


class RegistryPortabilityGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bundles = self.root / "bundles"
        self.bindings = self.root / "bindings.json"
        self._patches = [
            mock.patch.object(verify, "BUNDLES_DIR", self.bundles),
            mock.patch.object(verify, "BINDINGS_FILE", self.bindings),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def make_bundle(self) -> str:
        manifest = b"id: x\nversion: 1.0.0\nfiles:\n  - name: SOUL.md\n"
        content = b"voice\n"
        h = verify.canonical_hash(manifest, [("SOUL.md", content)])
        bdir = self.bundles / "x" / h
        bdir.mkdir(parents=True)
        (bdir / "persona.yaml").write_bytes(manifest)
        (bdir / "SOUL.md").write_bytes(content)
        (self.bundles / "x" / "index.json").write_bytes(
            (json.dumps({"persona": "x", "bundles": [
                {"version": "1.0.0", "hash": h, "source": "sources/x"}]}) + "\n").encode()
        )
        return h

    def write_binding(self, h: str, **extra) -> None:
        entry = {"slot": "s", "persona": "x", "hash": h, "host": "dsh", **extra}
        self.bindings.write_bytes(
            json.dumps({"bindings": [entry]}, ensure_ascii=False).encode("utf-8")
        )

    def test_rejects_machine_local_target(self):
        h = self.make_bundle()
        self.write_binding(h, target=r"D:\work\slot")
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            verify.main()
        self.assertEqual(raised.exception.code, 1)

    def test_rejects_absolute_index_source(self):
        h = self.make_bundle()
        idx = self.bundles / "x" / "index.json"
        idx.write_bytes(json.dumps({"persona": "x", "bundles": [
            {"version": "1.0.0", "hash": h, "source": r"D:\work\x"}]}).encode("utf-8"))
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            verify.main()

    def test_clean_registry_passes(self):
        h = self.make_bundle()
        self.write_binding(h)
        self.assertEqual(verify.main(), 0)


if __name__ == "__main__":
    unittest.main()
