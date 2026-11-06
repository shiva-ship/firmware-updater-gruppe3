import { FilePlus2 } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { formatBytes } from "../lib/format";
import { Spinner, cx } from "./ui";

const KDBX_SIGNATURE = [0x03, 0xd9, 0xa2, 0x9a, 0x67, 0xfb, 0x4b, 0xb5];

/** Vorabprüfung im Browser; die maßgebliche Prüfung erfolgt serverseitig. */
async function looksLikeKdbx(file: File): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  return KDBX_SIGNATURE.every((byte, i) => head[i] === byte);
}

interface UploadTileProps {
  maxBytes: number;
  disabled: boolean;
  uploading: boolean;
  onFile: (file: File) => void;
  onError: (message: string) => void;
  large?: boolean;
}

export function UploadTile({ maxBytes, disabled, uploading, onFile, onError, large }: UploadTileProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function accept(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".kdbx")) return onError("Bitte wählen Sie eine KeePass-Datei mit der Endung .kdbx.");
    if (file.size > maxBytes) return onError(`Die Datei ist zu groß. Maximal erlaubt: ${formatBytes(maxBytes)}.`);
    if (!(await looksLikeKdbx(file))) return onError("Die Datei ist keine gültige KeePass-Datenbank (KDBX).");
    onFile(file);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (disabled || uploading) return;
    if (event.dataTransfer.files.length > 1) return onError("Bitte jeweils nur eine Datei hochladen.");
    void accept(event.dataTransfer.files[0]);
  }

  const inactive = disabled || uploading;
  return (
    <div
      role="button"
      tabIndex={inactive ? -1 : 0}
      aria-disabled={inactive}
      onClick={() => !inactive && inputRef.current?.click()}
      onKeyDown={(e) => !inactive && (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!inactive) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      aria-label="KeePass-Datei auswählen oder hierher ziehen"
      className={cx(
        "flex rounded border-2 border-dashed",
        large ? "min-h-[180px] flex-col items-center justify-center gap-3 p-6 text-center" : "min-h-[52px] items-center gap-3 px-3 py-2 text-left",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ads-cyan",
        inactive ? "cursor-not-allowed border-line bg-surface opacity-70" : "cursor-pointer",
        !inactive && (dragging ? "border-ads-cyan bg-ads-cyan-light" : "border-slate-400 bg-white hover:border-ads-blue hover:bg-ads-blue-light"),
      )}
    >
      {uploading ? <Spinner className="h-5 w-5 text-ads-blue" /> : <FilePlus2 className={cx("shrink-0 text-ads-blue", large ? "h-10 w-10" : "h-5 w-5")} aria-hidden="true" />}
      <span className="min-w-0">
        <span className="block text-[13px] font-semibold text-ink">
          {uploading ? "Wird hochgeladen …" : dragging ? "Hier ablegen" : "Datei wählen oder hierher ziehen"}
        </span>
        <span className="block text-[11px] text-muted">
          {disabled ? "Maximale Anzahl erreicht" : `.kdbx · max. ${formatBytes(maxBytes)}`}
        </span>
      </span>
      <input
        ref={inputRef}
        type="file"
        accept=".kdbx"
        className="hidden"
        onChange={(e) => {
          void accept(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
