# Decision Log

## DEC-001: Race Session Selection for Phase 1 MVP
- **Date**: 2026-09-11
- **Decision**: Select the **2023 Austrian Grand Prix (Red Bull Ring / Spielberg)** as the primary dataset for Phase 1 telemetry and ground truth validation.
- **Context**: We need a representative Formula 1 race with high-density, contested track limits violations to calibrate spatial detection and evaluate our scrutineering pipeline against official stewarding decisions.
- **Alternatives Considered**:
  - *2023 Qatar GP (Lusail)*: Numerous violations due to high kerbs, but TUMFTM does not contain survey data for Lusail.
  - *2024 Austrian GP*: Track limits were heavily reduced due to new gravel strips installed at Turns 9 and 10, resulting in fewer violations to evaluate.
- **Chosen Decision**: 2023 Austrian GP (Spielberg).
- **Why**:
  - Over 1,200 reported track limit breaches, over 100 lap times deleted across the weekend, and 12 post-race penalties issued.
  - High concentration of infractions at Turns 9 and 10.
  - Survey geometry is available in the TUMFTM database (`Spielberg.csv`).
  - FastF1 provides full telemetry, deleted lap flags, and race control message logs.
- **Consequences**: Telemetry ingestion will focus on Spielberg coordinates and turns.
- **Future Considerations**: Generalize coordinate calibration parameters to support other circuits (Monza, Silverstone, Austin) in subsequent phases.

---

## DEC-002: Track Boundary Representation (TUMFTM vs. GeoJSON vs. SVG)
- **Date**: 2026-09-11
- **Decision**: Use **TUMFTM Racetrack Database** for spatial boundary calculations and containment, and format normalized coordinate paths (or vector SVG paths) for frontend dashboard presentation.
- **Context**: The system must deterministically check whether a vehicle breaches track limits (the white line). We needed to evaluate TUMFTM, `bacinger/f1-circuits` (GeoJSON), and `julesr0y/f1-circuits-svg` (SVG).
- **Alternatives Considered**:
  - *bacinger/f1-circuits (GeoJSON)*: Contains lat/lon coordinates, but lacks precise continuous track width measurements ($w_{left}, w_{right}$) needed to compute sub-meter boundary lines.
  - *julesr0y/f1-circuits-svg (SVG)*: Excellent visual paths, but does not provide meter-scale geometric coordinates for mathematical vehicle containment checks.
- **Chosen Decision**: TUMFTM for backend spatial logic; SVG/JSON geometry endpoints for the frontend.
- **Why**: TUMFTM provides $(x, y)$ centerline points with left and right track widths ($w_{tr\_left\_m}, w_{tr\_right\_m}$) allowing construction of exact 2D `shapely.Polygon` boundaries.
- **Consequences**: FastF1 telemetry coordinates must be transformed and aligned to TUMFTM metric space.
- **Future Considerations**: Cache calibrated transformation matrices per circuit.

---

## DEC-003: Ground Truth Source for Scrutineering Validation
- **Date**: 2026-09-11
- **Decision**: Use FastF1 `session.laps['Deleted']` alongside filtered `session.race_control_messages` as the official FIA Ground Truth.
- **Context**: To validate our spatial detection engine, we need an authoritative source of known infractions.
- **Alternatives Considered**: Manual scraping of FIA PDF stewarding documents.
- **Chosen Decision**: FastF1's built-in `session.laps['Deleted']`, `session.laps['DeletedReason']`, and `session.race_control_messages` feed.
- **Why**: Directly programmatically accessible, synchronized with lap times and driver car numbers, and provides specific turn references (e.g. `"TRACK LIMITS AT TURN 10 LAP 17"`).
- **Consequences**: Any lap officially flagged by the FIA can be automatically matched against our detected breaches.
- **Future Considerations**: Use this ground truth as training labels for the Phase 2 LightGBM model.

---

## DEC-004: Phase 1 Data Storage and Backend API
- **Date**: 2026-09-11
- **Decision**: Store detected violations in a structured CSV database (`data/violations.csv`) and expose them via a Flask REST API.
- **Context**: Phase 1 requires a lightweight, easily auditable storage format for forensic reports and a clean API for dashboard consumption.
- **Alternatives Considered**: SQLite, PostgreSQL.
- **Chosen Decision**: CSV ledger backed by pandas for querying, served via Flask endpoints.
- **Why**: Satisfies the project blueprint requirements, ensures forensic transparency (human-readable CSV), requires zero external database daemon setup, and integrates seamlessly with pandas.
- **Consequences**: Suitable for Phase 1 MVP dataset size (~100–1,500 records).
- **Future Considerations**: Migrate to SQLite or PostgreSQL if real-time multi-race streaming is introduced.

---

## DEC-005: Out-of-Bounds Event Clustering and Telemetry Alignment
- **Date**: 2026-09-11
- **Decision**: Cluster contiguous out-of-bounds telemetry samples into discrete stewarding violation events with peak excursion depth and duration, rather than logging raw point coordinates individually.
- **Context**: 3–4 Hz telemetry feeds generate 10–25 consecutive coordinate points during a single corner excursion. Logging every sample individually creates extreme noise and fails to represent an incident as reviewed by FIA stewards.
- **Alternatives Considered**: Logging every raw out-of-bounds point as a separate database row.
- **Chosen Decision**: Temporal and spatial clustering per corner per lap, computing `peak_breach_m`, `duration_sec`, `speed_kph`, and `confidence_score`.
- **Why**: Mirrors official stewarding workflow, enables concise reporting (`VIO-AUT23-HAM-L14-Turn10`), and allows direct one-to-one matching against FIA deleted laps.
- **Consequences**: Telemetry points within the incident are preserved and served via the `/api/telemetry/<driver>/<lap>` endpoint for visual scrubbers.
- **Future Considerations**: Feed these clustered 20-row sliding windows directly to the Phase 2 LightGBM tabular model.

---

## DEC-006: Dashboard Frontend Integration and Backend Truth Alignment
- **Date**: 2026-09-12
- **Decision**: Treat the Flask REST API backend as the single source of truth for race session data, circuit geometry, and forensic metrics, updating the `apexeye-1` dashboard to consume `/api/track/spielberg`, `/api/violations`, `/api/violations/stats`, and `/api/violations/<id>`.
- **Context**: The `apexeye-1` folder contained an uncoupled prototype relying on hardcoded mock arrays and placeholder metrics. To enable forensic review of track limits breaches, the frontend needed to reflect real telemetry and FIA ground truth.
- **Alternatives Considered**: Keeping mock data and developing a separate backend connector; having the frontend read raw CSV files directly in JavaScript.
- **Chosen Decision**: Dynamic API integration via `fetch()` against Flask endpoints, with optional unified static serving from Flask at `/`.
- **Why**: Ensures consistency across metrics, aligns the UI with 2023 Austrian GP stewarding ground truth, and centralizes calculations in the backend engine.
- **Consequences**: Spielberg is set as the active calibrated circuit; incident cards dynamically display breach depth, corner numbers, and FIA adjudication badges; incident detail modal renders authoritative stewarding notes and confidence scores.
- **Future Considerations**: Connect the modal's replay view to render an animated canvas or SVG scrubber tracing the car's path from `/api/telemetry/<driver>/<lap>`.

---

## DEC-007: Unified Repository Root Structure and Flattened Layout
- **Date**: 2026-09-12
- **Decision**: Flatten the repository by promoting the `.git` configuration and frontend files (`index.html`, `styles.css`, `app.js`) to the project workspace root (`ApexEye/`), eliminating the nested `apexeye-1` subfolder and establishing `.gitignore` exclusions for heavy local caches (`.venv/`, `.fastf1_cache/`).
- **Context**: The repository on GitHub (`Himanshi-code-rgb/apexeye-1`) was originally initialized with frontend files at its root level. Cloning it into `ApexEye/apexeye-1/` created an awkward nested layout where python environments and backend modules were detached from git tracking.
- **Alternatives Considered**: Moving backend modules into `apexeye-1/`; maintaining two separate git repositories.
- **Chosen Decision**: Promote git to root and flatten files into `ApexEye/`.
- **Why**: Keeps git history clean, preserves original remote URLs and root file paths on GitHub, ensures the Python environment (`.venv`) works without broken path imports, and delivers a unified full-stack codebase.
- **Consequences**: `src/app.py` serves the dashboard directly from `BASE_DIR`; all automated tests pass; `git status` shows clean diffs against upstream `origin/main`.

---

## DEC-008: Innovation Pivot to SAM-Vision Scrutineering & Steward Review Dashboard
- **Date**: 2026-09-12
- **Decision**: Pivot the project architecture to a single innovative vision-first path: Optical track limits scrutineering powered by **Segment Anything (SAM)**, paired with a dedicated **Steward Manual Review Dashboard**.
- **Context**: Rather than dividing effort across competing classical ML models and multi-track telemetry experiments, the project prioritizes maximum technical innovation for TrackShift 2026 by solving the fundamental physical challenge: promptable optical segmentation of tire contact patches against the white line.
- **Alternatives Considered**: 4-phase hybrid approach splitting focus between tabular LightGBM, telemetry heuristics, and vision.
- **Chosen Decision**: Single focused vision path using SAM (MobileSAM / SAM-2) for zero-shot white line and tire segmentation, deterministic contact-patch polygon intersection checking, and a dedicated steward review workstation with priority triage and "Hawk-Eye" zoom.
- **Why**: Delivers the highest innovation value, solves the physical contact patch question that 3-4Hz GPS telemetry cannot resolve on its own, and provides race stewards with an evidence-backed manual review console.
- **Consequences**: Architecture centers around `src/vision/` (homography, SAM segmenter, optical scrutineer, benchmark generator) and a re-engineered frontend dashboard for manual review.
- **Future Considerations**: Connect to live multi-camera RTSP feeds and deploy ONNX models on edge devices.

---

## DEC-009: Colab-Hosted SAM Service Behind a Cloudflare Tunnel
- **Date**: 2026-09-13
- **Decision**: Run SAM in a Google Colab GPU session exposed as a small FastAPI service through a Cloudflare quick tunnel. The local repository never loads the model; it calls the service over HTTP using `src/vision/sam_client.py`.
- **Context**: SAM 3.1 requires Python >=3.12, PyTorch >=2.7, CUDA >=12.6, and gated weights, which is heavy for the local Intel/RTX 2060 laptop. The local pipeline only needs structured mask outputs.
- **Alternatives Considered**: Manual download/upload of outputs; Google Drive mount + rclone sync; a git artifact branch; a paid hosted inference API.
- **Chosen Decision**: Colab runs `notebooks/sam_service.ipynb` (FastAPI + Cloudflare tunnel); the local client POSTs a base64 PNG plus prompts and receives RLE-encoded masks. Connection details come from `SAM_API_URL` / `SAM_API_KEY` env vars.
- **Why**: Zero manual artifact transfer after session start; the model backend is fully swappable (SAM 2.1 today, SAM 3.1 when gated access is granted); the repo stays lightweight.
- **Consequences**: The service is ephemeral (tunnel URL changes per session, session can disconnect); masks travel as RLE so no Pillow/torch/OpenCV is needed locally; a shared `X-API-Key` guards the public endpoint; a down service degrades to an explicit `SamServiceError`, never a wrong verdict.
- **Future Considerations**: Named Cloudflare tunnel with a persistent token for stability; batch endpoints; TrueNAS/edge ONNX deployment.

---

## DEC-010: SAM 2.1 as the Default Model, SAM 3.1 as Upgrade Path
- **Date**: 2026-09-13
- **Decision**: Default the Colab service to **SAM 2.1 Hiera Tiny** (Apache-2.0) and keep SAM 3.1 as a drop-in upgrade once Hugging Face gated access is granted.
- **Context**: Research confirmed SAM 3 / SAM 3.1 are public but gated behind a custom "SAM License" and require `hf auth login`; SAM 2.1 is Apache-2.0, downloadable without login, and runs comfortably on a Colab T4.
- **Alternatives Considered**: Blocking the vision path until SAM 3.1 access is granted; using a paid hosted endpoint.
- **Chosen Decision**: Model-agnostic service protocol (`/segment`) with a `MODEL_VARIANT` switch in the notebook; SAM 2.1 Tiny ships as the working default.
- **Why**: Keeps the pipeline runnable and demonstrable today while preserving the SAM 3.1 (text-prompt + object multiplexing) path for when access is available.
- **Consequences**: Text prompts are rejected by SAM 2.1 and require SAM 3; the client interface is identical for both.
- **Future Considerations**: Re-benchmark tire/contact-patch quality once SAM 3.1 is available, since its text prompting may reduce the need for hand-drawn boxes.

---




## DEC-011: JSON-First Evidence Packages with Renderer-Injected Images
- **Date**: 2026-09-13
- **Decision**: Build each incident's evidence package as a self-contained folder `data/incidents/<incident_id>/` holding `metadata.json`, `measurements.json`, `evidence.json` (artifact index) and an optional `masks/` directory; image rendering is supplied as an optional renderer callable so the JSON core runs on any machine with Pillow fully optional.
- **Context**: Plan section 25 sketches a full dossier (`original/`, `overlays/`, `birdseye/`, `hawkeye/`). Real broadcast footage and multi-camera renders do not exist locally yet, and hard-requiring image libraries would make evidence generation untestable on minimal installs.
- **Alternatives Considered**: Requiring OpenCV/Pillow up front and writing all image directories; storing everything in one large JSON blob.
- **Chosen Decision**: JSON core + artifact index + optional renderer-injected PNGs; the image-heavy directories of plan section 25 are deferred until real footage and multi-camera fusion exist.
- **Why**: A steward can already reconstruct WHY (identity, verdict, per-wheel geometry, homography, confidence, reason) from the JSON alone; images are additive, not structural.
- **Consequences**: The API can serve evidence without image dependencies; packages stay small and diff-friendly; missing image directories are an explicit, documented gap rather than an accident.
- **Future Considerations**: Implement the bird's-eye and Hawk-Eye renderers once corner-camera frames are available (the Iteration 9 dashboard loupe will consume them).

---

## DEC-012: /api/vision/* Serves the JSON Incident Store as Source of Truth
- **Date**: 2026-09-13
- **Decision**: Expose exactly the five planned endpoints (`GET /api/vision/incidents`, `GET /api/vision/incident/<id>`, `GET /api/vision/incident/<id>/frames`, `GET /api/vision/incident/<id>/evidence`, `POST /api/vision/incident/<id>/decision`) backed by the JSON document store (`data/vision_incidents.json`, `data/steward_decisions.json`), extending DEC-004's "backend as single source of truth" to vision data.
- **Context**: The steward dashboard (Iteration 9) needs the priority queue, per-incident forensics, frame-scrub data, evidence dossiers, and persistent adjudication.
- **Alternatives Considered**: Serving evidence packages from a static file mount; embedding steward decisions inside incident records; SQLite.
- **Chosen Decision**: JSON store + the five endpoints; decisions form an append-only log with "latest wins" folding into each incident response; unknown incidents are 404, invalid adjudications 400; the queue is ranked exactly like `rank_incidents` (priority, then breach depth, then confidence).
- **Why**: Zero new infrastructure, matches the CSV/JSON ledger philosophy, keeps decision history auditable, and the frontend needs no file-system access.
- **Consequences**: Concurrent writes are last-writer-wins (acceptable for a single-steward review station); the derived frame list assumes contiguous clusters, which `cluster_incidents` guarantees.
- **Future Considerations**: File locking if multi-steward editing is introduced; WebSocket push for live queues; serve rendered PNGs from packages via a static route.

---

## DEC-013: Steward Workstation Frontend on /api/vision/* with a Synthetic Demo Harness
- **Date**: 2026-09-13
- **Decision**: Rebuild the dashboard (`index.html`, `styles.css`, `app.js`) as the dedicated **Steward Scrutineering Workstation** consuming only the `/api/vision/*` endpoints; add `src/vision/demo.py` + `scripts/seed_vision_demo.py` to generate deterministic synthetic incidents and evidence packages (masks + keyframe) so the UI is verifiable without the Colab SAM service.
- **Context**: Plan section 26 defines the steward workstation (priority queue, forensic deck, dossier). The vision store is empty until the real pipeline runs against footage, which would leave the UI unverifiable.
- **Alternatives Considered**: Keeping the Phase 1 violations dashboard as the default view; mocking incident data inside `app.js` (violates DEC-012's backend-as-source-of-truth); requiring the live SAM service for any demo.
- **Chosen Decision**: The workstation reads the vision API exclusively; the demo harness writes through the SAME store and evidence builder as the real pipeline (no frontend mocks). Static evidence assets (mask PNGs, keyframes) are served by the existing Flask catch-all from the conventional root `/data/incidents/<id>/`.
- **Why**: The UI is exercised end-to-end against the real API contract; swapping synthetic data for pipeline output requires zero frontend changes.
- **Consequences**: The Phase 1 violations view is retired from the default page (its API remains untouched); the bird's-eye panel is a measurement-driven schematic until packages carry per-wheel contact polygons; the Hawk-Eye loupe needs mask PNGs to activate.
- **Future Considerations**: True homography projection panel; `<video>` scrubbing once benchmark clips exist; per-wheel polygon export in `measurements.json`.

---
