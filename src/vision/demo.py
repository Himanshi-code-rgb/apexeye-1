"""
Demo / verification harness for the steward workstation (Iteration 9).

Builds deterministic synthetic incidents and evidence packages so the
dashboard can be exercised end-to-end WITHOUT the Colab SAM service or real
broadcast footage. The synthetic keyframes/masks are illustrative: the
measurement numbers drive the UI; mask geometry only needs to be plausible.

Everything is written through the same store (`src.vision_store`) and package
builder (`src.vision.evidence`) the real pipeline uses, so swapping synthetic
data for pipeline output requires zero frontend changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src import vision_store
from src.vision import evidence as vision_evidence
from src.vision.evidence import build_evidence_package
from src.vision.homography import Homography
from src.vision.incidents import Incident
from src.vision.optical_scrutineer import WHEELS, ScrutineeringResult, WheelAssessment

FRAME_W, FRAME_H = 640, 360
LINE_X0, LINE_X1 = 432, 458          # painted line band in the synthetic frame
GRASS_X = 60                          # grass verge left of this column

# Synthetic top-down frame geometry. Front wheels are the right-hand pair.
WHEEL_W, WHEEL_H = 30, 16
WHEEL_Y = {"FL": 110, "FR": 230, "RL": 110, "RR": 230}
TIER_WHEEL_X = {
    # front/rear wheel x origin per stewarding tier
    "breach": {"front": 470, "rear": 470},      # everything past LINE_X1
    "borderline": {"front": 452, "rear": 436},  # touching the outer edge
    "cleared": {"front": 418, "rear": 418},     # clearly overlapping the paint
}

LINE_COLOR = (57, 255, 136)
TIRE_COLOR = (255, 70, 90)
HOMOGRAPHY_POINTS = (
    [(80, 340), (560, 340), (470, 60), (170, 60)],
    [(0.0, 0.0), (4.0, 0.0), (4.0, 10.0), (0.0, 10.0)],
)

# (driver, lap, corner, start, peak, end, breach_cm, priority, confidence, with_evidence)
DEMO_SPEC = [
    ("VER", 8,  "Turn 10", 210, 213, 215, 10.4, "CRITICAL",   0.97, True),
    ("HAM", 14, "Turn 10", 101, 103, 104,  9.1, "CRITICAL",   0.95, True),
    ("ALO", 33, "Turn 9",  512, 514, 516,  8.6, "CRITICAL",   0.90, False),
    ("NOR", 20, "Turn 9",  300, 302, 303,  1.2, "BORDERLINE", 0.72, True),
    ("GAS", 41, "Turn 10", 620, 622, 623,  0.8, "BORDERLINE", 0.68, False),
    ("LEC", 5,  "Turn 9",  740, 742, 744, -0.4, "CLEARED",    0.81, False),
]

def _wheel_rects(tier: str) -> Dict[str, tuple]:
    xs = TIER_WHEEL_X[tier]
    return {
        wid: (xs["front" if wid in ("FL", "FR") else "rear"], WHEEL_Y[wid])
        for wid in WHEELS
    }


def _frames(
    start: int, peak: int, end: int, breach: float, confidence: float
) -> List[Dict[str, Any]]:
    """Per-frame records for the scrubber: ramp up to the peak, hold after."""
    frames = []
    for n in range(start, end + 1):
        if breach > 0:
            if n < peak:
                frac = 0.3 + 0.5 * (n - start) / max(1, peak - start)
                excursion = round(breach * frac, 2)
            elif n == peak:
                excursion = round(breach, 2)
            else:
                excursion = round(breach * 0.9, 2)
        else:
            excursion = round(breach, 2)
        frames.append({
            "frame": n,
            "four_wheels_off": excursion > 0,
            "signed_excursion_cm": excursion,
            "is_peak": n == peak,
            "confidence": round(confidence, 3),
        })
    return frames


def build_demo_incidents() -> List[Dict[str, Any]]:
    """Builds the store documents (`Incident.to_dict()` shape + frames)."""
    docs = []
    for driver, lap, corner, start, peak, end, breach, priority, confidence, _ in DEMO_SPEC:
        incident = Incident(
            incident_id=f"VIS-{driver}-L{lap}-{corner.replace(' ', '')}-0",
            driver=driver,
            lap=lap,
            corner=corner,
            start_frame=start,
            peak_frame=peak,
            end_frame=end,
            peak_breach_cm=breach,
            priority=priority,
            confidence=confidence,
            frame_count=end - start + 1,
        )
        doc = incident.to_dict()
        doc["frames"] = _frames(start, peak, end, breach, confidence)
        docs.append(doc)
    return docs


def _synthetic_masks(tier: str) -> Dict[str, np.ndarray]:
    masks: Dict[str, np.ndarray] = {"line": np.zeros((FRAME_H, FRAME_W), dtype=bool)}
    masks["line"][:, LINE_X0:LINE_X1 + 1] = True
    for wid, (x, y) in _wheel_rects(tier).items():
        mask = np.zeros((FRAME_H, FRAME_W), dtype=bool)
        mask[y:y + WHEEL_H, x:x + WHEEL_W] = True
        masks[wid] = mask
    return masks


def _result_for(breach: float, priority: str) -> ScrutineeringResult:
    overlapping = priority == "CLEARED"
    wheels = {
        w: WheelAssessment(
            wheel=w,
            overlapping=overlapping,
            overlap_area_cm2=42.0 if overlapping else 0.0,
            gap_cm=0.0 if overlapping else abs(breach),
            signed_excursion_cm=breach,
        )
        for w in WHEELS
    }
    reasons = {
        "CRITICAL": "All four wheels clearly beyond the white line.",
        "BORDERLINE": "Tire edge near the line boundary; steward review advised.",
        "CLEARED": "Tires remain legally in contact with the boundary.",
    }
    return ScrutineeringResult(
        wheels=wheels,
        four_wheels_off=(priority != "CLEARED"),
        peak_excursion_cm=breach,
        priority=priority,
        confidence=0.9,
        reason=reasons.get(priority, reasons["BORDERLINE"]),
    )

def _write_keyframe(package_dir: Path, tier: str) -> None:
    """Draws the synthetic top-down keyframe (Pillow required, like mask PNGs)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (FRAME_W, FRAME_H), (44, 48, 56))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, GRASS_X, FRAME_H], fill=(30, 80, 40))
    draw.rectangle([LINE_X0, 0, LINE_X1, FRAME_H], fill=(232, 232, 236))
    rects = _wheel_rects(tier)
    body_x0 = min(r[0] for r in rects.values())
    body_x1 = max(r[0] for r in rects.values()) + WHEEL_W
    draw.rectangle([body_x0, 140, body_x1, 215], fill=(150, 152, 160), outline=(20, 20, 24))
    for x, y in rects.values():
        draw.rectangle([x, y, x + WHEEL_W, y + WHEEL_H], fill=(20, 20, 24), outline=(70, 70, 78))
    target = package_dir / "original" / "keyframe.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)


def seed(evidence_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Writes the demo incidents into the vision store and builds evidence
    packages (masks + synthetic keyframe) for the flagged subset.

    Args:
        evidence_dir: Optional root for packages; defaults to the module
            attribute `src.vision.evidence.INCIDENTS_DIR` (patchable in tests).

    Returns:
        Summary dict with the seeded incident ids and package ids.
    """
    docs = build_demo_incidents()
    vision_store.save_incidents(docs)

    evidence_root = (
        Path(evidence_dir) if evidence_dir is not None else Path(vision_evidence.INCIDENTS_DIR)
    )
    homography = Homography.from_correspondences(*HOMOGRAPHY_POINTS)
    built = []
    for spec, doc in zip(DEMO_SPEC, docs):
        if not spec[-1]:
            continue
        priority = spec[7]
        tier = "cleared" if priority == "CLEARED" else (
            "borderline" if priority == "BORDERLINE" else "breach"
        )
        incident = Incident(**{
            key: doc[key] for key in (
                "incident_id", "driver", "lap", "corner", "start_frame", "peak_frame",
                "end_frame", "peak_breach_cm", "priority", "confidence", "frame_count",
            )
        })
        package = build_evidence_package(
            incident=incident,
            result=_result_for(spec[6], priority),
            masks=_synthetic_masks(tier),
            homography=homography,
            output_dir=evidence_root,
            mask_colors={"line": LINE_COLOR, **{w: TIRE_COLOR for w in WHEELS}},
        )
        _write_keyframe(package.package_dir, tier)
        built.append(package.incident.incident_id)

    return {"incidents": [d["incident_id"] for d in docs], "packages": built}