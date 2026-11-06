"""
Driver for the Murrelektronik IMPACT67 Pro PN DIO8 IOL8 M12L 5P (art. 54630).

Device information comes from the documented IO-Link JSON REST API.
The firmware push uses the HTTP calls of the device's own web UI
(/netx/login, /netx/firmware, /netx/reset), which Murrelektronik does not
document as a public API.

Host, username and password come from the caller. The driver never reads KeePass itself.

Usage (IMPACT67_HOST is required, IMPACT67_USERNAME defaults to admin):
    python3 murrelektronik.py info
    python3 murrelektronik.py login
    python3 murrelektronik.py check /firmware/54630_1.09.01-V-00.m3z
    python3 murrelektronik.py update /firmware/54630_1.09.01-V-00.m3z [--allow-downgrade]

The update command is for supervised tests and asks for confirmation first.
"""

import getpass
import hashlib
import json
import os
import re
import sys
import time
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

ARTICLE_NUMBER = "54630"
IDENTIFICATION_PATH = "/iolink/v1/gateway/identification"


class FirmwareRejected(Exception):
    """The firmware file is not valid for this device."""


@dataclass
class DeviceInfo:
    ip: str
    state: str
    name: str | None = None
    mac: str | None = None
    serial: str | None = None
    firmware: str | None = None
    hardware: str | None = None
    vendor: str | None = None


@dataclass
class FirmwarePackage:
    path: str
    article: str
    version: str
    hardware: str
    vendor_id: int
    device_id: int
    payload: bytes


def parse_version(text: str | None) -> tuple[int, ...]:
    """Turns "V1.9.1" and "1.09.01-V-00" into (1, 9, 1)."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if match is None:
        raise ValueError(f"no version in {text!r}")
    return tuple(int(part or 0) for part in match.groups())


def same_version(reported: str | None, expected: str) -> bool:
    """A device answer without a readable version never counts as the expected version."""
    try:
        return parse_version(reported) == parse_version(expected)
    except ValueError:
        return False


def _check_sidecar_hash(path: Path) -> None:
    """Compares against the SHA256 in the vendor's .md5 file, if it sits next to the firmware."""
    sidecar = path.with_suffix(".md5")
    if not sidecar.exists():
        return
    match = re.search(r"\b[0-9a-fA-F]{64}\b", sidecar.read_text(errors="replace"))
    if match is None:
        raise FirmwareRejected(f"{sidecar.name} contains no SHA256")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != match.group().lower():
        raise FirmwareRejected(f"SHA256 mismatch for {path.name}")


def read_package(firmware_path: str) -> FirmwarePackage:
    """Opens an .m3z container and extracts the FWUPDATE.ZIP the device expects."""
    path = Path(firmware_path)
    if not path.is_file():
        raise FirmwareRejected(f"file not found: {firmware_path}")
    if path.suffix.lower() != ".m3z":
        raise FirmwareRejected(f"expected an .m3z file, got {path.name}")
    _check_sidecar_hash(path)

    try:
        with zipfile.ZipFile(path) as container:
            info = json.loads(container.read("info.json").decode("utf-8-sig"))
            device = info["device"]
            inner = (
                f"Binaries/{device['vendorId']}_{device['deviceId']}_"
                f"{device['articleNo']}_{device['hwVersion']}/FWUPDATE.ZIP"
            )
            payload = container.read(inner)
        entry = next(item for item in info["files"] if item["name"] == "FWUPDATE.ZIP")
        expected_size = int(entry["sizeInBytes"], 16)
        expected_crc = int(entry["crc32"], 16)
        package = FirmwarePackage(
            path=str(path),
            article=device["articleNo"],
            version=device["releaseVersion"],
            hardware=device["hwVersion"],
            vendor_id=int(device["vendorId"], 16),
            device_id=int(device["deviceId"], 16),
            payload=payload,
        )
        parse_version(package.version)
        parse_version(package.hardware)
    except (zipfile.BadZipFile, KeyError, StopIteration, TypeError, ValueError) as error:
        raise FirmwareRejected(f"corrupted update container: {error!r}") from error

    if package.article != ARTICLE_NUMBER:
        raise FirmwareRejected(f"firmware is for article {package.article}, not {ARTICLE_NUMBER}")
    if len(payload) != expected_size:
        raise FirmwareRejected("FWUPDATE.ZIP size does not match info.json")
    if zlib.crc32(payload) != expected_crc:
        raise FirmwareRejected("FWUPDATE.ZIP CRC32 does not match info.json")
    return package


def _not_started(status: str, detail: str) -> dict:
    """Result for every stop before the upload. The device is unchanged."""
    return {"status": status, "phase": "precheck", "detail": detail}


class Impact67Driver:
    def __init__(
        self,
        host: str,
        username: str | None = None,
        password: str | None = None,
        retries: int = 3,
        retry_delay: float = 2.0,
        request_timeout: float = 5.0,
        reset_settle: float = 5.0,
        poll_interval: float = 4.0,
        ready_timeout: float = 300.0,
        upload_timeout: float = 600.0,
        stable_checks: int = 5,
        stable_delay: float = 2.0,
        allow_downgrade: bool = False,
        progress: Callable[[str, float], None] | None = None,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.retries = retries
        self.retry_delay = retry_delay
        self.request_timeout = request_timeout
        self.reset_settle = reset_settle
        self.poll_interval = poll_interval
        self.ready_timeout = ready_timeout
        self.upload_timeout = upload_timeout
        self.stable_checks = stable_checks
        self.stable_delay = stable_delay
        self.allow_downgrade = allow_downgrade
        self.progress = progress
        url = host if "://" in host else f"http://{host}"
        self.base_url = url.rstrip("/")

    def _step(self, message: str, fraction: float) -> None:
        if self.progress:
            self.progress(message, fraction)

    def _read_identification(self) -> dict:
        response = requests.get(f"{self.base_url}{IDENTIFICATION_PATH}", timeout=self.request_timeout)
        response.raise_for_status()
        identification = response.json()
        if not isinstance(identification, dict):
            raise ValueError("identification is not a JSON object")
        return identification

    def _identification(self) -> dict:
        """Reads are safe to repeat. The device times out sporadically, so they retry with growing pauses."""
        for attempt in range(self.retries - 1):
            try:
                return self._read_identification()
            except requests.RequestException:
                time.sleep(self.retry_delay * 2**attempt)
        return self._read_identification()

    def _auth(self) -> tuple[str, str]:
        if not self.username or not self.password:
            raise FirmwareRejected("no credentials configured for IMPACT67")
        return self.username, self.password

    def get_info(self) -> DeviceInfo:
        try:
            identification = self._identification()
        except (requests.HTTPError, ValueError):
            return DeviceInfo(self.host, "error")
        except requests.RequestException:
            return DeviceInfo(self.host, "offline")
        return DeviceInfo(
            ip=self.host,
            state="online",
            name=identification.get("productName"),
            mac=identification.get("macAddress"),
            serial=identification.get("serialNumber"),
            firmware=identification.get("firmwareRevision"),
            hardware=identification.get("hardwareRevision"),
            vendor=identification.get("vendorName"),
        )

    def get_status(self) -> dict:
        return asdict(self.get_info())

    def login(self) -> None:
        """Checks the credentials once. A wrong password must not be retried."""
        response = requests.get(f"{self.base_url}/netx/login", auth=self._auth(), timeout=20)
        response.raise_for_status()

    def precheck(self, package: FirmwarePackage) -> dict | None:
        """Returns the result to stop with, or None if the update may start."""
        identification = self._identification()
        product_id = str(identification.get("productId"))
        if product_id != str(package.device_id):
            raise FirmwareRejected(f"device reports product {product_id}, firmware is for {package.device_id}")

        hardware = parse_version(identification.get("hardwareRevision"))[0]
        if hardware != parse_version(package.hardware)[0]:
            raise FirmwareRejected(f"hardware {hardware} does not match firmware hardware {package.hardware}")

        reported = identification.get("firmwareRevision")
        current = parse_version(reported)
        target = parse_version(package.version)
        if current == target:
            return {"status": "already_up_to_date", "version": reported}
        if current > target and not self.allow_downgrade:
            raise FirmwareRejected(f"downgrade from {current} to {target} is not allowed")
        return None

    def is_stable(self) -> bool:
        """Requires consecutive answers, so a flash never starts on a device that keeps dropping out."""
        for attempt in range(self.stable_checks):
            try:
                self._read_identification()
            except (requests.RequestException, ValueError):
                return False
            if attempt < self.stable_checks - 1:
                time.sleep(self.stable_delay)
        return True

    def wait_ready(self, target: str) -> dict | None:
        """Waits until the device answers with the target version, or returns its last answer."""
        time.sleep(self.reset_settle)
        deadline = time.monotonic() + self.ready_timeout
        last_answer = None
        while time.monotonic() < deadline:
            try:
                answer = self._read_identification()
            except (requests.RequestException, ValueError):
                pass
            else:
                if answer != last_answer:
                    self._step(f"device answers with {answer.get('firmwareRevision')}", 0.8)
                last_answer = answer
                if same_version(answer.get("firmwareRevision"), target):
                    return answer
            time.sleep(self.poll_interval)
        return last_answer

    def update(self, firmware_path: str) -> dict:
        """Never raises for device or file problems. "phase": "precheck" means the device is unchanged."""
        try:
            package = read_package(firmware_path)
            self._step(f"firmware file ok: {package.version}", 0.05)
            stop_result = self.precheck(package)
            if stop_result:
                return stop_result
            self._step("precheck ok", 0.08)
            self.login()
            self._step("login ok", 0.1)
            if not self.is_stable():
                return _not_started("network_failed", "device not stable before upload")
            self._step(f"device stable, {self.stable_checks} answers in a row", 0.15)
        except FirmwareRejected as error:
            return _not_started("rejected", str(error))
        except requests.HTTPError as error:
            code = error.response.status_code
            status = "rejected" if code in (401, 403) else "network_failed"
            return _not_started(status, f"HTTP {code} before upload")
        except requests.RequestException as error:
            return _not_started("network_failed", f"{type(error).__name__} before upload")
        except ValueError as error:
            return _not_started("rejected", f"unusable device answer: {error}")
        return self._flash(package)

    def _flash(self, package: FirmwarePackage) -> dict:
        """Upload and reset are never repeated: their effect on the device is unknown after an error."""
        self._step(f"upload started, {len(package.payload)} bytes", 0.2)
        started = time.monotonic()
        try:
            response = requests.post(
                f"{self.base_url}/netx/firmware",
                data=package.payload,
                headers={"Content-Type": "application/zip"},
                auth=self._auth(),
                # One value on purpose: with a (connect, read) tuple the connect value also
                # limits sending the body, which aborted uploads after 10 s on the real device.
                timeout=self.upload_timeout,
            )
        except requests.RequestException as error:
            return {
                "status": "network_failed",
                "phase": "upload",
                "detail": f"{type(error).__name__}: {error}"[:300],
                "seconds": round(time.monotonic() - started, 1),
            }
        if response.status_code != 200:
            return {
                "status": "failed",
                "phase": "upload",
                "detail": f"HTTP {response.status_code}: {response.text[:200]}",
            }
        self._step("upload finished, sending reset", 0.5)

        reset_answer = "no answer"
        try:
            response = requests.post(f"{self.base_url}/netx/reset", auth=self._auth(), timeout=5)
            reset_answer = f"HTTP {response.status_code}"
        except requests.RequestException:
            pass  # The device may restart before answering, so the version check decides.
        self._step(f"reset answered with {reset_answer}, waiting for device", 0.55)

        identification = self.wait_ready(package.version)
        if identification is None:
            return {
                "status": "network_failed",
                "phase": "wait_ready",
                "detail": f"device did not return, reset: {reset_answer}",
            }

        reported = identification.get("firmwareRevision")
        if not same_version(reported, package.version):
            return {
                "status": "failed",
                "phase": "verify",
                "detail": f"device reports {reported}, reset: {reset_answer}",
            }
        self._step(f"verified {reported}", 0.95)
        return {"status": "ok", "version": reported, "reset": reset_answer}


def print_progress(message: str, _fraction: float) -> None:
    print(f"    [{time.strftime('%H:%M:%S')}] {message}", flush=True)


def driver_from_env(allow_downgrade: bool = False) -> Impact67Driver:
    host = os.environ.get("IMPACT67_HOST")
    if not host:
        raise SystemExit("Set IMPACT67_HOST to the IP address of the device.")
    return Impact67Driver(
        host,
        os.environ.get("IMPACT67_USERNAME", "admin"),
        os.environ.get("IMPACT67_PASSWORD"),
        allow_downgrade=allow_downgrade,
        progress=print_progress,
    )


def manual_update(firmware_path: str, allow_downgrade: bool) -> int:
    """Single supervised flash for testing. Asks for confirmation before touching the device."""
    driver = driver_from_env(allow_downgrade)
    try:
        package = read_package(firmware_path)
    except FirmwareRejected as error:
        print(f"REJECTED: {error}")
        return 1

    status = driver.get_status()
    print(f"Device {driver.host}: {status['firmware']} ({status['state']})")
    print(f"Firmware file: {package.version}, {len(package.payload)} bytes")
    if status["state"] != "online":
        print("Device is not online. Nothing was started.")
        return 1
    if input("Type FLASH to start: ") != "FLASH":
        print("Aborted. Nothing was started.")
        return 1

    driver.password = driver.password or getpass.getpass(f"Password for {driver.username}: ")
    started = time.monotonic()
    result = driver.update(firmware_path)
    print(json.dumps(result, indent=2))
    print(f"Duration: {time.monotonic() - started:.0f} s")
    print(json.dumps(driver.get_status(), indent=2))
    return 0 if result["status"] in ("ok", "already_up_to_date") else 1


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "info":
        print(json.dumps(driver_from_env().get_status(), indent=2))
        return 0
    if command == "login":
        driver = driver_from_env()
        driver.password = driver.password or getpass.getpass(f"Password for {driver.username}: ")
        try:
            driver.login()
        except requests.HTTPError as error:
            print(f"LOGIN FAILED: HTTP {error.response.status_code}. Do not retry.")
            return 1
        except requests.RequestException as error:
            print(f"NO ANSWER: {type(error).__name__}")
            return 1
        print("LOGIN OK")
        return 0
    if command == "check" and len(sys.argv) > 2:
        try:
            package = read_package(sys.argv[2])
        except FirmwareRejected as error:
            print(f"REJECTED: {error}")
            return 1
        print(f"OK: {package.article} {package.version}, hardware {package.hardware}, {len(package.payload)} bytes")
        return 0
    if command == "update" and len(sys.argv) > 2:
        return manual_update(sys.argv[2], "--allow-downgrade" in sys.argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
