import { ArrowDown, ArrowUp, ArrowUpDown, ChevronsDownUp, ChevronsUpDown, FileLock2, KeyRound, PackageCheck, Plus, RefreshCw, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { DatabaseInfo, DatabaseList, DeviceStatus, DeviceType, EntryNode, FirmwarePackage, GroupNode, SystemInfo, TreeResponse, UpdateJob, UpdatePlan } from "../api/types";
import { DeviceDetails } from "../components/DeviceDetails";
import { MasterPasswordModal } from "../components/MasterPasswordModal";
import { SelectionTable, type SelectionRow } from "../components/SelectionTable";
import { SERIAL_COL, TreeView } from "../components/TreeView";
import { UpdateDialog } from "../components/UpdateDialog";
import { UploadTile } from "../components/UploadTile";
import { Alert, Button, Dialog, ProgressBar, Spinner, cx } from "../components/ui";
import { JOB_STATE, VENDOR_LABELS } from "../lib/labels";
import { entriesOf, pruneSelection, selectAll, selectVendor, toggleEntry, toggleGroup, vendorCounts } from "../lib/selection";
import { buildEntryIndex, buildPathIndex, collectGroupIds, filterTree, sortTree, type SortKey, type TreeSort } from "../lib/tree";

interface WorkspaceProps {
  system: SystemInfo | null;
  active: boolean;
  onReadyChange: (ready: boolean) => void;
}

type PerDb<T> = Record<string, T>;
const EMPTY: ReadonlySet<string> = new Set<string>();

function setIn<T>(prev: PerDb<T>, dbId: string, value: T): PerDb<T> {
  return { ...prev, [dbId]: value };
}
function without<T>(prev: PerDb<T>, dbId: string): PerDb<T> {
  const next = { ...prev };
  delete next[dbId];
  return next;
}
function toggled(set: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

export function WorkspacePage({ system, active, onReadyChange }: WorkspaceProps) {
  const [list, setList] = useState<DatabaseList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [refreshDb, setRefreshDb] = useState<DatabaseInfo | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [booting, setBooting] = useState(true);

  // Je KeePass-Datei: ein Baum, eine Auswahl, ein Inventar
  const [trees, setTrees] = useState<PerDb<TreeResponse>>({});
  const [selected, setSelected] = useState<PerDb<Set<string>>>({});
  const [expanded, setExpanded] = useState<PerDb<Set<string>>>({});
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [inventory, setInventory] = useState<PerDb<Record<string, DeviceStatus>>>({});
  const [focused, setFocused] = useState<{ dbId: string; entry: EntryNode } | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<TreeSort>({ key: "name", dir: "asc" });
  const [tab, setTab] = useState<"details" | "selection">("details");
  const [packages, setPackages] = useState<FirmwarePackage[]>([]);

  const [plan, setPlan] = useState<UpdatePlan | null>(null);
  const [job, setJob] = useState<UpdateJob | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [preparing, setPreparing] = useState<string | null>(null);
  const [livePrepare, setLivePrepare] = useState<{ dbId: string; ids: string[] } | null>(null);
  const treesRef = useRef(trees);
  treesRef.current = trees;

  const hasTrees = Object.keys(trees).length > 0;
  useEffect(() => onReadyChange(hasTrees), [hasTrees, onReadyChange]);

  const refreshList = useCallback(async () => {
    try {
      const data = await api.listDatabases();
      setList(data);
      return data;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Dateien konnten nicht geladen werden.");
      return null;
    }
  }, []);

  const loadInventory = useCallback(async (dbId: string) => {
    try {
      const inv = await api.getInventory(dbId);
      setInventory((p) => setIn(p, dbId, inv.devices));
    } catch {
      /* optional */
    }
  }, []);

  const loadTree = useCallback(
    async (dbId: string) => {
      try {
        const next = await api.getTree(dbId);
        const isNew = !treesRef.current[dbId];
        setTrees((p) => setIn(p, dbId, next));
        if (isNew) setExpanded((p) => setIn(p, dbId, new Set(collectGroupIds(next.root))));
        setSelected((p) => setIn(p, dbId, pruneSelection(next.root, p[dbId] ?? EMPTY)));
        setFocused((prev) => {
          if (!prev || prev.dbId !== dbId) return prev;
          const entry = buildEntryIndex(next.root).get(prev.entry.id);
          return entry ? { dbId, entry } : null;
        });
        await loadInventory(dbId);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Geräte konnten nicht geladen werden.");
      }
    },
    [loadInventory],
  );

  const loadPackages = useCallback(() => {
    api.listPackages().then((d) => setPackages(d.packages)).catch(() => setPackages([]));
  }, []);

  useEffect(() => {
    void (async () => {
      const data = await refreshList();
      await Promise.all((data?.databases ?? []).filter((d) => d.status === "unlocked").map((d) => loadTree(d.id)));
      setBooting(false);
    })();
  }, [refreshList, loadTree]);

  useEffect(() => {
    if (active) loadPackages();
  }, [active, loadPackages]);

  useEffect(() => {
    if (!job || job.state !== "running") return;
    const id = window.setInterval(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.state !== "running" && plan) void loadInventory(plan.db_id);
      } catch {
        /* nächster Versuch */
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [job, plan, loadInventory]);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const db = await api.uploadDatabase(file);
      await refreshList();
      setUploadOpen(false);
      setRefreshDb(db); // direkt weiter zum Entsperren
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setUploading(false);
    }
  }

  async function submitRefresh(masterPassword: string) {
    if (!refreshDb) return;
    const db = await api.refreshDatabase(refreshDb.id, masterPassword);
    setRefreshDb(null);
    setError(null);
    await Promise.all([refreshList(), loadTree(db.id)]);
  }

  async function close(db: DatabaseInfo) {
    try {
      await api.closeDatabase(db.id);
    } catch {
      /* bereits geschlossen */
    }
    setTrees((p) => without(p, db.id));
    setSelected((p) => without(p, db.id));
    setExpanded((p) => without(p, db.id));
    setInventory((p) => without(p, db.id));
    setFocused((f) => (f?.dbId === db.id ? null : f));
    if (plan?.db_id === db.id) setPlan(null);
    await refreshList();
  }

  async function prepare(dbId: string, ids: string[], masterPassword: string | null) {
    setPlan(await api.prepareUpdates(dbId, ids, masterPassword));
    if (job?.state !== "running") setJob(null);
    setDialogOpen(true);
    await loadInventory(dbId);
  }

  async function startPrepare(dbId: string, ids: string[]) {
    if (!ids.length) return;
    if (job?.state === "running") return setError("Es läuft bereits ein Update.");
    setPreparing(dbId);
    setError(null);
    try {
      // Login-Daten aus "Daten aktualisieren" werden 30 Minuten weiterverwendet.
      await prepare(dbId, ids, null);
    } catch (err) {
      // Frist abgelaufen → Masterpasswort erneut abfragen
      if (err instanceof ApiError && err.code === "master_password_required") return setLivePrepare({ dbId, ids });
      setError(err instanceof ApiError ? err.message : "Updates konnten nicht vorbereitet werden.");
    } finally {
      setPreparing(null);
    }
  }

  const searching = query.trim().length > 0;
  const databases = list?.databases ?? [];
  const openDbs = databases.filter((d) => trees[d.id]);
  const lockedDbs = databases.filter((d) => !trees[d.id]);
  const filenameOf = (dbId: string) => databases.find((d) => d.id === dbId)?.filename ?? trees[dbId]?.database.filename ?? "";

  const filtered = useMemo(() => {
    const out: PerDb<GroupNode | null> = {};
    for (const [id, t] of Object.entries(trees)) {
      const hit = filterTree(t.root, query);
      out[id] = hit ? sortTree(hit, sort) : null;
    }
    return out;
  }, [trees, query, sort]);

  const sortBy = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  const SortIcon = ({ k }: { k: SortKey }) =>
    sort.key !== k ? <ArrowUpDown className="h-3 w-3 opacity-40" /> : sort.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;

  const totalDevices = Object.values(trees).reduce((n, t) => n + t.stats.entries, 0);
  const selectedCount = Object.values(selected).reduce((n, s) => n + s.size, 0);
  const selectedByDb = openDbs.map((db) => ({ db, ids: [...(selected[db.id] ?? EMPTY)] })).filter((x) => x.ids.length > 0);

  const counts = useMemo(() => {
    const total: Record<DeviceType | "unknown", number> = { adstec: 0, balluff: 0, siemens: 0, unknown: 0 };
    Object.values(trees).forEach((t) => {
      const c = vendorCounts(t.root);
      (Object.keys(total) as (keyof typeof total)[]).forEach((k) => (total[k] += c[k]));
    });
    return total;
  }, [trees]);

  const rows: SelectionRow[] = useMemo(
    () =>
      Object.entries(trees).flatMap(([dbId, t]) =>
        entriesOf(t.root)
          .filter((e) => selected[dbId]?.has(e.id))
          .map((entry) => ({ dbId, filename: t.database.filename, entry, status: inventory[dbId]?.[entry.id] })),
      ),
    [trees, selected, inventory],
  );

  const forAll = (fn: (root: GroupNode, s: ReadonlySet<string>) => Set<string>) =>
    setSelected((p) => {
      const next: PerDb<Set<string>> = { ...p };
      for (const [id, t] of Object.entries(trees)) next[id] = fn(t.root, p[id] ?? EMPTY);
      return next;
    });

  const focusEntry = useCallback((dbId: string, entry: EntryNode) => {
    setFocused({ dbId, entry });
    setTab("details");
  }, []);

  const focusedPath = focused && trees[focused.dbId] ? (buildPathIndex(trees[focused.dbId].root).get(focused.entry.id) ?? []) : [];
  const focusedKey = focused ? `${focused.dbId}:${focused.entry.id}` : null;
  const jobRunning = job?.state === "running";
  const canAddFile = list ? databases.length < list.max_databases : true;

  const modals = (
    <>
      <MasterPasswordModal
        open={refreshDb !== null}
        title="Datei entsperren"
        description="Masterpasswort der KeePass-Datei"
        fileName={refreshDb?.filename ?? ""}
        confirmLabel="Daten aktualisieren"
        busyLabel="Wird entschlüsselt …"
        confirmIcon={<RefreshCw className="h-4 w-4" />}
        onSubmit={submitRefresh}
        onClose={() => setRefreshDb(null)}
      />
      <MasterPasswordModal
        open={livePrepare !== null}
        title="Geräte prüfen"
        description="Geräte werden nur gelesen, nicht verändert."
        fileName={livePrepare ? filenameOf(livePrepare.dbId) : ""}
        confirmLabel="Prüfen"
        busyLabel="Geräte werden abgefragt …"
        busyHint="Das kann je Gerät einige Sekunden dauern."
        confirmIcon={<PackageCheck className="h-4 w-4" />}
        onSubmit={async (pw) => {
          if (livePrepare) await prepare(livePrepare.dbId, livePrepare.ids, pw);
          setLivePrepare(null);
        }}
        onClose={() => setLivePrepare(null)}
      />
      <Dialog open={uploadOpen} title="Weitere KeePass-Datei" onClose={() => setUploadOpen(false)} closable={!uploading}>
        <UploadTile
          maxBytes={list?.max_upload_bytes ?? 20 * 1024 * 1024}
          disabled={!canAddFile}
          uploading={uploading}
          onFile={upload}
          onError={setError}
          large
        />
      </Dialog>
      {plan && dialogOpen && (
        <UpdateDialog
          open
          plan={plan}
          job={job && job.plan_id === plan.id ? job : null}
          dbFilename={filenameOf(plan.db_id)}
          onJob={setJob}
          onClose={() => {
            setDialogOpen(false);
            loadPackages();
          }}
        />
      )}
    </>
  );

  const errorBox = error && (
    <Alert className="mb-4" onClose={() => setError(null)}>
      {error}
    </Alert>
  );

  const lockedRow = (db: DatabaseInfo) => (
    <div key={db.id} className="flex items-center gap-3 rounded border border-line bg-white px-3 py-2.5">
      <FileLock2 className="h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{db.filename}</span>
      <Button size="sm" icon={<KeyRound className="h-3.5 w-3.5" />} onClick={() => setRefreshDb(db)}>
        Daten aktualisieren
      </Button>
      <button type="button" onClick={() => void close(db)} className="rounded p-1 text-muted hover:text-red-700" aria-label={`${db.filename} entfernen`}>
        <X className="h-4 w-4" />
      </button>
    </div>
  );

  // ---------- Noch keine entsperrte Datei ----------
  if (!hasTrees) {
    return (
      <div className="mx-auto max-w-xl pt-10">
        {errorBox}
        {booting ? (
          <div className="flex items-center justify-center gap-2 py-16 text-muted">
            <Spinner /> Wird geladen …
          </div>
        ) : (
          <div className="rounded border border-line bg-white p-8">
            <h1 className="text-center text-lg font-semibold">{lockedDbs.length ? "Datei entsperren" : "KeePass-Datei hochladen"}</h1>
            <div className="mt-6 space-y-2">
              {lockedDbs.map(lockedRow)}
              {lockedDbs.length === 0 ? (
                <UploadTile maxBytes={list?.max_upload_bytes ?? 20 * 1024 * 1024} disabled={false} uploading={uploading} onFile={upload} onError={setError} large />
              ) : (
                canAddFile && (
                  <button type="button" onClick={() => setUploadOpen(true)} className="mx-auto flex items-center gap-1 pt-2 text-xs font-semibold text-ads-blue">
                    <Plus className="h-3.5 w-3.5" /> weitere Datei hochladen
                  </button>
                )
              )}
            </div>
          </div>
        )}
        {modals}
      </div>
    );
  }

  // ---------- Geräte ----------
  return (
    <div>
      {errorBox}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(400px,500px)_minmax(0,1fr)]">
        {/* Bäume (einer je Datei) */}
        <section className="rounded border border-line bg-white lg:sticky lg:top-[108px]">
          <div className="space-y-2 border-b border-line p-3">
            <div className="flex gap-2">
              <label className="relative block flex-1">
                <span className="sr-only">Suchen</span>
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Suchen: Name, Seriennummer, Hersteller"
                  maxLength={128}
                  className="h-9 w-full rounded bg-surface pl-8 pr-3 text-[13px] placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-ads-cyan"
                />
              </label>
              <Button variant="secondary" icon={<Plus className="h-4 w-4" />} onClick={() => setUploadOpen(true)} disabled={!canAddFile} title="Weitere KeePass-Datei hinzufügen">
                Datei
              </Button>
            </div>
            <div className="flex items-center gap-1.5">
              <Button size="sm" variant="secondary" onClick={() => forAll((root, s) => selectAll(root, s))}>
                Alle
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setSelected({})} disabled={selectedCount === 0}>
                Keine
              </Button>
              <select
                value=""
                onChange={(e) => {
                  const v = e.target.value as DeviceType;
                  if (v) forAll((root, s) => selectVendor(root, v, s));
                }}
                aria-label="Alle Geräte eines Herstellers auswählen"
                className="h-8 rounded bg-white px-2 text-xs font-semibold text-ads-blue ring-1 ring-inset ring-line focus:outline-none focus:ring-2 focus:ring-ads-cyan"
              >
                <option value="">Hersteller …</option>
                {(Object.keys(VENDOR_LABELS) as DeviceType[])
                  .filter((v) => counts[v])
                  .map((v) => (
                    <option key={v} value={v}>
                      {VENDOR_LABELS[v]} ({counts[v]})
                    </option>
                  ))}
              </select>
              <span className="ml-auto flex">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={searching}
                  title="Alle aufklappen"
                  aria-label="Alle aufklappen"
                  onClick={() => {
                    setCollapsed(new Set());
                    setExpanded(Object.fromEntries(Object.entries(trees).map(([id, t]) => [id, new Set(collectGroupIds(t.root))])));
                  }}
                  icon={<ChevronsUpDown className="h-4 w-4" />}
                />
                <Button size="sm" variant="ghost" disabled={searching} title="Alle zuklappen" aria-label="Alle zuklappen" onClick={() => setExpanded({})} icon={<ChevronsDownUp className="h-4 w-4" />} />
              </span>
            </div>
          </div>

          <div className="flex h-8 items-center gap-2 border-b border-line bg-surface pl-[58px] pr-[18px] text-[11px] font-semibold text-muted">
            <button type="button" onClick={() => sortBy("name")} className={cx("flex min-w-0 flex-1 items-center gap-1 hover:text-ink", sort.key === "name" && "text-ads-blue")}>
              Gerät <SortIcon k="name" />
            </button>
            <button type="button" onClick={() => sortBy("serial")} className={cx(SERIAL_COL, "flex items-center gap-1 hover:text-ink", sort.key === "serial" && "text-ads-blue")}>
              Seriennummer <SortIcon k="serial" />
            </button>
          </div>
          <div className="max-h-[calc(100vh-282px)] min-h-[300px] divide-y divide-line overflow-auto">
            {openDbs.map((db) => {
              const root = filtered[db.id];
              if (!root) {
                return (
                  <p key={db.id} className="px-4 py-3 text-xs text-muted">
                    {db.filename}: nichts gefunden
                  </p>
                );
              }
              return (
                <TreeView
                  key={db.id}
                  root={root}
                  rootLabel={db.filename}
                  collapsed={collapsed.has(db.id) && !searching}
                  onToggleCollapsed={() => setCollapsed((p) => toggled(p, db.id))}
                  rootActions={
                    <>
                      <button type="button" onClick={() => setRefreshDb(db)} className="rounded p-1 text-muted hover:bg-white hover:text-ads-blue" title="Daten aktualisieren" aria-label={`${db.filename} aktualisieren`}>
                        <RefreshCw className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" onClick={() => void close(db)} className="rounded p-1 text-muted hover:bg-white hover:text-red-700" title="Datei schließen" aria-label={`${db.filename} schließen`}>
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </>
                  }
                  expanded={(expanded[db.id] as Set<string> | undefined) ?? new Set()}
                  onToggleExpand={(gid) => setExpanded((p) => setIn(p, db.id, toggled(p[db.id] ?? EMPTY, gid)))}
                  forceExpanded={searching}
                  query={query}
                  focusedId={focused?.dbId === db.id ? focused.entry.id : null}
                  onFocus={(entry) => focusEntry(db.id, entry)}
                  selected={selected[db.id] ?? EMPTY}
                  onToggleEntry={(id) => setSelected((p) => setIn(p, db.id, toggleEntry(id, p[db.id] ?? EMPTY)))}
                  onToggleGroup={(group) => setSelected((p) => setIn(p, db.id, toggleGroup(group, p[db.id] ?? EMPTY)))}
                  inventory={inventory[db.id] ?? {}}
                />
              );
            })}
            {lockedDbs.length > 0 && <div className="space-y-2 bg-surface p-2">{lockedDbs.map(lockedRow)}</div>}
          </div>
        </section>

        {/* Rechte Seite */}
        <div className="min-w-0 space-y-4">
          <section className="rounded border border-line bg-white px-4 py-3">
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-[13px] text-muted">
                <span className="font-mono text-xl font-semibold text-ads-blue">{selectedCount}</span> von {totalDevices} ausgewählt
              </span>
              {job && (
                <button type="button" onClick={() => setDialogOpen(true)} disabled={!plan} className="flex items-center gap-2 text-xs text-muted hover:text-ink">
                  <span className={cx("font-semibold", jobRunning ? "text-ads-blue" : "text-ink")}>
                    {job.dry_run ? "Dry-Run" : "Update"}: {JOB_STATE[job.state].label}
                  </span>
                  {jobRunning && (
                    <span className="w-24">
                      <ProgressBar value={job.items.filter((i) => !["pending", "running"].includes(i.state)).length / Math.max(1, job.items.length)} label="Fortschritt" />
                    </span>
                  )}
                </button>
              )}
              {selectedByDb.length <= 1 && (
                <Button
                  icon={<PackageCheck className="h-4 w-4" />}
                  onClick={() => selectedByDb[0] && void startPrepare(selectedByDb[0].db.id, selectedByDb[0].ids)}
                  loading={preparing !== null}
                  disabled={selectedCount === 0 || jobRunning}
                  className="ml-auto h-10 px-5"
                >
                  Firmwareupdates vorbereiten
                </Button>
              )}
            </div>
            {selectedByDb.length > 1 && (
              <div className="mt-3 space-y-1.5 border-t border-line pt-3">
                <p className="text-xs text-muted">Auswahl aus {selectedByDb.length} Dateien – pro Datei vorbereiten (eigenes Masterpasswort):</p>
                {selectedByDb.map(({ db, ids }) => (
                  <div key={db.id} className="flex items-center gap-3">
                    <FileLock2 className="h-4 w-4 text-ads-blue" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{db.filename}</span>
                    <span className="text-xs text-muted">{ids.length} Geräte</span>
                    <Button size="sm" icon={<PackageCheck className="h-3.5 w-3.5" />} loading={preparing === db.id} disabled={jobRunning || preparing !== null} onClick={() => void startPrepare(db.id, ids)}>
                      Vorbereiten
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded border border-line bg-white">
            <div className="flex border-b border-line" role="tablist">
              {(
                [
                  ["details", "Gerät"],
                  ["selection", `Auswahl (${selectedCount})`],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                  className={cx("h-10 border-b-2 px-4 text-[13px] font-semibold", tab === id ? "border-ads-blue text-ads-blue" : "border-transparent text-muted hover:text-ink")}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "details" ? (
              <DeviceDetails
                key={focusedKey ?? "none"}
                dbId={focused?.dbId ?? ""}
                entry={focused?.entry ?? null}
                path={openDbs.length > 1 && focused ? [filenameOf(focused.dbId), ...focusedPath] : focusedPath}
                status={focused ? inventory[focused.dbId]?.[focused.entry.id] : undefined}
                packages={packages}
                drivers={system?.drivers ?? []}
                onPrepareSingle={(entry) => focused && void startPrepare(focused.dbId, [entry.id])}
              />
            ) : (
              <SelectionTable
                rows={rows}
                showFile={openDbs.length > 1}
                packages={packages}
                focusedKey={focusedKey}
                onFocus={focusEntry}
                onRemove={(dbId, id) => setSelected((p) => setIn(p, dbId, toggleEntry(id, p[dbId] ?? EMPTY)))}
              />
            )}
          </section>
        </div>
      </div>
      {modals}
    </div>
  );
}
