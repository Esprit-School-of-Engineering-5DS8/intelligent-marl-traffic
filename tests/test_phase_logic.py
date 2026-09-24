import pytest

from cotraffic.envs.intersection import green_states, is_green_state, yellow_state

# netconvert program of a 4-arm junction with 16 vehicle signals and 4 crossings (16-19)
PROGRAM = [
    "gGGgrrrrgGGgrrrrrGrG",  # north-south green, two crossings green
    "gGGgrrrrgGGgrrrrrrrr",  # pedestrian clearance: same vehicle signals, crossings red
    "yyyyrrrryyyyrrrrrrrr",
    "rrrrgGGgrrrrgGGgGrGr",
    "rrrrgGGgrrrrgGGgrrrr",
    "rrrryyyyrrrryyyyrrrr",
]
CROSSINGS = frozenset({16, 17, 18, 19})


def test_is_green_state():
    assert is_green_state("GGrr")
    assert not is_green_state("yyrr")
    assert not is_green_state("rrrr")


def test_pedestrian_clearance_variants_are_merged_into_one_phase():
    greens = green_states(PROGRAM, CROSSINGS)
    assert greens == [PROGRAM[0], PROGRAM[3]]


def test_without_crossing_information_every_distinct_green_is_a_phase():
    assert len(green_states(PROGRAM)) == 4


def test_duplicates_are_removed_and_order_kept():
    assert green_states(["rG", "yr", "Gr", "ry", "rG"]) == ["rG", "Gr"]


def test_yellow_state_turns_lost_greens_yellow_and_keeps_new_greens_red():
    assert yellow_state("GGgrr", "rGrGG") == "yGyrr"


def test_yellow_state_turns_crossings_red_immediately():
    y = yellow_state(PROGRAM[0], PROGRAM[3], CROSSINGS)
    assert y[:16] == "yyyyrrrryyyyrrrr"
    assert y[16:] == "rrrr"


def test_yellow_state_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        yellow_state("GG", "GGG")
