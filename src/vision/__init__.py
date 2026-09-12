"""
ApexEye Vision Package (SAM 3.1 Optical Scrutineering)

Modules are added one iteration at a time:
    homography.py         - pixel <-> metric track-plane mapping
    contact_patch.py      - visible tire mask -> ground contact polygon
    optical_scrutineer.py - FIA four-wheels-off deterministic adjudication
    sam_client.py         - HTTP client to the Colab-hosted SAM service
    config.py             - env-driven pipeline tunables
    pipeline.py           - per-frame and per-sequence orchestration
    incidents.py          - breach-frame clustering into steward incidents
    video_sampler.py      - scan/refine frame-rate planning
    evidence.py           - reproducible per-incident forensic packages
"""
