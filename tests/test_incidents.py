"""
Tests for incident clustering and video sampling (ApexEye Vision - Iteration 6).

Concept under test: consecutive breach frames form one incident, and the
two-stage frame selection math is correct without needing a video file.
"""

import unittest

from src.vision.incidents import cluster_incidents, rank_incidents
from src.vision.video_sampler import (
    VideoSamplerError,
    plan_refine_timestamps,
    plan_scan_timestamps,
    scan_step_frames,
)


def frame(index, breach, excursion, priority="CRITICAL", confidence=0.9, lap=5, corner="Turn 10"):
    return {
        "frame": index,
        "driver": "HAM",
        "lap": lap,
        "corner": corner,
        "four_wheels_off": breach,
        "signed_excursion_cm": excursion,
        "priority": priority,
        "confidence": confidence,
    }


class TestIncidentClustering(unittest.TestCase):
    def test_consecutive_breach_frames_become_one_incident(self):
        verdicts = [
            frame(100, False, 0.0),
            frame(101, True, 4.0),
            frame(102, True, 7.5),
            frame(103, True, 9.1),
            frame(104, True, 5.0),
            frame(105, False, 0.0),
        ]
        incidents = cluster_incidents(verdicts)
        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident.start_frame, 101)
        self.assertEqual(incident.peak_frame, 103)
        self.assertEqual(incident.end_frame, 104)
        self.assertAlmostEqual(incident.peak_breach_cm, 9.1)
        self.assertEqual(incident.frame_count, 4)

    def test_two_separate_excursions_become_two_incidents(self):
        verdicts = [
            frame(10, True, 5.0),
            frame(11, True, 6.0),
            frame(12, False, 0.0),
            frame(20, True, 8.0),
        ]
        incidents = cluster_incidents(verdicts)
        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)

    def test_no_breach_yields_no_incidents(self):
        verdicts = [frame(i, False, 0.0) for i in range(5)]
        self.assertEqual(cluster_incidents(verdicts), [])

    def test_min_frames_filters_transient(self):
        verdicts = [frame(1, True, 9.0), frame(2, False, 0.0)]
        self.assertEqual(len(cluster_incidents(verdicts, min_frames=1)), 1)
        self.assertEqual(len(cluster_incidents(verdicts, min_frames=2)), 0)

    def test_peak_frame_is_max_excursion_not_last(self):
        verdicts = [frame(1, True, 3.0), frame(2, True, 12.0), frame(3, True, 2.0)]
        incident = cluster_incidents(verdicts)[0]
        self.assertEqual(incident.peak_frame, 2)

    def test_incident_takes_most_urgent_priority(self):
        verdicts = [
            frame(1, True, 1.0, priority="BORDERLINE"),
            frame(2, True, 9.0, priority="CRITICAL"),
        ]
        incident = cluster_incidents(verdicts)[0]
        self.assertEqual(incident.priority, "CRITICAL")

    def test_rank_incidents_orders_critical_first(self):
        verdicts = [
            frame(1, True, 1.0, priority="BORDERLINE"),
            frame(2, False, 0.0),
            frame(3, True, 9.0, priority="CRITICAL"),
        ]
        ranked = rank_incidents(cluster_incidents(verdicts))
        self.assertEqual(ranked[0].priority, "CRITICAL")
        self.assertEqual(ranked[1].priority, "BORDERLINE")


class TestVideoSamplerMath(unittest.TestCase):
    def test_scan_step(self):
        self.assertEqual(scan_step_frames(60.0, 5.0), 12)
        self.assertEqual(scan_step_frames(60.0, 10.0), 6)

    def test_scan_step_rejects_bad_rates(self):
        with self.assertRaises(VideoSamplerError):
            scan_step_frames(0.0, 5.0)
        with self.assertRaises(VideoSamplerError):
            scan_step_frames(30.0, 60.0)

    def test_plan_scan_timestamps(self):
        self.assertEqual(plan_scan_timestamps(10, 3), [0, 3, 6, 9])

    def test_plan_refine_around_peak(self):
        result = plan_refine_timestamps(peak_frame=100, frame_count=200, window_sec=1.0, source_fps=10.0)
        self.assertEqual(result, list(range(90, 111)))

    def test_plan_refine_clamps_to_bounds(self):
        result = plan_refine_timestamps(peak_frame=2, frame_count=200, window_sec=1.0, source_fps=10.0)
        self.assertEqual(result[0], 0)
        result_end = plan_refine_timestamps(peak_frame=199, frame_count=200, window_sec=1.0, source_fps=10.0)
        self.assertEqual(result_end[-1], 199)

    def test_plan_refine_rejects_bad_fps(self):
        with self.assertRaises(VideoSamplerError):
            plan_refine_timestamps(10, 100, 1.0, 0.0)


if __name__ == "__main__":
    unittest.main()
