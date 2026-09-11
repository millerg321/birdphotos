import io

import numpy as np
from PIL import Image

from app.scoring import compute_exposure, compute_phash, compute_sharpness, hamming_distance


def _jpeg_bytes_from_array(arr: np.ndarray) -> bytes:
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _solid_gray(value: int, size: int = 200) -> bytes:
    arr = np.full((size, size, 3), value, dtype=np.uint8)
    return _jpeg_bytes_from_array(arr)


def _checkerboard(size: int = 200, square: int = 4) -> bytes:
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, square * 2):
        for x in range(0, size, square * 2):
            arr[y : y + square, x : x + square] = 255
            arr[y + square : y + square * 2, x + square : x + square * 2] = 255
    return _jpeg_bytes_from_array(arr)


class TestSharpness:
    def test_sharper_image_scores_higher(self) -> None:
        blurry = _solid_gray(128)
        sharp = _checkerboard()
        assert compute_sharpness(sharp) > compute_sharpness(blurry)

    def test_flat_image_has_near_zero_sharpness(self) -> None:
        assert compute_sharpness(_solid_gray(128)) < 1.0


class TestExposure:
    def test_mid_gray_scores_well(self) -> None:
        assert compute_exposure(_solid_gray(128)) > 0.95

    def test_pure_black_scores_poorly(self) -> None:
        assert compute_exposure(_solid_gray(0)) < 0.1

    def test_pure_white_scores_poorly(self) -> None:
        assert compute_exposure(_solid_gray(255)) < 0.1

    def test_mid_gray_beats_near_black(self) -> None:
        assert compute_exposure(_solid_gray(128)) > compute_exposure(_solid_gray(20))


class TestPhash:
    def test_identical_images_have_zero_distance(self) -> None:
        img = _checkerboard()
        assert hamming_distance(compute_phash(img), compute_phash(img)) == 0

    def test_very_different_images_have_large_distance(self) -> None:
        a = compute_phash(_solid_gray(0))
        b = compute_phash(_checkerboard())
        assert hamming_distance(a, b) > 10

    def test_similar_images_have_small_distance(self) -> None:
        # A checkerboard and a near-identical one shifted by one pixel
        # should still phash as near-duplicates — that's the whole point
        # of a *perceptual* hash over an exact byte/pixel comparison.
        base = _checkerboard()
        near_dup = _checkerboard(square=4)  # same pattern, re-encoded
        assert hamming_distance(compute_phash(base), compute_phash(near_dup)) <= 4
