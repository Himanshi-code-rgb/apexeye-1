"""
Video Sampler & Two-Stage Frame Extraction (ApexEye Vision - Iteration 6)

Running SAM on every frame of 60 FPS footage is wasteful. The plan's two-stage
approach is:

    Stage 1 (cheap):    sample at SCAN_FPS (e.g. 5) and flag candidates.
    Stage 2 (precise):  around a candidate, extract a short window at REFINE_FPS
                        (e.g. 30) for detailed tracking.

This module owns frame extraction. It uses OpenCV when available because it is
the standard way to decode video, but the frame-selection math is separated
(`plan_scan_timestamps`, `plan_refine_timestamps`) so it can be tested without
any video file or OpenCV install.
"""

from __future__ import annotations

from fractions import Fraction
from typing import List, Tuple


class VideoSamplerError(RuntimeError):
    """Raised when video metadata cannot be read."""


def scan_step_frames(source_fps: float, scan_fps: float) -> int:
    """
    Number of source frames to advance per scan sample.

    E.g. 60 FPS source, 5 FPS scan -> every 12th frame.
    """
    if source_fps <= 0:
        raise VideoSamplerError("source_fps must be positive.")
    if scan_fps <= 0:
        raise VideoSamplerError("scan_fps must be positive.")
    if scan_fps > source_fps:
        raise VideoSamplerError("scan_fps cannot exceed source_fps.")
    return max(1, int(round(source_fps / scan_fps)))


def plan_scan_timestamps(frame_count: int, step: int) -> List[int]:
    """Returns the frame indices to inspect during the cheap scan."""
    if frame_count < 0:
        raise VideoSamplerError("frame_count must be non-negative.")
    if step <= 0:
        raise VideoSamplerError("step must be positive.")
    return list(range(0, frame_count, step))


def plan_refine_timestamps(
    peak_frame: int,
    frame_count: int,
    window_sec: float,
    source_fps: float,
) -> List[int]:
    """
    Returns contiguous frame indices around a candidate for detailed analysis.

    Args:
        peak_frame: The scan frame that flagged a candidate.
        frame_count: Total frames in the video (clamps the result).
        window_sec: Half-window in seconds (e.g. 1.5 -> +-1.5 s).
        source_fps: Source video FPS.

    Returns:
        A sorted list of frame indices within [0, frame_count).
    """
    if source_fps <= 0:
        raise VideoSamplerError("source_fps must be positive.")
    if window_sec < 0:
        raise VideoSamplerError("window_sec must be non-negative.")

    half = int(round(window_sec * source_fps))
    start = max(0, peak_frame - half)
    end = min(frame_count, peak_frame + half + 1)
    return list(range(start, end))


def probe_video(path: str) -> Tuple[float, int]:
    """
    Returns (fps, frame_count) for a video file using OpenCV.

    Raises VideoSamplerError if OpenCV is unavailable or the file cannot be read.
    """
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise VideoSamplerError(
            "Reading video requires opencv-python. Install it locally to decode clips."
        ) from exc

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise VideoSamplerError(f"Could not open video: {path}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()

    if fps <= 0 or frame_count <= 0:
        raise VideoSamplerError(f"Invalid video metadata for {path}: fps={fps}, frames={frame_count}")
    return fps, frame_count


def read_frames(path: str, frame_indices: List[int]):
    """
    Yields (frame_index, BGR image array) for the requested frame indices.

    Frames are read in ascending order for efficiency.
    """
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise VideoSamplerError("Reading video requires opencv-python.") from exc

    if not frame_indices:
        return

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise VideoSamplerError(f"Could not open video: {path}")
    try:
        for index in sorted(frame_indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if ok:
                yield index, frame
    finally:
        capture.release()
