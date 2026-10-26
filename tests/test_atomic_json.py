import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from storage.atomic_json import atomic_json_dump


class AtomicJsonTests(unittest.TestCase):
    def test_replaces_existing_json_with_complete_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}', encoding="utf-8")
            atomic_json_dump(str(path), {"new": [1, 2, 3]}, indent=2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": [1, 2, 3]})
            self.assertEqual(list(Path(tmp).glob(".state-*.tmp")), [])

    def test_failed_serialization_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}', encoding="utf-8")
            with mock.patch("storage.atomic_json.json.dump", side_effect=TypeError("serialization failed")):
                with self.assertRaises(TypeError):
                    atomic_json_dump(str(path), {"new": object()})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
            self.assertEqual(list(Path(tmp).glob(".state-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
