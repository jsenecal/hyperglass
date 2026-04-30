"""Tests for cgroup/affinity-aware system info utilities."""

# Standard Library
import os
import sys

# Third Party
import pytest

# Local
from ..system_info import cpu_count


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
