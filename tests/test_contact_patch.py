"""
Tests for tire contact-patch estimation (ApexEye Vision - Iteration 2).

Concept under test: the visible tire mask is reduced to the ground-side band
and projected into metric track coordinates as a contact polygon.
"""

import unittest

import numpy as np

from src.vision.contact_patch import (
    ContactPatchError,
    estimate_contact_patch,
)
from src.vision.homography import Homography


def make_tire_mask(height: int = 100, width: int = 40, top: int = 200, left: int = 300) -> np.ndarray:
    """Builds a simple solid rectangular 'tire' mask on a blank image."""
    mask = np.zeros((400, 600), dtype=bool)
    mask[top : top + height, left : left + width] = True
    return mask


class TestContactPatch(unittest.TestCase):
    def setUp(self):
        # Same calibrated camera strip as the homography tests: 4 m wide track.
        image_quad = [(200, 540), (800, 540), (650, 100), (350, 100)]
        track_quad = [(0.0, 0.0), (4.0, 0.0), (4.0, 10.0), (0.0, 10.0)]
        self.h = Homography.from_correspondences(image_quad, track_quad)
        self.mask = make_tire_mask()

    def test_returns_polygon_centroid_and_area(self):
        patch = estimate_contact_patch(self.mask, self.h)
        self.assertGreater(patch.polygon.area, 0.0)
        self.assertGreater(patch.area_cm2, 0.0)
        self.assertEqual(len(patch.centroid), 2)

    def test_contact_band_uses_bottom_of_tire(self):
        # The contact patch must sit at the bottom of the tire, i.e. its metric
        # centroid should have a smaller Y (ground side) than the whole tire.
        patch = estimate_contact_patch(self.mask, self.h, contact_fraction=0.20)
        full_band = estimate_contact_patch(self.mask, self.h, contact_fraction=1.0)
        self.assertLess(patch.centroid[1], full_band.centroid[1])

    def test_smaller_fraction_makes_smaller_patch(self):
        small = estimate_contact_patch(self.mask, self.h, contact_fraction=0.10)
        large = estimate_contact_patch(self.mask, self.h, contact_fraction=0.50)
        self.assertLess(small.polygon.area, large.polygon.area)

    def test_empty_mask_rejected(self):
        empty = np.zeros((100, 100), dtype=bool)
        with self.assertRaises(ContactPatchError):
            estimate_contact_patch(empty, self.h)

    def test_bad_fraction_rejected(self):
        with self.assertRaises(ContactPatchError):
            estimate_contact_patch(self.mask, self.h, contact_fraction=0.0)
        with self.assertRaises(ContactPatchError):
            estimate_contact_patch(self.mask, self.h, contact_fraction=1.5)

    def test_single_row_mask_does_not_crash(self):
        mask = np.zeros((400, 600), dtype=bool)
        mask[300, 300:340] = True
        patch = estimate_contact_patch(mask, self.h)
        self.assertGreater(patch.polygon.area, 0.0)


if __name__ == "__main__":
    unittest.main()
