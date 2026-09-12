"""
Automated Test Suite for ApexEye Phase 1 Backend API & Scrutineering Engine
"""

import unittest
from src.app import app
from src.spatial import SpielbergTrackGeometry
from src.db import ViolationsDatabase


class TestApexEyePhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.track = SpielbergTrackGeometry()
        cls.db = ViolationsDatabase()

    def test_01_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("ApexEye", data["service"])

    def test_02_track_geometry_endpoint(self):
        res = self.client.get("/api/track/spielberg")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["circuit_name"], "Red Bull Ring (Spielberg)")
        self.assertGreater(data["track_length_m"], 4000)
        self.assertGreater(len(data["centerline"]), 100)
        self.assertGreater(len(data["left_boundary"]), 100)
        self.assertGreater(len(data["right_boundary"]), 100)
        self.assertTrue(data["svg_available"])

    def test_03_spatial_containment_logic(self):
        # Center of track must be contained
        c_x, c_y = self.track.centerline[100]
        inside, dist = self.track.check_point_containment(c_x, c_y)
        self.assertTrue(inside)
        self.assertEqual(dist, 0.0)

        # Displace normal vector far outside track
        l_x, l_y = self.track.left_boundary[100]
        dx = l_x - c_x
        dy = l_y - c_y
        out_x, out_y = l_x + dx * 2, l_y + dy * 2
        inside_out, dist_out = self.track.check_point_containment(out_x, out_y)
        self.assertFalse(inside_out)
        self.assertGreater(dist_out, 1.0)

    def test_04_violations_stats_endpoint(self):
        res = self.client.get("/api/violations/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data["total_violations"], 0)
        self.assertGreater(data["fia_confirmed_count"], 0)
        self.assertIn("Turn 10", data["corner_breakdown"])

    def test_05_violations_query_filtering(self):
        res = self.client.get("/api/violations?driver=HAM&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertLessEqual(len(data["violations"]), 10)
        for v in data["violations"]:
            self.assertEqual(v["driver"], "HAM")

    def test_06_violation_detail_and_forensics(self):
        # Fetch one record to get an ID
        list_res = self.client.get("/api/violations?limit=1").get_json()
        v_id = list_res["violations"][0]["violation_id"]

        detail_res = self.client.get(f"/api/violations/{v_id}")
        self.assertEqual(detail_res.status_code, 200)
        data = detail_res.get_json()
        self.assertEqual(data["violation"]["violation_id"], v_id)
        self.assertIn("forensic_report", data)
        self.assertIn("incident_id", data["forensic_report"])
        self.assertIn("peak_excursion_depth", data["forensic_report"])

    def test_07_telemetry_stream_endpoint(self):
        res = self.client.get("/api/telemetry/HAM/14")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["driver"], "HAM")
        self.assertEqual(data["lap_number"], 14)
        self.assertGreater(data["sample_count"], 100)
        self.assertGreater(data["violation_samples"], 0)
        sample = data["telemetry"][0]
        self.assertIn("speed_kph", sample)
        self.assertIn("is_violation", sample)
        self.assertIn("x", sample)
        self.assertIn("y", sample)

    def test_08_dashboard_static_serving(self):
        # Verify index.html is served
        res_idx = self.client.get("/")
        self.assertEqual(res_idx.status_code, 200)
        self.assertIn(b"Red Bull Ring (Spielberg)", res_idx.data)
        self.assertIn(b"adjudicationFilter", res_idx.data)

        # Verify app.js is served and contains API client logic
        res_js = self.client.get("/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn(b"loadViolations", res_js.data)
        self.assertIn(b"F1_DRIVERS", res_js.data)

        # Verify styles.css is served
        res_css = self.client.get("/styles.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b".forensic-adjudication-box", res_css.data)


if __name__ == "__main__":
    unittest.main()
