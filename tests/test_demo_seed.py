"""
Tests for the demo/verification seeder (Iteration 9).

Concept under test: `src/vision/demo.py` writes synthetic incidents and
evidence packages through the SAME store and package builder the real
pipeline uses, so the steward workstation is verifiable without the SAM
service. Tests are hermetic: all paths are redirected into a temp dir.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from src import vision_store
from src.vision import demo
from src.vision import evidence as vision_evidence


class TestDemoSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (
            vision_store.VISION_INCIDENTS_JSON,
            vision_store.STEWARD_DECISIONS_JSON,
            vision_evidence.INCIDENTS_DIR,
        )
        vision_store.VISION_INCIDENTS_JSON = self.tmp / "vision_incidents.json"
        vision_store.STEWARD_DECISIONS_JSON = self.tmp / "steward_decisions.json"
        vision_evidence.INCIDENTS_DIR = self.tmp / "incidents"

    def tearDown(self):
        (
            vision_store.VISION_INCIDENTS_JSON,
            vision_store.STEWARD_DECISIONS_JSON,
            vision_evidence.INCIDENTS_DIR,
        ) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_writes_store_and_packages(self):
        result = demo.seed()
        self.assertEqual(len(result["incidents"]), 6)
        self.assertEqual(len(result["packages"]), 3)

        stored = vision_store.load_incidents()
        self.assertEqual(len(stored), 6)
        self.assertEqual(
            {i["priority"] for i in stored}, {"CRITICAL", "BORDERLINE", "CLEARED"}
        )

        for package_id in result["packages"]:
            pkg = vision_evidence.INCIDENTS_DIR / package_id
            self.assertTrue((pkg / "metadata.json").exists())
            self.assertTrue((pkg / "measurements.json").exists())
            self.assertTrue((pkg / "evidence.json").exists())
            self.assertTrue((pkg / "masks" / "line.png").exists())
            self.assertTrue((pkg / "masks" / "FL.png").exists())
            self.assertTrue((pkg / "original" / "keyframe.jpg").exists())

        # every demo doc carries per-frame records for the scrubber
        ham = next(i for i in stored if i["driver"] == "HAM")
        self.assertEqual(len(ham["frames"]), 4)
        self.assertTrue(any(f["is_peak"] for f in ham["frames"]))

    def test_seed_is_idempotent(self):
        demo.seed()
        demo.seed()
        self.assertEqual(len(vision_store.load_incidents()), 6)


if __name__ == "__main__":
    unittest.main()