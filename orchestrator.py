"""
Orchestrator: reads a job file describing a sequence of steps, dispatches
each step to the matching device driver, and halts immediately (reporting
device + state) on any failure instead of continuing blindly.

Usage:
    python3 orchestrator.py /jobs/job.json
"""

import json
import sys

from weidmueller import WeidmuellerSwitchDriver, WeidmuellerSteuerungDriver

# Registry: job file "device" key -> driver instance
DRIVERS = {
    "weidmueller-switch": WeidmuellerSwitchDriver(),
    "weidmueller-steuerung": WeidmuellerSteuerungDriver(),
    # add more vendors here as drivers are built, e.g.:
    # "balluff-io-link-master": BalluffIOLinkMasterDriver(),
}


def run_job(job_path: str) -> bool:
    with open(job_path) as f:
        job = json.load(f)

    steps = job.get("steps", [])
    print(f"Loaded job with {len(steps)} step(s) from {job_path}")

    for i, step in enumerate(steps, start=1):
        device_key = step["device"]
        action = step["action"]

        driver = DRIVERS.get(device_key)
        if driver is None:
            print(f"[FAILED] Step {i}: unknown device '{device_key}' - no driver registered")
            return False

        print(f"[{i}/{len(steps)}] {device_key}: {action} ...")

        if action == "stop":
            ok = driver.stop()
            if not ok:
                _report_failure(i, device_key, action, driver)
                return False

        elif action == "run":
            ok = driver.run()
            if not ok:
                _report_failure(i, device_key, action, driver)
                return False

        elif action == "update":
            firmware_path = step["firmware"]
            result = driver.update(firmware_path)
            print(f"    -> {result}")

            if result["status"] == "ok":
                pass  # success, continue
            elif result["status"] == "already_up_to_date":
                print(f"    -> already up to date, continuing")
            else:
                # rejected / network_failed / failed - stop here, don't continue blindly
                print(f"[FAILED] Step {i}: update of '{device_key}' did not succeed ({result['status']})")
                print(f"    Device status now: {driver.get_status()}")
                return False

        else:
            print(f"[FAILED] Step {i}: unknown action '{action}'")
            return False

    print("Job completed successfully - all steps done.")
    return True


def _report_failure(step_num, device_key, action, driver):
    print(f"[FAILED] Step {step_num}: '{action}' on '{device_key}' did not succeed")
    print(f"    Device status now: {driver.get_status()}")


if __name__ == "__main__":
    job_file = sys.argv[1] if len(sys.argv) > 1 else "/jobs/job.json"
    success = run_job(job_file)
    sys.exit(0 if success else 1)
