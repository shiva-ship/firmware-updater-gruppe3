import type { BadgeTone } from "../components/ui";
import type { ConnectionState, DeviceType, JobItemState, JobState, PlanStatus } from "../api/types";

export const VENDOR_LABELS: Record<DeviceType, string> = {
  balluff: "Balluff",
  adstec: "ads-tec",
  siemens: "Siemens",
};

export const VENDOR_LONG: Record<DeviceType, string> = {
  balluff: "Balluff IO-Link-Master",
  adstec: "ads-tec Firewall / Router",
  siemens: "Siemens SIMATIC SPS",
};

export function vendorLabel(vendor: DeviceType | null): string {
  return vendor ? VENDOR_LABELS[vendor] : "Unbekannt";
}

export const CONNECTION: Record<ConnectionState, { label: string; tone: BadgeTone }> = {
  online: { label: "Erreichbar", tone: "green" },
  offline: { label: "Nicht erreichbar", tone: "red" },
  error: { label: "Fehler", tone: "red" },
  not_checked: { label: "Nicht geprüft", tone: "neutral" },
};

export const PLAN_STATUS: Record<PlanStatus, { label: string; tone: BadgeTone }> = {
  ready: { label: "Bereit", tone: "blue" },
  up_to_date: { label: "Aktuell", tone: "green" },
  blocked: { label: "Blockiert", tone: "red" },
  no_driver: { label: "Kein Treiber", tone: "amber" },
};

export const JOB_ITEM_STATE: Record<JobItemState, { label: string; tone: BadgeTone }> = {
  pending: { label: "Wartend", tone: "neutral" },
  running: { label: "Läuft", tone: "cyan" },
  succeeded: { label: "Erfolgreich", tone: "green" },
  dry_run_ok: { label: "Dry-Run OK", tone: "green" },
  failed: { label: "Fehlgeschlagen", tone: "red" },
  skipped: { label: "Übersprungen", tone: "amber" },
  aborted: { label: "Nicht ausgeführt", tone: "red" },
};

export const JOB_STATE: Record<JobState, { label: string; tone: BadgeTone }> = {
  running: { label: "Läuft", tone: "cyan" },
  completed: { label: "Abgeschlossen", tone: "green" },
  completed_with_errors: { label: "Abgeschlossen mit Fehlern", tone: "amber" },
  aborted: { label: "Gestoppt", tone: "red" },
  cancelled: { label: "Abgebrochen", tone: "amber" },
};
