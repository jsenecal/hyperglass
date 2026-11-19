"""Utility functions for gathering system information."""

# Standard Library
import os
import sys
import math
import typing as t
import platform
from pathlib import Path

# Third Party
import psutil as _psutil
from cpuinfo import get_cpu_info as _get_cpu_info  # type: ignore

# Project
from hyperglass.constants import __version__

SystemData = t.Dict[str, t.Tuple[t.Union[str, int], str]]


def _cpu() -> SystemData:
    """Construct CPU Information."""
    cpu_info = _get_cpu_info()
    brand = cpu_info.get("brand_raw", "")
    cores_logical = _psutil.cpu_count()
    cores_raw = _psutil.cpu_count(logical=False)
    # TODO: this is currently broken for M1 Macs, check status of: https://github.com/giampaolo/psutil/issues/1892
    cpu_ghz = _psutil.cpu_freq().current / 1000
    return (brand, cores_logical, cores_raw, cpu_ghz)


def _memory() -> SystemData:
    """Construct RAM Information."""
    mem_info = _psutil.virtual_memory()
    total_gb = round(mem_info.total / 1e9, 2)
    usage_percent = mem_info.percent
    return (total_gb, usage_percent)


def _disk() -> SystemData:
    """Construct Disk Information."""
    disk_info = _psutil.disk_usage("/")
    total_gb = round(disk_info.total / 1e9, 2)
    usage_percent = disk_info.percent
    return (total_gb, usage_percent)


def get_node_version() -> t.Optional[t.Tuple[int, int, int]]:
    """Get the system's NodeJS version."""

    # Standard Library
    import shutil
    import subprocess

    node_path = shutil.which("node")
    if node_path is None:
        return None

    raw_version = subprocess.check_output([node_path, "--version"]).decode()  # noqa: S603

    # Node returns the version as 'v14.5.0', for example. Remove the v.
    version = raw_version.replace("v", "")
    # Parse the version parts.
    return tuple((int(v) for v in version.split(".")))


# Overridable in tests.
_CGROUP_ROOT = Path("/sys/fs/cgroup")
_PROC_SELF_CGROUP = Path("/proc/self/cgroup")


def _read(path: Path) -> t.Optional[str]:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None


def _quota_cpus(quota: int, period: int) -> t.Optional[int]:
    if quota <= 0 or period <= 0:
        return None
    return max(math.ceil(quota / period), 1)


def _visible_ancestors(root: Path, relative: str) -> t.List[Path]:
    """Walk to the visible controller root without escaping the cgroup namespace."""
    relative_path = Path(relative.lstrip("/"))
    if ".." in relative_path.parts:
        return [root]
    directory = root / relative_path
    directories = [directory]
    while directory != root:
        directory = directory.parent
        directories.append(directory)
    return directories


def _cgroup_dirs() -> t.Tuple[t.List[Path], t.List[Path]]:
    """Get candidate cgroup v2 and v1 CPU controller directories for this process."""
    v2_dirs: t.List[Path] = []
    v1_dirs: t.List[Path] = []
    for line in (_read(_PROC_SELF_CGROUP) or "").splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        _, controllers, rel = parts
        if controllers == "":
            v2_dirs.extend(_visible_ancestors(_CGROUP_ROOT, rel))
        elif "cpu" in controllers.split(","):
            for mount in (controllers, "cpu,cpuacct", "cpu"):
                v1_dirs.extend(_visible_ancestors(_CGROUP_ROOT / mount, rel))
    # Inside a container the cgroup namespace makes the root the container's own cgroup.
    v2_dirs.append(_CGROUP_ROOT)
    return list(dict.fromkeys(v2_dirs)), list(dict.fromkeys(v1_dirs))


def _cgroup_v2_limit(dirs: t.List[Path]) -> t.Tuple[bool, t.Optional[int]]:
    """Read the smallest visible cgroup v2 quota. Returns (found, limit)."""
    found = False
    limits = []
    for directory in dirs:
        raw = _read(directory / "cpu.max")
        if raw is None:
            continue
        found = True
        try:
            quota, period = raw.split()
            if quota == "max":
                continue
            limit = _quota_cpus(int(quota), int(period))
        except ValueError:
            continue
        if limit is not None:
            limits.append(limit)
    return found, min(limits, default=None)


def _cgroup_v1_limit(dirs: t.List[Path]) -> t.Optional[int]:
    """Read the smallest visible cgroup v1 CFS quota and period pair."""
    limits = []
    for directory in dirs:
        quota = _read(directory / "cpu.cfs_quota_us")
        period = _read(directory / "cpu.cfs_period_us")
        if quota is None or period is None:
            continue
        try:
            limit = _quota_cpus(int(quota), int(period))
        except ValueError:
            continue
        if limit is not None:
            limits.append(limit)
    return min(limits, default=None)


def _cgroup_cpu_limit() -> t.Optional[int]:
    """Get the CPU limit from the process's cgroup CPU quota, if one is set.

    Docker's ``--cpus`` and Kubernetes CPU limits set a CFS quota, not a CPU
    affinity mask, so neither ``os.process_cpu_count()`` nor
    ``os.sched_getaffinity()`` sees them. Returns ``None`` when no quota applies
    or the cgroup files cannot be read.
    """
    v2_dirs, v1_dirs = _cgroup_dirs()
    found, limit = _cgroup_v2_limit(v2_dirs)
    if found:
        return limit
    return _cgroup_v1_limit(v1_dirs)


def cpu_count(multiplier: int = 1) -> int:
    """Get the number of CPUs this process may use, times ``multiplier``.

    Starts from the CPUs in the process's affinity mask
    (``os.process_cpu_count()`` on Python 3.13+, else ``os.sched_getaffinity()``,
    else the host count), then lowers it to the cgroup CPU quota when one is
    set. On bare metal without limits the result matches the host CPU count.
    The result is never below 1.
    """
    n: t.Optional[int] = None

    process_cpu_count = getattr(os, "process_cpu_count", None)
    if callable(process_cpu_count):
        n = process_cpu_count()

    if n is None and hasattr(os, "sched_getaffinity"):
        try:
            n = len(os.sched_getaffinity(0))
        except OSError:
            pass

    if n is None:
        # Standard Library
        import multiprocessing

        n = multiprocessing.cpu_count()

    limit = _cgroup_cpu_limit()
    if limit is not None:
        n = min(n, limit)

    return max(n * multiplier, 1)


def check_python() -> str:
    """Verify Python Version."""
    # Project
    from hyperglass.constants import MIN_PYTHON_VERSION

    pretty_version = ".".join(tuple(str(v) for v in MIN_PYTHON_VERSION))
    running_version = ".".join(
        str(v) for v in (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    )
    if sys.version_info < MIN_PYTHON_VERSION:
        raise RuntimeError(f"Python {pretty_version}+ is required (Running {running_version})")
    return running_version


def get_system_info() -> SystemData:
    """Get system info."""

    cpu_info, cpu_logical, cpu_physical, cpu_speed = _cpu()
    mem_total, mem_usage = _memory()
    disk_total, disk_usage = _disk()

    node_version = get_node_version()
    node_version_text = "not installed"
    if node_version is not None:
        node_version_text = ".".join(str(v) for v in node_version)

    return {
        "Hyperglass Version": (__version__, "text"),
        "Hyperglass Path": (os.environ["hyperglass_directory"], "code"),
        "Python Version": (platform.python_version(), "code"),
        "Node Version": (node_version_text, "code"),
        "Platform Info": (platform.platform(), "code"),
        "CPU Info": (cpu_info, "text"),
        "Logical Cores": (cpu_logical, "code"),
        "Physical Cores": (cpu_physical, "code"),
        "Processor Speed": (f"{cpu_speed}GHz", "code"),
        "Total Memory": (f"{mem_total} GB", "text"),
        "Memory Utilization": (f"{mem_usage}%", "text"),
        "Total Disk Space": (f"{disk_total} GB", "text"),
        "Disk Utilization": (f"{disk_usage}%", "text"),
    }
