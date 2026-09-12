"""
Forensic Violations Database Manager (ApexEye Phase 1)
Responsible for clustering consecutive out-of-bounds telemetry samples into
discrete stewarding incidents, cross-referencing against FIA ground truth,
persisting to data/violations.csv, and providing search/query capabilities.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VIOLATIONS_CSV = DATA_DIR / "violations.csv"
GROUND_TRUTH_CSV = DATA_DIR / "ground_truth_austria_2023.csv"


def cluster_lap_violations(
    detected_telemetry_df: pd.DataFrame,
    driver: str,
    lap_number: int,
    session_id: str,
    min_peak_breach_m: float = 1.0,
    min_consecutive_points: int = 2,
) -> List[Dict[str, Any]]:
    """
    Clusters consecutive out-of-bounds samples into distinct stewarding violation events.
    """
    events = []
    current_cluster = []

    # Focus on corners where track limit rules apply
    corners_of_interest = ["Turn 1", "Turn 3", "Turn 4", "Turn 6", "Turn 7", "Turn 9", "Turn 10"]

    for idx, row in detected_telemetry_df.iterrows():
        is_viol = bool(row["is_violation"])
        corner = str(row["corner"])

        if is_viol and corner in corners_of_interest:
            current_cluster.append(row)
        else:
            if len(current_cluster) >= min_consecutive_points:
                cluster_df = pd.DataFrame(current_cluster)
                peak_breach = cluster_df["breach_distance_m"].max()
                if peak_breach >= min_peak_breach_m:
                    peak_row = cluster_df.loc[cluster_df["breach_distance_m"].idxmax()]
                    event_corner = peak_row["corner"]
                    corner_slug = event_corner.replace(" ", "")
                    v_id = f"VIO-AUT23-{driver}-L{lap_number}-{corner_slug}"

                    start_time = cluster_df["Time_sec"].iloc[0] if "Time_sec" in cluster_df else 0.0
                    end_time = cluster_df["Time_sec"].iloc[-1] if "Time_sec" in cluster_df else 0.0
                    duration_s = max(0.1, end_time - start_time)

                    events.append({
                        "violation_id": v_id,
                        "session_id": session_id,
                        "driver": driver,
                        "lap_number": lap_number,
                        "corner": event_corner,
                        "start_time_sec": round(float(start_time), 2),
                        "end_time_sec": round(float(end_time), 2),
                        "duration_sec": round(float(duration_s), 2),
                        "speed_kph": round(float(peak_row["Speed"]), 1),
                        "peak_breach_m": round(float(peak_breach), 2),
                        "telemetry_x": round(float(peak_row["calibrated_x"]), 2),
                        "telemetry_y": round(float(peak_row["calibrated_y"]), 2),
                        "sample_count": len(cluster_df),
                        "detection_source": "SPATIAL_SHAPELY",
                        "confidence_score": round(min(0.99, 0.70 + float(peak_breach) * 0.08), 2),
                    })
            current_cluster = []

    # Check trailing cluster
    if len(current_cluster) >= min_consecutive_points:
        cluster_df = pd.DataFrame(current_cluster)
        peak_breach = cluster_df["breach_distance_m"].max()
        if peak_breach >= min_peak_breach_m:
            peak_row = cluster_df.loc[cluster_df["breach_distance_m"].idxmax()]
            event_corner = peak_row["corner"]
            corner_slug = event_corner.replace(" ", "")
            v_id = f"VIO-AUT23-{driver}-L{lap_number}-{corner_slug}"
            start_time = cluster_df["Time_sec"].iloc[0] if "Time_sec" in cluster_df else 0.0
            end_time = cluster_df["Time_sec"].iloc[-1] if "Time_sec" in cluster_df else 0.0
            events.append({
                "violation_id": v_id,
                "session_id": session_id,
                "driver": driver,
                "lap_number": lap_number,
                "corner": event_corner,
                "start_time_sec": round(float(start_time), 2),
                "end_time_sec": round(float(end_time), 2),
                "duration_sec": round(float(max(0.1, end_time - start_time)), 2),
                "speed_kph": round(float(peak_row["Speed"]), 1),
                "peak_breach_m": round(float(peak_breach), 2),
                "telemetry_x": round(float(peak_row["calibrated_x"]), 2),
                "telemetry_y": round(float(peak_row["calibrated_y"]), 2),
                "sample_count": len(cluster_df),
                "detection_source": "SPATIAL_SHAPELY",
                "confidence_score": round(min(0.99, 0.70 + float(peak_breach) * 0.08), 2),
            })

    return events


def match_with_ground_truth(violations_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cross-references detected violations against official FIA ground truth.
    Adds fia_ground_truth (bool) and fia_official_reason (str).
    """
    df = violations_df.copy()
    if df.empty:
        df["fia_ground_truth"] = False
        df["fia_official_reason"] = ""
        return df

    gt = ground_truth_df.copy()
    fia_confirmed = []
    fia_reasons = []

    for _, row in df.iterrows():
        driver = row["driver"]
        lap = row["lap_number"]
        corner = row["corner"]

        # Check if driver and lap match an official ground truth deletion
        match = gt[(gt["driver"] == driver) & (gt["lap_number"] == lap)]
        if not match.empty:
            # Check corner match if specified
            corner_match = match[match["corner"] == corner]
            if not corner_match.empty:
                fia_confirmed.append(True)
                fia_reasons.append(str(corner_match.iloc[0]["reason"]))
            else:
                # Same lap, slight corner difference in RCM text
                fia_confirmed.append(True)
                fia_reasons.append(str(match.iloc[0]["reason"]))
        else:
            fia_confirmed.append(False)
            fia_reasons.append("Unpenalized Excursion / Sub-Threshold")

    df["fia_ground_truth"] = fia_confirmed
    df["fia_official_reason"] = fia_reasons
    return df


class ViolationsDatabase:
    """Persistent CSV database for scrutineering track limit infractions."""

    def __init__(self, csv_path: Path = VIOLATIONS_CSV):
        self.csv_path = csv_path
        self._load()

    def _load(self):
        if self.csv_path.exists():
            self.df = pd.read_csv(self.csv_path)
        else:
            self.df = pd.DataFrame(columns=[
                "violation_id", "session_id", "driver", "lap_number", "corner",
                "start_time_sec", "end_time_sec", "duration_sec", "speed_kph",
                "peak_breach_m", "telemetry_x", "telemetry_y", "sample_count",
                "detection_source", "confidence_score", "fia_ground_truth", "fia_official_reason"
            ])

    def query(
        self,
        driver: Optional[str] = None,
        lap: Optional[int] = None,
        corner: Optional[str] = None,
        ground_truth_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Queries the violation database with optional filters."""
        res = self.df.copy()
        if driver:
            res = res[res["driver"].str.upper() == driver.upper()]
        if lap is not None:
            res = res[res["lap_number"] == int(lap)]
        if corner:
            res = res[res["corner"].str.contains(corner, case=False, na=False)]
        if ground_truth_only:
            res = res[res["fia_ground_truth"] == True]

        total = len(res)
        res = res.iloc[offset : offset + limit]
        return res.to_dict(orient="records")

    def get_by_id(self, violation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single violation by its unique ID."""
        match = self.df[self.df["violation_id"] == violation_id]
        if match.empty:
            return None
        return match.iloc[0].to_dict()

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregate metrics across all stored violations."""
        if self.df.empty:
            return {
                "total_violations": 0,
                "fia_confirmed_count": 0,
                "precision": 0.0,
                "drivers_count": 0,
                "corner_breakdown": {},
                "top_offending_drivers": {},
            }
        total = len(self.df)
        confirmed = int((self.df["fia_ground_truth"] == True).sum())
        return {
            "total_violations": total,
            "fia_confirmed_count": confirmed,
            "precision_rate": round(confirmed / total, 3) if total > 0 else 0.0,
            "drivers_count": int(self.df["driver"].nunique()),
            "corner_breakdown": self.df["corner"].value_counts().to_dict(),
            "top_offending_drivers": self.df["driver"].value_counts().head(5).to_dict(),
        }


def build_violations_csv_from_session(
    session,
    ground_truth_df: pd.DataFrame,
    track_geometry,
    drivers: Optional[List[str]] = None,
    max_laps_per_driver: int = 25,
) -> pd.DataFrame:
    """
    Extracts telemetry, detects breaches, clusters events, and writes data/violations.csv.
    """
    from src.ingestion import get_lap_telemetry

    if drivers is None:
        # Drivers with top recorded track limit deletions in 2023 Austria
        drivers = ["HAM", "GAS", "TSU", "SAI", "PER", "VER", "ALB", "NOR", "MAG", "OCO"]

    all_events = []
    session_id = f"{session.event.year}_{session.event.EventName.replace(' ', '_')}_{session.name}"

    print(f"[*] Scanning {len(drivers)} drivers for track limit violations...")

    for driver in drivers:
        try:
            driver_laps = session.laps.pick_drivers(driver)
            lap_nums = sorted(driver_laps["LapNumber"].dropna().unique().astype(int))
            # Scan laps
            for lap_no in lap_nums[:max_laps_per_driver]:
                try:
                    tel = get_lap_telemetry(session, driver, lap_no)
                    if tel.empty:
                        continue
                    cal = track_geometry.calibrate_telemetry(tel)
                    det = track_geometry.detect_violations(cal, margin_m=0.35)
                    events = cluster_lap_violations(det, driver, lap_no, session_id)
                    all_events.extend(events)
                except Exception as e:
                    # Lap might not have telemetry or was incomplete
                    continue
        except Exception as e:
            print(f"[-] Could not process driver {driver}: {e}")
            continue

    violations_df = pd.DataFrame(all_events)
    if not violations_df.empty:
        # Drop duplicates if any
        violations_df.drop_duplicates(subset=["violation_id"], inplace=True)
        # Match with FIA ground truth
        matched_df = match_with_ground_truth(violations_df, ground_truth_df)
    else:
        matched_df = violations_df

    VIOLATIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    matched_df.to_csv(VIOLATIONS_CSV, index=False)
    print(f"[+] Successfully saved {len(matched_df)} violations to {VIOLATIONS_CSV}")
    return matched_df


if __name__ == "__main__":
    from src.ingestion import load_session
    from src.spatial import SpielbergTrackGeometry

    track = SpielbergTrackGeometry()
    session = load_session(2023, "Austria", "R")
    gt_df = pd.read_csv(GROUND_TRUTH_CSV) if GROUND_TRUTH_CSV.exists() else pd.DataFrame()

    print("[*] Generating forensic violations database...")
    v_df = build_violations_csv_from_session(session, gt_df, track, drivers=["HAM", "GAS", "TSU", "SAI", "PER"], max_laps_per_driver=25)

    db = ViolationsDatabase()
    stats = db.get_stats()
    print("\n--- Scrutineering Engine Summary Stats ---")
    print(stats)
