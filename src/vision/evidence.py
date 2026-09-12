"""
Evidence Package Builder (ApexEye Vision - Iteration 7)

Every incident must be reproducible: a steward should be able to reconstruct
WHY the system reached its recommendation. This module writes a self-contained
folder per incident:

    data/incidents/<incident_id>/
        metadata.json        identity, verdict, priority, confidence
        measurements.json    per-wheel geometry, white-line polygon, calibration
        evidence.json        index of the rendered images
        frames/              annotated keyframe overlays (optional)
        masks/               per-object mask PNGs (optional)

The geometry and JSON writing have no vision-library dependency; image
rendering is optional and only runs when a caller supplies a renderer. That
keeps evidence generation testable on any machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from src.vision.homography import Homography
from src.vision.incidents import Incident
from src.vision.optical_scrutineer import ScrutineeringResult

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INCIDENTS_DIR = BASE_DIR / "data" / "incidents"

# A renderer turns a boolean mask into a colour (H, W, 3) uint8 image.
MaskRenderer = Callable[[np.ndarray, tuple], np.ndarray]


@dataclass
class EvidencePackage:
    """Paths and payload written for one incident."""

    incident: Incident
    package_dir: Path
    metadata_path: Path
    measurements_path: Path
    evidence_path: Path
    rendered: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident.incident_id,
            "package_dir": str(self.package_dir),
            "metadata_path": str(self.metadata_path),
            "measurements_path": str(self.measurements_path),
            "evidence_path": str(self.evidence_path),
            "rendered": self.rendered,
        }


def _mask_overlay(mask: np.ndarray, color: tuple, opacity: float = 0.5) -> np.ndarray:
    """
    Default mask renderer: paints a coloured overlay only on mask pixels.

    Produces an RGBA PNG via Pillow if available, otherwise an RGB array. We
    keep Pillow optional so evidence building works on minimal installs.
    """
    arr = np.asarray(mask).astype(bool)
    h, w = arr.shape
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    for channel, value in enumerate(color):
        canvas[..., channel][arr] = value
    return canvas


def _save_image(path: Path, image: np.ndarray) -> bool:
    """Writes an image array to PNG if Pillow is available. Returns success."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] == 4:
        Image.fromarray(arr, mode="RGBA").save(path)
    else:
        Image.fromarray(arr).save(path)
    return True


def build_evidence_package(
    incident: Incident,
    result: ScrutineeringResult,
    masks: Optional[Dict[str, np.ndarray]] = None,
    homography: Optional[Homography] = None,
    output_dir: Path = INCIDENTS_DIR,
    renderer: Optional[MaskRenderer] = None,
    mask_colors: Optional[Dict[str, tuple]] = None,
) -> EvidencePackage:
    """
    Writes the incident's metadata, measurements and (optionally) mask images.

    Args:
        incident: The clustered incident.
        result: The frame-level scrutineering result (typically the peak frame).
        masks: Optional mapping of object id -> boolean image mask, rendered to
            masks/<id>.png when Pillow is available.
        homography: Optional camera calibration, serialized into measurements.
        output_dir: Root directory for evidence packages.
        renderer: Optional custom mask renderer; defaults to a flat colour mask.
        mask_colors: Optional id -> RGB tuple for rendering.

    Returns:
        An EvidencePackage describing what was written.
    """
    package_dir = Path(output_dir) / incident.incident_id
    package_dir.mkdir(parents=True, exist_ok=True)

    metadata = incident.to_dict()
    metadata["verdict"] = result.to_dict()

    measurements: Dict[str, Any] = {
        "incident_id": incident.incident_id,
        "peak_breach_cm": incident.peak_breach_cm,
        "wheels": result.to_dict()["wheels"],
        "four_wheels_off": result.four_wheels_off,
        "confidence": result.confidence,
        "reason": result.reason,
    }
    if homography is not None:
        measurements["homography"] = homography.to_dict()

    metadata_path = package_dir / "metadata.json"
    measurements_path = package_dir / "measurements.json"
    evidence_path = package_dir / "evidence.json"

    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    with open(measurements_path, "w", encoding="utf-8") as handle:
        json.dump(measurements, handle, indent=2)

    rendered: List[str] = []
    render_fn = renderer or _mask_overlay
    if masks:
        for name, mask in masks.items():
            color = (mask_colors or {}).get(name, (0, 220, 120))
            image = render_fn(mask, color)
            target = package_dir / "masks" / f"{name}.png"
            if _save_image(target, image):
                rendered.append(str(target.relative_to(package_dir)))

    with open(evidence_path, "w", encoding="utf-8") as handle:
        json.dump({"rendered": rendered}, handle, indent=2)

    return EvidencePackage(
        incident=incident,
        package_dir=package_dir,
        metadata_path=metadata_path,
        measurements_path=measurements_path,
        evidence_path=evidence_path,
        rendered=rendered,
    )
