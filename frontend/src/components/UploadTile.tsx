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
}

export function UploadTile({ maxBytes, disabled, uploading, onFile, onError }: UploadTileProps) {
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
        "flex min-h-[188px] flex-col items-center justify-center rounded-xl border-2 border-dashed px-5 py-6 text-center transition-all",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-500",
        inactive ? "cursor-not-allowed border-slate-200 bg-slate-50 opacity-70" : "cursor-pointer",
        !inactive && (dragging ? "scale-[1.01] border-cyan-500 bg-cyan-50" : "border-slate-300 bg-white hover:border-cyan-400 hover:bg-cyan-50/40"),
      )}
    >
      <span
        className={cx(
          "flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-navy-800 to-navy-600 text-brand-cyan shadow-md transition-transform",
          dragging && "scale-110",
        )}
      >
        {uploading ? <Spinner className="h-6 w-6" /> : <FilePlus2 className="h-6 w-6" aria-hidden="true" />}
      </span>
      <p className="mt-3 text-sm font-semibold text-navy-900">
        {uploading ? "Wird hochgeladen …" : dragging ? "Datei hier ablegen" : "KeePass-Datei hochladen"}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {disabled ? "Maximale Anzahl erreicht" : `.kdbx hierher ziehen oder klicken · max. ${formatBytes(maxBytes)}`}
      </p>
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
