import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.scoring import hamming_distance

TIME_WINDOW = timedelta(seconds=90)
# Tuned against the real local test set, not just the plan's initial ~10
# guess: a moving subject (e.g. a bird shifting in/out of a nest hole
# between frames) can push same-burst distances well past 10. 20 merges
# most real bursts while staying clear of the ~24 floor observed between
# two genuinely distinct bursts 90s apart in that same test set. Revisit
# with more data once Phase 2's full import is running.
HAMMING_THRESHOLD = 20  # of 64 bits

# Time-only fallback: photos this close together merge regardless of hash
# distance, on the assumption that a ~5s gap is almost always the same
# moment even if the subject moved a lot between frames. Added after
# HAMMING_THRESHOLD=20 alone still left two real burst photos unmerged
# (their nearest hash-neighbor was 26-40 away) despite sitting only 1-3s
# from the rest of the sequence. Tradeoff: this bypasses the hash check
# entirely inside the window, so two genuinely different subjects shot
# within 5s of each other (e.g. quickly swinging to a different bird)
# would also merge — judged an acceptable risk against the more common
# case of under-merging a real rapid-fire sequence.
TIGHT_TIME_WINDOW = timedelta(seconds=5)

SHARPNESS_WEIGHT = 0.6
EXPOSURE_WEIGHT = 0.4


@dataclass
class PhotoForGrouping:
    id: uuid.UUID
    taken_at: datetime
    phash: str


class _UnionFind:
    def __init__(self, items: list[uuid.UUID]):
        self._parent = {item: item for item in items}

    def find(self, item: uuid.UUID) -> uuid.UUID:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]  # path halving
            item = self._parent[item]
        return item

    def union(self, a: uuid.UUID, b: uuid.UUID) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b


def group_by_burst(photos: list[PhotoForGrouping]) -> list[list[uuid.UUID]]:
    """Groups photos into bursts. Two photos merge if either:
    - they're within TIGHT_TIME_WINDOW of each other (time-only fallback
      for rapid-fire sequences — see TIGHT_TIME_WINDOW), or
    - they're within TIME_WINDOW AND perceptually similar (both must
      hold — see plan: two distinct bursts of different subjects shot
      90s apart must not merge just because they're at the window
      boundary).

    Sliding window: for each photo, compare against subsequent photos
    within TIME_WINDOW (sorted by taken_at, so this is transitive/
    chaining — a continuous shooting sequence stays one group even if
    the first and last frame alone would fall outside the window).
    """
    sorted_photos = sorted(photos, key=lambda p: p.taken_at)
    uf = _UnionFind([p.id for p in sorted_photos])

    for i, photo in enumerate(sorted_photos):
        for other in sorted_photos[i + 1 :]:
            gap = other.taken_at - photo.taken_at
            if gap > TIME_WINDOW:
                break
            if gap <= TIGHT_TIME_WINDOW:
                uf.union(photo.id, other.id)
            elif hamming_distance(photo.phash, other.phash) <= HAMMING_THRESHOLD:
                uf.union(photo.id, other.id)

    groups: dict[uuid.UUID, list[uuid.UUID]] = {}
    for photo in sorted_photos:
        root = uf.find(photo.id)
        groups.setdefault(root, []).append(photo.id)

    return list(groups.values())


@dataclass
class PhotoForScoring:
    id: uuid.UUID
    sharpness_score: float
    exposure_score: float


def _zscore(value: float, values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    return 0.0 if stdev == 0 else (value - mean) / stdev


def select_best_shot(photos: list[PhotoForScoring]) -> uuid.UUID:
    """Weighted z-score of sharpness (0.6) + exposure (0.4) within the
    group; ties broken by list order (caller passes photos pre-sorted by
    taken_at, so this means earliest wins — see plan: Burst Detection)."""
    if len(photos) == 1:
        return photos[0].id

    sharpness_values = [p.sharpness_score for p in photos]
    exposure_values = [p.exposure_score for p in photos]

    def combined_score(p: PhotoForScoring) -> float:
        return SHARPNESS_WEIGHT * _zscore(
            p.sharpness_score, sharpness_values
        ) + EXPOSURE_WEIGHT * _zscore(p.exposure_score, exposure_values)

    return max(photos, key=combined_score).id
