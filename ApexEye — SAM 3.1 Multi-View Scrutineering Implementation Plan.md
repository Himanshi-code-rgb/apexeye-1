# ApexEye — Implementation Plan
## SAM 3.1 Multi-View Optical Track-Limits Scrutineering & Steward Review System

---

# 1. Goal

Pivot ApexEye into a **vision-first optical track-limits scrutineering system** using **SAM 3.1** as the primary perception model.

The system will process F1 corner footage from **multiple camera angles and positions**, identify and track cars and individual tires, segment the official track-limit white line, estimate tire/line geometry in metric coordinates, and determine whether a four-wheel track-limits breach has occurred.

The system will deliberately avoid processing every source-video frame with the expensive segmentation model. Instead, it will use **low-FPS event scanning followed by higher-FPS analysis around suspicious events**.

The final product is a **Steward Review Workstation** that presents the visual evidence, measurements, multi-camera agreement, confidence, and recommended classification while leaving the final adjudication auditable and human-reviewable.

---

# 2. Core Architecture

```text
                    MULTI-ANGLE RACE VIDEO
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
           Camera A       Camera B       Camera C
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                  LOW-FPS VIDEO SAMPLING
                         5–10 FPS
                             │
                             ▼
                   EVENT / CAR FILTERING
                             │
                  suspicious frames only
                             ▼
                         SAM 3.1
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          CAR/TIRES       WHITE LINE       KERB
              │              │
              └──────────────┼──────────────┘
                             ▼
                    TEMPORAL TRACKING
                             │
                             ▼
                 CAMERA-SPECIFIC HOMOGRAPHY
                             │
                             ▼
                METRIC TIRE/LINE GEOMETRY
                             │
                             ▼
                 CONTACT-PATCH ANALYSIS
                             │
                             ▼
                   MULTI-CAMERA FUSION
                             │
                             ▼
                TEMPORAL CONSISTENCY CHECK
                             │
                ┌────────────┼────────────┐
                ▼            ▼            ▼
             CRITICAL    BORDERLINE    CLEARED
                │            │            │
                └────────────┼────────────┘
                             ▼
                  STEWARD REVIEW DASHBOARD
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
           Video          Hawk-Eye       Evidence
           scrubber         zoom          dossier
                             │
                             ▼
                 CONFIRM / WARN / DISMISS
```

SAM 3.1 is particularly appropriate because its update introduces object multiplexing for joint multi-object tracking, allowing multiple objects to be processed together rather than requiring an independent tracking pass for each object. Meta reports substantially improved video throughput from this change.

---

# 3. Model Strategy

## 3.1 Primary model: SAM 3.1

ApexEye will use **SAM 3.1**, rather than SAM, SAM 2, MobileSAM, or FastSAM, as the primary segmentation/tracking foundation.

SAM 3 introduced concept-based detection, segmentation and tracking using text, exemplar and visual prompts. SAM 3.1 retains this architecture while improving multi-object video efficiency.

The system will use SAM 3.1 for:

- car detection/segmentation
- individual tire segmentation
- white-line segmentation
- optional kerb segmentation
- temporal object tracking
- frame-to-frame mask propagation
- generation of initial dataset annotations

---

# 4. Google Colab Vision Environment

The **SAM 3.1 experimentation and segmentation pipeline will initially run in Google Colab**.

The repository itself does not need to carry the heavy model execution environment.

```text
ApexEye Repository
        │
        ├── preprocessing
        ├── geometry
        ├── API
        ├── dashboard
        └── benchmark
                 │
                 ▼
          Google Colab
                 │
              SAM 3.1
                 │
                 ▼
        masks / tracking data
                 │
                 ▼
          ApexEye datasets
```

The Colab environment will be responsible for GPU-intensive work.

The local Flask application will primarily consume the resulting structured outputs during the MVP.

SAM 3.1 requires the current SAM 3 codebase/checkpoint rather than the older SAM implementation; the current ecosystem uses modern PyTorch/CUDA requirements, so the Colab notebook should pin the exact working environment rather than relying on whatever versions happen to be installed.

---

# 5. Dataset Strategy

ApexEye will build a **small, high-quality F1 track-limits dataset** rather than attempting to collect an enormous generic segmentation dataset.

The dataset should contain:

```text
Race
 └── Circuit
      └── Corner
           └── Camera
                └── Incident
                     ├── video
                     ├── frames
                     ├── car mask
                     ├── FL mask
                     ├── FR mask
                     ├── RL mask
                     ├── RR mask
                     ├── white-line mask
                     ├── kerb mask
                     └── ground-truth verdict
```

The initial dataset should concentrate on:

- Spielberg Turn 9
- Spielberg Turn 10
- multiple camera positions
- clear breaches
- borderline cases
- clean cases

The 2023 Austrian GP remains the Phase-1 ground-truth race because the existing decision log selected it specifically for its large number of track-limit incidents and available TUMFTM geometry/FastF1 data.

---

# 6. SAM 3.1 as Dataset Annotation Tool

SAM 3.1 will first be used to **accelerate annotation**.

Pipeline:

```text
Raw video
    ↓
sample frames
    ↓
SAM 3.1 prompt
    ↓
initial masks
    ↓
human correction
    ↓
verified ground truth
```

Prompts may include:

- `"Formula 1 car"`
- `"race car tire"`
- `"white track limit line"`
- visual exemplars
- bounding boxes
- positive/negative clicks

SAM 3 supports text, exemplar and visual prompts and returns masks plus object identities, which makes this annotation workflow feasible.

### Important rule

**SAM-generated masks are not automatically considered ground truth.**

For benchmark-quality samples:

```text
SAM 3.1 output
       ↓
Human verification
       ↓
Ground-truth mask
```

This prevents model-generated labels from being used to falsely prove the model is accurate.

---

# 7. SAM 3.1 as the Final Detection Model

SAM 3.1 is also the **actual inference model**.

It is not merely being used to create the dataset.

Final pipeline:

```text
New race video
      ↓
sampled frame
      ↓
SAM 3.1
      ↓
car + tire + white-line masks
      ↓
tracking
      ↓
geometry
      ↓
violation analysis
```

Therefore the MVP does **not require training a new neural network**.

We first benchmark pretrained SAM 3.1.

---

# 8. Fine-Tuning Strategy

Fine-tuning will be treated as an **optional second stage**, not a prerequisite.

### Phase A

Use pretrained SAM 3.1.

Measure:

- tire segmentation accuracy
- white-line segmentation accuracy
- mask IoU
- boundary error
- contact-patch error
- gap measurement error
- multi-camera consistency
- temporal stability

### Phase B

If failures are systematic, create a curated training dataset and investigate SAM 3.1 fine-tuning.

For example:

```text
SAM 3.1
   ↓
Excellent car segmentation
Excellent line segmentation
Weak tire-contact segmentation
   ↓
fine-tune / specialize
   ↓
improved tire-contact masks
```

Meta's SAM 3 release includes fine-tuning code, so this path remains available.

We should **not train from scratch**.

---

# 9. PyTorch / TorchVision Role

PyTorch is the underlying deep-learning framework used to execute SAM 3.1.

It is not a replacement segmentation model.

```text
PyTorch
    ↓
runs SAM 3.1

OpenCV
    ↓
video decoding / frame extraction

NumPy
    ↓
numerical processing

Shapely
    ↓
polygon intersection / geometry

FastF1
    ↓
race telemetry / FIA-related session data

Flask
    ↓
backend API

JavaScript
    ↓
steward dashboard
```

TorchVision may be used for supporting computer-vision utilities where useful, but ApexEye should **not introduce another large segmentation model unnecessarily**.

---

# 10. Multi-Camera Architecture

ApexEye will support multiple cameras viewing the same track-limit event.

Each camera is calibrated independently.

```text
Camera A
   ↓
SAM 3.1
   ↓
measurement A
   ↓
confidence A

Camera B
   ↓
SAM 3.1
   ↓
measurement B
   ↓
confidence B

Camera C
   ↓
SAM 3.1
   ↓
measurement C
   ↓
confidence C

             ↓

       Evidence Fusion
```

The first implementation will **not require full 3D reconstruction**.

Instead, each camera produces an independent metric observation.

This allows ApexEye to benefit from additional viewpoints without introducing unnecessary multi-view reconstruction complexity.

---

# 11. Camera Calibration

Create:

`src/vision/homography.py`

Each camera receives its own calibration.

```text
Camera A → H_A
Camera B → H_B
Camera C → H_C
```

The homography converts image coordinates into a local metric ground plane.

```text
pixels
   ↓
homography
   ↓
track coordinates
   ↓
meters / centimeters
```

Known track points, white-line points, kerb points or surveyed TUMFTM geometry can be used for calibration.

TUMFTM remains the preferred geometric reference for the Spielberg track because the existing architecture selected it specifically for its centerline and left/right width information.

---

# 12. Low-FPS Inference

The original video may be:

```text
50–60 FPS
```

ApexEye will **not run full SAM 3.1 inference on every frame**.

Initial processing:

```text
60 FPS
   ↓
5–10 FPS sampling
   ↓
candidate detection
```

This substantially reduces computational cost.

The exact sampling rate will be benchmarked rather than permanently hard-coded.

---

# 13. Two-Stage Video Processing

ApexEye will use two levels of temporal processing.

### Stage 1 — Cheap scan

Process approximately:

```text
5–10 FPS
```

to identify:

- approaching cars
- track-limit proximity
- candidate excursions
- suspicious movement

### Stage 2 — Event refinement

When a candidate is detected:

```text
candidate frame
      ↓
retrieve temporal window
      ↓
±1–2 seconds
      ↓
higher-FPS processing
      ↓
SAM 3.1 detailed segmentation/tracking
```

For example:

```text
60 FPS source

────────────────────────────────────
       normal driving
     5 FPS processing
────────────────────────────────────
                    ▲
                    │
               suspicious
                    │
             ┌──────────────┐
             │ high FPS     │
             │ investigation│
             └──────────────┘
```

This gives us high temporal precision only where it matters.

---

# 14. Temporal Tracking

SAM 3.1 will be used to maintain object identity through the incident.

```text
Frame 100
   ↓
identify FL / FR / RL / RR

Frame 101
   ↓
track

Frame 102
   ↓
track

Frame 103
   ↓
track

Frame 104
   ↓
refine / correct
```

SAM 3.1's multi-object tracking improvements are particularly relevant here because a single F1 car creates multiple simultaneous objects that need to be tracked together. Meta's SAM 3.1 update specifically introduces object multiplexing for this scenario.

---

# 15. Tire Contact-Patch Estimation

The visible tire mask is **not automatically equivalent to the physical contact patch**.

ApexEye should therefore distinguish:

```text
Visible tire
     ↓
ground-contact region
     ↓
contact polygon
```

The initial MVP can approximate the contact region geometrically.

Later iterations can train/specialize a contact-patch model if the benchmark demonstrates that SAM 3.1's visible tire segmentation is insufficient.

This is a major research area for ApexEye because the final question is not simply:

> "Where is the tire?"

It is:

> "Does the portion of the tire actually contacting the ground still intersect the legal boundary?"

---

# 16. White-Line Detection

SAM 3.1 will segment the official white track-limit line.

The output will be converted into a geometric representation:

```text
SAM mask
   ↓
clean mask
   ↓
contour
   ↓
polygon / centerline
   ↓
metric coordinates
```

Additional processing may include:

- morphological cleanup
- connected-component filtering
- temporal smoothing
- known track geometry constraints

The line should be treated as a physical reference rather than simply a generic white object.

---

# 17. Deterministic Optical Scrutineer

Create:

`src/vision/optical_scrutineer.py`

Inputs:

```text
FL contact polygon
FR contact polygon
RL contact polygon
RR contact polygon

white-line geometry
```

For every wheel:

```text
contact ∩ white_line
```

Calculate:

- overlap
- gap
- perpendicular distance
- signed excursion

Example:

```text
Overlap > 0
→ tire remains on line

Overlap = 0
→ calculate gap

Gap > threshold
→ candidate breach
```

Then:

```python
four_wheels_off = (
    FL_off and
    FR_off and
    RL_off and
    RR_off
)
```

The existing implementation plan's deterministic intersection concept is retained.

---

# 18. Multi-Camera Evidence Fusion

Each camera produces:

```text
breach_cm
confidence
visibility
mask_quality
```

The fusion layer combines them.

Example:

```text
Camera A: +9.1 cm / 0.96 confidence
Camera B: +8.7 cm / 0.94 confidence
Camera C: +9.4 cm / 0.91 confidence

→ Fused result: ~9.1 cm
→ HIGH confidence
```

Contradictory evidence should **reduce confidence rather than be hidden**.

Example:

```text
Camera A: +8.7 cm
Camera B: +0.3 cm
Camera C: tire occluded

→ BORDERLINE / REVIEW
```

This makes the system more defensible to a steward.

---

# 19. Confidence Model

Confidence should not depend only on breach distance.

Use:

```text
Optical Confidence =
    segmentation quality
    × line quality
    × tire quality
    × calibration quality
    × temporal consistency
    × camera agreement
    × geometric margin
```

Possible components:

```text
SAM mask confidence
Boundary stability
Homography error
Multi-view agreement
Frame-to-frame stability
Distance from threshold
```

The final confidence should communicate **evidence quality**, not pretend to be a calibrated probability unless we actually calibrate it against ground truth.

---

# 20. Incident Clustering

Multiple consecutive frames should become one incident.

```text
Frame 101 → legal
Frame 102 → breach
Frame 103 → breach
Frame 104 → breach
Frame 105 → breach
Frame 106 → legal

             ↓

         ONE INCIDENT
```

Store:

```text
incident_id
driver
lap
corner
camera_ids

start_frame
peak_frame
end_frame

peak_breach_cm
duration_ms

camera_agreement
optical_confidence
priority
```

This follows the existing decision to represent contiguous excursions as discrete stewarding events rather than raw telemetry points.

---

# 21. Priority Classification

Initial thresholds:

### CRITICAL

Clear geometric separation from the legal boundary.

```text
large positive gap
high confidence
multi-frame persistence
```

### BORDERLINE

Near the boundary or inconsistent between views.

```text
small gap
line-contact ambiguity
low camera agreement
occlusion
```

### CLEARED

Strong evidence that the tire remains legally connected to the boundary.

These thresholds must be **benchmark-calibrated** rather than presented as FIA rules.

---

# 22. Benchmark Dataset

Create:

```text
benchmarks/
    spielberg/
        turn_09/
            camera_A/
            camera_B/
            camera_C/

        turn_10/
            camera_A/
            camera_B/
            camera_C/
```

Each incident should be classified as:

```text
CLEAR_BREACH
BORDERLINE
CLEAN
```

Benchmark metrics:

```text
Mask IoU
Boundary error
Contact-patch error
Breach distance MAE
False positive rate
False negative rate
Incident classification accuracy
Multi-camera agreement
Temporal stability
Processing FPS
GPU memory
```

---

# 23. Paper-Based Baseline

The previously identified 2026 SCITEPress paper will be treated as a **reference/baseline**, not as the final ApexEye architecture.

The intended comparison is:

```text
Existing paper approach
        ↓
baseline methodology/results

ApexEye
        ↓
SAM 3.1
+ multi-camera
+ temporal tracking
+ metric geometry
+ evidence fusion
+ steward workstation
```

The paper should be incorporated into the implementation/research process after its methodology and experimental results have been fully inspected. The supplied PDF could not be fetched by the current web retrieval system, so no numerical claims from it are incorporated into this plan.

---

# 24. Backend

Retain:

`src/app.py`

Add:

```text
GET /api/vision/incidents

GET /api/vision/incident/<incident_id>

GET /api/vision/incident/<incident_id>/frames

GET /api/vision/incident/<incident_id>/evidence

POST /api/vision/incident/<incident_id>/decision
```

The API becomes the source of truth for the frontend, consistent with the existing architecture decision.

---

# 25. Evidence Package

Every incident should produce a reproducible forensic package:

```text
incident/
    metadata.json

    original/
        keyframe.jpg

    masks/
        car.png
        FL.png
        FR.png
        RL.png
        RR.png
        white_line.png

    overlays/
        camera_A.jpg
        camera_B.jpg
        camera_C.jpg

    birdseye/
        projection.png

    hawkeye/
        FL_zoom.png
        FR_zoom.png
        RL_zoom.png
        RR_zoom.png

    measurements/
        geometry.json
```

The evidence should allow a steward to reconstruct **why** the system made its recommendation.

---

# 26. Steward Dashboard

### Left — Priority Queue

```text
CRITICAL
────────────────
HAM   T10   +9.7 cm
VER   T9    +10.4 cm

BORDERLINE
────────────────
NOR   T10   +1.2 cm
ALO   T9    +0.8 cm

CLEARED
────────────────
LEC   T10   -4.2 cm
```

### Center — Video Deck

Features:

- multi-camera synchronized playback
- play/pause
- frame stepping
- timeline
- slow motion
- mask toggles
- opacity controls
- bird's-eye projection

### Right — Steward Dossier

```text
PEAK EXCURSION
+9.7 cm

OPTICAL CONFIDENCE
97%

CAMERA AGREEMENT
3 / 3

TIME
00:41:23.420

SPEED
284 km/h
```

Actions:

```text
[ CONFIRM DELETION ]

[ ISSUE WARNING ]

[ DISMISS ]
```

---

# 27. Multi-Camera Hawk-Eye

The Hawk-Eye interface should allow the steward to switch between views:

```text
┌──────────────┬──────────────┐
│ Camera A     │ Camera B     │
│              │              │
│     CAR      │     CAR      │
│      ◉       │      ◉       │
└──────────────┴──────────────┘

        SELECTED WHEEL

┌──────────────────────────────┐
│                              │
│       TIRE                   │
│      █████                   │
│                              │
│───────────────               │
│ WHITE LINE                   │
│                              │
│        +1.7 cm               │
└──────────────────────────────┘
```

This is particularly valuable for borderline incidents where one camera alone is ambiguous.

---

# 28. File Structure

```text
ApexEye/
│
├── src/
│   ├── app.py
│   │
│   └── vision/
│       ├── __init__.py
│       ├── sam31_segmenter.py
│       ├── video_sampler.py
│       ├── tracker.py
│       ├── homography.py
│       ├── contact_patch.py
│       ├── optical_scrutineer.py
│       ├── multi_camera.py
│       ├── evidence.py
│       └── benchmark.py
│
├── notebooks/
│   ├── sam31_setup.ipynb
│   ├── annotation.ipynb
│   ├── inference.ipynb
│   ├── benchmark.ipynb
│   └── finetuning.ipynb
│
├── data/
│   ├── raw/
│   ├── annotations/
│   ├── benchmarks/
│   └── incidents/
│
├── tests/
│   ├── test_homography.py
│   ├── test_contact_patch.py
│   ├── test_multi_camera.py
│   ├── test_scrutineer.py
│   └── test_vision_api.py
│
├── index.html
├── styles.css
├── app.js
├── requirements.txt
└── IMPLEMENTATION_PLAN.md
```

---

# 29. Development Phases

## Phase 1 — Geometry

Before SAM 3.1:

```text
manual masks
      ↓
homography
      ↓
metric geometry
      ↓
gap calculation
```

Prove that the mathematics works.

---

## Phase 2 — SAM 3.1 Zero-Shot

```text
video
 ↓
SAM 3.1
 ↓
car/tire/line masks
```

Measure actual performance.

Do not fine-tune yet.

---

## Phase 3 — Dataset Creation

Use SAM 3.1 to accelerate annotation:

```text
SAM 3.1
 ↓
initial mask
 ↓
human correction
 ↓
verified dataset
```

Create clear/borderline/clean benchmark categories.

---

## Phase 4 — Temporal Pipeline

Add:

```text
low-FPS scan
 ↓
candidate detection
 ↓
high-FPS temporal window
 ↓
SAM 3.1 tracking
 ↓
incident clustering
```

---

## Phase 5 — Multi-Camera Fusion

Add:

```text
Camera A
Camera B
Camera C
    ↓
independent measurements
    ↓
evidence fusion
    ↓
confidence
```

---

## Phase 6 — Steward Workstation

Connect the vision backend to the existing frontend.

Implement:

- priority queue
- synchronized video
- mask overlays
- Hawk-Eye
- bird's-eye view
- evidence dossier
- steward decision

---

## Phase 7 — Optional Fine-Tuning

Only after benchmark analysis.

If:

```text
SAM 3.1
      ↓
fails consistently on
contact patches / white line / F1-specific views
```

then investigate fine-tuning.

Otherwise:

**keep the pretrained model.**

---

# 30. Verification Plan

### Geometry

Test:

```text
legal overlap
small overlap
touching
small gap
large gap
```

### Vision

Measure:

```text
IoU
boundary error
contact-patch error
```

### Temporal

Test:

```text
mask stability
identity stability
incident clustering
```

### Multi-camera

Test:

```text
camera agreement
occluded camera
contradictory cameras
single-camera fallback
```

### End-to-end

Test:

```text
video
 ↓
SAM 3.1
 ↓
geometry
 ↓
fusion
 ↓
classification
 ↓
dashboard
```

---

# 31. Primary Technical Principle

ApexEye should **not claim that SAM 3.1 itself decides whether a driver violated track limits.**

Instead:

```text
SAM 3.1
   ↓
PERCEPTION
"What is visible?"

Geometry Engine
   ↓
MEASUREMENT
"How far is the tire from the boundary?"

Evidence Fusion
   ↓
CONFIDENCE
"Do the cameras and frames agree?"

Steward
   ↓
ADJUDICATION
"What should the official decision be?"
```

This separation makes ApexEye explainable, auditable and much more appropriate for a stewarding workflow.

---

# 32. Final MVP Definition

The MVP is complete when ApexEye can take a multi-angle Spielberg corner video and:

1. Sample the video at a reduced FPS.
2. Identify candidate cars/events.
3. Run SAM 3.1 on relevant frames.
4. Segment the car, tires and track-limit line.
5. Track the relevant objects through the event.
6. Transform the observations into metric coordinates.
7. Estimate tire contact patches.
8. Determine tire/white-line intersection or gap.
9. Combine evidence from multiple camera views.
10. Produce a Critical / Borderline / Cleared recommendation.
11. Display synchronized video and SAM 3.1 masks.
12. Show the exact measurement in the Hawk-Eye view.
13. Preserve the underlying evidence.
14. Allow a steward to Confirm, Warn or Dismiss.
15. Record the final human decision.

The ultimate objective is therefore not simply:

**"SAM detects track limits."**

It is:

**"ApexEye turns multi-camera race footage into measurable, auditable track-limits evidence that a steward can review and adjudicate."**