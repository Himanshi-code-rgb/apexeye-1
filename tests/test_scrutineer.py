"""
Tests for the deterministic optical scrutineer (ApexEye Vision - Iteration 3).

Concept under test: the FIA "four wheels off the white line" rule, encoded as
polygon intersection between tire contact patches and the line geometry.
"""

import unittest

from shapely.geometry import LineString

from src.vision.contact_patch import ContactPatch
from src.vision.optical_scrutineer import (
    WHEELS,
    ScrutineerError,
    adjudicate,
    assess_wheel,
)


def square(cx: float, cy: float, half: float = 0.10) -> ContactPatch:
    """Builds a small square contact patch centred at (cx, cy) meters."""
    from shapely.geometry import Polygon

    poly = Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )
    return ContactPatch(polygon=poly, centroid=(cx, cy), area_cm2=poly.area * 10_000.0)


def make_line(offset_x: float = 0.0):
    """
    A vertical white line running along X = offset_x, buffered to a 15 cm
    painted strip, with the legal track interior to its right.
    """
    line = LineString([(offset_x, 0.0), (offset_x, 10.0)])
    return line.buffer(0.075, cap_style=2)


def make_contacts(fl_x: float, fr_x: float, rl_x: float, rr_x: float):
    y_positions = {"FL": 1.0, "FR": 2.0, "RL": 3.0, "RR": 4.0}
    xs = {"FL": fl_x, "FR": fr_x, "RL": rl_x, "RR": rr_x}
    return {w: square(xs[w], y_positions[w]) for w in WHEELS}


class TestOpticalScrutineer(unittest.TestCase):
    def test_caseA_all_four_clearly_off_is_critical(self):
        # Line at X=0; all tires centred at X=-0.5 (0.5 m outside), no overlap.
        contacts = make_contacts(-0.5, -0.6, -0.5, -0.6)
        result = adjudicate(contacts, make_line(0.0))
        self.assertTrue(result.four_wheels_off)
        self.assertEqual(result.priority, "CRITICAL")
        self.assertGreater(result.peak_excursion_cm, 8.0)
        self.assertGreater(result.confidence, 0.5)

    def test_caseB_one_wheel_overlaps_line_is_cleared(self):
        # Front-left overlaps the line; the rest are off. Rule: NOT a breach.
        contacts = make_contacts(0.0, -0.6, -0.5, -0.6)
        result = adjudicate(contacts, make_line(0.0))
        self.assertFalse(result.four_wheels_off)
        self.assertEqual(result.priority, "CLEARED")
        self.assertTrue(result.wheels["FL"].overlapping)
        self.assertLessEqual(result.wheels["FL"].signed_excursion_cm, 0.0)

    def test_caseC_touching_outer_edge_is_borderline(self):
        # Tires just clear the line with a small gap -> BORDERLINE.
        contacts = make_contacts(-0.20, -0.22, -0.20, -0.22)
        result = adjudicate(contacts, make_line(0.0), critical_cm=8.0)
        self.assertTrue(result.four_wheels_off)
        self.assertEqual(result.priority, "BORDERLINE")
        self.assertTrue(0.0 < result.peak_excursion_cm <= 8.0)

    def test_legal_wheel_has_zero_gap_and_negative_excursion(self):
        wheel = assess_wheel("FL", square(0.0, 1.0), make_line(0.0))
        self.assertTrue(wheel.overlapping)
        self.assertEqual(wheel.gap_cm, 0.0)
        self.assertLess(wheel.signed_excursion_cm, 0.0)

    def test_gap_is_measured_when_not_overlapping(self):
        wheel = assess_wheel("FL", square(-0.30, 1.0), make_line(0.0))
        self.assertFalse(wheel.overlapping)
        self.assertGreater(wheel.gap_cm, 0.0)
        self.assertEqual(wheel.signed_excursion_cm, wheel.gap_cm)

    def test_missing_wheel_rejected(self):
        contacts = make_contacts(-0.5, -0.6, -0.5, -0.6)
        del contacts["RR"]
        with self.assertRaises(ScrutineerError):
            adjudicate(contacts, make_line(0.0))

    def test_empty_line_rejected(self):
        from shapely.geometry import GeometryCollection

        with self.assertRaises(ScrutineerError):
            adjudicate(make_contacts(-0.5, -0.6, -0.5, -0.6), GeometryCollection())

    def test_quality_factors_reduce_confidence(self):
        contacts = make_contacts(-0.5, -0.6, -0.5, -0.6)
        high = adjudicate(contacts, make_line(0.0))
        low = adjudicate(contacts, make_line(0.0), quality={"segmentation": 0.5})
        self.assertLess(low.confidence, high.confidence)


if __name__ == "__main__":
    unittest.main()
