"""
ApexEye Flask REST API Backend (Phase 1)
Serves circuit geometry, searchable forensic track limits violations,
and high-frequency lap telemetry with out-of-bounds containment flags.
"""

from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from src.spatial import SpielbergTrackGeometry
from src.db import ViolationsDatabase
from src.ingestion import load_session, get_lap_telemetry

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_DIR = BASE_DIR

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing for dashboard frontends

# Initialize singleton instances
track_geometry = SpielbergTrackGeometry()
db = ViolationsDatabase()
_cached_session = None


def get_session_instance():
    """Lazily loads and caches the 2023 Austrian GP session."""
    global _cached_session
    if _cached_session is None:
        _cached_session = load_session(2023, "Austria", "R")
    return _cached_session


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check and API service metadata."""
    return jsonify({
        "status": "healthy",
        "service": "ApexEye Scrutineering API",
        "version": "1.0.0",
        "circuit": "Red Bull Ring (Spielberg)",
        "phase": "Phase 1 - Spatial Ground Truth Engine",
    })


@app.route("/api/track/spielberg", methods=["GET"])
def get_track_layout():
    """
    Returns survey geometry for the Red Bull Ring.
    Includes centerline, left boundary, right boundary, and corner markers.
    """
    track_data = track_geometry.to_dict()

    # If SVG representation is available on disk, include path
    svg_path = DATA_DIR / "spielberg-3.svg"
    if svg_path.exists():
        try:
            track_data["svg_available"] = True
            with open(svg_path, "r", encoding="utf-8") as f:
                track_data["svg_content"] = f.read()
        except Exception:
            track_data["svg_available"] = False
    else:
        track_data["svg_available"] = False

    return jsonify(track_data)


@app.route("/api/violations", methods=["GET"])
def get_violations():
    """
    Search and query recorded track limit violations.
    
    Query Params:
        driver (str): 3-letter driver code (e.g. HAM, GAS, TSU)
        lap (int): Lap number
        corner (str): Corner name filter (e.g. 'Turn 10')
        ground_truth_only (bool): 'true' or '1' to filter for FIA-penalized laps only
        limit (int): Max items to return (default 50, max 500)
        offset (int): Pagination offset (default 0)
    """
    driver = request.args.get("driver")
    lap = request.args.get("lap", type=int)
    corner = request.args.get("corner")
    gt_param = request.args.get("ground_truth_only", "false").lower()
    ground_truth_only = gt_param in ("true", "1", "yes")

    limit = min(request.args.get("limit", 50, type=int), 500)
    offset = max(request.args.get("offset", 0, type=int), 0)

    records = db.query(
        driver=driver,
        lap=lap,
        corner=corner,
        ground_truth_only=ground_truth_only,
        limit=limit,
        offset=offset,
    )

    return jsonify({
        "count": len(records),
        "limit": limit,
        "offset": offset,
        "filters": {
            "driver": driver,
            "lap": lap,
            "corner": corner,
            "ground_truth_only": ground_truth_only,
        },
        "violations": records,
    })


@app.route("/api/violations/stats", methods=["GET"])
def get_violations_stats():
    """Returns high-level statistics and aggregate metrics."""
    stats = db.get_stats()
    return jsonify(stats)


@app.route("/api/violations/<violation_id>", methods=["GET"])
def get_violation_detail(violation_id: str):
    """Retrieves full forensic details for an individual violation."""
    record = db.get_by_id(violation_id)
    if not record:
        return jsonify({"error": f"Violation with ID '{violation_id}' not found."}), 404

    return jsonify({
        "violation": record,
        "forensic_report": {
            "incident_id": record["violation_id"],
            "driver": record["driver"],
            "lap": record["lap_number"],
            "location": record["corner"],
            "peak_excursion_depth": f"{record['peak_breach_m']} meters past track limits line",
            "vehicle_speed": f"{record['speed_kph']} km/h",
            "duration": f"{record['duration_sec']} seconds",
            "fia_official_adjudication": (
                f"CONFIRMED DELETION: {record['fia_official_reason']}"
                if record["fia_ground_truth"]
                else "NOT PENALIZED BY STEWARDS"
            ),
            "scrutineering_confidence": f"{int(record['confidence_score'] * 100)}%",
        },
    })


@app.route("/api/telemetry/<driver>/<int:lap_number>", methods=["GET"])
def get_lap_telemetry_stream(driver: str, lap_number: int):
    """
    Returns calibrated telemetry stream for a driver and lap,
    with out-of-bounds containment checks applied to each point.
    """
    driver = driver.upper()
    try:
        session = get_session_instance()
        raw_tel = get_lap_telemetry(session, driver, lap_number)
        cal_tel = track_geometry.calibrate_telemetry(raw_tel)
        det_tel = track_geometry.detect_violations(cal_tel, margin_m=0.35)

        # Simplify output for frontend JSON payload
        samples = []
        for _, row in det_tel.iterrows():
            samples.append({
                "time_sec": round(float(row.get("Time_sec", 0.0)), 3),
                "distance_m": round(float(row.get("Distance", 0.0)), 1),
                "speed_kph": round(float(row.get("Speed", 0.0)), 1),
                "throttle": round(float(row.get("Throttle", 0.0)), 1),
                "brake": bool(row.get("Brake", 0.0)),
                "x": round(float(row.get("calibrated_x", 0.0)), 2),
                "y": round(float(row.get("calibrated_y", 0.0)), 2),
                "corner": str(row.get("corner", "")),
                "is_violation": bool(row.get("is_violation", False)),
                "breach_dist_m": round(float(row.get("breach_distance_m", 0.0)), 2),
            })

        return jsonify({
            "driver": driver,
            "lap_number": lap_number,
            "sample_count": len(samples),
            "violation_samples": sum(1 for s in samples if s["is_violation"]),
            "telemetry": samples,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve telemetry for {driver} Lap {lap_number}: {str(e)}"}), 400


@app.route("/", methods=["GET"])
def serve_dashboard_index():
    """Serves the ApexEye web dashboard."""
    if (DASHBOARD_DIR / "index.html").exists():
        return send_from_directory(DASHBOARD_DIR, "index.html")
    return jsonify({"service": "ApexEye API", "message": "Dashboard not found"}), 404


@app.route("/<path:path>", methods=["GET"])
def serve_dashboard_static(path):
    """Serves static dashboard files (styles, scripts, assets)."""
    target = DASHBOARD_DIR / path
    allowed_extensions = (".css", ".js", ".svg", ".png", ".jpg", ".avif", ".ico", ".html")
    if target.is_file() and (path.endswith(allowed_extensions) or path == "index.html"):
        return send_from_directory(DASHBOARD_DIR, path)
    return jsonify({"error": f"Resource '{path}' not found."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
