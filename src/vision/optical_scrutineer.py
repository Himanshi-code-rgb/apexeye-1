"""
Deterministic Optical Scrutineer (ApexEye Vision - Iteration 3)

This module encodes the actual Formula 1 track-limits rule as deterministic
geometry. It does NOT use a neural network to decide anything: SAM's job ends
at producing masks. Here we take the four tire contact polygons (metric) and
the white-line geometry (metric) and answer one question:

    "Do all four wheels have zero contact with the white line?"

FIA rule as implemented:
    A breach exists if and only if ALL four wheels are off the white line.
    A wheel is "on the line" when its contact polygon intersects the line
    geometry (positive intersection area). If it does not intersect, the
    perpendicular gap is measured in centimeters.

    four_wheels_off = (no wheel intersects the line)

Signed excursion convention (centimeters):
    <= 0  -> wheel overlaps the line (legal); magnitude approximates how deep
             the contact region sits past the line.
    >  0  -> daylight gap between the contact region and the line (off-track).

Priority is a *triage* label, not a rule:
    CRITICAL   : four wheels clearly off, peak gap beyond the critical margin
    BORDERLINE : near the boundary or ambiguous evidence -> human review
    CLEARED    : strong evidence the tire remains legally on the line

The confidence value communicates evidence quality (margin-based), and is
deliberately not presented as a calibrated probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from shapely.geometry.base import BaseGeometry

from src.vision.contact_patch import ContactPatch

WHEELS = ("FL", "FR", "RL", "RR")

# Default FIA painted track-limit line width, used only to convert an overlap
# *area* into an approximate penetration *depth*.
DEFAULT_LINE_WIDTH_M = 0.15


class ScrutineerError(ValueError):
    """Raised when the scrutineer is given inconsistent or missing inputs."""


@dataclass
class WheelAssessment:
    """Per-wheel adjudication result."""

    wheel: str
    overlapping: bool
    overlap_area_cm2: float
    gap_cm: float
    signed_excursion_cm: float

    def to_dict(self) -> dict:
        return {
            "wheel": self.wheel,
            "overlapping": self.overlapping,
            "overlap_area_cm2": round(self.overlap_area_cm2, 2),
            "gap_cm": round(self.gap_cm, 2),
            "signed_excursion_cm": round(self.signed_excursion_cm, 2),
        }


@dataclass
class ScrutineeringResult:
    """Aggregate adjudication for one car at one frame."""

    wheels: Dict[str, WheelAssessment]
    four_wheels_off: bool
    peak_excursion_cm: float
    priority: str
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "four_wheels_off": self.four_wheels_off,
            "peak_excursion_cm": round(self.peak_excursion_cm, 2),
            "priority": self.priority,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "wheels": {k: v.to_dict() for k, v in self.wheels.items()},
        }


def _classify(peak_cm: float, four_wheels_off: bool, critical_cm: float) -> str:
    """
    Maps the FIA condition to a triage priority label.

    The four-wheels-off condition dominates: if any wheel still touches the
    line, the car is CLEARED regardless of how far the other wheels are. Only
    when all four are off do we distinguish a clear CRITICAL daylight gap from
    a BORDERLINE case needing human review.
    """
    if not four_wheels_off:
        return "CLEARED"
    if peak_cm > critical_cm:
        return "CRITICAL"
    return "BORDERLINE"


def _margin_confidence(peak_cm: float, boundary_cm: float = 8.0, steepness: float = 0.6) -> float:
    """
    Evidence-quality score in [0, 1] from how far the peak is from the
    boundary. This is a transparent geometric margin, not a calibrated
    probability.
    """
    x = peak_cm - boundary_cm
    value = 1.0 / (1.0 + pow(2.718281828459045, -steepness * x))
    return float(min(1.0, max(0.0, value)))


def assess_wheel(
    wheel: str,
    contact: ContactPatch,
    white_line: BaseGeometry,
    line_width_m: float = DEFAULT_LINE_WIDTH_M,
) -> WheelAssessment:
    """
    Adjudicates a single wheel against the white line.

    Args:
        wheel: One of FL, FR, RL, RR.
        contact: Metric contact patch for the wheel.
        white_line: Shapely geometry of the track-limit line on the same
            metric plane (Polygon or buffered LineString).
        line_width_m: Painted line width, used to convert overlap area to an
            approximate penetration depth.

    Returns:
        A WheelAssessment.
    """
    if white_line is None or white_line.is_empty:
        raise ScrutineerError("White-line geometry is missing or empty.")
    if line_width_m <= 0.0:
        raise ScrutineerError("line_width_m must be positive.")

    contact_poly = contact.polygon
    intersection = contact_poly.intersection(white_line)
    overlap_area_m2 = intersection.area
    overlapping = overlap_area_m2 > 1e-9

    if overlapping:
        # Approximate penetration depth: volume-of-paint over line width.
        penetration_m = overlap_area_m2 / line_width_m
        gap_cm = 0.0
        signed_cm = -penetration_m * 100.0
    else:
        gap_m = contact_poly.distance(white_line)
        gap_cm = gap_m * 100.0
        signed_cm = gap_cm

    return WheelAssessment(
        wheel=wheel,
        overlapping=overlapping,
        overlap_area_cm2=overlap_area_m2 * 10_000.0,
        gap_cm=gap_cm,
        signed_excursion_cm=signed_cm,
    )


def adjudicate(
    contacts: Dict[str, ContactPatch],
    white_line: BaseGeometry,
    line_width_m: float = DEFAULT_LINE_WIDTH_M,
    critical_cm: float = 8.0,
    quality: Optional[Dict[str, float]] = None,
) -> ScrutineeringResult:
    """
    Applies the FIA four-wheels-off rule to a full car.

    Args:
        contacts: Mapping of wheel name -> ContactPatch. All four of FL, FR,
            RL, RR are required.
        white_line: Metric white-line geometry.
        line_width_m: Painted line width.
        critical_cm: Peak-gap threshold above which a four-wheels-off incident
            is triaged CRITICAL.
        quality: Optional per-evidence quality factors (e.g. segmentation,
            calibration, temporal consistency) in [0, 1]. Folded into the
            confidence as a multiplicative modifier.

    Returns:
        A ScrutineeringResult.
    """
    missing = [w for w in WHEELS if w not in contacts]
    if missing:
        raise ScrutineerError(f"Missing contact patches for wheels: {', '.join(missing)}")

    assessments = {
        w: assess_wheel(w, contacts[w], white_line, line_width_m=line_width_m) for w in WHEELS
    }

    four_wheels_off = all(not a.overlapping for a in assessments.values())
    peak_excursion_cm = max(a.signed_excursion_cm for a in assessments.values())

    priority = _classify(peak_excursion_cm, four_wheels_off, critical_cm)
    confidence = _margin_confidence(peak_excursion_cm, boundary_cm=critical_cm)

    if quality:
        for factor in quality.values():
            confidence *= float(min(1.0, max(0.0, factor)))

    if four_wheels_off:
        reason = (
            f"All four wheels off the white line; peak excursion {peak_excursion_cm:.1f} cm."
        )
    else:
        on_line = [w for w, a in assessments.items() if a.overlapping]
        reason = (
            "No breach: wheel(s) " + ", ".join(on_line) + " remain in contact with the white line."
        )

    return ScrutineeringResult(
        wheels=assessments,
        four_wheels_off=four_wheels_off,
        peak_excursion_cm=peak_excursion_cm,
        priority=priority,
        confidence=confidence,
        reason=reason,
    )
