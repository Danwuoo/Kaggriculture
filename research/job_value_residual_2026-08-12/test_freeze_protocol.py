"""Regression tests for immutable control freezing."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from freeze_protocol import freeze_file


class FreezeFileTests(unittest.TestCase):
    def test_refuses_to_replace_a_different_frozen_control(self):
        """Catch a later mutable artifact silently replacing the matched control."""
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "source.py"
            target = directory / "controls" / "main.py"
            source.write_bytes(b"control-A\n")
            first = freeze_file(source, target)
            source.write_bytes(b"candidate-B\n")

            with self.assertRaisesRegex(RuntimeError, "frozen control differs"):
                freeze_file(source, target)

            self.assertEqual(b"control-A\n", target.read_bytes())
            self.assertEqual(10, first["bytes"])


if __name__ == "__main__":
    unittest.main()
