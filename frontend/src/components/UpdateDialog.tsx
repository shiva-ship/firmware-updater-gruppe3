import { AlertOctagon, CheckCircle2, ChevronDown, ChevronRight, Download, FlaskConical, KeyRound, MinusCircle, Play, ShieldCheck, Square, XCircle } from "lucide-react";
import { Fragment, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { ApiError, api } from "../api/client";
import type { PlanCheck, PlanItem, UpdateJob, UpdatePlan } from "../api/types";
import { formatDateTime } from "../lib/format";
import { JOB_ITEM_STATE, JOB_STATE, PLAN_STATUS } from "../lib/labels";
import { Alert, Badge, Button, Checkbox, Dialog, PasswordField, ProgressBar, cx } from "./ui";

type Stage = "plan" | "authorize" | "confirm" | "job";

interface UpdateDialogProps {
  open: boolean;
  plan: UpdatePlan;
  job: UpdateJob | null;
  dbFilename: string;
  onJob: (job: UpdateJob) => void;
  onClose: () => void;
}

const th = "border-b border-line bg-surface px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-muted";
const td = "border-b border-line/70 px-2 py-1.5 align-top";

function CheckIcon({ status }: { status: PlanCheck["status"] }) {
  if (status === "ok") return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" aria-label="OK" />;
  if (status === "warn") return <AlertOctagon className="h-3.5 w-3.5 shrink-0 text-amber-600" aria-label="Hinweis" />;
  if (status === "fail") return <XCircle className="h-3.5 w-3.5 shrink-0 text-red-600" aria-label="Fehler" />;
  return <MinusCircle className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-label="Übersprungen" />;
}

function compatibility(item: PlanItem): ReactNode {
  const check = item.checks.find((c) => c.key === "compatibility");
  if (!check) return <span className="text-muted">–</span>;
  return (
    <span className="inline-flex items-center gap-1" title={check.message}>
      <CheckIcon status={check.status} />
      {check.status === "ok" ? "kompatibel" : check.status === "fail" ? "nicht bestätigt" : "Hinweis"}
    </span>
  );
}

function ModeBanner({ plan }: { plan: UpdatePlan }) {
  return plan.simulated ? (
    <Alert tone="warning">DEMO: Alles wird nur simuliert. Kein Gerät wird verändert.</Alert>
  ) : (
    <Alert tone="error">LIVE: Echte Geräte werden aktualisiert.</Alert>
  );
}

function Summary({ plan }: { plan: UpdatePlan }) {
  const tiles: [string, number, string][] = [
    ["Ausgewählt", plan.items.length, "text-ink"],
    ["Bereit", plan.counts.ready, "text-ads-blue"],
    ["Aktuell", plan.counts.up_to_date, "text-emerald-700"],
    ["Blockiert", plan.counts.blocked, "text-red-700"],
    ["Kein Treiber", plan.counts.no_driver, "text-amber-800"],
  ];
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-5">
      {tiles.map(([label, value, color]) => (
        <div key={label} className="bg-white px-3 py-2">
          <div className={cx("font-mono text-lg font-semibold tabular-nums", color)}>{value}</div>
          <div className="text-[11px] text-muted">{label}</div>
        </div>
      ))}
    </div>
  );
}

function PlanTable({ plan }: { plan: UpdatePlan }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <div className="max-h-[42vh] overflow-auto rounded border border-line">
      <table className="w-full border-collapse text-[12.5px]">
        <thead className="sticky top-0 z-10">
          <tr>
            <th className={cx(th, "w-8")}>#</th>
            <th className={th}>Gerät</th>
            <th className={th}>Seriennummer</th>
            <th className={th}>Hersteller</th>
            <th className={th}>Aktuell</th>
            <th className={th}>Ziel</th>
            <th className={th}>Kompatibilität</th>
            <th className={th}>Status</th>
            <th className={th}>Hinweis</th>
          </tr>
        </thead>
        <tbody>
          {plan.items.map((item) => {
            const expanded = open.has(item.entry_id);
            const status = PLAN_STATUS[item.status];
            return (
              <Fragment key={item.entry_id}>
                <tr className="cursor-pointer hover:bg-surface" onClick={() => toggle(item.entry_id)}>
                  <td className={cx(td, "font-mono text-muted")}>{item.position}</td>
                  <td className={td}>
                    <span className="flex items-center gap-1 font-medium">
                      {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
                      {item.title}
                    </span>
                    <span className="block pl-[18px] text-[11px] text-muted">{item.path.join(" / ") || "Stammgruppe"}</span>
                  </td>
                  <td className={cx(td, "font-mono")}>{item.serial_number ?? "–"}</td>
                  <td className={td}>{item.vendor_label}</td>
                  <td className={cx(td, "font-mono")}>{item.installed_version ?? "–"}</td>
                  <td className={cx(td, "font-mono")}>{item.target_version ?? "–"}</td>
                  <td className={td}>{compatibility(item)}</td>
                  <td className={td}>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </td>
                  <td className={cx(td, "max-w-[260px] text-[11.5px]", item.blockers.length ? "text-red-800" : "text-muted")}>
                    {item.blockers[0] ?? item.warnings[0] ?? (item.status === "ready" ? item.order_reason : "")}
                    {item.blockers.length > 1 && ` (+${item.blockers.length - 1})`}
                  </td>
                </tr>
                {expanded && (
                  <tr className="bg-surface/60">
                    <td className={td} />
                    <td className={td} colSpan={8}>
                      <ul className="grid gap-1 sm:grid-cols-2">
                        {item.checks.map((c) => (
                          <li key={c.key} className="flex items-start gap-1.5 text-[11.5px]">
                            <CheckIcon status={c.status} />
                            <span>
                              <span className="font-semibold">{c.label}:</span> {c.message}
                            </span>
                          </li>
                        ))}
                      </ul>
                      <p className="mt-2 text-[11.5px] text-muted">
                        Reihenfolge: {item.order_reason}
                        {item.package && ` · Paket: ${item.package}`}
                        {item.driver_module && ` · Treiber: ${item.driver_module}.py`}
                      </p>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function jobProgress(job: UpdateJob): number {
  const relevant = job.items.filter((i) => i.plan_status === "ready");
  if (!relevant.length) return 1;
  const done = relevant.reduce((sum, i) => sum + (i.state === "running" ? i.progress : i.state === "pending" ? 0 : 1), 0);
  return done / relevant.length;
}

function downloadReport(plan: UpdatePlan, job: UpdateJob, dbFilename: string) {
  const report = {
    report: "ADS-TEC Firmware Management – Ergebnisbericht",
    generated_at: new Date().toISOString(),
    keepass_file: dbFilename,
    mode: plan.mode,
    simulated: job.simulated,
    dry_run: job.dry_run,
    state: job.state,
    abort_reason: job.abort_reason,
    summary: job.summary,
    devices: job.items.map((i) => ({
      position: i.position,
      title: i.title,
      serial_number: i.serial_number,
      vendor: i.vendor_label,
      plan_status: i.plan_status,
      from_version: i.from_version,
      to_version: i.to_version,
      verified_version: i.verified_version,
      package: i.package,
      result: i.state,
      message: i.message,
      started_at: i.started_at,
      finished_at: i.finished_at,
      log: i.log,
    })),
  };
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `firmware-bericht-${job.dry_run ? "dryrun-" : ""}${job.id.slice(0, 8)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function JobView({ plan, job, dbFilename }: { plan: UpdatePlan; job: UpdateJob; dbFilename: string }) {
  const [openLog, setOpenLog] = useState<string | null>(null);
  const state = JOB_STATE[job.state];
  const running = job.state === "running";
  const progress = jobProgress(job);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 rounded border border-line px-3 py-2.5">
        <span className="text-[13px] font-semibold">{job.dry_run ? "Dry-Run" : job.simulated ? "Update (simuliert)" : "Firmwareupdate"}</span>
        <Badge tone={state.tone}>{state.label}</Badge>
        <span className="text-xs text-muted">gestartet {formatDateTime(job.created_at)}</span>
        {job.finished_at && <span className="text-xs text-muted">· beendet {formatDateTime(job.finished_at)}</span>}
        <div className="ml-auto flex w-full items-center gap-2 sm:w-72">
          <ProgressBar value={progress} tone={job.state === "aborted" ? "red" : job.state === "completed_with_errors" ? "amber" : running ? "blue" : "green"} label="Gesamtfortschritt" />
          <span className="w-10 text-right font-mono text-xs tabular-nums">{Math.round(progress * 100)}%</span>
        </div>
      </div>
      {job.abort_reason && (
        <Alert>
          <strong>Gestoppt:</strong> {job.abort_reason}
        </Alert>
      )}
      <div className="max-h-[46vh] overflow-auto rounded border border-line">
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className={cx(th, "w-8")}>#</th>
              <th className={th}>Gerät</th>
              <th className={th}>Seriennummer</th>
              <th className={th}>Version</th>
              <th className={th}>Status</th>
              <th className={cx(th, "w-56")}>Fortschritt</th>
              <th className={th}>Meldung</th>
            </tr>
          </thead>
          <tbody>
            {job.items.map((i) => {
              const s = JOB_ITEM_STATE[i.state];
              return (
                <Fragment key={i.entry_id}>
                  <tr className="cursor-pointer hover:bg-surface" onClick={() => setOpenLog(openLog === i.entry_id ? null : i.entry_id)}>
                    <td className={cx(td, "font-mono text-muted")}>{i.position}</td>
                    <td className={cx(td, "font-medium")}>{i.title}</td>
                    <td className={cx(td, "font-mono")}>{i.serial_number ?? "–"}</td>
                    <td className={cx(td, "font-mono whitespace-nowrap")}>
                      {i.from_version ?? "?"} → {i.verified_version ?? i.to_version ?? "?"}
                    </td>
                    <td className={td}>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </td>
                    <td className={td}>
                      {i.plan_status === "ready" ? (
                        <>
                          <ProgressBar value={i.state === "pending" ? 0 : i.state === "running" ? i.progress : 1} tone={i.state === "failed" || i.state === "aborted" ? "red" : i.state === "running" ? "blue" : "green"} label={`Fortschritt ${i.title}`} />
                          <span className="mt-0.5 block truncate text-[11px] text-muted">{i.step ?? ""}</span>
                        </>
                      ) : (
                        <span className="text-[11px] text-muted">–</span>
                      )}
                    </td>
                    <td className={cx(td, "max-w-[280px] text-[11.5px]", i.state === "failed" || i.state === "aborted" ? "text-red-800" : "text-muted")}>{i.message ?? ""}</td>
                  </tr>
                  {openLog === i.entry_id && (
                    <tr className="bg-surface/60">
                      <td className={td} />
                      <td className={td} colSpan={6}>
                        {i.log.length ? (
                          <ol className="space-y-0.5 font-mono text-[11px]">
                            {i.log.map((l, n) => (
                              <li key={n} className={l.level === "error" ? "text-red-700" : l.level === "warn" ? "text-amber-800" : "text-ink"}>
                                {new Date(l.at).toLocaleTimeString("de-DE")} {l.message}
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <span className="text-[11px] text-muted">Keine Protokolleinträge.</span>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {!running && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded border border-line bg-surface px-3 py-2 text-[12.5px]">
          <span className="font-semibold">Ergebnisbericht:</span>
          {job.dry_run ? (
            <span>{job.summary.dry_run_ok} geprüft, nichts verändert</span>
          ) : (
            <span className="text-emerald-800">{job.summary.succeeded} erfolgreich</span>
          )}
          <span className="text-red-800">{job.summary.failed} fehlgeschlagen</span>
          <span className="text-red-800">{job.summary.aborted} nicht ausgeführt</span>
          <span className="text-amber-800">{job.summary.skipped} übersprungen</span>
          <Button size="sm" variant="secondary" className="ml-auto" icon={<Download className="h-3.5 w-3.5" />} onClick={() => downloadReport(plan, job, dbFilename)}>
            Bericht speichern
          </Button>
        </div>
      )}
    </div>
  );
}

export function UpdateDialog({ open, plan, job, dbFilename, onJob, onClose }: UpdateDialogProps) {
  const [stage, setStage] = useState<Stage>(job ? "job" : "plan");
  const [password, setPassword] = useState("");
  const [authId, setAuthId] = useState<string | null>(null);
  const [authExpires, setAuthExpires] = useState<number>(0);
  const [now, setNow] = useState(Date.now());
  const [ackImpact, setAckImpact] = useState(false);
  const [ackLive, setAckLive] = useState(false);
  const [ackStopRun, setAckStopRun] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Die beim Vorbereiten gelesenen Zugangsdaten sind nur einmal verwendbar.
  const [usedStoredCredentials, setUsedStoredCredentials] = useState(false);

  const ready = useMemo(() => plan.items.filter((i) => i.status === "ready"), [plan]);
  const effects = useMemo(() => [...new Set(ready.flatMap((i) => i.effects))], [ready]);
  const running = job?.state === "running";

  useEffect(() => {
    if (stage !== "confirm") return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [stage]);

  useEffect(() => {
    if (!open) {
      setPassword("");
      setAuthId(null);
      setError(null);
    }
  }, [open]);

  const remaining = Math.max(0, Math.round((authExpires - now) / 1000));
  useEffect(() => {
    if (stage === "confirm" && authId && remaining === 0) {
      setAuthId(null);
      setStage("authorize");
      setError("Die Freigabe ist abgelaufen. Bitte geben Sie das Masterpasswort erneut ein.");
    }
  }, [stage, authId, remaining]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Vorgang fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const startDryRun = () =>
    run(async () => {
      onJob(await api.startDryRun(plan.id));
      setStage("job");
    });

  function acceptAuthorization(result: { authorization_id: string; expires_in_seconds: number }) {
    setAuthId(result.authorization_id);
    setAuthExpires(Date.now() + result.expires_in_seconds * 1000);
    setNow(Date.now());
    setAckImpact(false);
    setAckLive(false);
    setAckStopRun(false);
    setStage("confirm");
  }

  /** Freigeben: Liegen die Zugangsdaten vom Vorbereiten noch vor, ohne erneute Passworteingabe. */
  async function startRelease() {
    if (usedStoredCredentials) return setStage("authorize");
    setUsedStoredCredentials(true);
    setBusy(true);
    setError(null);
    try {
      acceptAuthorization(await api.authorizePlan(plan.id, null));
    } catch {
      setStage("authorize"); // Frist abgelaufen → Passwort abfragen
    } finally {
      setBusy(false);
    }
  }

  async function authorize(event: FormEvent) {
    event.preventDefault();
    if (!password) return setError("Bitte geben Sie das Masterpasswort ein.");
    const value = password;
    setPassword("");
    await run(async () => {
      acceptAuthorization(await api.authorizePlan(plan.id, value));
    });
  }

  const execute = () =>
    run(async () => {
      if (!authId) throw new ApiError(0, "no_auth", "Keine gültige Freigabe.");
      const started = await api.executePlan(plan.id, authId, ackStopRun);
      setAuthId(null);
      onJob(started);
      setStage("job");
    });

  const canExecute = ackImpact && (plan.simulated || ackLive) && (!plan.requires_stop_run || ackStopRun) && !!authId;

  let body: ReactNode;
  let footer: ReactNode;
  if (stage === "plan") {
    body = (
      <div className="space-y-3">
        <ModeBanner plan={plan} />
        <Summary plan={plan} />
        <PlanTable plan={plan} />
        <p className="text-[11px] text-muted">Zeile anklicken für alle Prüfungen. Die Nummer # ist die Update-Reihenfolge.</p>
      </div>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={onClose}>
          Schließen
        </Button>
        <Button variant="secondary" icon={<FlaskConical className="h-4 w-4" />} onClick={() => void startDryRun()} loading={busy} disabled={!ready.length}>
          Dry-Run ausführen
        </Button>
        <Button icon={<ShieldCheck className="h-4 w-4" />} onClick={() => void startRelease()} loading={busy && stage === "plan"} disabled={!ready.length || busy}>
          Update freigeben ({ready.length})
        </Button>
      </>
    );
  } else if (stage === "authorize") {
    body = (
      <form id="authorize-form" onSubmit={authorize} noValidate className="mx-auto max-w-md space-y-4 py-2">
        <ModeBanner plan={plan} />
        <p className="text-[13px]">
          <strong>{ready.length} Gerät(e)</strong> freigeben – Masterpasswort erneut eingeben
        </p>
        <PasswordField
          id="update-master-password"
          label="KeePass-Masterpasswort"
          autoComplete="off"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          maxLength={4096}
          icon={<KeyRound className="h-4 w-4" />}
          hint="Wird nur auf dem Server geprüft und nicht gespeichert."
        />
      </form>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={() => setStage("plan")} disabled={busy}>
          Zurück zum Plan
        </Button>
        <Button type="submit" form="authorize-form" loading={busy} icon={<KeyRound className="h-4 w-4" />}>
          Masterpasswort prüfen
        </Button>
      </>
    );
  } else if (stage === "confirm") {
    body = (
      <div className="space-y-3">
        <ModeBanner plan={plan} />
        <p className="text-[13px]">
          Bitte prüfen und bestätigen. Gültig noch{" "}
          <span className="font-mono">
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
          </span>{" "}
          min.
        </p>
        <div className="overflow-auto rounded border border-line">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr>
                <th className={th}>Reihenfolge</th>
                <th className={th}>Gerät</th>
                <th className={th}>Seriennummer</th>
                <th className={th}>Aktuelle Firmware</th>
                <th className={th}>Ziel-Firmware</th>
                <th className={th}>Paket</th>
                <th className={th}>Kompatibilität</th>
              </tr>
            </thead>
            <tbody>
              {ready.map((i, n) => (
                <tr key={i.entry_id}>
                  <td className={cx(td, "font-mono")}>{n + 1}</td>
                  <td className={cx(td, "font-medium")}>{i.title}</td>
                  <td className={cx(td, "font-mono")}>{i.serial_number}</td>
                  <td className={cx(td, "font-mono")}>{i.installed_version}</td>
                  <td className={cx(td, "font-mono font-semibold text-ads-blue")}>{i.target_version}</td>
                  <td className={cx(td, "max-w-[220px] truncate font-mono text-[11px]")}>{i.package}</td>
                  <td className={td}>{compatibility(i)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {plan.counts.no_driver + plan.counts.blocked > 0 && (
          <p className="text-xs text-muted">
            {plan.counts.no_driver + plan.counts.blocked} weitere ausgewählte Gerät(e) werden nicht aktualisiert (blockiert oder ohne Update-Treiber).
          </p>
        )}
        <ul className="list-disc space-y-0.5 pl-5 text-[12.5px]">
          {effects.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
        <div className="space-y-2 rounded border border-line bg-surface p-3 text-[12.5px]">
          <label className="flex items-start gap-2">
            <Checkbox checked={ackImpact} onChange={setAckImpact} label="Auswirkungen bestätigen" className="mt-0.5" />
            <span>Geprüft – Updates jetzt installieren.</span>
          </label>
          {!plan.simulated && (
            <label className="flex items-start gap-2">
              <Checkbox checked={ackLive} onChange={setAckLive} label="Reale Geräte bestätigen" className="mt-0.5" />
              <span>Echte Geräte starten neu und sind kurz nicht erreichbar.</span>
            </label>
          )}
          {plan.requires_stop_run && (
            <label className="flex items-start gap-2">
              <Checkbox checked={ackStopRun} onChange={setAckStopRun} label="STOP/RUN freigeben" className="mt-0.5" />
              <span>Ich gebe den getesteten STOP/RUN-Ablauf der SPS ausdrücklich frei. Die Anlage wird dabei angehalten.</span>
            </label>
          )}
        </div>
      </div>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={() => { setAuthId(null); setStage("plan"); }} disabled={busy}>
          Abbrechen
        </Button>
        <Button variant="danger" icon={<Play className="h-4 w-4" />} onClick={() => void execute()} loading={busy} disabled={!canExecute}>
          Installation starten
        </Button>
      </>
    );
  } else {
    body = job ? <JobView plan={plan} job={job} dbFilename={dbFilename} /> : null;
    footer = (
      <>
        {running && !job?.dry_run && (
          <Button
            variant="secondary"
            icon={<Square className="h-3.5 w-3.5" />}
            disabled={job?.cancel_requested}
            onClick={() => job && void run(async () => onJob(await api.cancelJob(job.id)))}
          >
            {job?.cancel_requested ? "Wird angehalten …" : "Anhalten"}
          </Button>
        )}
        {!running && job?.dry_run && (
          <Button variant="secondary" onClick={() => setStage("plan")}>
            Zurück zum Plan
          </Button>
        )}
        <Button variant={running ? "secondary" : "primary"} onClick={onClose}>
          {running ? "Ausblenden" : "Schließen"}
        </Button>
      </>
    );
  }

  return (
    <Dialog
      open={open}
      title={stage === "job" ? (job?.dry_run ? "Dry-Run – Ergebnis" : "Sammelupdate – Fortschritt") : stage === "plan" ? "Updateplan" : "Firmwareupdate freigeben"}
      subtitle={`${dbFilename} · Plan vom ${formatDateTime(plan.created_at)} · ${plan.simulated ? "DEMO (simuliert)" : "LIVE"}`}
      onClose={onClose}
      closable={!busy}
      width={stage === "authorize" ? "max-w-xl" : "max-w-6xl"}
      footer={footer}
    >
      {error && (
        <Alert className="mb-3" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {body}
    </Dialog>
  );
}
