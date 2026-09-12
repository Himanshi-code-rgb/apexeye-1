"""
SAM Service Client (ApexEye Vision - Iteration 4)

The heavy segmentation model does not run in this repository. It runs in a
Google Colab GPU session that exposes a small HTTP API (see
notebooks/sam_service.ipynb) behind a Cloudflare tunnel. The local pipeline
only ever exchanges structured data with it:

    local frame (PNG, base64) + prompts  ──►  POST /segment
    masks (base64 RLE)                   ◄──  200 OK

Masks are transferred as run-length-encoded boolean arrays so the local
machine needs neither Pillow, torch, nor OpenCV to consume them. This keeps
the repository lightweight and the model backend swappable (SAM 2.1 today,
SAM 3.1 once gated access is granted).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import requests


class SamServiceError(RuntimeError):
    """Raised when the SAM service is unreachable or returns an error."""


def rle_encode(mask: np.ndarray) -> Dict[str, Any]:
    """
    Run-length encodes a 2D boolean mask in row-major order.

    Returns a dict with the shape and a flat list of run lengths, alternating
    between False/True runs and always starting with a False run.
    """
    arr = np.asarray(mask).astype(bool)
    flat = arr.reshape(-1)
    if flat.size == 0:
        return {"shape": list(arr.shape), "counts": []}

    changes = np.flatnonzero(flat[1:] != flat[:-1]) + 1
    boundaries = np.concatenate(([0], changes, [flat.size]))
    run_lengths = np.diff(boundaries)

    # Standard COCO-style RLE: if the mask starts with True, prepend a zero
    # length False run so decoding is unambiguous.
    counts = run_lengths.tolist()
    if flat[0]:
        counts = [0] + counts
    return {"shape": list(arr.shape), "counts": counts}


def rle_decode(encoded: Dict[str, Any]) -> np.ndarray:
    """Decodes an RLE dict produced by `rle_encode` back into a boolean mask."""
    try:
        shape = tuple(int(s) for s in encoded["shape"])
        counts = [int(c) for c in encoded["counts"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise SamServiceError(f"Malformed RLE payload: {exc}") from exc

    total = int(np.prod(shape))
    if sum(counts) != total:
        raise SamServiceError(
            f"RLE counts sum to {sum(counts)} but shape {shape} has {total} pixels."
        )

    values: List[bool] = []
    current = False
    for run in counts:
        values.extend([current] * run)
        current = not current

    return np.asarray(values, dtype=bool).reshape(shape)


def encode_image_png_base64(image: np.ndarray) -> str:
    """
    Encodes an image array to base64 PNG bytes for transport.

    Uses OpenCV if available, otherwise Pillow. Both are optional local
    dependencies; the Colab service can also accept raw bytes. We import
    lazily so the rest of the client (and its tests) needs neither.
    """
    arr = np.asarray(image)
    try:
        import cv2  # type: ignore

        ok, buffer = cv2.imencode(".png", arr)
        if not ok:
            raise SamServiceError("OpenCV failed to encode the image to PNG.")
        return base64.b64encode(buffer.tobytes()).decode("ascii")
    except ImportError:
        pass

    try:
        from PIL import Image  # type: ignore
        import io

        # Default OpenCV images are BGR; convert so PNG colours look right.
        if arr.ndim == 3 and arr.shape[2] == 3:
            arr = arr[:, :, ::-1]
        buffer = io.BytesIO()
        Image.fromarray(arr).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except ImportError as exc:
        raise SamServiceError(
            "Encoding images requires either opencv-python or Pillow locally."
        ) from exc


@dataclass
class SegmentRequest:
    """A single segmentation request: one frame plus a list of prompts."""

    image: np.ndarray
    prompts: List[Dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "image": encode_image_png_base64(self.image),
            "prompts": self.prompts,
        }


# A transport takes (url, json_payload, headers, timeout) and returns a
# requests-like response. Injectable so tests need no live server.
Transport = Callable[..., Any]


@dataclass
class SamServiceClient:
    """
    HTTP client for the Colab-hosted SAM service.

    Args:
        base_url: Tunnel URL, e.g. "https://xxxx.trycloudflare.com".
        api_key: Shared secret sent as the X-API-Key header.
        timeout: Per-request timeout in seconds.
        transport: Optional injection point for testing (defaults to requests.post).
    """

    base_url: str
    api_key: Optional[str] = None
    timeout: float = 120.0
    transport: Optional[Transport] = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        sender = self.transport or requests.post
        try:
            response = sender(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except Exception as exc:  # network errors, DNS, timeout, etc.
            raise SamServiceError(f"SAM service unreachable at {url}: {exc}") from exc

        status = getattr(response, "status_code", None)
        if status != 200:
            body = getattr(response, "text", "")
            raise SamServiceError(f"SAM service returned HTTP {status}: {body[:200]}")

        try:
            return response.json()
        except Exception as exc:
            raise SamServiceError(f"SAM service returned non-JSON response: {exc}") from exc

    def health(self) -> Dict[str, Any]:
        """Checks that the service is up and reports the loaded model."""
        return self._post("/health", {})

    def segment(
        self,
        image: np.ndarray,
        prompts: List[Dict[str, Any]],
    ) -> Dict[str, np.ndarray]:
        """
        Segments one frame and returns a mapping of prompt id -> boolean mask.

        Args:
            image: HxWx3 image array.
            prompts: Prompt dicts, e.g.
                {"id": "car", "type": "text", "text": "Formula 1 car"}
                {"id": "FL", "type": "box", "box": [x1, y1, x2, y2]}
                {"id": "line", "type": "point", "points": [[x, y]], "labels": [1]}

        Returns:
            Dict of prompt id -> 2D boolean NumPy mask.
        """
        payload = SegmentRequest(image=image, prompts=prompts).to_payload()
        body = self._post("/segment", payload)

        raw_masks = body.get("masks")
        if not isinstance(raw_masks, dict) or not raw_masks:
            raise SamServiceError("SAM service response contained no masks.")

        return {name: rle_decode(encoded) for name, encoded in raw_masks.items()}

    def is_available(self) -> bool:
        """Returns True if the service answers a health check."""
        try:
            self.health()
            return True
        except SamServiceError:
            return False
