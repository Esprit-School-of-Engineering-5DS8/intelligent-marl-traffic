"""Training logs of resumed runs: rows of the lost session are dropped on resume."""

import pandas as pd

from cotraffic.training.train import list_checkpoints, trim_episode_log


def test_trim_keeps_rows_up_to_the_checkpoint(tmp_path):
    path = tmp_path / "episodes.csv"
    pd.DataFrame({"timesteps": [5040, 10080, 15120, 20160], "mean_halting": [9, 8, 7, 6]}).to_csv(
        path, index=False
    )
    assert trim_episode_log(path, 12000) == 2
    log = pd.read_csv(path)
    assert log["timesteps"].tolist() == [5040, 10080]
    assert list(log.columns) == ["timesteps", "mean_halting"]
    assert trim_episode_log(path, 12000) == 0
    # a fresh start (no checkpoint) keeps only the header
    assert trim_episode_log(path, 0) == 2
    assert pd.read_csv(path).empty


def test_trim_without_log_does_nothing(tmp_path):
    assert trim_episode_log(tmp_path / "episodes.csv", 100) == 0


def test_checkpoints_are_sorted_by_steps(tmp_path):
    for steps in (99988, 149982, 49994):
        (tmp_path / f"model_{steps}_steps.zip").write_bytes(b"")
    assert [s for s, _ in list_checkpoints(tmp_path)] == [49994, 99988, 149982]
