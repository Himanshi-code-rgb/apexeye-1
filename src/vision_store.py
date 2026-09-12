"""
Vision Incident Store (ApexEye - Iteration 8)

Persistence for SAM-vision incidents and steward decisions. Kept deliberately
simple: a JSON document on disk plus an in-memory cache, mirroring the
CSV-ledger philosophy of DEC-004. No database daemon is required.

Two stores live here:
    - incident store: the detected incidents (from `src/vision/incidents.py`)
    - decision store: the human steward adjudications recorded against them
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VISION_INCIDENTS_JSON = DATA_DIR / "vision_incidents.json"
STEWARD_DECISIONS_JSON = DATA_DIR / "steward_decisions.json"

VALID_DECISIONS = {"CONFIRM_DELETION", "ISSUE_WARNING", "DISMISS"}


class VisionStoreError(ValueError):
    """Raised for invalid decisions or malformed store contents."""


def record_decision(
    incident_id: str,
    decision: str,
    steward: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Records a steward adjudication for an incident.

    Args:
        incident_id: The incident being adjudicated.
        decision: One of CONFIRM_DELETION, ISSUE_WARNING, DISMISS.
        steward: Name/identifier of the adjudicating steward.
        notes: Optional free-text steward rationale.

    Returns:
        The stored decision record.
    """
    decision = decision.upper().strip()
    if decision not in VALID_DECISIONS:
        raise VisionStoreError(
            f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}."
        )
    if not incident_id:
        raise VisionStoreError("incident_id is required.")

    record = {
        "incident_id": incident_id,
        "decision": decision,
        "steward": steward or "UNKNOWN",
        "notes": notes,
    }
    decisions = load_decisions()
    decisions.append(record)
    _write_json(STEWARD_DECISIONS_JSON, decisions)
    return record


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise VisionStoreError(f"Could not read {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_incidents() -> List[Dict[str, Any]]:
    """Loads all detected vision incidents from disk."""
    data = _read_json(VISION_INCIDENTS_JSON, [])
    if not isinstance(data, list):
        raise VisionStoreError(f"{VISION_INCIDENTS_JSON} must contain a JSON list.")
    return data


def save_incidents(incidents: List[Dict[str, Any]]) -> None:
    """Overwrites the incident store with the given incidents."""
    _write_json(VISION_INCIDENTS_JSON, incidents)


def load_decisions() -> List[Dict[str, Any]]:
    """Loads all recorded steward decisions from disk."""
    data = _read_json(STEWARD_DECISIONS_JSON, [])
    if not isinstance(data, list):
        raise VisionStoreError(f"{STEWARD_DECISIONS_JSON} must contain a JSON list.")
    return data


def decisions_by_incident() -> Dict[str, Dict[str, Any]]:
    """Returns the latest decision per incident id."""
    latest: Dict[str, Dict[str, Any]] = {}
    for record in load_decisions():
        latest[record["incident_id"]] = record
    return latest


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    """Finds a single incident by id."""
    for incident in load_incidents():
        if incident.get("incident_id") == incident_id:
            return incident
    return None
