# Lightweight image for the orchestrator. Runs on the IRF itself (Docker/edge-computing capability).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY driver_base.py weidmueller.py orchestrator.py ./

# Firmware files are provided locally on the IRF (per challenge spec, not our job to fetch them) -
# mount them in at runtime instead of baking them into the image.
VOLUME ["/firmware"]

# Job file (device/action/order) also mounted in at runtime so it can change without a rebuild.
VOLUME ["/jobs"]

ENTRYPOINT ["python3", "orchestrator.py"]
CMD ["/jobs/job.json"]
