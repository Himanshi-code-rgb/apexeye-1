"""
Incident Clustering (ApexEye Vision - Iteration 6)

Multiple consecutive frames of the same excursion are ONE steward incident,
not N separate violations. This mirrors the existing telemetry decision
(DEC-005): contiguous out-of-bounds samples are clustered into a discrete
event with a peak and a duration.

A frame enters a cluster when its verdict is a breach (`four_wheels_off`).
Frames that are legal close the cluster. A single excursion may span several
frames; we keep the peak frame and the peak excursion as the representative
evidence, and record how many frames voted for the breach.

Working with plain dicts (not NumPy masks) keeps this module trivially
testable and independent of the vision geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Incident:
    """A discrete stewarding incident assembled from consecutive breach frames."""

    incident_id: str
    driver: str
    lap: int
    corner: str
    start_frame: int
    peak_frame: int
    end_frame: int
    peak_breach_cm: float
    priority: str
    confidence: float
    frame_count: int

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "driver": self.driver,
            "lap": self.lap,
            "corner": self.corner,
            "start_frame": self.start_frame,
            "peak_frame": self.peak_frame,
            "end_frame": self.end_frame,
            "peak_breach_cm": round(self.peak_breach_cm, 2),
            "priority": self.priority,
            "confidence": round(self.confidence, 3),
            "frame_count": self.frame_count,
        }


# Priority ordering for the steward queue: most urgent first.
PRIORITY_RANK = {"CRITICAL": 0, "BORDERLINE": 1, "CLEARED": 2}


def _driver_lap_corner(frames: List[Dict[str, Any]]) -> tuple[str, int, str]:
    """Reads driver/lap/corner from the first frame of a cluster."""
    first = frames[0]
    return (
        str(first.get("driver", "UNK")),
        int(first.get("lap", 0)),
        str(first.get("corner", "Unknown")),
    )


def _build_cluster(
    frames: List[Dict[str, Any]],
    sequence: int,
) -> Optional[Incident]:
    """
    Turns a run of breach frames into one Incident, or None if the run is too
    weak to count (no positive peak).
    """
    if not frames:
        return None

    peak_frame_dict = max(frames, key=lambda f: float(f.get("signed_excursion_cm", 0.0)))
    peak_breach_cm = float(peak_frame_dict.get("signed_excursion_cm", 0.0))
    if peak_breach_cm <= 0.0:
        return None

    driver, lap, corner = _driver_lap_corner(frames)
    peak_frame_number = int(peak_frame_dict.get("frame", frames[0].get("frame", 0)))
    start_frame = int(frames[0].get("frame", peak_frame_number))
    end_frame = int(frames[-1].get("frame", peak_frame_number))

    # The incident takes the most urgent priority seen across its frames.
    priority = min(
        (str(f.get("priority", "BORDERLINE")) for f in frames),
        key=lambda p: PRIORITY_RANK.get(p, 99),
    )

    confidence = max(float(f.get("confidence", 0.0)) for f in frames)
    corner_slug = corner.replace(" ", "")
    incident_id = f"VIS-{driver}-L{lap}-{corner_slug}-{sequence}"

    return Incident(
        incident_id=incident_id,
        driver=driver,
        lap=lap,
        corner=corner,
        start_frame=start_frame,
        peak_frame=peak_frame_number,
        end_frame=end_frame,
        peak_breach_cm=peak_breach_cm,
        priority=priority,
        confidence=confidence,
        frame_count=len(frames),
    )


def cluster_incidents(
    frame_verdicts: List[Dict[str, Any]],
    min_frames: int = 1,
) -> List[Incident]:
    """
    Clusters a chronological list of per-frame verdicts into incidents.

    Args:
        frame_verdicts: Ordered list of dicts, each with at least:
            frame, four_wheels_off, signed_excursion_cm, priority, confidence,
            driver, lap, corner.
        min_frames: Minimum consecutive breach frames for a cluster to count.
            The default of 1 keeps a single-frame clear breach; raise it to
            require temporal persistence.

    Returns:
        A list of Incidents in frame order.
    """
    incidents: List[Incident] = []
    current: List[Dict[str, Any]] = []
    sequence = 0

    def flush():
        nonlocal current, sequence
        if len(current) >= min_frames:
            incident = _build_cluster(current, sequence)
            if incident is not None:
                incidents.append(incident)
                sequence += 1
        current = []

    for verdict in frame_verdicts:
        if bool(verdict.get("four_wheels_off", False)):
            current.append(verdict)
        else:
            flush()
    flush()

    return incidents


def rank_incidents(incidents: List[Incident]) -> List[Incident]:
    """
    Sorts incidents for the steward priority queue: CRITICAL first, then
    BORDERLINE, then CLEARED; within a priority, larger peak excursion and
    higher confidence come first.
    """
    return sorted(
        incidents,
        key=lambda i: (
            PRIORITY_RANK.get(i.priority, 99),
            -i.peak_breach_cm,
            -i.confidence,
        ),
    )
