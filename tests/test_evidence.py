"""
Tests for the evidence package builder (ApexEye Vision - Iteration 7).

Concept under test: each incident produces a reproducible, self-contained
folder of metadata, measurements and optional mask images.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.vision.evidence import build_evidence_package
from src.vision.homography import Homography
from src.vision.incidents import Incident
from src.vision.optical_scrutineer import WHEELS, ScrutineeringResult
from src.vision.contact_patch import ContactPatch
from shapely.geometry import Polygon


def make_incident() -> Incident:
    return Incident(
        incident_id="VIS-HAM-L14-Turn10-0",
        driver="HAM",
        lap=14,
        corner="Turn 10",
        start_frame=101,
        peak_frame=103,
        end_frame=104,
        peak_breach_cm=9.1,
        priority="CRITICAL",
        confidence=0.95,
        frame_count=4,
    )


def make_result() -> ScrutineeringResult:
    from src.vision.optical_scrutineer import WheelAssessment

    wheels = {
        w: WheelAssessment(wheel=w, overlapping=False, overlap_area_cm2=0.0, gap_cm=9.1, signed_excursion_cm=9.1)
        for w in WHEELS
    }
    return ScrutineeringResult(
        wheels=wheels,
        four_wheels_off=True,
        peak_excursion_cm=9.1,
        priority="CRITICAL",
        confidence=0.95,
        reason="All four wheels off the white line.",
    )


class TestEvidencePackage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.h = Homography.from_correspondences(
            [(200, 540), (800, 540), (650, 100), (350, 100)],
            [(0.0, 0.0), (4.0, 0.0), (4.0, 10.0), (0.0, 10.0)],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_metadata_and_measurements(self):
        package = build_evidence_package(
            incident=make_incident(),
            result=make_result(),
            homography=self.h,
            output_dir=self.tmp,
        )
        self.assertTrue(package.metadata_path.exists())
        self.assertTrue(package.measurements_path.exists())
        self.assertTrue(package.evidence_path.exists())

        metadata = json.loads(package.metadata_path.read_text())
        self.assertEqual(metadata["incident_id"], "VIS-HAM-L14-Turn10-0")
        self.assertEqual(metadata["priority"], "CRITICAL")
        self.assertTrue(metadata["verdict"]["four_wheels_off"])

        measurements = json.loads(package.measurements_path.read_text())
        self.assertAlmostEqual(measurements["peak_breach_cm"], 9.1)
        self.assertIn("homography", measurements)
        self.assertEqual(measurements["homography"]["matrix"][0][0], self.h.matrix[0][0])

    def test_renders_masks_when_pillow_available(self):
        masks = {
            "FL": np.zeros((50, 50), dtype=bool),
            "line": np.zeros((50, 50), dtype=bool),
        }
        masks["FL"][10:20, 10:20] = True
        masks["line"][0:50, 25:27] = True

        package = build_evidence_package(
            incident=make_incident(),
            result=make_result(),
            masks=masks,
            output_dir=self.tmp,
        )
        try:
            import PIL  # noqa: F401

            self.assertIn("masks/FL.png", package.rendered)
            self.assertIn("masks/line.png", package.rendered)
            self.assertTrue((package.package_dir / "masks" / "FL.png").exists())
        except ImportError:
            self.assertEqual(package.rendered, [])

    def test_custom_renderer_is_used(self):
        calls = {"count": 0}

        def renderer(mask, color):
            calls["count"] += 1
            return np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)

        build_evidence_package(
            incident=make_incident(),
            result=make_result(),
            masks={"FL": np.ones((10, 10), dtype=bool)},
            output_dir=self.tmp,
            renderer=renderer,
        )
        self.assertEqual(calls["count"], 1)

    def test_works_without_masks(self):
        package = build_evidence_package(
            incident=make_incident(),
            result=make_result(),
            output_dir=self.tmp,
        )
        self.assertEqual(package.rendered, [])
        self.assertTrue(package.metadata_path.exists())


if __name__ == "__main__":
    unittest.main()
