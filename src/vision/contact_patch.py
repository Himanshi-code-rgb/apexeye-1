"""
Tire Contact-Patch Estimation (ApexEye Vision - Iteration 2)

A SAM tire mask covers the *visible* tire - including sidewall well above the
ground. FIA track-limits rules care about the part of the tire actually
touching the track surface, so this module reduces a visible tire mask to an
approximate ground-contact polygon in metric track coordinates.

MVP approximation (documented, not hidden):
    The contact patch is modelled as the ground-side band of the visible tire
    mask. For a typical trackside camera the ground side is the bottom of the
    tire in image space (largest v). We take the bottom `contact_fraction` of
    the mask's vertical extent, project those pixels through the camera
    homography, and return their convex hull in meters.

This is deliberately a geometric approximation. If benchmarking later shows it
is insufficient, this single module is the place to replace with a learned
contact-patch model - nothing else in the pipeline needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
from shapely.geometry import MultiPoint, Polygon

from src.vision.homography import Homography


class ContactPatchError(ValueError):
    """Raised when a contact patch cannot be estimated from the given mask."""


@dataclass
class ContactPatch:
    """
    The estimated ground-contact region of a single tire, in metric track coords.

    Attributes:
        polygon: Shapely polygon on the track ground plane (meters).
        centroid: (X, Y) representative contact point in meters.
        area_cm2: Contact region area in square centimeters.
    """

    polygon: Polygon
    centroid: Tuple[float, float]
    area_cm2: float

    def to_dict(self) -> dict:
        return {
            "polygon": [[round(x, 4), round(y, 4)] for x, y in self.polygon.exterior.coords],
            "centroid": [round(self.centroid[0], 4), round(self.centroid[1], 4)],
            "area_cm2": round(self.area_cm2, 2),
        }


def _mask_to_pixels(mask: np.ndarray) -> np.ndarray:
    """Converts a 2D boolean/0-1 mask to an (N, 2) array of (u, v) pixel coords."""
    arr = np.asarray(mask)
    if arr.ndim != 2:
        raise ContactPatchError("Tire mask must be a 2D array.")
    rows, cols = np.nonzero(arr)
    if len(rows) == 0:
        raise ContactPatchError("Tire mask is empty; cannot estimate a contact patch.")
    return np.column_stack([cols, rows]).astype(np.float64)


def estimate_contact_patch(
    tire_mask: np.ndarray,
    homography: Homography,
    contact_fraction: float = 0.20,
) -> ContactPatch:
    """
    Estimates a tire's ground-contact polygon from its visible image mask.

    Args:
        tire_mask: 2D boolean (or 0/1) mask of the visible tire in image space.
        homography: Calibrated camera homography (image pixels -> track meters).
        contact_fraction: Fraction of the tire's vertical extent (from the
            ground side) treated as the contact band. 0.20 is a conservative
            default.

    Returns:
        A ContactPatch with the projected polygon, centroid and area.
    """
    if not 0.0 < contact_fraction <= 1.0:
        raise ContactPatchError("contact_fraction must be in the range (0, 1].")

    pixels = _mask_to_pixels(tire_mask)
    v = pixels[:, 1]
    v_min, v_max = float(v.min()), float(v.max())

    # Ground side = bottom of the tire in image space (largest v).
    v_threshold = v_max - contact_fraction * (v_max - v_min)
    ground_pixels = pixels[v >= v_threshold - 1e-9]

    track_points = homography.image_to_track(ground_pixels)

    hull = MultiPoint(track_points).convex_hull
    if hull.is_empty or hull.area <= 0.0:
        # Degenerate (e.g. a single row of pixels): fall back to a tiny square
        # around the centroid so downstream geometry never sees an empty shape.
        cx, cy = track_points[:, 0].mean(), track_points[:, 1].mean()
        eps = 0.005  # 5 mm half-width
        hull = Polygon(
            [
                (cx - eps, cy - eps),
                (cx + eps, cy - eps),
                (cx + eps, cy + eps),
                (cx - eps, cy + eps),
            ]
        )

    area_cm2 = hull.area * 10_000.0
    centroid = (float(hull.centroid.x), float(hull.centroid.y))
    return ContactPatch(polygon=hull, centroid=centroid, area_cm2=area_cm2)
