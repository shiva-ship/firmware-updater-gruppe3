import { CheckCircle2, CircleDashed, FileLock2, RefreshCw, X } from "lucide-react";

import type { DatabaseInfo } from "../api/types";
import { formatBytes, formatTime } from "../lib/format";
import { Button, Spinner, cx } from "./ui";

interface DatabaseCardProps {
  db: DatabaseInfo;
  active: boolean;
  closing: boolean;
  onSelect: () => void;
  onRefresh: () => void;
  onClose: () => void;
}

export function DatabaseCard({ db, active, closing, onSelect, onRefresh, onClose }: DatabaseCardProps) {
  const unlocked = db.status === "unlocked";
  return (
    <article
      className={cx(
        "group relative flex flex-col overflow-hidden rounded-xl border bg-white shadow-sm transition-all animate-rise",
        active ? "border-cyan-400 shadow-lg shadow-cyan-500/10 ring-1 ring-cyan-400" : "border-slate-200 hover:border-slate-300 hover:shadow-md",
      )}
    >
      <div className={cx("h-1", unlocked ? "bg-gradient-to-r from-brand-cyan to-brand-teal" : "bg-slate-200")} />
      <button
        type="button"
        onClick={onSelect}
        disabled={!unlocked}
        className="flex flex-1 items-start gap-3 p-4 text-left disabled:cursor-default"
        aria-label={unlocked ? `${db.filename} anzeigen` : undefined}
      >
        <span
          className={cx(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg",
            unlocked ? "bg-navy-900 text-brand-cyan" : "bg-slate-100 text-slate-500",
          )}
        >
          <FileLock2 className="h-5 w-5" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold text-navy-900" title={db.filename}>
            {db.filename}
          </span>
          <span className="mt-0.5 block text-xs text-slate-500">
            {formatBytes(db.size_bytes)} · hochgeladen {formatTime(db.uploaded_at)}
          </span>
          <span
            className={cx(
              "mt-2.5 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
              unlocked ? "bg-teal-50 text-teal-700 ring-1 ring-teal-200" : "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
            )}
          >
            {unlocked ? <CheckCircle2 className="h-3 w-3" /> : <CircleDashed className="h-3 w-3" />}
            {unlocked ? `Aktualisiert ${formatTime(db.unlocked_at)}` : "Hochgeladen · nicht ausgelesen"}
          </span>
        </span>
      </button>
      <div className="flex items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-3">
        <Button onClick={onRefresh} icon={<RefreshCw className="h-4 w-4" />} className="flex-1 py-2">
          Aktualisieren
        </Button>
        <button
          type="button"
          onClick={onClose}
          disabled={closing}
          title="Datenbank schließen und Datei löschen"
          aria-label={`${db.filename} schließen`}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 ring-1 ring-slate-200 transition hover:bg-red-50 hover:text-red-600 hover:ring-red-200"
        >
          {closing ? <Spinner /> : <X className="h-4 w-4" />}
        </button>
      </div>
    </article>
  );
}
