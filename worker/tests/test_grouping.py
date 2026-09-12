import uuid
from datetime import datetime, timedelta

from app.grouping import (
    PhotoForGrouping,
    PhotoForScoring,
    group_by_burst,
    select_best_shot,
)

BASE_TIME = datetime(2024, 2, 12, 7, 28, 16)

# Two perceptually-identical hashes and two very different ones, reused
# across tests rather than computing real phashes (that's scoring.py's
# job — grouping.py's tests are pure logic on precomputed hash strings).
HASH_A = "0000000000000000"
HASH_A_NEAR_DUP = "0000000000000001"  # 1 bit different
HASH_B = "ffffffffffffffff"


def _photo(taken_at: datetime, phash: str) -> PhotoForGrouping:
    return PhotoForGrouping(id=uuid.uuid4(), taken_at=taken_at, phash=phash)


class TestGroupByBurst:
    def test_close_in_time_and_similar_hash_merge(self) -> None:
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(seconds=1), HASH_A_NEAR_DUP),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_similar_hash_but_far_apart_in_time_stay_separate(self) -> None:
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(hours=1), HASH_A_NEAR_DUP),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 2

    def test_close_in_time_but_different_subject_stay_separate(self) -> None:
        """The real edge case from the test dataset: two distinct bursts
        (different birds) exactly 90s apart at the window boundary must
        not merge just because of timing — the hash similarity check is
        what actually separates them."""
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(seconds=90), HASH_B),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 2

    def test_tight_time_window_merges_despite_very_different_hash(self) -> None:
        """The documented tradeoff of TIGHT_TIME_WINDOW: photos within
        ~5s merge even if they look nothing alike by hash. Verified
        against real data — two lone frames in the parakeet burst never
        got within 26 of any neighbor by hash, but sat 1-3s away in
        time, so this fallback is what actually unites them (see the
        dataset-shaped test below)."""
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(seconds=2), HASH_B),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 1

    def test_just_outside_tight_window_falls_back_to_hash_check(self) -> None:
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(seconds=16), HASH_B),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 2

    def test_real_dataset_parakeet_stragglers_now_fully_merge(self) -> None:
        """The exact gap HAMMING_THRESHOLD=20 alone left unfixed: photos
        at +0/+1/+10s formed one hash-similar cluster, but +9s and +13s
        never got within 26 of any neighbor by hash despite sitting
        1-3s away in time. TIGHT_TIME_WINDOW should now unite all 5."""
        start = datetime(2024, 2, 12, 7, 30, 5)
        photos = [
            _photo(start, HASH_A),  # 07:30:05
            _photo(start + timedelta(seconds=1), HASH_A),  # :06
            _photo(start + timedelta(seconds=4), HASH_B),  # :09 — the straggler
            _photo(start + timedelta(seconds=5), HASH_A),  # :10
            _photo(start + timedelta(seconds=8), HASH_B),  # :13 — the other straggler
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 1
        assert len(groups[0]) == 5

    def test_transitive_chain_stays_one_group(self) -> None:
        """A continuous burst where consecutive frames are similar, even
        if the first and last frame alone would exceed the time window."""
        photos = [
            _photo(BASE_TIME, HASH_A),
            _photo(BASE_TIME + timedelta(seconds=60), HASH_A_NEAR_DUP),
            _photo(BASE_TIME + timedelta(seconds=120), HASH_A),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_single_photo_is_its_own_group(self) -> None:
        groups = group_by_burst([_photo(BASE_TIME, HASH_A)])
        assert groups == [[groups[0][0]]]

    def test_real_manual_upload_burst_fully_merges_with_wider_thresholds(self) -> None:
        """The 5-photo burst that motivated raising HAMMING_THRESHOLD to 25
        and TIGHT_TIME_WINDOW to 15s: a deliberately-paced (not rapid-fire)
        sequence over 29s, with same-subject hash distances up to 32 that
        HAMMING_THRESHOLD=20 alone couldn't bridge. Real hashes/timestamps
        from the manual-upload grouping investigation."""
        photos = [
            _photo(datetime(2020, 12, 31, 9, 49, 48), "c64fb913863bce24"),
            _photo(datetime(2020, 12, 31, 9, 49, 49), "c76bb903822bec3c"),
            _photo(datetime(2020, 12, 31, 9, 49, 58), "9652e969fcec24a1"),
            _photo(datetime(2020, 12, 31, 9, 50, 13), "90638a699f976798"),
            _photo(datetime(2020, 12, 31, 9, 50, 17), "907389699e4b6e9c"),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 1
        assert len(groups[0]) == 5

    def test_real_manual_upload_burst_still_splits_on_a_late_outlier(self) -> None:
        """The known-remaining gap from the same investigation: this
        3-photo burst's third frame sits 30-31s from the other two (past
        TIGHT_TIME_WINDOW) with hash distances of 28 and 34 (past even the
        raised HAMMING_THRESHOLD=25), so it still splits off. Documents
        the limit of this tuning rather than a regression to fix here."""
        photos = [
            _photo(datetime(2021, 2, 4, 8, 56, 49), "c7ec5cb273029b25"),
            _photo(datetime(2021, 2, 4, 8, 56, 50), "9fe85eb43106836d"),
            _photo(datetime(2021, 2, 4, 8, 57, 20), "c5d3cd6cf20a1e98"),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 2
        assert {len(g) for g in groups} == {2, 1}

    def test_two_real_bursts_from_the_test_dataset(self) -> None:
        """Mirrors the actual 07:28:16-07:28:35 and 07:30:05-07:30:13
        sequences (exactly 90s apart) from the local test photo set."""
        burst_1_start = datetime(2024, 2, 12, 7, 28, 16)
        burst_2_start = datetime(2024, 2, 12, 7, 30, 5)  # 109s after burst 1 starts

        photos = [
            _photo(burst_1_start, HASH_A),
            _photo(burst_1_start + timedelta(seconds=1), HASH_A_NEAR_DUP),
            _photo(burst_1_start + timedelta(seconds=6), HASH_A),
            _photo(burst_1_start + timedelta(seconds=19), HASH_A_NEAR_DUP),
            _photo(burst_2_start, HASH_B),
            _photo(burst_2_start + timedelta(seconds=1), HASH_B),
            _photo(burst_2_start + timedelta(seconds=4), HASH_B),
        ]
        groups = group_by_burst(photos)
        assert len(groups) == 2
        assert {len(g) for g in groups} == {4, 3}


class TestSelectBestShot:
    def test_single_photo_wins_trivially(self) -> None:
        photo_id = uuid.uuid4()
        result = select_best_shot(
            [PhotoForScoring(id=photo_id, sharpness_score=1.0, exposure_score=1.0)]
        )
        assert result == photo_id

    def test_sharper_photo_wins_when_exposure_equal(self) -> None:
        sharp = PhotoForScoring(id=uuid.uuid4(), sharpness_score=500.0, exposure_score=0.9)
        blurry = PhotoForScoring(id=uuid.uuid4(), sharpness_score=50.0, exposure_score=0.9)
        assert select_best_shot([sharp, blurry]) == sharp.id

    def test_better_exposed_photo_wins_when_sharpness_equal(self) -> None:
        well_exposed = PhotoForScoring(id=uuid.uuid4(), sharpness_score=200.0, exposure_score=0.95)
        overexposed = PhotoForScoring(id=uuid.uuid4(), sharpness_score=200.0, exposure_score=0.1)
        assert select_best_shot([well_exposed, overexposed]) == well_exposed.id

    def test_sharpness_weighted_more_than_exposure(self) -> None:
        """0.6/0.4 weighting: a photo noticeably sharper but slightly
        worse-exposed than its rival should still win."""
        sharper_slightly_worse_exposure = PhotoForScoring(
            id=uuid.uuid4(), sharpness_score=1000.0, exposure_score=0.7
        )
        blurrier_better_exposure = PhotoForScoring(
            id=uuid.uuid4(), sharpness_score=100.0, exposure_score=0.95
        )
        result = select_best_shot(
            [sharper_slightly_worse_exposure, blurrier_better_exposure]
        )
        assert result == sharper_slightly_worse_exposure.id
