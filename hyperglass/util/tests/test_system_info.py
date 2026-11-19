"""Tests for cgroup/affinity-aware system info utilities."""

# Standard Library
import os

# Third Party
import pytest

# Local
from ..system_info import cpu_count


@pytest.fixture(autouse=True)
def isolated_cgroup(monkeypatch, tmp_path):
    """Host cgroup quotas must not change mocked affinity or fallback assertions."""
    from .. import system_info

    monkeypatch.setattr(system_info, "_CGROUP_ROOT", tmp_path / "cgroup")
    monkeypatch.setattr(system_info, "_PROC_SELF_CGROUP", tmp_path / "proc_self_cgroup")


def test_cpu_count_default_multiplier_returns_at_least_one():
    """cpu_count() with no args returns >=1 on any platform."""
    assert cpu_count() >= 1


def test_cpu_count_multiplier_scales():
    """cpu_count(N) scales the detected count."""
    base = cpu_count()
    assert cpu_count(2) == base * 2


def test_cpu_count_floor_is_one():
    """cpu_count(0) returns at least 1, never 0."""
    assert cpu_count(0) == 1


@pytest.mark.skipif(
    not hasattr(os, "sched_getaffinity"),
    reason="sched_getaffinity is Linux-only",
)
def test_cpu_count_respects_sched_getaffinity(monkeypatch):
    """When process_cpu_count is unavailable, falls back to sched_getaffinity."""
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: {0, 1, 2})
    assert cpu_count() == 3


def test_cpu_count_falls_back_to_multiprocessing(monkeypatch):
    """When neither cgroup-aware API works, falls back to multiprocessing."""
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)

    # Standard Library
    import multiprocessing

    monkeypatch.setattr(multiprocessing, "cpu_count", lambda: 7)
    assert cpu_count() == 7


def _fake_cgroup(tmp_path, monkeypatch, files):
    """Point the cgroup readers at a fake hierarchy under tmp_path."""
    # Local
    from .. import system_info

    root = tmp_path / "cgroup"
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text(files.get("__proc__", "0::/\n"))
    monkeypatch.setattr(system_info, "_CGROUP_ROOT", root)
    monkeypatch.setattr(system_info, "_PROC_SELF_CGROUP", proc_cgroup)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 72, raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: set(range(72)), raising=False)


def test_cpu_count_honors_cgroup_v2_quota(tmp_path, monkeypatch):
    """A cgroup v2 quota (docker --cpus=2) limits the count below the affinity count."""
    _fake_cgroup(tmp_path, monkeypatch, {"cpu.max": "200000 100000\n"})
    assert cpu_count() == 2
    assert cpu_count(2) == 4


def test_cpu_count_rounds_fractional_quota_up(tmp_path, monkeypatch):
    """A fractional quota (cpu: 1500m) rounds up rather than down to zero or one."""
    _fake_cgroup(tmp_path, monkeypatch, {"cpu.max": "150000 100000\n"})
    assert cpu_count() == 2


def test_cpu_count_unlimited_cgroup_v2(tmp_path, monkeypatch):
    """`max` means no quota, so the affinity count stands."""
    _fake_cgroup(tmp_path, monkeypatch, {"cpu.max": "max 100000\n"})
    assert cpu_count() == 72


def test_cpu_count_reads_nested_cgroup_v2_path(tmp_path, monkeypatch):
    """On a host, the process's own cgroup (from /proc/self/cgroup) holds the quota."""
    _fake_cgroup(
        tmp_path,
        monkeypatch,
        {
            "__proc__": "0::/system.slice/hyperglass.service\n",
            "system.slice/hyperglass.service/cpu.max": "300000 100000\n",
        },
    )
    assert cpu_count() == 3


def test_cpu_count_honors_cgroup_v1_quota(tmp_path, monkeypatch):
    """Cgroup v1 expresses the quota as cfs_quota_us / cfs_period_us."""
    _fake_cgroup(
        tmp_path,
        monkeypatch,
        {
            "__proc__": "4:cpu,cpuacct:/docker/abc\n",
            "cpu,cpuacct/cpu.cfs_quota_us": "100000\n",
            "cpu,cpuacct/cpu.cfs_period_us": "100000\n",
        },
    )
    assert cpu_count() == 1


def test_cpu_count_unlimited_cgroup_v1(tmp_path, monkeypatch):
    """A v1 quota of -1 means no limit."""
    _fake_cgroup(
        tmp_path,
        monkeypatch,
        {
            "__proc__": "4:cpu,cpuacct:/\n",
            "cpu,cpuacct/cpu.cfs_quota_us": "-1\n",
            "cpu,cpuacct/cpu.cfs_period_us": "100000\n",
        },
    )
    assert cpu_count() == 72


def test_cpu_count_without_cgroup_files(tmp_path, monkeypatch):
    """No readable cgroup files (macOS, restricted /sys) falls back to affinity."""
    _fake_cgroup(tmp_path, monkeypatch, {})
    assert cpu_count() == 72


@pytest.mark.parametrize("child", ["max 100000", "800000 100000", "invalid", "0 0"])
def test_v2_limited_parent_caps_child(tmp_path, monkeypatch, child):
    _fake_cgroup(tmp_path, monkeypatch, {
        "__proc__": "0::/parent/child\n",
        "cpu.max": "max 100000",
        "parent/cpu.max": "100000 100000",
        "parent/child/cpu.max": child,
    })
    assert cpu_count() == 1
    assert cpu_count(2) == 2


@pytest.mark.parametrize("mount", ["cpu,cpuacct", "cpu"])
@pytest.mark.parametrize("child_quota", ["-1", "800000", "invalid", "0"])
def test_v1_limited_parent_caps_child(tmp_path, monkeypatch, mount, child_quota):
    _fake_cgroup(tmp_path, monkeypatch, {
        "__proc__": "4:cpu,cpuacct:/parent/child\n",
        f"{mount}/cpu.cfs_quota_us": "-1",
        f"{mount}/cpu.cfs_period_us": "100000",
        f"{mount}/parent/cpu.cfs_quota_us": "100000",
        f"{mount}/parent/cpu.cfs_period_us": "100000",
        f"{mount}/parent/child/cpu.cfs_quota_us": child_quota,
        f"{mount}/parent/child/cpu.cfs_period_us": "100000",
    })
    assert cpu_count() == 1


def test_child_quota_can_be_lower_than_ancestors(tmp_path, monkeypatch):
    _fake_cgroup(tmp_path, monkeypatch, {
        "__proc__": "0::/parent/child\n",
        "cpu.max": "600000 100000",
        "parent/cpu.max": "400000 100000",
        "parent/child/cpu.max": "150000 100000",
    })
    assert cpu_count() == 2


def test_namespace_root_quota_applies_when_membership_path_is_not_visible(tmp_path, monkeypatch):
    _fake_cgroup(tmp_path, monkeypatch, {
        "__proc__": "0::/unmounted/parent/child\n", "cpu.max": "100000 100000",
    })
    assert cpu_count() == 1


def test_cgroup_walk_stops_at_visible_root(tmp_path, monkeypatch):
    _fake_cgroup(tmp_path, monkeypatch, {
        "__proc__": "0::/child\n", "cpu.max": "max 100000",
        "child/cpu.max": "max 100000",
    })
    (tmp_path / "cpu.max").write_text("100000 100000")
    assert cpu_count() == 72


def test_affinity_still_limits_a_larger_cgroup_quota(tmp_path, monkeypatch):
    _fake_cgroup(tmp_path, monkeypatch, {"cpu.max": "800000 100000"})
    monkeypatch.setattr(os, "process_cpu_count", lambda: 2, raising=False)
    assert cpu_count() == 2
