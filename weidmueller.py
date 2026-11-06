"""
Drivers for the two confirmed Weidmüller devices.

Confirmed endpoints (live-tested at the hackathon):
  - Switch IE-SW-AL06LM-4TX-2SC     : POST http://192.168.0.110/web_upgrade   field="firmware"
  - Steuerung UC20-M3000 (u-OS)     : POST https://192.168.0.101/update/upload  field="file"  (SWUpdate)
      NOTE: path is /update/upload, NOT /upload - confirmed from the real browser's HAR capture.
      /upload returns 413 (nginx client_max_body_size rejects the file before it reaches the backend);
      /update/upload is the actual location block the dashboard uses.

TODO before relying on this in the demo:
  - Confirm login shape via browser DevTools -> Network tab:
      * If every request carries "Authorization: Basic ..." header      -> BASIC_AUTH mode (already wired below)
      * If login is a POST to /login (or similar) that sets a cookie    -> SESSION mode (swap USE_SESSION_LOGIN = True
                                                                             and fill in LOGIN_PATH / LOGIN_PAYLOAD)
"""

from driver_base import DriverBase
import re
import time
import requests


class WeidmuellerSwitchDriver(DriverBase):
    """Weidmüller IE-SW-AL06LM-4TX-2SC Ethernet switch.

    Status info (firmware version, serial, MAC) is parsed off /main.htm,
    which embeds it as JS calls: MT(5,"v1.05") = Firmware Version,
    MT(8,"020095C00031") = Serial Number (field indices confirmed from a
    live capture of that page: 0=Name,1=Description,2=Location,3=Contact,
    4=SNMP OID,5=Firmware Version,6=Kernel Version,7=MAC Address,8=Serial).
    """

    HOST = "192.168.0.110"
    USERNAME = "admin"
    PASSWORD = "Detmold"
    UPLOAD_URL = f"http://{HOST}/web_upgrade"
    INFO_URL = f"http://{HOST}/main.htm"

    def __init__(self):
        self.session = requests.Session()
        self.session.auth = (self.USERNAME, self.PASSWORD)  # swap for session login if needed, see TODO above

    def update(self, firmware_path: str) -> dict:
        result = self._upload_with_retry(
            self.UPLOAD_URL,
            firmware_path,
            field_name="firmware",
            session=self.session,
            verify=True,
        )
        if result["status"] == "ok":
            print("[Switch] Update accepted - system restart in progress...")
            self._wait_for_reboot()
            print("[Switch] Update successful - device back online.")
        return result

    def _wait_for_reboot(self, down_timeout=60, up_timeout=180, poll_interval=5):
        """Mirrors the Steuerung's reboot-wait logic: confirm the device
        actually drops off, then wait for it to come back before declaring
        success - never trust the upload HTTP response alone."""
        went_down = False
        down_deadline = time.time() + down_timeout
        while time.time() < down_deadline:
            try:
                self.session.get(f"http://{self.HOST}/", timeout=3)
                time.sleep(poll_interval)
            except requests.exceptions.RequestException:
                went_down = True
                break
        if not went_down:
            print("[Switch] WARNING: device never appeared to go down - "
                  "continuing to check for it coming back anyway.")

        up_deadline = time.time() + up_timeout
        while time.time() < up_deadline:
            try:
                resp = self.session.get(f"http://{self.HOST}/", timeout=5)
                if resp.status_code in (200, 401, 403):
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(poll_interval)

        raise RuntimeError(
            f"Switch did not come back online within {up_timeout}s after update - "
            f"halting, do not assume success"
        )

    def get_status(self) -> str:
        try:
            resp = self.session.get(self.INFO_URL, timeout=10)
            if resp.status_code != 200:
                return f"reachable (HTTP {resp.status_code})"
            fw_match = re.search(r'MT\(5,\s*"([^"]*)"\)', resp.text)
            serial_match = re.search(r'MT\(8,\s*"([^"]*)"\)', resp.text)
            fw = fw_match.group(1) if fw_match else "unknown"
            serial = serial_match.group(1) if serial_match else "unknown"
            return f"reachable - firmware {fw}, serial {serial}"
        except requests.exceptions.RequestException as e:
            return f"unreachable ({e})"


class WeidmuellerSteuerungDriver(DriverBase):
    """Weidmüller UC20-M3000 controller (u-OS, SWUpdate-based)."""

    HOST = "192.168.0.101"
    USERNAME = "admin"
    PASSWORD = "Detmold"
    UPLOAD_URL = f"https://{HOST}/update/upload"

    # Administration API (u-OS Admin API v1.4.0) - OAuth2 client_credentials.
    # Used only for get_status() - NOT for the firmware upload itself, which
    # still goes through the dashboard's LDAP-session-gated /update/upload.
    TOKEN_URL = f"https://{HOST}/oauth2/token"
    ADMIN_API_BASE = f"https://{HOST}/u-os-adm/api/v1"
    CLIENT_ID = "dda068a4-1521-4f5b-aff7-375c5f1a3c1f"
    CLIENT_SECRET = "gRAJgn7AScranpAZ0n56kicmHH"  # TODO: move to env var before pushing to the public repo
    ADMIN_SCOPES = ["u-os-adm.system.readonly", "u-os-adm.update.readonly"]

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False  # self-signed cert on the device
        requests.packages.urllib3.disable_warnings()  # silence the verify=False warning spam
        self._admin_token = None
        self._dashboard_logged_in = False

    def _login_dashboard(self):
        """Replicate the LDAP login -> OIDC callback flow to obtain the
        _oauth2_proxy_ session cookie. This is REQUIRED for /update/upload -
        Basic Auth gets routed to a restricted nginx location with a tiny
        body-size cap (confirmed via live testing: 413 every time). Only the
        real browser-session cookie unlocks the full-size upload path."""
        # Step 1: hit the protected root resource ("/" - confirmed gated by
        # oauth2-proxy; "/update/" itself appears to serve its static page
        # regardless of auth state, so hitting that doesn't trigger the
        # redirect). Let requests follow the redirect chain down to the LDAP
        # login form - this is where the server generates the per-flow
        # "state" CSRF token, so we can't hardcode it.
        # "/" itself just returns 403 flatly (confirmed via live testing) -
        # it does NOT redirect into the login flow. The actual entry point
        # is oauth2-proxy's own "/auth/start" endpoint, which kicks off the
        # OIDC/PKCE dance against the device's IDP and eventually lands back
        # at /auth/callback with the _oauth2_proxy_ cookie set. Confirmed via
        # live Burp capture of the real browser flow.
        browser_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = self.session.get(
            f"https://{self.HOST}/auth/start?rd=%2F", headers=browser_headers, timeout=15
        )
        login_url = resp.url  # .../idp/auth/ldap/login?back=...&state=...

        print(f"[Steuerung] GET /auth/start -> status: {resp.status_code}, final URL: {login_url}")

        if "idp/auth/ldap/login" not in login_url:
            if resp.status_code != 200:
                raise RuntimeError(
                    f"/auth/start did not redirect to login and did not return 200 either "
                    f"(status: {resp.status_code}) - can't tell if we're authenticated"
                )
            # already logged in (session cookie still valid from a previous run)
            print("[Steuerung] no redirect to login page, got 200 - assuming already authenticated")
            self._dashboard_logged_in = True
            return

        # Step 2+3: POST credentials to that exact URL; requests follows the
        # 303 -> /auth/callback -> 302 -> / chain automatically, picking up
        # the _oauth2_proxy_ cookie into self.session.cookies along the way.
        resp = self.session.post(
            login_url,
            data={"login": self.USERNAME, "password": self.PASSWORD},
            timeout=15,
        )
        print(f"[Steuerung] login POST -> final URL: {resp.url}, status: {resp.status_code}")
        print(f"[Steuerung] cookies after login: {list(self.session.cookies.get_dict().keys())}")

        if "_oauth2_proxy_" not in self.session.cookies.get_dict():
            raise RuntimeError(
                f"Dashboard login did not yield an _oauth2_proxy_ cookie "
                f"(final URL: {resp.url}, status: {resp.status_code})"
            )
        self._dashboard_logged_in = True

    def stop(self) -> bool:
        """Put the controller into STOP before updating.
        TODO: wire up to the actual PLC-stop mechanism once confirmed with
        the on-site Weidmüller expert (u-OS Control Center likely exposes
        this; no public API endpoint was found for it as of this writing)."""
        print("[Steuerung] stop() not yet wired to a real endpoint - confirm with André Riess")
        return True

    def run(self) -> bool:
        """Bring the controller back into RUN after updating. Same caveat as stop()."""
        print("[Steuerung] run() not yet wired to a real endpoint - confirm with André Riess")
        return True

    def update(self, firmware_path: str) -> dict:
        if not self._dashboard_logged_in:
            self._login_dashboard()
        result = self._upload_with_retry(
            self.UPLOAD_URL,
            firmware_path,
            field_name="file",
            session=self.session,
            verify=False,
        )
        if result["status"] == "ok":
            print("[Steuerung] Update accepted - system restart in progress...")
            self._wait_for_reboot()
            print("[Steuerung] Update successful - device back online.")
        return result

    def _wait_for_reboot(self, down_timeout=60, up_timeout=300, poll_interval=5):
        """After an accepted update, the device restarts. Wait for it to go
        down (confirms a restart actually started) then come back up before
        reporting success - don't just trust the upload HTTP response, since
        the real failure mode we care about is the device never coming back.
        """
        # Invalidate cached tokens/session - they won't survive a reboot.
        self._admin_token = None
        self._dashboard_logged_in = False

        went_down = False
        down_deadline = time.time() + down_timeout
        while time.time() < down_deadline:
            try:
                requests.get(f"https://{self.HOST}/", verify=False, timeout=3)
                time.sleep(poll_interval)
            except requests.exceptions.RequestException:
                went_down = True
                break
        if not went_down:
            print("[Steuerung] WARNING: device never appeared to go down - "
                  "continuing to check for it coming back anyway.")

        up_deadline = time.time() + up_timeout
        while time.time() < up_deadline:
            try:
                resp = requests.get(f"https://{self.HOST}/", verify=False, timeout=5)
                if resp.status_code in (200, 403, 302, 303):  # any real HTTP response = device is up
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(poll_interval)

        raise RuntimeError(
            f"Device did not come back online within {up_timeout}s after update - "
            f"halting, do not assume success"
        )

    def _get_admin_token(self) -> str:
        resp = requests.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials", "scope": " ".join(self.ADMIN_SCOPES)},
            auth=(self.CLIENT_ID, self.CLIENT_SECRET),
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def get_status(self) -> str:
        """Real device status via the documented Admin API (OAuth2 client_credentials),
        falling back to a plain reachability check if the token/API call fails."""
        try:
            if self._admin_token is None:
                self._admin_token = self._get_admin_token()
            headers = {"Authorization": f"Bearer {self._admin_token}"}
            resp = requests.get(f"{self.ADMIN_API_BASE}/system/info", headers=headers, verify=False, timeout=10)
            if resp.status_code == 200:
                info = resp.json()
                fw = info.get("firmware", {})
                return f"reachable - {fw.get('name')} {fw.get('version')}"
            return f"reachable (Admin API HTTP {resp.status_code})"
        except requests.exceptions.RequestException as e:
            return f"unreachable ({e})"


if __name__ == "__main__":
    # quick manual smoke test - run this file directly to sanity-check both drivers
    import sys

    switch = WeidmuellerSwitchDriver()
    print("Switch status:", switch.get_status())

    steuerung = WeidmuellerSteuerungDriver()
    print("Steuerung status:", steuerung.get_status())

    if len(sys.argv) > 1:
        # e.g. python3 weidmueller.py path/to/firmware.swu steuerung
        firmware_path = sys.argv[1]
        target = sys.argv[2] if len(sys.argv) > 2 else "switch"
        driver = steuerung if target == "steuerung" else switch
        print(f"Updating {target} with {firmware_path} ...")
        print(driver.update(firmware_path))
