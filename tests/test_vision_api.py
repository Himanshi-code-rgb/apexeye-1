"""
Tests for the /api/vision/* endpoints (ApexEye Vision - Iteration 8).

Concept under test: the Flask API exposes the vision incident store and the
evidence packages as the single source of truth for the steward dashboard,
with priority-queue ordering consistent with `rank_incidents` and strict
404 (unknown incident / missing package) and 400 (invalid decision) semantics.

The tests are hermetic: the store paths and the evidence directory are
redirected into a temp dir, so the real files under data/ are never touched.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src import vision_store
from src.app import app
from src.vision import evidence as vision_evidence
from src.vision.evidence import build_evidence_package
from src.vision.incidents import Incident
from src.vision.optical_scrutineer import WHEELS, ScrutineeringResult, WheelAssessment


def incident_dict(incident_id: str, driver: str, priority: str, breach: float) -> dict:
    """Store document shape (matches `Incident.to_dict()`)."""
    return {
        "incident_id": incident_id,
        "driver": driver,
        "lap": 14,
        "corner": "Turn 10",
        "start_frame": 101,
        "peak_frame": 103,
        "end_frame": 104,
        "peak_breach_cm": breach,
        "priority": priority,
        "confidence": 0.95,
        "frame_count": 4,
    }


def make_incident(incident_id: str = "VIS-HAM-L14-Turn10-0") -> Incident:
    """Dataclass shape for building a matching evidence package."""
    return Incident(
        incident_id=incident_id,
        driver="HAM",
        lap=14,
        corner="Turn 10",
        start_frame=101,
        peak_frame=103,
        end_frame=104,
        peak_breach_cm=9.1,
        priority="CRITICAL",
        confidence=0.95,
        frame_count=4,
    )


def make_result() -> ScrutineeringResult:
    wheels = {
        w: WheelAssessment(wheel=w, overlapping=False, overlap_area_cm2=0.0, gap_cm=9.1, signed_excursion_cm=9.1)
        for w in WHEELS
    }
    return ScrutineeringResult(
        wheels=wheels,
        four_wheels_off=True,
        peak_excursion_cm=9.1,
        priority="CRITICAL",
        confidence=0.95,
        reason="All four wheels off the white line.",
    )


class TestVisionIncidentEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (
            vision_store.VISION_INCIDENTS_JSON,
            vision_store.STEWARD_DECISIONS_JSON,
            vision_evidence.INCIDENTS_DIR,
        )
        vision_store.VISION_INCIDENTS_JSON = self.tmp / "vision_incidents.json"
        vision_store.STEWARD_DECISIONS_JSON = self.tmp / "steward_decisions.json"
        vision_evidence.INCIDENTS_DIR = self.tmp / "incidents"
        self.client = app.test_client()

        vision_store.save_incidents([
            incident_dict("VIS-HAM-L14-Turn10-0", "HAM", "CRITICAL", 9.1),
            incident_dict("VIS-NOR-L20-Turn9-0", "NOR", "BORDERLINE", 1.2),
            incident_dict("VIS-VER-L8-Turn10-0", "VER", "CRITICAL", 10.4),
        ])

    def tearDown(self):
        (
            vision_store.VISION_INCIDENTS_JSON,
            vision_store.STEWARD_DECISIONS_JSON,
            vision_evidence.INCIDENTS_DIR,
        ) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_is_priority_ranked(self):
        res = self.client.get("/api/vision/incidents")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 3)
        ids = [i["incident_id"] for i in data["incidents"]]
        self.assertEqual(ids[0], "VIS-VER-L8-Turn10-0")   # CRITICAL, biggest breach
        self.assertEqual(ids[1], "VIS-HAM-L14-Turn10-0")  # CRITICAL, smaller breach
        self.assertEqual(ids[2], "VIS-NOR-L20-Turn9-0")   # BORDERLINE last
        for item in data["incidents"]:
            self.assertIn("steward_decision", item)
            self.assertIsNone(item["steward_decision"])
            self.assertIn("has_evidence", item)
            self.assertFalse(item["has_evidence"])

    def test_list_filters_by_driver_and_priority(self):
        data = self.client.get("/api/vision/incidents?driver=ham").get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["incidents"][0]["driver"], "HAM")

        data = self.client.get("/api/vision/incidents?priority=CRITICAL").get_json()
        self.assertEqual(data["count"], 2)
        self.assertTrue(all(i["priority"] == "CRITICAL" for i in data["incidents"]))

    def test_detail_found_and_unknown_404(self):
        res = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["incident_id"], "VIS-HAM-L14-Turn10-0")
        self.assertIsNone(data["steward_decision"])

        res = self.client.get("/api/vision/incident/NOPE")
        self.assertEqual(res.status_code, 404)

    def test_frames_derived_from_consecutive_range(self):
        res = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0/frames")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["frame_count"], 4)
        self.assertEqual([f["frame"] for f in data["frames"]], [101, 102, 103, 104])
        self.assertEqual([f["frame"] for f in data["frames"] if f["is_peak"]], [103])

        res = self.client.get("/api/vision/incident/NOPE/frames")
        self.assertEqual(res.status_code, 404)

    def test_frames_returns_stored_records_when_present(self):
        incidents = vision_store.load_incidents()
        incidents[0]["frames"] = [
            {"frame": 101, "four_wheels_off": True},
            {"frame": 102, "four_wheels_off": True},
        ]
        vision_store.save_incidents(incidents)

        data = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0/frames").get_json()
        self.assertEqual(
            data["frames"],
            [
                {"frame": 101, "four_wheels_off": True},
                {"frame": 102, "four_wheels_off": True},
            ],
        )

    def test_evidence_endpoint_serves_package(self):
        masks = {"FL": np.zeros((10, 10), dtype=bool)}
        masks["FL"][2:5, 2:5] = True
        build_evidence_package(
            incident=make_incident(),
            result=make_result(),
            masks=masks,
            output_dir=vision_evidence.INCIDENTS_DIR,
        )

        res = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0/evidence")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["metadata"]["incident_id"], "VIS-HAM-L14-Turn10-0")
        self.assertAlmostEqual(data["measurements"]["peak_breach_cm"], 9.1)
        self.assertEqual(data["evidence"]["rendered"], ["masks/FL.png"])

        # has_evidence flips on the queue once the package exists
        data = self.client.get("/api/vision/incidents").get_json()
        ham = next(i for i in data["incidents"] if i["driver"] == "HAM")
        self.assertTrue(ham["has_evidence"])

        # Unknown incident AND known incident without a package both 404
        self.assertEqual(self.client.get("/api/vision/incident/NOPE/evidence").status_code, 404)
        self.assertEqual(
            self.client.get("/api/vision/incident/VIS-NOR-L20-Turn9-0/evidence").status_code, 404
        )

    def test_decision_records_persists_and_overrides(self):
        res = self.client.post(
            "/api/vision/incident/VIS-HAM-L14-Turn10-0/decision",
            json={"decision": "confirm_deletion", "steward": "STW-1", "notes": "Clear daylight."},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["recorded"]["decision"], "CONFIRM_DELETION")

        detail = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0").get_json()
        self.assertEqual(detail["steward_decision"]["steward"], "STW-1")

        # A newer decision for the same incident becomes the latest one...
        self.client.post(
            "/api/vision/incident/VIS-HAM-L14-Turn10-0/decision",
            json={"decision": "DISMISS", "steward": "STW-2"},
        )
        detail = self.client.get("/api/vision/incident/VIS-HAM-L14-Turn10-0").get_json()
        self.assertEqual(detail["steward_decision"]["decision"], "DISMISS")

        # ...while the full history is preserved on disk.
        self.assertEqual(len(vision_store.load_decisions()), 2)

    def test_decision_validation(self):
        res = self.client.post(
            "/api/vision/incident/VIS-HAM-L14-Turn10-0/decision",
            json={"decision": "BAN_THE_DRIVER", "steward": "STW-1"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        res = self.client.post("/api/vision/incident/NOPE/decision", json={"decision": "DISMISS"})
        self.assertEqual(res.status_code, 404)

        res = self.client.post(
            "/api/vision/incident/VIS-HAM-L14-Turn10-0/decision",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()