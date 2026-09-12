"""
Camera Homography (ApexEye Vision - Iteration 1)

Maps image pixels from a trackside camera into a local metric ground plane
(meters / centimeters) using a 4-point perspective transform. This is the
foundation for every downstream measurement: a tire-to-white-line gap can
only be reported in centimeters once we know how many centimeters one pixel
represents at the contact point.

The transform is estimated with the standard Direct Linear Transform (DLT)
implemented in pure NumPy, so this module has no OpenCV dependency and can be
unit-tested anywhere.

Coordinate convention:
    - Image coordinates: (u, v) in pixels, origin top-left.
    - Track coordinates: (X, Y) in meters on the local ground plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


# A single point is (x, y); a quad is exactly four points.
Point = Sequence[float]


class HomographyError(ValueError):
    """Raised when a homography cannot be estimated from the given points."""


def _as_points(points: Sequence[Point], expected: int | None = None) -> np.ndarray:
    """Validates and converts an input point collection to a float64 (N, 2) array."""
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise HomographyError("Points must be a sequence of (x, y) pairs.")
    if expected is not None and len(arr) != expected:
        raise HomographyError(f"Expected exactly {expected} points, got {len(arr)}.")
    return arr


def estimate_homography(image_quad: Sequence[Point], track_quad: Sequence[Point]) -> np.ndarray:
    """
    Estimates a 3x3 homography H such that H maps image pixels -> track meters.

    Both quads must be supplied in the same correspondence order. Four point
    pairs are the minimum for a well-conditioned projective transform; we solve
    the 8x8 linear system that results from setting the homogeneous scale to 1.

    Args:
        image_quad: Four (u, v) pixel corners.
        track_quad: Four (X, Y) metric corners, same order as image_quad.

    Returns:
        A normalized 3x3 NumPy matrix mapping homogeneous image points to
        homogeneous track points.
    """
    src = _as_points(image_quad, expected=4)
    dst = _as_points(track_quad, expected=4)

    # Build the standard DLT system: for each correspondence (u,v)->(X,Y)
    #   X = (h00 u + h01 v + h02) / (h20 u + h21 v + 1)
    #   Y = (h10 u + h11 v + h12) / (h20 u + h21 v + 1)
    # Rearranged into two linear equations with h22 = 1.
    a = []
    for (u, v), (X, Y) in zip(src, dst):
        a.append([u, v, 1, 0, 0, 0, -u * X, -v * X])
        a.append([0, 0, 0, u, v, 1, -u * Y, -v * Y])
    a = np.asarray(a, dtype=np.float64)
    b = dst.reshape(-1)

    try:
        solution, *_ = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError as exc:  # pragma: no cover - defensive
        raise HomographyError(f"Homography solve failed: {exc}") from exc

    h = np.append(solution, 1.0).reshape(3, 3)

    # Normalize so h22 is 1 where possible (keeps numbers readable/debuggable).
    if abs(h[2, 2]) > 1e-12:
        h = h / h[2, 2]
    return h


@dataclass
class Homography:
    """
    A calibrated camera mapping between image pixels and the metric track plane.

    Usage:
        h = Homography.from_correspondences(image_quad, track_quad)
        track_xy = h.image_to_track([(512, 300), (800, 310)])
        cm = h.cm_per_pixel([(512, 300), (800, 310)])[0]
    """

    matrix: np.ndarray

    def __post_init__(self) -> None:
        self.matrix = np.asarray(self.matrix, dtype=np.float64)
        if self.matrix.shape != (3, 3):
            raise HomographyError("Homography matrix must be 3x3.")

    @classmethod
    def from_correspondences(
        cls, image_quad: Sequence[Point], track_quad: Sequence[Point]
    ) -> "Homography":
        """Builds a Homography from four image/track corner correspondences."""
        return cls(estimate_homography(image_quad, track_quad))

    def image_to_track(self, points: Sequence[Point]) -> np.ndarray:
        """
        Projects image pixel points to metric track-plane coordinates.

        Args:
            points: One or more (u, v) pixel points.

        Returns:
            An (N, 2) float array of (X, Y) track coordinates in meters.
        """
        pts = _as_points(points)
        ones = np.ones((len(pts), 1), dtype=np.float64)
        homogeneous = np.hstack([pts, ones])  # (N, 3)
        projected = homogeneous @ self.matrix.T  # (N, 3)

        w = projected[:, 2:3]
        if np.any(np.abs(w) < 1e-12):
            raise HomographyError(
                "A point maps to infinity under this homography (degenerate projection)."
            )
        return projected[:, :2] / w

    def track_to_image(self, points: Sequence[Point]) -> np.ndarray:
        """Inverse projection: metric track coordinates back to image pixels."""
        inv = np.linalg.inv(self.matrix)
        pts = _as_points(points)
        ones = np.ones((len(pts), 1), dtype=np.float64)
        homogeneous = np.hstack([pts, ones])
        projected = homogeneous @ inv.T
        w = projected[:, 2:3]
        if np.any(np.abs(w) < 1e-12):
            raise HomographyError("A point maps to infinity under the inverse homography.")
        return projected[:, :2] / w

    def cm_per_pixel(self, points: Sequence[Point], step_px: float = 1.0) -> np.ndarray:
        """
        Local metric scale at each image point, in centimeters per pixel.

        A homography is perspective, so scale changes across the image (things
        farther from the camera are compressed). We therefore probe the scale
        at each requested point by projecting it and a point offset by
        `step_px` horizontally in image space, then measuring the metric
        distance between the two projections.

        Args:
            points: Image pixel points where the local scale is wanted.
            step_px: Pixel probe distance (default 1 px).

        Returns:
            An (N,) array of cm/px values, one per input point.
        """
        pts = _as_points(points)
        neighbors = pts.copy()
        neighbors[:, 0] += step_px

        base_track = self.image_to_track(pts)
        neighbor_track = self.image_to_track(neighbors)

        distances_m = np.linalg.norm(neighbor_track - base_track, axis=1)
        return (distances_m / step_px) * 100.0

    def to_dict(self) -> dict:
        """Serializes the calibration for the evidence package / API."""
        return {"matrix": self.matrix.tolist()}
