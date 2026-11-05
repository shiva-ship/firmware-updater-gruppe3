import { ChevronsDownUp, ChevronsUpDown, Cpu, FolderTree, Hash, RefreshCw, Search, StickyNote, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "../api/client";
import type { DatabaseInfo, DatabaseList, EntryNode, GroupNode, TreeResponse } from "../api/types";
import { PageTitle } from "../components/AppShell";
import { DatabaseCard } from "../components/DatabaseCard";
import { DeviceDetails } from "../components/DeviceDetails";
import { MasterPasswordModal } from "../components/MasterPasswordModal";
import { TreeView } from "../components/TreeView";
import { UploadTile } from "../components/UploadTile";
import { Alert, Button, Spinner } from "../components/ui";
import { plural } from "../lib/format";
import { collectGroupIds, filterTree } from "../lib/tree";

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg bg-white/5 px-3 py-2 ring-1 ring-white/10">
      <span className="text-brand-cyan">{icon}</span>
      <span className="font-mono text-base font-semibold tabular-nums text-white">{value.toLocaleString("de-DE")}</span>
      <span className="text-xs text-slate-400">{label}</span>
    </div>
  );
}

function buildPathIndex(root: GroupNode): Map<string, string[]> {
  const index = new Map<string, string[]>();
  const walk = (group: GroupNode, path: string[]) => {
    group.entries.forEach((e) => index.set(e.id, path));
    group.groups.forEach((g) => walk(g, [...path, g.name]));
  };
  walk(root, []);
  return index;
}

function findEntry(root: GroupNode, id: string): EntryNode | null {
  for (const e of root.entries) if (e.id === id) return e;
  for (const g of root.groups) {
    const hit = findEntry(g, id);
    if (hit) return hit;
  }
  return null;
}

export function WorkspacePage() {
  const [list, setList] = useState<DatabaseList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [modalDb, setModalDb] = useState<DatabaseInfo | null>(null);

  const [tree, setTree] = useState<TreeResponse | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<EntryNode | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setList(await api.listDatabases());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Datenbanken konnten nicht geladen werden.");
    }
  }, []);

  const loadTree = useCallback(async (id: string) => {
    setTreeLoading(true);
    try {
      const next = await api.getTree(id);
      setTree((prev) => {
        if (prev?.database.id !== id) {
          setExpanded(new Set(next.root.groups.map((g) => g.id)));
          setQuery("");
        }
        return next;
      });
      setSelected((prev) => (prev ? findEntry(next.root, prev.id) : null));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Baumstruktur konnte nicht geladen werden.");
    } finally {
      setTreeLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const data = await api.listDatabases().catch(() => null);
      if (!data) return refreshList();
      setList(data);
      const firstUnlocked = data.databases.find((d) => d.status === "unlocked");
      if (firstUnlocked) void loadTree(firstUnlocked.id);
    })();
  }, [refreshList, loadTree]);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const db = await api.uploadDatabase(file);
      await refreshList();
      setNotice(`„${db.filename}“ wurde hochgeladen. Klicken Sie auf „Aktualisieren“, um die Geräte auszulesen.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setUploading(false);
    }
  }

  async function submitMasterPassword(masterPassword: string) {
    if (!modalDb) return;
    const db = await api.refreshDatabase(modalDb.id, masterPassword); // wirft bei falschem Passwort → Modal zeigt Fehler
    setModalDb(null);
    setError(null);
    await Promise.all([refreshList(), loadTree(db.id)]);
    setNotice(`„${db.filename}“ wurde entschlüsselt und die Geräteübersicht aktualisiert.`);
  }

  async function close(db: DatabaseInfo) {
    setClosingId(db.id);
    try {
      await api.closeDatabase(db.id);
    } catch {
      /* bereits geschlossen */
    }
    if (tree?.database.id === db.id) {
      setTree(null);
      setSelected(null);
    }
    setClosingId(null);
    setNotice(null);
    await refreshList();
  }

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const searching = query.trim().length > 0;
  const filtered = useMemo(() => (tree ? filterTree(tree.root, query) : null), [tree, query]);
  const pathIndex = useMemo(() => (tree ? buildPathIndex(tree.root) : new Map<string, string[]>()), [tree]);

  const databases = list?.databases ?? [];
  const limitReached = list ? databases.length >= list.max_databases : false;

  return (
    <div className="space-y-8">
      <section className="animate-rise">
        <PageTitle
          eyebrow="Geräteverwaltung"
          title="KeePass-Datenbanken"
          description="Laden Sie eine KDBX-Datei hoch und klicken Sie auf „Aktualisieren“. Erst dann wird das Masterpasswort abgefragt und die Geräteliste ausgelesen."
        />
        {error && (
          <Alert className="mb-4">
            <span className="flex items-start justify-between gap-3">
              {error}
              <button type="button" onClick={() => setError(null)} aria-label="Meldung schließen" className="text-red-500 hover:text-red-700">
                <X className="h-4 w-4" />
              </button>
            </span>
          </Alert>
        )}
        {notice && !error && (
          <Alert tone="success" className="mb-4">
            {notice}
          </Alert>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <UploadTile
            maxBytes={list?.max_upload_bytes ?? 20 * 1024 * 1024}
            disabled={limitReached}
            uploading={uploading}
            onFile={upload}
            onError={(m) => {
              setNotice(null);
              setError(m);
            }}
          />
          {databases.map((db) => (
            <DatabaseCard
              key={db.id}
              db={db}
              active={tree?.database.id === db.id}
              closing={closingId === db.id}
              onSelect={() => void loadTree(db.id)}
              onRefresh={() => setModalDb(db)}
              onClose={() => void close(db)}
            />
          ))}
        </div>
      </section>

      {!tree && !treeLoading && databases.length > 0 && (
        <section className="flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center animate-fade-in">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-navy-900 text-brand-cyan">
            <RefreshCw className="h-6 w-6" aria-hidden="true" />
          </span>
          <p className="mt-3 font-semibold text-navy-900">Noch keine Geräteübersicht</p>
          <p className="mt-1 max-w-md text-sm text-slate-500">
            Klicken Sie bei einer Datei auf „Aktualisieren“ und geben Sie das Masterpasswort ein, um Gruppen, Geräte und
            Seriennummern anzuzeigen.
          </p>
        </section>
      )}

      {treeLoading && !tree && (
        <div className="flex items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white py-16 text-sm text-slate-500">
          <Spinner className="h-5 w-5 text-cyan-600" /> Geräteübersicht wird geladen …
        </div>
      )}

      {tree && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm animate-rise">
          <div className="relative overflow-hidden bg-navy-900 px-5 py-5 text-white sm:px-6">
            <div className="circuit-pattern pointer-events-none absolute inset-0" aria-hidden="true" />
            <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-300">Geräteübersicht</div>
                <h2 className="mt-0.5 truncate text-xl font-semibold tracking-tight">{tree.database.filename}</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                <Stat icon={<FolderTree className="h-4 w-4" />} label="Gruppen" value={tree.stats.groups} />
                <Stat icon={<Cpu className="h-4 w-4" />} label="Geräte" value={tree.stats.entries} />
                <Stat icon={<StickyNote className="h-4 w-4" />} label="S/N aus Notizen" value={tree.stats.serials_from_notes} />
                <Stat icon={<Hash className="h-4 w-4" />} label="ohne S/N" value={tree.stats.entries_without_serial} />
              </div>
            </div>
          </div>
          <div className="h-0.5 bg-gradient-to-r from-brand-cyan via-brand-teal to-transparent" />

          <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50/60 px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative block flex-1">
              <span className="sr-only">Suche nach Gerätename oder Seriennummer</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Gerätename oder Seriennummer suchen …"
                maxLength={128}
                className="w-full rounded-lg bg-white py-2 pl-10 pr-10 text-sm ring-1 ring-slate-200 transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700"
                  aria-label="Suche leeren"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </label>
            <div className="flex gap-1">
              <Button variant="ghost" disabled={searching} onClick={() => setExpanded(new Set(collectGroupIds(tree.root)))} icon={<ChevronsUpDown className="h-4 w-4" />}>
                Aufklappen
              </Button>
              <Button variant="ghost" disabled={searching} onClick={() => setExpanded(new Set())} icon={<ChevronsDownUp className="h-4 w-4" />}>
                Zuklappen
              </Button>
            </div>
          </div>

          {searching && (
            <div className="border-b border-slate-100 bg-cyan-50/60 px-5 py-2 text-xs text-navy-800" aria-live="polite">
              {filtered ? plural(filtered.total_entry_count, "Treffer", "Treffer") : "Keine Treffer"} für „{query.trim()}“
            </div>
          )}

          <div className="grid lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="max-h-[70vh] overflow-auto p-4 sm:p-5">
              {filtered ? (
                <TreeView
                  root={filtered}
                  rootLabel="ADS-TEC Security Manager"
                  rootSubtitle={`${tree.root.name} · ${tree.database.filename}`}
                  expanded={expanded}
                  onToggle={toggle}
                  forceExpanded={searching}
                  query={query}
                  selectedId={selected?.id ?? null}
                  onSelect={setSelected}
                />
              ) : (
                <p className="py-12 text-center text-sm text-slate-500">Keine Geräte gefunden, die zur Suche passen.</p>
              )}
            </div>
            <aside className="border-t border-slate-200 bg-white lg:border-l lg:border-t-0">
              <div className="lg:sticky lg:top-16">
                <DeviceDetails entry={selected} path={selected ? (pathIndex.get(selected.id) ?? []) : []} />
              </div>
            </aside>
          </div>
        </section>
      )}

      <MasterPasswordModal
        open={modalDb !== null}
        title="Datenbank aktualisieren"
        description="Geben Sie das Masterpasswort ein, um Gruppen, Geräte und Seriennummern auszulesen."
        fileName={modalDb?.filename ?? ""}
        confirmLabel="Entschlüsseln & aktualisieren"
        busyLabel="Wird entschlüsselt …"
        confirmIcon={<RefreshCw className="h-4 w-4" />}
        onSubmit={submitMasterPassword}
        onClose={() => setModalDb(null)}
      />
    </div>
  );
}
