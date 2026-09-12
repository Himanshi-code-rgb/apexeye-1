"""
Data Ingestion & Ground Truth Engine (ApexEye Phase 1)
Responsible for fetching F1 session telemetry and extracting official FIA
track limit infractions from FastF1 session data and Race Control Messages.
"""

import os
import re
from pathlib import Path
import pandas as pd
import fastf1

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".fastf1_cache"
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Enable FastF1 disk cache
fastf1.Cache.enable_cache(str(CACHE_DIR))


def load_session(year: int = 2023, circuit: str = "Austria", session_type: str = "R"):
    """
    Loads an F1 session using FastF1 with telemetry and race control messages.
    
    Args:
        year: Championship season (default 2023)
        circuit: Circuit identifier or country (default 'Austria' / Red Bull Ring)
        session_type: 'R' (Race), 'Q' (Qualifying), 'SQ' (Sprint Shootout), 'S' (Sprint)
    """
    print(f"[*] Loading FastF1 session: {year} {circuit} [{session_type}]...")
    session = fastf1.get_session(year, circuit, session_type)
    session.load(telemetry=True, laps=True, weather=False, messages=True)
    print(f"[+] Loaded session: {session.event['EventName']} ({session.name})")
    return session


def parse_corner_from_text(text: str) -> str:
    """Extracts corner/turn reference from race control or deletion strings."""
    if not isinstance(text, str):
        return "Unknown"
    match = re.search(r"TURN\s*(\d+)", text, re.IGNORECASE)
    if match:
        return f"Turn {match.group(1)}"
    return "Unknown"


def extract_ground_truth_violations(session) -> pd.DataFrame:
    """
    Extracts official track limit ground truth from session.laps and session.race_control_messages.
    
    Returns:
        pd.DataFrame containing standardized infraction records.
    """
    records = []
    session_id = f"{session.event.year}_{session.event.EventName.replace(' ', '_')}_{session.name}"

    # 1. Extract from session.laps
    if hasattr(session, "laps") and session.laps is not None:
        laps_df = session.laps
        if "Deleted" in laps_df.columns:
            deleted_laps = laps_df[laps_df["Deleted"] == True].copy()
            for _, row in deleted_laps.iterrows():
                driver = str(row.get("Driver", ""))
                lap_no = int(row.get("LapNumber", 0)) if pd.notna(row.get("LapNumber")) else 0
                reason = str(row.get("DeletedReason", "Track Limits"))
                corner = parse_corner_from_text(reason)
                time_str = str(row.get("Time", ""))

                records.append({
                    "session_id": session_id,
                    "driver": driver,
                    "lap_number": lap_no,
                    "corner": corner,
                    "event_type": "DELETED_LAP",
                    "reason": reason,
                    "timestamp": time_str,
                    "source": "LAPS_TABLE"
                })

    # 2. Extract from session.race_control_messages
    if hasattr(session, "race_control_messages") and session.race_control_messages is not None:
        rcm = session.race_control_messages
        if "Message" in rcm.columns:
            tl_messages = rcm[rcm["Message"].str.contains("TRACK LIMIT", case=False, na=False)].copy()
            for _, row in tl_messages.iterrows():
                msg = str(row.get("Message", ""))
                time_val = str(row.get("Time", ""))
                flag = str(row.get("Flag", ""))
                driver_match = re.search(r"CAR\s*(\d+)\s*\(([A-Z]{3})\)", msg, re.IGNORECASE)
                driver = driver_match.group(2) if driver_match else "UNK"
                lap_match = re.search(r"LAP\s*(\d+)", msg, re.IGNORECASE)
                lap_no = int(lap_match.group(1)) if lap_match else 0
                corner = parse_corner_from_text(msg)

                records.append({
                    "session_id": session_id,
                    "driver": driver,
                    "lap_number": lap_no,
                    "corner": corner,
                    "event_type": "RACE_CONTROL_MESSAGE",
                    "reason": msg,
                    "timestamp": time_val,
                    "source": "RCM"
                })

    df = pd.DataFrame(records)
    if not df.empty:
        # Drop strict duplicates if message and lap table reported same driver & lap
        df.drop_duplicates(subset=["session_id", "driver", "lap_number", "corner", "event_type"], inplace=True)
    return df


def get_lap_telemetry(session, driver: str, lap_number: int) -> pd.DataFrame:
    """
    Retrieves full high-frequency telemetry stream for a specific driver and lap.
    
    Returns:
        pd.DataFrame with columns: [Time, Distance, Speed, X, Y, Z, Throttle, Brake, nGear, DRS]
    """
    driver_laps = session.laps.pick_drivers(driver)
    lap = driver_laps[driver_laps["LapNumber"] == lap_number]
    if lap.empty:
        raise ValueError(f"No lap data found for driver {driver} lap {lap_number}")
    
    telemetry = lap.iloc[0].get_telemetry()
    cols_to_keep = ["Time", "Distance", "Speed", "X", "Y", "Z", "Throttle", "Brake", "nGear", "DRS"]
    existing_cols = [c for c in cols_to_keep if c in telemetry.columns]
    
    clean_df = telemetry[existing_cols].copy()
    # Convert timedelta to seconds float
    if "Time" in clean_df.columns:
        clean_df["Time_sec"] = clean_df["Time"].dt.total_seconds()
    return clean_df


if __name__ == "__main__":
    # Test Ingestion Tracer Bullet
    session = load_session(2023, "Austria", "R")
    gt_df = extract_ground_truth_violations(session)
    print(f"[+] Extracted {len(gt_df)} official ground truth violations.")
    
    output_csv = DATA_DIR / "ground_truth_austria_2023.csv"
    gt_df.to_csv(output_csv, index=False)
    print(f"[+] Ground truth saved to {output_csv}")
    
    # Inspect top infractions
    if not gt_df.empty:
        print("\n--- Sample Official Ground Truth Records ---")
        print(gt_df[["driver", "lap_number", "corner", "event_type", "reason"]].head(10))
    
    # Verify telemetry retrieval on a driver with known deletions (e.g. HAM or PER)
    test_driver = "HAM"
    test_lap = 14
    print(f"\n[*] Extracting telemetry for {test_driver} Lap {test_lap}...")
    telemetry = get_lap_telemetry(session, test_driver, test_lap)
    print(f"[+] Retrieved {len(telemetry)} telemetry samples. Columns: {list(telemetry.columns)}")
