# Implementation Plan: ApexEye SAM-Vision Scrutineering & Steward Review System

## Goal Description
Pivot ApexEye entirely to a single innovative vision-first path:
Build an **optical track limits scrutineering engine powered by Segment Anything (SAM)** that segments track boundaries (white line) and tire contact patches from corner camera footage, deterministically verifies four-wheels-off breaches, computes optical excursion depths, and delivers a **dedicated Steward Manual Review Dashboard** with prioritized queues, interactive mask overlays ("Hawk-Eye" zoom), and forensic evidence dossiers.

---

## User Review Required

> [!IMPORTANT]
> **Key Architecture Decisions for the Single Vision Path:**
> 1. **SAM Segmentation Engine**: We will implement promptable zero-shot segmentation using the Segment Anything (SAM / MobileSAM / SAM-2 lightweight) architecture. It takes bounding-box and point prompts on corner exit footage to isolate:
>    - Official track boundary line (white line polygon)
>    - Vehicle tire contact patches (Left-Front, Left-Rear, Right-Front, Right-Rear)
> 2. **Deterministic Contact Patch Adjudication**:
>    - In F1 regulations, a violation occurs **if and only if** all four wheels have no contact with the white line.
>    - The engine calculates the intersection $\text{Tire Masks} \cap \text{White Line Mask}$. If the intersection area is zero, it measures the exact physical gap (daylight in centimeters) and assigns an **Optical Confidence Score** and **Triage Priority**.
> 3. **Benchmark Video Clips**: To ensure the system is immediately testable and verifiable without requiring hundreds of gigabytes of copyrighted FOM broadcast video:
>    - We will include high-precision benchmark video clips for Turns 9 and 10 covering the three stewarding categories:
>      1. **Clear Breach** (Daylight $>10\text{cm}$ past line $\rightarrow$ Critical Priority)
>      2. **Borderline Case** (Tire edge within $\pm 2\text{cm}$ of paint $\rightarrow$ Steward Review Priority)
>      3. **Clean / Sub-threshold** (Inner tire clearly overlapping line $\rightarrow$ Cleared)
>    - The engine also allows uploading any custom external `.mp4` video file.

---

## Open Questions

> [!NOTE]
> 1. **SAM Model Weight Selection**: To ensure fast inference on standard hardware (Intel CPU / RTX 2060 Mobile):
>    - Option A: **MobileSAM / FastSAM ONNX**: Lightweight, runs at 15–30 FPS on CPU, promptable via box/points.
>    - Option B: **Meta SAM-2 ViT-Tiny**: Meta's latest video model, slightly heavier (~300MB weights).
>    *(Recommendation: Implement a modular SAM interface that defaults to MobileSAM/FastSAM for instant CPU evaluation with support for SAM-2 weights when available).*
> 2. **Steward Decision Export**: Would you like the dashboard to generate an official FIA-formatted Decision Document (e.g. PDF or printable HTML case summary with timestamped mask screenshots and steward signature block)? *(Recommendation: Yes, this strongly enhances the hackathon demo).*

---

## Proposed Changes

```
┌─────────────────────────────────────────────────────────────┐
│                    CORNER CAMERA FOOTAGE                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  src/vision/ Track & Car SAM                │
│  - Perspective Homography (Bird's Eye Transform)            │
│  - SAM-Prompted Tire Contact Patch & White Line Masks       │
│  - Contact Intersection ($Tire \cap Line$) & Gap in cm      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  src/vision/ Scrutineer Triage              │
│  - Optical Confidence Score [0.0 - 1.0]                     │
│  - Priority: [CRITICAL] / [BORDERLINE REVIEW] / [CLEARED]   │
│  - Forensic Evidence Package (Masks, Metrics, Loupe Crop)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              STEWARD MANUAL REVIEW DASHBOARD                │
│  - Priority Queue (Urgent Deletions vs Borderline Cases)    │
│  - Video Scrubber with Interactive SAM Mask Layer Toggles   │
│  - "Hawk-Eye" Contact Patch Zoom-in Loupe                   │
│  - One-Click Steward Decision: Confirm / Warn / Dismiss     │
└─────────────────────────────────────────────────────────────┘
```

---

### Component 1: Dependencies & Environment

#### [MODIFY] [requirements.txt](file:///home/gaurav/Documents/ApexEye/requirements.txt)
- Add computer vision and segmentation dependencies:
  - `opencv-python-headless>=4.8.0`
  - `torch>=2.0.0`
  - `torchvision>=0.15.0`
  - `onnxruntime>=1.15.0`
  - `pillow>=9.5.0`

---

### Component 2: SAM Computer Vision Pipeline (`src/vision/`)

#### [NEW] `src/vision/homography.py`
- Implements 4-point perspective transformation for corner exit cameras (e.g. Spielberg Turns 9 & 10).
- Maps camera 2D screen coordinates into a calibrated metric top-down plane (meters/centimeters per pixel).

#### [NEW] `src/vision/sam_segmenter.py`
- Lightweight promptable SAM interface:
  - Takes video frame and bounding box/points.
  - Generates binary masks for:
    - Track boundary white line.
    - Outer kerb.
    - Vehicle chassis.
    - Individual wheel contact patches (Left-Rear, Right-Rear).
  - Caches masks for playback scrubbers.

#### [NEW] `src/vision/optical_scrutineer.py`
- Evaluates four-wheels-off condition:
  - Checks polygon intersection between white line and tire contact patches.
  - Measures perpendicular distance:
    - If overlap $> 0$: `breach_cm = -overlap_depth` (Inside track, legal).
    - If overlap $= 0$: `breach_cm = +gap_distance` (Outside track, breach).
  - Calculates **Optical Confidence Score**:
    $$\text{Confidence} = 1.0 - \frac{1}{1 + e^{k \cdot (\text{breach\_cm} - \text{margin})}}$$
  - Assigns Stewarding Priority:
    - `CRITICAL`: Breach $> 8\text{cm}$ (Clear daylight, 95%+ confidence) $\rightarrow$ Fast-track deletion.
    - `BORDERLINE`: Breach between $-3\text{cm}$ and $+8\text{cm}$ $\rightarrow$ Priority manual steward review.
    - `CLEARED`: Breach $< -3\text{cm}$ (Tire well within line) $\rightarrow$ Auto-dismissed.

#### [NEW] `src/vision/benchmark.py`
- Creates and manages benchmark corner incidents with synchronized video frames, simulated corner footage, and verified ground-truth contact masks for Spielberg Turn 9 and Turn 10.

---

### Component 3: Forensic API Endpoints (`src/app.py`)

#### [MODIFY] [src/app.py](file:///home/gaurav/Documents/ApexEye/src/app.py)
- Add endpoints:
  - `GET /api/vision/incidents`: Returns the priority-sorted list of video incidents with optical confidence and breach metrics.
  - `GET /api/vision/incident/<incident_id>`: Returns full forensic dossier, including video URL, frame timestamps, peak breach frame, and metric measurements.
  - `GET /api/vision/incident/<incident_id>/frames`: Serves the annotated keyframe sequence with SAM masks (car, line, contact patch, bird's eye view).
  - `POST /api/vision/incident/<incident_id>/decision`: Records steward manual verdict (`CONFIRM_DELETION`, `ISSUE_WARNING`, `DISMISS`), steward notes, and generates an official signed case record.

---

### Component 4: Steward Manual Review Dashboard

#### [MODIFY] [index.html](file:///home/gaurav/Documents/ApexEye/index.html)
- Redesign layout into a dedicated **Steward Scrutineering Workstation**:
  - **Left Sidebar: Steward Priority Triage Queue**:
    - Filter tabs: `Critical (Instant Deletion)`, `Borderline (Review Required)`, `Cleared / Dismissed`.
    - Incident cards showing Driver badge, Corner, Breach in cm, Optical Confidence, and Driver Strike tally.
  - **Center Canvas: Forensic Video & Keyframe Scrutineer Deck**:
    - Video / Frame Scrubber with play/pause and frame-by-frame step buttons ($\pm 1$ frame).
    - **SAM Mask Layer Controls**:
      - `[x] White Line Boundary (Neon Green/Red)`
      - `[x] Vehicle & Tire Contact Patches`
      - `[x] Hawk-Eye Contact Loupe (2x zoom on critical contact edge)`
      - `[x] Bird's Eye 2D Perspective Projection`
  - **Right Sidebar: Official Stewarding Action & Case Dossier**:
    - Live optical telemetry readouts (Peak Excursion in cm, Daylight Separation %, Vehicle Speed, Timecode).
    - Cumulative Driver Strike Tracker (1st Offense, 2nd, Black & White Flag, 5s Penalty).
    - Steward Action Buttons:
      - **[Confirm Lap Deletion]** (Red)
      - **[Issue Black & White Warning]** (Yellow)
      - **[Dismiss / No Infraction]** (Green)
    - Export Formal FIA Stewarding Document button.

#### [MODIFY] [styles.css](file:///home/gaurav/Documents/ApexEye/styles.css)
- Steward HUD styling: high-contrast dark theme, crisp video player deck, floating mask overlay controls, and zoom loupe aesthetics.
- Priority pill styling (Critical red pulse, Borderline amber glow, Cleared tech-cyan).

#### [MODIFY] [app.js](file:///home/gaurav/Documents/ApexEye/app.js)
- Implement video frame scrub synchronization.
- Implement canvas-based mask rendering: draws SAM boundary polygons and tire contact patches on top of video frames with toggleable opacity.
- Connect steward adjudication actions to `POST /api/vision/incident/<id>/decision` with instant UI status updates.

---

## Verification Plan

### Automated Tests
1. **Vision Geometry & Overlap Tests** (`tests/test_vision_geometry.py`):
   - Test homography projection: verified pixel-to-meter scaling accuracy.
   - Test contact patch polygon intersection:
     - Case A: Tire completely outside line $\rightarrow$ overlap area $= 0$, breach $> 0$, priority `CRITICAL`.
     - Case B: Tire clipping line by 2 cm $\rightarrow$ overlap area $> 0$, breach $\le 0$, priority `CLEARED`.
     - Case C: Tire touching outer edge of line $\rightarrow$ priority `BORDERLINE`.
2. **API Tests** (`tests/test_vision_api.py`):
   - Test `GET /api/vision/incidents` returns prioritized incidents.
   - Test `GET /api/vision/incident/<id>` returns complete evidence pack.
   - Test `POST /api/vision/incident/<id>/decision` updates database and persists steward verdict.

### Manual Verification
1. Start backend: `python -m src.app`
2. Open `http://localhost:5000/`:
   - Inspect Priority Queue: Verify incidents are categorized into *Critical*, *Borderline*, and *Cleared*.
   - Click a Borderline Incident: Video player loads corner footage.
   - Toggle Masks: Toggle white line and tire contact patch overlays to confirm SAM masks accurately track the wheel.
   - Inspect Hawk-Eye Loupe: Verify magnified view shows the exact boundary interface and distance in centimeters.
   - Steward Adjudication: Click "Confirm Lap Deletion", verify decision badge updates and driver strike count increments.
