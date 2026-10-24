import numpy as np
import pytest

from app.services.faces import INTRA_MIN_SIMILARITY, group_consistency


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _person(seed: int, count: int, spread: float) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    base = _unit(rng.normal(size=512))
    return [_unit(base + spread * rng.normal(size=512) / np.sqrt(512)) for _ in range(count)]


def test_photos_of_one_person_pass_even_when_two_poses_differ_a_lot():
    person = _person(seed=1, count=4, spread=1.4)
    group_sim, _, min_pair = group_consistency(person)
    assert group_sim >= INTRA_MIN_SIMILARITY
    assert min_pair < 0.55


def test_an_intruder_photo_is_rejected_and_identified():
    photos = _person(seed=2, count=3, spread=0.3)
    intruder = _person(seed=99, count=1, spread=0.3)[0]
    group_sim, worst_index, _ = group_consistency([*photos[:2], intruder, photos[2]])
    assert group_sim < INTRA_MIN_SIMILARITY
    assert worst_index == 2


@pytest.mark.parametrize("count", [3, 4, 5])
def test_identical_photos_are_fully_consistent(count):
    vector = _person(seed=3, count=1, spread=0)[0]
    group_sim, _, min_pair = group_consistency([vector] * count)
    assert group_sim == pytest.approx(1.0, abs=1e-5)
    assert min_pair == pytest.approx(1.0, abs=1e-5)
