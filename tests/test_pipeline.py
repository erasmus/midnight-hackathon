import subprocess
import sys
from pathlib import Path

import pytest

import pipeline
from core.schema import Person, RawProfile

REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeAdapter:
    """A stand-in module implementing the adapter interface."""

    name = "fake"

    def __init__(self, profiles=None):
        self._profiles = profiles or [RawProfile(platform="fake", handle="alice")]
        self.requested = None

    def fetch_top(self, n):
        self.requested = n
        return self._profiles[:n]


def run(tmp_path, adapters, **kwargs):
    return pipeline.run(
        adapters=adapters, db_path=tmp_path / "db.sqlite", out_dir=tmp_path / "out", **kwargs
    )


def test_pipeline_runs_end_to_end_and_creates_the_database(tmp_path):
    db_path = tmp_path / "db.sqlite"
    pipeline.run(adapters=[], db_path=db_path, out_dir=tmp_path / "out")
    assert db_path.exists()


def test_pipeline_with_no_adapters_persists_nothing(tmp_path):
    result = run(tmp_path, adapters=[])
    assert result.raw_profiles == []
    assert result.persons == []


def test_pipeline_persists_profiles_fetched_by_adapters(tmp_path):
    result = run(tmp_path, adapters=[FakeAdapter()])
    assert [p.handle for p in result.raw_profiles] == ["alice"]


def test_adapters_are_asked_for_the_requested_number_of_profiles(tmp_path):
    adapter = FakeAdapter()
    run(tmp_path, adapters=[adapter], top_n=25)
    assert adapter.requested == 25


def test_persisted_data_survives_the_run(tmp_path):
    run(tmp_path, adapters=[FakeAdapter()])
    from core.db import Database

    assert len(Database(tmp_path / "db.sqlite").all_raw_profiles()) == 1


def test_rerunning_the_pipeline_does_not_duplicate_rows(tmp_path):
    run(tmp_path, adapters=[FakeAdapter()])
    result = run(tmp_path, adapters=[FakeAdapter()])
    assert len(result.raw_profiles) == 1


def test_a_failing_adapter_does_not_abort_the_run(tmp_path):
    class Broken:
        name = "broken"

        def fetch_top(self, n):
            raise RuntimeError("upstream is down")

    result = run(tmp_path, adapters=[Broken(), FakeAdapter()])
    assert [p.handle for p in result.raw_profiles] == ["alice"]


def test_skipping_a_stage_records_it_as_skipped(tmp_path):
    result = run(tmp_path, adapters=[FakeAdapter()], skip=["enrich"])
    assert "enrich" in result.skipped
    assert "resolve" not in result.skipped


def test_each_stage_can_be_skipped_independently(tmp_path):
    for stage in pipeline.SKIPPABLE_STAGES:
        result = run(tmp_path, adapters=[FakeAdapter()], skip=[stage])
        assert result.skipped == [stage]


def test_skipping_an_unknown_stage_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        run(tmp_path, adapters=[FakeAdapter()], skip=["nonsense"])


def test_skipping_resolve_still_produces_one_person_per_profile(tmp_path):
    result = run(tmp_path, adapters=[FakeAdapter()], skip=["resolve"])
    assert len(result.persons) == 1


def test_stages_receive_and_return_persons(tmp_path):
    result = run(tmp_path, adapters=[FakeAdapter()])
    assert all(isinstance(p, Person) for p in result.persons)


def test_running_the_script_writes_an_empty_database(tmp_path):
    proc = subprocess.run(
        [sys.executable, "pipeline.py", "--db", str(tmp_path / "db.sqlite"),
         "--out", str(tmp_path / "out"), "--skip-fetch"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "db.sqlite").exists()


def test_the_script_accepts_a_skip_flag(tmp_path):
    proc = subprocess.run(
        [sys.executable, "pipeline.py", "--db", str(tmp_path / "db.sqlite"),
         "--out", str(tmp_path / "out"), "--skip-fetch", "--skip-enrich"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "enrich" in proc.stdout + proc.stderr


def test_skipping_fetch_runs_no_adapters(tmp_path):
    adapter = FakeAdapter()
    run(tmp_path, adapters=[adapter], skip=["fetch"])
    assert adapter.requested is None


def test_skipping_fetch_still_processes_already_persisted_profiles(tmp_path):
    run(tmp_path, adapters=[FakeAdapter()])
    result = run(tmp_path, adapters=[FakeAdapter()], skip=["fetch"])
    assert [p.handle for p in result.raw_profiles] == ["alice"]
    assert len(result.persons) == 1


def test_fetch_is_a_skippable_stage(tmp_path):
    assert "fetch" in pipeline.SKIPPABLE_STAGES
