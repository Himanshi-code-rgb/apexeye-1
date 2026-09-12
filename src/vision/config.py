"""
Vision Pipeline Configuration (ApexEye).

All tunables live here so the pipeline reads them from one place. Values come
from environment variables with safe defaults, which keeps the Colab service
URL and API key out of the source tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Standard FIA painted track-limit line width.
LINE_WIDTH_M = float(os.environ.get("APEXEYE_LINE_WIDTH_M", "0.15"))

# Peak-gap (cm) above which a confirmed four-wheels-off incident is CRITICAL.
CRITICAL_GAP_CM = float(os.environ.get("APEXEYE_CRITICAL_GAP_CM", "8.0"))

# Fraction of the visible tire mask treated as ground contact.
CONTACT_FRACTION = float(os.environ.get("APEXEYE_CONTACT_FRACTION", "0.20"))

# Candidate scan rate and refinement rate (frames per second).
SCAN_FPS = float(os.environ.get("APEXEYE_SCAN_FPS", "5"))
REFINE_FPS = float(os.environ.get("APEXEYE_REFINE_FPS", "30"))
REFINE_WINDOW_SEC = float(os.environ.get("APEXEYE_REFINE_WINDOW_SEC", "1.5"))


@dataclass
class SamConfig:
    """Connection settings for the Colab-hosted SAM service."""

    url: str = ""
    api_key: str = ""
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "SamConfig":
        return cls(
            url=os.environ.get("SAM_API_URL", ""),
            api_key=os.environ.get("SAM_API_KEY", ""),
            timeout=float(os.environ.get("SAM_TIMEOUT", "120")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url)
