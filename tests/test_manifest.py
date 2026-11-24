import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from persona_stack.manifest import validate_source


class ModuleValidationTest(unittest.TestCase):
    def test_detects_sibling_reference_at_end_of_sentence(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "persona.yaml").write_bytes(
                b"id: test\nversion: 2.0.0\nfiles:\n  - name: AGENTS.md\n  - name: SOUL.md\n"
            )
            (source / "AGENTS.md").write_bytes(b"Follow the applicable requirements.\n")
            (source / "SOUL.md").write_bytes(b"Speak directly. See AGENTS.md.\n")

            _, _, _, errors, _ = validate_source(source)

        self.assertEqual(errors, ["SOUL.md: remove module filename references: AGENTS.md"])
