"""The progress store, which will hold personal performance data the moment identity exists.

These controls survived the V0.24.0 rewrite because `progress.py` did: the illustrative drill
engine was replaced, the store was not. Their tests were in the retired `test_training.py`, and
restoring them here is the point. Deleting a suite for a module that still exists takes its
controls with it, and the register would have gone on citing them.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from enlightenment.training import ProgressStore, RunRecord, now_utc


def _record(item_id: str = "DRL-0001") -> RunRecord:
    return RunRecord(
        item_id=item_id,
        item_version="",
        content_hash="0" * 64,
        procedure_id="PROC-MNV",
        axis="CMP-02",
        seed=1,
        answered_at=now_utc().isoformat(),
        classification="accept",
        first_action="",
        confidence=4,
        correct=True,
        action_correct=True,
        brier=0.0625,
        points=1.25,
        rating_before=1200,
        rating_after=1216,
    )


def test_a_missing_progress_file_is_not_an_error(tmp_path: Path) -> None:
    """A first run has no file. Treating that as a fault would break every fresh install."""
    store = ProgressStore(tmp_path / "progress.json")
    progress = store.load("operator-a")
    assert progress.operator_id == "operator-a"
    assert progress.runs == []


@pytest.mark.skipif(os.geteuid() == 0, reason="running as root bypasses directory permissions")
def test_the_progress_file_is_never_world_readable(tmp_path: Path) -> None:
    """This file will hold personal performance data tied to a named individual.

    Written with a narrow mode at creation rather than narrowed afterwards: a chmod after the
    write leaves a window in which the file exists and is readable, and a window is a disclosure.
    """
    path = tmp_path / "progress.json"
    store = ProgressStore(path)
    progress = store.load("operator-a")
    progress.runs.append(_record())
    store.save(progress)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert not mode & stat.S_IROTH, oct(mode)
    assert not mode & stat.S_IWOTH, oct(mode)
    assert not mode & stat.S_IRGRP, oct(mode)


def test_a_damaged_progress_file_degrades_to_defaults_rather_than_a_500(tmp_path: Path) -> None:
    """A corrupt file must not take the service down or leak its internals to a caller.

    Degrading to defaults loses history, which is the lesser harm: the alternative is an operator
    who cannot drill at all because one byte of their own progress file is wrong.
    """
    path = tmp_path / "progress.json"
    path.write_text("{ not json", encoding="utf-8")
    progress = ProgressStore(path).load("operator-a")
    assert progress.runs == []
    assert progress.operator_id == "operator-a"


def test_a_run_row_of_an_unknown_shape_is_skipped_rather_than_fatal(tmp_path: Path) -> None:
    """One unreadable row must not discard the rest of an operator's history."""
    path = tmp_path / "progress.json"
    path.write_text(
        json.dumps({"operator-a": {"rating": 1300, "runs": [{"nonsense": True}]}}),
        encoding="utf-8",
    )
    progress = ProgressStore(path).load("operator-a")
    assert progress.rating == 1300


def test_run_history_is_capped_so_the_file_cannot_grow_without_limit(tmp_path: Path) -> None:
    """The file is read whole on every request, so unbounded growth is a latency fault.

    It is also a retention question: an uncapped history keeps every answer an operator has ever
    given, and the retention period is still an open decision.
    """
    store = ProgressStore(tmp_path / "progress.json")
    progress = store.load("operator-a")
    for index in range(500):
        progress.runs.append(_record(f"DRL-{index:04d}"))
    store.save(progress)
    reloaded = store.load("operator-a")
    assert len(reloaded.runs) < 500
    assert reloaded.runs[-1].item_id == "DRL-0499", "the cap dropped the NEWEST rows"


def test_saving_one_operator_preserves_every_other_operator(tmp_path: Path) -> None:
    """One JSON file, many operators. A save that read-modify-wrote carelessly would lose them."""
    store = ProgressStore(tmp_path / "progress.json")
    first = store.load("operator-a")
    first.runs.append(_record())
    store.save(first)
    second = store.load("operator-b")
    second.runs.append(_record("DRL-0002"))
    store.save(second)

    assert store.load("operator-a").runs
    assert store.load("operator-b").runs


def test_a_cue_with_no_recorded_due_date_is_due(tmp_path: Path) -> None:
    """An item never seen is due now. The alternative is an item that is never served."""
    progress = ProgressStore(tmp_path / "progress.json").load("operator-a")
    assert progress.cue("DRL-0001").is_due(now_utc()) is True


def test_a_miss_returns_the_spacing_interval_to_the_front(tmp_path: Path) -> None:
    """A wrong answer resets the streak, which puts the item back at the front interval.

    The whole point of the spacing model: an item you got wrong comes back soon, and an item you
    have got right repeatedly comes back much later.
    """
    progress = ProgressStore(tmp_path / "progress.json").load("operator-a")
    schedule = progress.cue("DRL-0001")
    for _ in range(4):
        schedule.record(correct=True, now=now_utc())
    long_streak = schedule.streak
    schedule.record(correct=False, now=now_utc())
    assert schedule.streak == 0
    assert long_streak > 0


def test_an_axis_with_no_attempts_reports_nothing_rather_than_zero(tmp_path: Path) -> None:
    """ "Not measured" and "measured at zero" are different statements and must stay different."""
    progress = ProgressStore(tmp_path / "progress.json").load("operator-a")
    axis = progress.axis("CMP-02")
    assert axis.accuracy is None
    assert axis.interval is None


def test_a_perfect_small_sample_still_reports_a_non_zero_interval(tmp_path: Path) -> None:
    """Three out of three is not certainty.

    A plain Wald interval on a perfect small sample reports zero width, which is the most
    confident and least true thing this could say. The Agresti-Coull adjustment is what stops a
    supervisor reading three answers as proof.
    """
    progress = ProgressStore(tmp_path / "progress.json").load("operator-a")
    axis = progress.axis("CMP-02")
    axis.attempts = 3
    axis.correct = 3
    interval = axis.interval
    assert interval is not None
    low, high = interval
    assert high - low > 0.1, interval
    assert low < 1.0
