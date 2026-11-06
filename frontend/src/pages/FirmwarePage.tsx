import { RefreshCw, ShieldCheck, Undo2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { FirmwarePackage, SystemInfo } from "../api/types";
import { formatBytes, formatDateTime, shortHash } from "../lib/format";
import { VENDOR_LONG } from "../lib/labels";
import { Alert, Badge, Button, Checkbox, Dialog, Panel, Spinner, StatusDot, TextField, cx } from "../components/ui";

const th = "border-b border-line bg-surface px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted";
const td = "border-b border-line/70 px-3 py-2 align-top text-[12.5px]";

const STATUS = {
  released: { label: "Freigegeben", tone: "green" },
  unreleased: { label: "Nicht freigegeben", tone: "amber" },
  hash_mismatch: { label: "Prüfsumme abweichend", tone: "red" },
} as const;

function ReleaseDialog({ pkg, onClose, onDone }: { pkg: FirmwarePackage; onClose: () => void; onDone: () => void }) {
  const [version, setVersion] = useState(pkg.version ?? pkg.filename_version ?? "");
  const [models, setModels] = useState(pkg.models.join(", "));
  const [vendorSha, setVendorSha] = useState("");
  const [notes, setNotes] = useState(pkg.notes ?? "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.releasePackage({
        name: pkg.name,
        version: version.trim(),
        models: models.split(",").map((m) => m.trim()).filter(Boolean),
        vendor_sha256: vendorSha.trim() || null,
        notes: notes.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Freigabe fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      title="Firmwarepaket freigeben"
      subtitle={pkg.name}
      onClose={onClose}
      closable={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Abbrechen
          </Button>
          <Button type="submit" form="release-form" loading={busy} disabled={!confirmed || !version.trim()} icon={<ShieldCheck className="h-4 w-4" />}>
            Freigeben
          </Button>
        </>
      }
    >
      <form id="release-form" onSubmit={submit} className="space-y-3" noValidate>
        <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-[12.5px]">
          <dt className="text-muted">Hersteller</dt>
          <dd>{VENDOR_LONG[pkg.vendor]}</dd>
          <dt className="text-muted">Größe</dt>
          <dd>{formatBytes(pkg.size_bytes)}</dd>
          <dt className="text-muted">SHA-256</dt>
          <dd className="break-all font-mono text-[11px]">{pkg.sha256}</dd>
        </dl>
        <TextField
          id="release-version"
          label="Zielversion (Firmware nach der Installation)"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          maxLength={64}
          hint={pkg.filename_version ? `Aus dem Dateinamen erkannt: ${pkg.filename_version}. Bitte mit der Herstellerfreigabe abgleichen.` : "Die Version ist im Dateinamen nicht enthalten – bitte aus der Herstellerfreigabe übernehmen."}
        />
        <TextField
          id="release-models"
          label="Kompatible Modelle (kommagetrennt, * als Platzhalter)"
          value={models}
          onChange={(e) => setModels(e.target.value)}
          placeholder="z. B. IRF3*, IRF2*"
          maxLength={500}
          hint="Leer = freigegeben für alle Modelle dieses Herstellers. Mit Angabe werden Geräte unbekannten Modells blockiert."
        />
        <TextField
          id="release-sha"
          label="SHA-256 laut Hersteller (optional)"
          value={vendorSha}
          onChange={(e) => setVendorSha(e.target.value)}
          maxLength={128}
          className="font-mono text-xs"
          hint="Wird mit der Datei verglichen. Bei Abweichung wird die Freigabe abgelehnt."
        />
        <TextField id="release-notes" label="Bemerkung (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
        {error && <Alert>{error}</Alert>}
        <label className="flex items-start gap-2 text-[12.5px]">
          <Checkbox checked={confirmed} onChange={setConfirmed} label="Freigabe bestätigen" className="mt-0.5" />
          <span>Ich bestätige, dass dieses Paket vom Hersteller stammt, für die angegebenen Modelle getestet ist und installiert werden darf.</span>
        </label>
      </form>
    </Dialog>
  );
}

export function FirmwarePage({ system }: { system: SystemInfo | null }) {
  const [packages, setPackages] = useState<FirmwarePackage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [releasing, setReleasing] = useState<FirmwarePackage | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPackages((await api.listPackages()).packages);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Firmwarepakete konnten nicht geladen werden.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function revoke(pkg: FirmwarePackage) {
    try {
      setPackages((await api.revokePackage(pkg.name)).packages);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Freigabe konnte nicht zurückgezogen werden.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      <Panel
        title="Firmware (wird auf das Gerät installiert)"
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => void load()}>
            Neu einlesen
          </Button>
        }
      >
        {!packages ? (
          <div className="flex items-center gap-2 px-4 py-6 text-muted">
            <Spinner /> Prüfsummen werden berechnet …
          </div>
        ) : packages.length === 0 ? (
          <p className="px-4 py-6 text-muted">Keine Firmwarepakete (.bin, .bff) im Ordner „Firmware“ gefunden.</p>
        ) : (
          <div className="overflow-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className={th}>Datei</th>
                  <th className={th}>Hersteller</th>
                  <th className={th}>Größe</th>
                  <th className={th}>Zielversion</th>
                  <th className={th}>Modelle</th>
                  <th className={th}>SHA-256</th>
                  <th className={th}>Freigabe</th>
                  <th className={th} />
                </tr>
              </thead>
              <tbody>
                {packages.map((p) => (
                  <tr key={p.name}>
                    <td className={cx(td, "max-w-[280px] break-all font-mono text-[11.5px]")}>{p.name}</td>
                    <td className={td}>{VENDOR_LONG[p.vendor]}</td>
                    <td className={cx(td, "whitespace-nowrap")}>{formatBytes(p.size_bytes)}</td>
                    <td className={cx(td, "font-mono")}>
                      {p.version ?? <span className="text-muted">{p.filename_version ? `${p.filename_version} (Dateiname)` : "unbekannt"}</span>}
                    </td>
                    <td className={td}>{p.status === "released" ? (p.models.length ? p.models.join(", ") : "alle") : "–"}</td>
                    <td className={cx(td, "font-mono text-[11px]")} title={p.sha256}>
                      {shortHash(p.sha256)}
                      {p.vendor_checksum_verified && <span className="block text-emerald-700">Hersteller-Prüfsumme bestätigt</span>}
                    </td>
                    <td className={td}>
                      <Badge tone={STATUS[p.status].tone}>{STATUS[p.status].label}</Badge>
                      {p.released_by && (
                        <span className="mt-0.5 block text-[11px] text-muted">
                          {p.released_by}, {formatDateTime(p.released_at)}
                        </span>
                      )}
                    </td>
                    <td className={cx(td, "whitespace-nowrap text-right")}>
                      <Button size="sm" variant={p.status === "released" ? "secondary" : "primary"} onClick={() => setReleasing(p)}>
                        {p.status === "released" ? "Ändern" : "Freigeben"}
                      </Button>
                      {p.status !== "unreleased" && (
                        <Button size="sm" variant="ghost" className="ml-1" icon={<Undo2 className="h-3.5 w-3.5" />} onClick={() => void revoke(p)}>
                          Zurückziehen
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Treiber (führen das Update aus)">
        <div className="overflow-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={th}>Gerätetyp</th>
                <th className={th}>Treiber</th>
                <th className={th}>Firmware-Format</th>
                <th className={th}>Version lesen</th>
                <th className={th}>Firmwareupdate</th>
                <th className={th}>Treiber ladbar</th>
                <th className={th}>Hinweis</th>
              </tr>
            </thead>
            <tbody>
              {(system?.drivers ?? []).map((d) => (
                <tr key={d.vendor}>
                  <td className={cx(td, "font-medium")}>{d.label}</td>
                  <td className={cx(td, "font-mono")}>{d.driver_module}{d.driver_module === "snap7" ? "" : ".py"}</td>
                  <td className={cx(td, "font-mono")}>{d.firmware_suffixes.join(", ") || "–"}</td>
                  <td className={td}>{d.supports_read ? <StatusDot tone="green">ja</StatusDot> : <StatusDot tone="neutral">nein</StatusDot>}</td>
                  <td className={td}>{d.supports_update ? <StatusDot tone="green">unterstützt</StatusDot> : <StatusDot tone="amber">fehlt</StatusDot>}</td>
                  <td className={td}>
                    {d.driver_available ? <StatusDot tone="green">ja</StatusDot> : <StatusDot tone="red">nein</StatusDot>}
                    {d.driver_error && <span className="mt-0.5 block max-w-[260px] break-words text-[11px] text-red-700">{d.driver_error}</span>}
                  </td>
                  <td className={cx(td, "max-w-[360px] text-muted")}>{d.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {releasing && (
        <ReleaseDialog
          pkg={releasing}
          onClose={() => setReleasing(null)}
          onDone={() => {
            setReleasing(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
