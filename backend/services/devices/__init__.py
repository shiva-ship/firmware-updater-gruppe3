"""Herstelleradapter (Python-Gerätetreiber) und DEMO-Simulator."""

from __future__ import annotations

from .adstec import AdstecAdapter
from .balluff import BalluffAdapter
from .base import (
    VENDOR_LABELS,
    CriticalDeviceError,
    DeviceAdapter,
    DeviceError,
    DeviceInfo,
    UpdateResult,
)
from .demo import DemoSimulator
from .siemens import SiemensAdapter
from .versions import compare_versions, parse_version, version_from_filename


def default_adapters(timeout: float = 10, reboot_timeout: float = 900) -> dict[str, DeviceAdapter]:
    return {
        "balluff": BalluffAdapter(timeout=timeout, reboot_timeout=reboot_timeout),
        "adstec": AdstecAdapter(timeout=timeout, reboot_timeout=reboot_timeout),
        "siemens": SiemensAdapter(),
    }


__all__ = [
    "VENDOR_LABELS",
    "AdstecAdapter",
    "BalluffAdapter",
    "CriticalDeviceError",
    "DemoSimulator",
    "DeviceAdapter",
    "DeviceError",
    "DeviceInfo",
    "SiemensAdapter",
    "UpdateResult",
    "compare_versions",
    "default_adapters",
    "parse_version",
    "version_from_filename",
]
