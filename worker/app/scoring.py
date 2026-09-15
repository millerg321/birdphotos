import hashlib
import io

import cv2
import imagehash
import numpy as np
from PIL import Image


def compute_content_hash(image_bytes: bytes) -> str:
    """Exact-duplicate fingerprint (see plan: prevent duplicate photos) —
    a plain cryptographic hash of the raw file bytes, unlike compute_phash
    below, which is perceptual and only used for burst-grouping near-
    identical shots taken close together in time. Two different files of
    the same subject (a re-export, a resize) hash completely differently
    here; that's intentional — this only catches literally the same file
    uploaded twice."""
    return hashlib.sha256(image_bytes).hexdigest()


def compute_phash(image_bytes: bytes) -> str:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return str(imagehash.phash(img))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def _to_grayscale_array(image_bytes: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return np.array(img.convert("L"))


def compute_sharpness(image_bytes: bytes) -> float:
    """Laplacian-variance sharpness — higher means sharper (see plan:
    Burst/Duplicate Detection). Computed on a downscaled copy since the
    metric is about relative sharpness within a burst, not absolute
    pixel-level detail, and full-resolution originals are unnecessarily
    slow to convolve."""
    gray = _to_grayscale_array(image_bytes)
    if max(gray.shape) > 1024:
        scale = 1024 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_exposure(image_bytes: bytes) -> float:
    """1.0 = well-exposed (mean near mid-gray, not clipped), lower is worse."""
    gray = _to_grayscale_array(image_bytes)
    mean = float(gray.mean())
    base_score = 1.0 - abs(mean - 127.5) / 127.5

    clipped_shadows = float((gray == 0).mean())
    clipped_highlights = float((gray == 255).mean())
    clipping_penalty = clipped_shadows + clipped_highlights

    return max(0.0, base_score - clipping_penalty)
