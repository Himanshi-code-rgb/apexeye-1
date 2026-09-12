"""
Spatial Track Boundary & Containment Engine (ApexEye Phase 1)
Builds mathematical circuit boundaries from TUMFTM survey data,
performs coordinate calibration on FastF1 telemetry, and executes
deterministic point-in-polygon containment checks using Shapely.
"""

from pathlib import Path
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, Point, LineString

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TUMFTM_FILE = DATA_DIR / "Spielberg_tumftm.csv"

# Precomputed global bounds for 2023 Austrian GP (Spielberg)
# TUMFTM survey coordinates (in meters)
TUM_X_MIN = -957.61
TUM_X_MAX = 299.03
TUM_Y_MIN = -115.57
TUM_Y_MAX = 675.41

# FastF1 telemetry coordinate extents (in decimeters)
FF1_X_MIN = -8233.0
FF1_X_MAX = 4246.0
FF1_Y_MIN = -2243.7
FF1_Y_MAX = 5679.2

# Corner distance ranges along Red Bull Ring lap (in meters, total lap ~4318m)
CORNER_RANGES = [
    (0, 200, "Main Straight"),
    (200, 480, "Turn 1"),
    (480, 1300, "Uphill Straight"),
    (1300, 1600, "Turn 3"),
    (1600, 2000, "Straight 2"),
    (2000, 2350, "Turn 4"),
    (2350, 2600, "Turn 5"),
    (2600, 2900, "Turn 6"),
    (2900, 3300, "Turn 7"),
    (3300, 3650, "Turn 8"),
    (3650, 4000, "Turn 9"),
    (4000, 4318, "Turn 10"),
]


class SpielbergTrackGeometry:
    """Encapsulates the 2D polygon boundaries and surveying coordinates for Spielberg."""

    def __init__(self, tumftm_csv_path: Path = TUMFTM_FILE):
        self.tumftm_csv_path = tumftm_csv_path
        self._load_and_build_geometry()

    def _load_and_build_geometry(self):
        """Loads TUMFTM data and computes inner/outer boundary ribbons and Shapely polygon."""
        df = pd.read_csv(
            self.tumftm_csv_path,
            comment="#",
            names=["x_m", "y_m", "w_tr_right_m", "w_tr_left_m"],
        )
        self.raw_df = df

        x = df["x_m"].values
        y = df["y_m"].values
        w_right = df["w_tr_right_m"].values
        w_left = df["w_tr_left_m"].values

        # Segment differentials (periodic boundary)
        dx = np.roll(x, -1) - np.roll(x, 1)
        dy = np.roll(y, -1) - np.roll(y, 1)
        norm = np.hypot(dx, dy)
        tx = dx / norm
        ty = dy / norm

        # Left boundary points (outer line on right-hand turns)
        left_x = x - ty * w_left
        left_y = y + tx * w_left

        # Right boundary points (inner line)
        right_x = x + ty * w_right
        right_y = y - tx * w_right

        self.centerline = list(zip(x, y))
        self.left_boundary = list(zip(left_x, left_y))
        self.right_boundary = list(zip(right_x, right_y))

        # Closed ribbon polygon: follow left forward, then right backward
        ribbon_coords = self.left_boundary + self.right_boundary[::-1]
        self.polygon = Polygon(ribbon_coords)
        if not self.polygon.is_valid:
            self.polygon = self.polygon.buffer(0)

        # Centerline line string for distance projection
        self.centerline_line = LineString(self.centerline)

    def calibrate_point(self, ff1_x: float, ff1_y: float) -> Tuple[float, float]:
        """
        Maps a FastF1 (X, Y) decimeter point to TUMFTM meter coordinates using min-max scaling.
        """
        x_norm = (ff1_x - FF1_X_MIN) / (FF1_X_MAX - FF1_X_MIN)
        y_norm = (ff1_y - FF1_Y_MIN) / (FF1_Y_MAX - FF1_Y_MIN)

        cal_x = TUM_X_MIN + x_norm * (TUM_X_MAX - TUM_X_MIN)
        cal_y = TUM_Y_MIN + y_norm * (TUM_Y_MAX - TUM_Y_MIN)
        return float(cal_x), float(cal_y)

    def calibrate_telemetry(self, telemetry_df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies min-max coordinate alignment to an entire FastF1 telemetry DataFrame.
        """
        df = telemetry_df.copy()
        x_norm = (df["X"] - FF1_X_MIN) / (FF1_X_MAX - FF1_X_MIN)
        y_norm = (df["Y"] - FF1_Y_MIN) / (FF1_Y_MAX - FF1_Y_MIN)

        df["calibrated_x"] = TUM_X_MIN + x_norm * (TUM_X_MAX - TUM_X_MIN)
        df["calibrated_y"] = TUM_Y_MIN + y_norm * (TUM_Y_MAX - TUM_Y_MIN)
        return df

    @staticmethod
    def identify_corner(distance_m: float) -> str:
        """Identifies circuit corner name from lap distance in meters."""
        norm_dist = distance_m % 4318.0
        for start, end, name in CORNER_RANGES:
            if start <= norm_dist < end:
                return name
        return "Unknown"

    def check_point_containment(self, x: float, y: float, margin_m: float = 0.5) -> Tuple[bool, float]:
        """
        Tests if a point is within the track polygon (within margin_m buffer for tire width).
        
        Returns:
            (is_inside: bool, distance_from_track_edge: float)
            Positive distance indicates out-of-bounds breach.
        """
        pt = Point(x, y)
        if self.polygon.contains(pt):
            return True, 0.0
        
        # Calculate distance outside the boundary
        dist = self.polygon.exterior.distance(pt)
        if dist <= margin_m:
            # Within tire width margin
            return True, 0.0
        return False, dist

    def detect_violations(self, calibrated_df: pd.DataFrame, margin_m: float = 0.5) -> pd.DataFrame:
        """
        Scans a calibrated telemetry DataFrame and detects track limit breach points.
        """
        df = calibrated_df.copy()
        results = []

        for idx, row in df.iterrows():
            cx, cy = row["calibrated_x"], row["calibrated_y"]
            dist_m = row.get("Distance", 0.0)
            corner = self.identify_corner(dist_m)
            
            is_inside, breach_dist = self.check_point_containment(cx, cy, margin_m=margin_m)
            is_violation = not is_inside

            results.append({
                "is_violation": is_violation,
                "breach_distance_m": round(breach_dist, 3),
                "corner": corner
            })

        res_df = pd.DataFrame(results, index=df.index)
        return pd.concat([df, res_df], axis=1)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes track geometry for JSON API consumers."""
        return {
            "circuit_name": "Red Bull Ring (Spielberg)",
            "country": "Austria",
            "track_length_m": round(self.centerline_line.length, 2),
            "centerline": [[round(x, 2), round(y, 2)] for x, y in self.centerline],
            "left_boundary": [[round(x, 2), round(y, 2)] for x, y in self.left_boundary],
            "right_boundary": [[round(x, 2), round(y, 2)] for x, y in self.right_boundary],
            "corners": [
                {"name": name, "start_m": s, "end_m": e}
                for s, e, name in CORNER_RANGES
            ]
        }


if __name__ == "__main__":
    track = SpielbergTrackGeometry()
    print(f"[+] Loaded Spielberg Geometry. Area: {track.polygon.area:.1f} m^2")
    print(f"[+] Track length: {track.centerline_line.length:.1f} m")

    # Verification: Test point inside and outside
    inside_pt = track.centerline[50]
    is_in, dist = track.check_point_containment(inside_pt[0], inside_pt[1])
    print(f"[+] Test Centerline Point: Inside={is_in}, Distance={dist}m")
    assert is_in is True, "Centerline point must be inside track polygon"

    # Test point outside track boundary (pushed 5m beyond left boundary along normal)
    p_center = track.centerline[50]
    p_left = track.left_boundary[50]
    out_dx = p_left[0] - p_center[0]
    out_dy = p_left[1] - p_center[1]
    outside_pt = (p_left[0] + out_dx, p_left[1] + out_dy)
    is_in, dist = track.check_point_containment(outside_pt[0], outside_pt[1])
    print(f"[+] Test Excursion Point (+5m normal): Inside={is_in}, Distance={dist:.2f}m")
    assert is_in is False, "Excursion point must be flagged as outside"
    assert dist > 4.0, "Excursion distance must be greater than 4m"
    print("[+] All spatial containment assertions passed successfully!")
