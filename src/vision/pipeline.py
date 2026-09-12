"""
Vision Scrutineering Pipeline (ApexEye Vision - Iteration 5)

Ties the pieces together for a single frame:

    SAM masks (image space)
        -> project white line into metric track plane
        -> tire masks -> contact patches
        -> deterministic FIA four-wheels-off adjudication

The geometry core (`assess_frame`) is deliberately separated from the SAM
network call (`adjudicate_frame`). That keeps the rule logic fully unit
testable with synthetic masks and means a broken tunnel degrades to an
explicit error, never a wrong verdict.

Wheel ids are the FIA wheel positions: FL, FR, RL, RR. The white line mask is
expected under the id "line".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
from shapely.geometry import MultiPoint, Polygon

from src.vision.contact_patch import estimate_contact_patch
from src.vision.homography import Homography
from src.vision.incidents import Incident, cluster_incidents, rank_incidents
from src.vision.optical_scrutineer import (
    WHEELS,
    ScrutineeringResult,
    ScrutineerError,
    adjudicate,
)
from src.vision.sam_client import SamServiceClient

LINE_ID = "line"


@dataclass
class FrameAssessment:
    """A single frame's scrutineering result plus the geometry used."""

    result: ScrutineeringResult
    white_line_polygon: Polygon

    def to_dict(self) -> dict:
        return {
            "verdict": self.result.to_dict(),
            "white_line_polygon": [
                [round(x, 4), round(y, 4)] for x, y in self.white_line_polygon.exterior.coords
            ],
        }


def mask_to_track_polygon(mask: np.ndarray, homography: Homography) -> Polygon:
    """
    Projects an image-space mask into the metric track plane and returns its
    convex hull as a Shapely polygon.

    This is exact for compact regions (a tire, a short line segment). For a
    white line spanning a large part of the frame the hull can over-cover; that
    limitation is documented and is a candidate for later refinement.
    """
    arr = np.asarray(mask).astype(bool)
    rows, cols = np.nonzero(arr)
    if len(rows) == 0:
        raise ScrutineerError("Received an empty mask; cannot build metric geometry.")

    pixels = np.column_stack([cols, rows]).astype(np.float64)
    track_points = homography.image_to_track(pixels)
    hull = MultiPoint(track_points).convex_hull

    if hull.is_empty or hull.area <= 0.0:
        cx, cy = track_points[:, 0].mean(), track_points[:, 1].mean()
        eps = 0.005
        hull = Polygon([(cx - eps, cy - eps), (cx + eps, cy - eps), (cx + eps, cy + eps), (cx - eps, cy + eps)])
    return hull


def assess_frame(
    masks: Dict[str, np.ndarray],
    homography: Homography,
    line_width_m: float = 0.15,
    critical_cm: float = 8.0,
    quality: Optional[Dict[str, float]] = None,
) -> FrameAssessment:
    """
    Runs the deterministic geometry on already-segmented masks.

    Args:
        masks: Mapping of id -> boolean image mask. Must contain "line" and all
            four of FL, FR, RL, RR.
        homography: Calibrated camera homography.
        line_width_m, critical_cm, quality: Passed through to the scrutineer.

    Returns:
        A FrameAssessment.
    """
    if LINE_ID not in masks:
        raise ScrutineerError(f"Missing '{LINE_ID}' mask required for adjudication.")

    white_line = mask_to_track_polygon(masks[LINE_ID], homography)

    contacts = {}
    for wheel in WHEELS:
        if wheel not in masks:
            raise ScrutineerError(f"Missing '{wheel}' tire mask required for adjudication.")
        contacts[wheel] = estimate_contact_patch(masks[wheel], homography)

    result = adjudicate(
        contacts=contacts,
        white_line=white_line,
        line_width_m=line_width_m,
        critical_cm=critical_cm,
        quality=quality,
    )
    return FrameAssessment(result=result, white_line_polygon=white_line)


def default_prompts(wheel_boxes: Dict[str, list], line_box: list) -> list:
    """
    Builds a SAM prompt list for the standard scrutineering targets.

    Args:
        wheel_boxes: Mapping of wheel id -> [x1, y1, x2, y2] image boxes.
        line_box: [x1, y1, x2, y2] box around the visible white line.

    Returns:
        A prompt list for `SamServiceClient.segment`.
    """
    prompts = [{"id": LINE_ID, "type": "box", "box": line_box}]
    for wheel in WHEELS:
        if wheel not in wheel_boxes:
            raise ScrutineerError(f"Missing box for wheel '{wheel}'.")
        prompts.append({"id": wheel, "type": "box", "box": wheel_boxes[wheel]})
    return prompts


def adjudicate_frame(
    image: np.ndarray,
    wheel_boxes: Dict[str, list],
    line_box: list,
    homography: Homography,
    client: SamServiceClient,
    line_width_m: float = 0.15,
    critical_cm: float = 8.0,
) -> FrameAssessment:
    """
    End-to-end for one frame: asks SAM for masks, then adjudicates.

    Raises SamServiceError (from the client) if the Colab service is
    unreachable, and ScrutineerError if masks are missing/empty.
    """
    prompts = default_prompts(wheel_boxes, line_box)
    masks = client.segment(image, prompts)
    return assess_frame(
        masks=masks,
        homography=homography,
        line_width_m=line_width_m,
        critical_cm=critical_cm,
    )


def verdict_to_frame_record(
    frame_index: int,
    assessment: FrameAssessment,
    driver: str = "UNK",
    lap: int = 0,
    corner: str = "Unknown",
) -> dict:
    """
    Flattens a FrameAssessment into the record shape expected by
    `cluster_incidents`, adding identity and the frame index.
    """
    return {
        "frame": frame_index,
        "driver": driver,
        "lap": lap,
        "corner": corner,
        "four_wheels_off": assessment.result.four_wheels_off,
        "signed_excursion_cm": assessment.result.peak_excursion_cm,
        "priority": assessment.result.priority,
        "confidence": assessment.result.confidence,
    }


def adjudicate_sequence(
    frame_assessments: Dict[int, FrameAssessment],
    driver: str = "UNK",
    lap: int = 0,
    corner: str = "Unknown",
    min_frames: int = 1,
) -> list:
    """
    Clusters a frame-indexed mapping of assessments into ranked incidents.

    Args:
        frame_assessments: frame index -> FrameAssessment.
        driver, lap, corner: Identity attached to every frame record.
        min_frames: Minimum consecutive breach frames for a cluster to count.

    Returns:
        A priority-ranked list of Incidents.
    """
    records = [
        verdict_to_frame_record(index, assessment, driver, lap, corner)
        for index, assessment in sorted(frame_assessments.items())
    ]
    return rank_incidents(cluster_incidents(records, min_frames=min_frames))
