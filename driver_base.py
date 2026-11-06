"""
Common interface every device driver implements.
The orchestrator only ever talks to this interface - it never knows
which vendor/device is actually behind it.
"""

from abc import ABC, abstractmethod
import time

import requests


class DriverBase(ABC):
    """Base class for all device drivers."""

    def stop(self) -> bool:
        """Put the device into a safe state before updating (e.g. PLC STOP).
        Default: no-op, override for devices that need it (controllers)."""
        return True

    def run(self) -> bool:
        """Bring the device back into normal operation after updating.
        Default: no-op, override for devices that need it (controllers)."""
        return True

    @abstractmethod
    def update(self, firmware_path: str) -> dict:
        """Upload/install new firmware. Must return a dict with at least:
        {"status": "ok" | "already_up_to_date" | "rejected" | "network_failed" | "failed", ...}
        """
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> str:
        """Return a short string describing current device state, used for
        reporting when the orchestrator halts on failure."""
        raise NotImplementedError

    # --- shared helper used by concrete drivers ---
    def _upload_with_retry(self, url, firmware_path, field_name,
                            session=None, max_retries=3, timeout=600,
                            verify=True, extra_kwargs=None):
        """POST a firmware file as multipart/form-data, retrying on
        connection/timeout errors only (never on a real rejection from the
        device). Reopens the file each attempt so a failed read doesn't
        leave the handle at EOF."""
        poster = session.post if session is not None else requests.post
        extra_kwargs = extra_kwargs or {}

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                with open(firmware_path, "rb") as f:
                    resp = poster(
                        url,
                        files={field_name: f},
                        timeout=timeout,
                        verify=verify,
                        **extra_kwargs,
                    )
                # Some devices (confirmed: the Weidmüller switch's legacy web
                # UI) always return HTTP 200 and put the real result in the
                # HTML body ("Apply fail... Flash is already updated with
                # this file") - so body content must be checked BEFORE
                # trusting the status code, not after.
                text_lower = resp.text.lower()
                already_markers = ("already updated", "already up to date", "already up-to-date",
                                    "no update needed", "up to date")
                failure_markers = ("apply fail", "fail", "error", "reject", "invalid")

                if any(marker in text_lower for marker in already_markers):
                    return {"status": "already_up_to_date", "code": resp.status_code, "detail": resp.text}

                if any(marker in text_lower for marker in failure_markers):
                    return {"status": "rejected", "code": resp.status_code, "detail": resp.text}

                if resp.status_code == 200:
                    return {"status": "ok", "code": resp.status_code, "detail": resp.text}

                return {"status": "rejected", "code": resp.status_code, "detail": resp.text}

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = str(e)
                if attempt == max_retries:
                    return {"status": "network_failed", "error": last_error, "attempts": attempt}
                wait = 2 ** attempt  # 2s, 4s, 8s, ...
                print(f"[{self.__class__.__name__}] upload attempt {attempt} failed "
                      f"({last_error}), retrying in {wait}s...")
                time.sleep(wait)

        return {"status": "network_failed", "error": last_error, "attempts": max_retries}