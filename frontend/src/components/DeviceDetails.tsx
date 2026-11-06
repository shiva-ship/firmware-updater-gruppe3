import { ChevronDown, ChevronRight, MousePointerClick, PackageCheck } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ApiError, api } from "../api/client";
import type { DeviceStatus, DriverInfo, EntryNode, FirmwarePackage } from "../api/types";
import { formatDateTime } from "../lib/format";
import { CONNECTION, VENDOR_LONG } from "../lib/labels";
import { Badge, Button, Spinner, StatusDot } from "./ui";

interface DeviceDetailsProps {
  dbId: string;
  entry: EntryNode | null;
  path: string[];
  status: DeviceStatus | undefined;
  packages: FirmwarePackage[];
  drivers: DriverInfo[];
  onPrepareSingle: (entry: EntryNode) => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5">
      <dt className="w-32 shrink-0 text-xs text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 break-words text-[13px]">{children}</dd>
    </div>
  );
}

const none = <span className="text-muted">–</span>;

export function availableFirmware(entry: EntryNode, packages: FirmwarePackage[]): { text: string; released: boolean } | null {
  if (!entry.device_type) return null;
  const own = packages.filter((p) => p.vendor === entry.device_type);
  const released = own.find((p) => p.status === "released");
  if (released) return { text: released.version ?? "?", released: true };
  if (own.length > 0) return { text: "nicht freigegeben", released: false };
  return null;
}

export function DeviceDetails({ dbId, entry, path, status, packages, drivers, onPrepareSingle }: DeviceDetailsProps) {
  const [more, setMore] = useState(false);
  const [notes, setNotes] = useState<string | null>(null);
  const [notesState, setNotesState] = useState<"idle" | "loading" | "error">("idle");

  if (!entry) {
    return (
      <div className="flex min-h-[220px] flex-col items-center justify-center gap-2 text-muted">
        <MousePointerClick className="h-7 w-7 text-slate-300" aria-hidden="true" />
        <span className="text-[13px]">Gerät im Baum anklicken</span>
      </div>
    );
  }

  const driver = drivers.find((d) => d.vendor === entry.device_type);
  const available = availableFirmware(entry, packages);
  const connection = status ? CONNECTION[status.connection] : CONNECTION.not_checked;

  async function loadNotes() {
    if (!entry) return;
    setNotesState("loading");
    try {
      setNotes((await api.getNotes(dbId, entry.id)).notes ?? "");
      setNotesState("idle");
    } catch (err) {
      setNotesState(err instanceof ApiError ? "error" : "error");
    }
  }

  return (
    <div className="p-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold">{entry.title}</h3>
          <p className="truncate text-xs text-muted">{path.join(" / ") || "–"}</p>
        </div>
        {status?.simulated && <Badge tone="amber">simuliert</Badge>}
      </div>

      <dl className="mt-3 divide-y divide-line/70">
        <Row label="Hersteller">{entry.device_type ? VENDOR_LONG[entry.device_type] : "unbekannt"}</Row>
        <Row label="Seriennummer">
          {entry.serial_number ? <span className="font-mono">{entry.serial_number}</span> : <Badge tone="amber">fehlt</Badge>}
          {entry.serial_status === "duplicate" && <Badge tone="red" className="ml-2">doppelt</Badge>}
        </Row>
        <Row label="IP-Adresse">{entry.host ? <span className="font-mono">{entry.host}</span> : none}</Row>
        <Row label="Firmware">
          <span className="font-mono">{status?.installed_version ?? "–"}</span>
          <span className="mx-1.5 text-muted">→</span>
          <span className={available?.released ? "font-mono font-semibold text-ads-blue" : "text-muted"}>{available?.text ?? "kein Paket"}</span>
        </Row>
        <Row label="Status">
          <StatusDot tone={connection.tone}>{connection.label}</StatusDot>
        </Row>
        <Row label="Update möglich">
          {driver?.supports_update ? <StatusDot tone="green">ja</StatusDot> : <StatusDot tone="amber">nein, kein Treiber</StatusDot>}
        </Row>
      </dl>

      <button type="button" onClick={() => setMore((m) => !m)} className="mt-2 flex items-center gap-1 text-xs font-semibold text-ads-blue">
        {more ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />} Mehr Details
      </button>
      {more && (
        <dl className="mt-1 divide-y divide-line/70">
          <Row label="Modell">{status?.model ?? entry.model ?? none}</Row>
          <Row label="MAC-Adresse">{status?.mac_address ?? entry.mac_address ?? none}</Row>
          <Row label="Letzte Prüfung">{status ? formatDateTime(status.checked_at) : none}</Row>
          <Row label="Treiber">{driver ? <span className="font-mono">{driver.driver_module}</span> : none}</Row>
          <Row label="KeePass-UUID">
            <span className="font-mono text-xs">{entry.id}</span>
          </Row>
          <Row label="Notes">
            {!entry.has_notes ? (
              none
            ) : notes === null ? (
              <button type="button" onClick={() => void loadNotes()} className="text-xs font-semibold text-ads-blue">
                {notesState === "loading" ? <Spinner className="h-3 w-3" /> : notesState === "error" ? "Fehler – erneut laden" : "anzeigen"}
              </button>
            ) : (
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-surface p-2 font-mono text-xs">{notes}</pre>
            )}
          </Row>
        </dl>
      )}

      <Button size="sm" variant="secondary" className="mt-4" icon={<PackageCheck className="h-3.5 w-3.5" />} onClick={() => onPrepareSingle(entry)}>
        Nur dieses Gerät updaten
      </Button>
    </div>
  );
}
