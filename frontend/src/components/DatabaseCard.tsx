import { FileLock2, RefreshCw, X } from "lucide-react";

import type { DatabaseInfo } from "../api/types";
import { formatBytes, formatTime } from "../lib/format";
import { Badge, Button, Spinner, cx } from "./ui";

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
    <article className={cx("flex items-center gap-3 rounded border bg-white px-3 py-2", active ? "border-ads-blue ring-1 ring-ads-blue" : "border-line")}>
      <button
        type="button"
        onClick={onSelect}
        disabled={!unlocked}
        className="flex min-w-0 flex-1 items-center gap-2.5 text-left disabled:cursor-default"
        aria-label={unlocked ? `${db.filename} anzeigen` : undefined}
      >
        <FileLock2 className={cx("h-5 w-5 shrink-0", unlocked ? "text-ads-blue" : "text-slate-400")} aria-hidden="true" />
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-semibold text-ink" title={db.filename}>
            {db.filename}
          </span>
          <span className="block text-[11px] text-muted">
            {formatBytes(db.size_bytes)} · hochgeladen {formatTime(db.uploaded_at)}
          </span>
        </span>
      </button>
      {unlocked ? <Badge tone="green">Ausgelesen {formatTime(db.unlocked_at)}</Badge> : <Badge tone="amber">Nicht ausgelesen</Badge>}
      <Button size="sm" onClick={onRefresh} icon={<RefreshCw className="h-3.5 w-3.5" />}>
        Daten aktualisieren
      </Button>
      <button
        type="button"
        onClick={onClose}
        disabled={closing}
        title="Datenbank schließen und Datei löschen"
        aria-label={`${db.filename} schließen`}
        className="flex h-8 w-8 items-center justify-center rounded text-muted ring-1 ring-inset ring-line hover:bg-red-50 hover:text-red-700"
      >
        {closing ? <Spinner /> : <X className="h-4 w-4" />}
      </button>
    </article>
  );
}
