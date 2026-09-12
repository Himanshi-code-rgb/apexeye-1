"""
Tests for the vision scrutineering pipeline (ApexEye Vision - Iteration 5).

Concept under test: the pipeline projects SAM-style masks into metric space and
reaches an FIA verdict, with the SAM network call isolated from the rule logic.
"""

import unittest

import numpy as np

from src.vision.homography import Homography
from src.vision.optical_scrutineer import ScrutineerError
from src.vision.pipeline import (
    adjudicate_frame,
    adjudicate_sequence,
    assess_frame,
    default_prompts,
    verdict_to_frame_record,
)
from src.vision.sam_client import SamServiceClient, SamServiceError


# A calibrated camera covering a 4 m x 10 m track strip.
IMAGE_QUAD = [(200, 540), (800, 540), (650, 100), (350, 100)]
TRACK_QUAD = [(0.0, 0.0), (4.0, 0.0), (4.0, 10.0), (0.0, 10.0)]


def build_homography() -> Homography:
    return Homography.from_correspondences(IMAGE_QUAD, TRACK_QUAD)


def blank_frame() -> np.ndarray:
    return np.zeros((600, 900, 3), dtype=np.uint8)


def rect_mask(height, width, top, left, shape=(600, 900)):
    mask = np.zeros(shape, dtype=bool)
    mask[top : top + height, left : left + width] = True
    return mask


class TestPipelineGeometry(unittest.TestCase):
    """The rule logic, exercised with synthetic masks (no SAM)."""

    def setUp(self):
        self.h = build_homography()
        self.line = rect_mask(400, 20, 100, 440)  # vertical band = white line

    def _wheel_masks(self, left):
        """Four tires stacked on the left side of the frame."""
        return {
            "FL": rect_mask(40, 30, 140, left),
            "FR": rect_mask(40, 30, 200, left),
            "RL": rect_mask(40, 30, 260, left),
            "RR": rect_mask(40, 30, 320, left),
        }

    def test_clear_breach_is_critical(self):
        masks = {"line": self.line, **self._wheel_masks(left=100)}
        assessment = assess_frame(masks, self.h)
        self.assertTrue(assessment.result.four_wheels_off)
        self.assertIn(assessment.result.priority, ("CRITICAL", "BORDERLINE"))

    def test_wheel_on_line_is_cleared(self):
        wheels = self._wheel_masks(left=100)
        wheels["FL"] = rect_mask(40, 30, 140, 440)  # overlapping the line
        masks = {"line": self.line, **wheels}
        assessment = assess_frame(masks, self.h)
        self.assertFalse(assessment.result.four_wheels_off)
        self.assertEqual(assessment.result.priority, "CLEARED")

    def test_missing_line_mask_rejected(self):
        with self.assertRaises(ScrutineerError):
            assess_frame(self._wheel_masks(left=100), self.h)

    def test_missing_wheel_mask_rejected(self):
        wheels = self._wheel_masks(left=100)
        del wheels["RR"]
        with self.assertRaises(ScrutineerError):
            assess_frame({"line": self.line, **wheels}, self.h)

    def test_empty_line_mask_rejected(self):
        empty_line = np.zeros((600, 900), dtype=bool)
        masks = {"line": empty_line, **self._wheel_masks(left=100)}
        with self.assertRaises(ScrutineerError):
            assess_frame(masks, self.h)

    def test_to_dict_is_json_friendly(self):
        masks = {"line": self.line, **self._wheel_masks(left=100)}
        assessment = assess_frame(masks, self.h)
        payload = assessment.to_dict()
        self.assertIn("verdict", payload)
        self.assertIn("white_line_polygon", payload)
        self.assertIn("wheels", payload["verdict"])


class TestPipelineWithFakeSam(unittest.TestCase):
    """Verifies the SAM call wiring using an injected fake client."""

    def test_adjudicate_frame_uses_client_masks(self):
        h = build_homography()
        line = rect_mask(400, 20, 100, 440)
        wheels = {
            "FL": rect_mask(40, 30, 140, 100),
            "FR": rect_mask(40, 30, 200, 100),
            "RL": rect_mask(40, 30, 260, 100),
            "RR": rect_mask(40, 30, 320, 100),
        }
        masks = {"line": line, **wheels}

        def fake_transport(url, json=None, headers=None, timeout=None):
            class R:
                status_code = 200

                def json(self_inner):
                    from src.vision.sam_client import rle_encode

                    return {"masks": {k: rle_encode(v) for k, v in masks.items()}}

            return R()

        client = SamServiceClient(base_url="https://fake", transport=fake_transport)
        boxes = {
            "FL": [100, 140, 130, 180],
            "FR": [100, 200, 130, 240],
            "RL": [100, 260, 130, 300],
            "RR": [100, 320, 130, 360],
        }
        assessment = adjudicate_frame(
            image=blank_frame(),
            wheel_boxes=boxes,
            line_box=[420, 100, 460, 500],
            homography=h,
            client=client,
        )
        self.assertTrue(assessment.result.four_wheels_off)

    def test_default_prompts_requires_all_wheels(self):
        with self.assertRaises(ScrutineerError):
            default_prompts({"FL": [0, 0, 1, 1]}, [0, 0, 1, 1])

    def test_service_down_propagates_error(self):
        def boom(*args, **kwargs):
            raise ConnectionError("tunnel down")

        client = SamServiceClient(base_url="https://x", transport=boom)
        boxes = {w: [0, 0, 1, 1] for w in ("FL", "FR", "RL", "RR")}
        with self.assertRaises(SamServiceError):
            adjudicate_frame(blank_frame(), boxes, [0, 0, 1, 1], build_homography(), client)


class TestSequenceAdjudication(unittest.TestCase):
    """Frame assessments -> ranked incidents."""

    def setUp(self):
        self.h = build_homography()
        self.line = rect_mask(400, 20, 100, 440)

    def _assessment(self, left):
        masks = {"line": self.line, **{
            "FL": rect_mask(40, 30, 140, left),
            "FR": rect_mask(40, 30, 200, left),
            "RL": rect_mask(40, 30, 260, left),
            "RR": rect_mask(40, 30, 320, left),
        }}
        return assess_frame(masks, self.h)

    def test_sequence_clusters_consecutive_frames(self):
        off = self._assessment(left=100)
        assessments = {10: off, 11: off, 12: off}
        incidents = adjudicate_sequence(assessments, driver="HAM", lap=14, corner="Turn 10")
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].driver, "HAM")
        self.assertEqual(incidents[0].lap, 14)
        self.assertEqual(incidents[0].frame_count, 3)

    def test_verdict_record_shape(self):
        record = verdict_to_frame_record(7, self._assessment(left=100), "VER", 3, "Turn 9")
        self.assertEqual(record["frame"], 7)
        self.assertEqual(record["driver"], "VER")
        self.assertIn("four_wheels_off", record)
        self.assertIn("signed_excursion_cm", record)


if __name__ == "__main__":
    unittest.main()
