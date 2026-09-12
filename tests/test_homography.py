"""
Tests for the camera homography (ApexEye Vision - Iteration 1).

The concept under test: a 4-point perspective transform maps image pixels to
metric track coordinates, and the local cm-per-pixel scale is correct.
"""

import unittest

import numpy as np

from src.vision.homography import Homography, HomographyError


class TestHomography(unittest.TestCase):
    def setUp(self):
        # A camera looking at a 4 m wide strip of track. The near edge (v=540)
        # spans the full 4 m in a wide pixel range; the far edge (v=100) is
        # compressed because it is farther from the camera.
        self.image_quad = [(200, 540), (800, 540), (650, 100), (350, 100)]
        self.track_quad = [(0.0, 0.0), (4.0, 0.0), (4.0, 10.0), (0.0, 10.0)]

    def test_corner_correspondences_project_exactly(self):
        h = Homography.from_correspondences(self.image_quad, self.track_quad)
        projected = h.image_to_track(self.image_quad)
        for got, expected in zip(projected, self.track_quad):
            np.testing.assert_allclose(got, expected, atol=1e-6)

    def test_round_trip_image_to_track_to_image(self):
        h = Homography.from_correspondences(self.image_quad, self.track_quad)
        samples = [(500, 300), (420, 200), (610, 450)]
        track = h.image_to_track(samples)
        back = h.track_to_image(track)
        np.testing.assert_allclose(back, samples, atol=1e-6)

    def test_cm_per_pixel_is_positive_and_larger_far_away(self):
        h = Homography.from_correspondences(self.image_quad, self.track_quad)
        near = h.cm_per_pixel([(500, 540)])[0]  # bottom (near) edge
        far = h.cm_per_pixel([(500, 100)])[0]   # top (far) edge
        self.assertGreater(near, 0.0)
        self.assertGreater(far, 0.0)
        # Perspective compression: a pixel near the horizon covers more meters.
        self.assertGreater(far, near)

    def test_cm_per_pixel_matches_known_width(self):
        # The near edge spans 4 m over 600 px, so ~0.667 cm/px at that edge.
        h = Homography.from_correspondences(self.image_quad, self.track_quad)
        near = h.cm_per_pixel([(500, 540)])[0]
        expected = (400.0 / 600.0)
        self.assertAlmostEqual(near, expected, places=2)

    def test_rejects_wrong_point_count(self):
        with self.assertRaises(HomographyError):
            Homography.from_correspondences(self.image_quad[:3], self.track_quad)
        with self.assertRaises(HomographyError):
            Homography.from_correspondences(self.image_quad, self.track_quad[:3])

    def test_rejects_non_3x3_matrix(self):
        with self.assertRaises(HomographyError):
            Homography(np.eye(2))


if __name__ == "__main__":
    unittest.main()
