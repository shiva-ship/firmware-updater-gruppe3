import { X } from "lucide-react";

import type { DeviceStatus, EntryNode, FirmwarePackage } from "../api/types";
import { CONNECTION } from "../lib/labels";
import { availableFirmware } from "./DeviceDetails";
import { StatusDot, cx } from "./ui";

export interface SelectionRow {
  dbId: string;
  filename: string;
  entry: EntryNode;
  status: DeviceStatus | undefined;
}

interface SelectionTableProps {
  rows: SelectionRow[];
  showFile: boolean;
  packages: FirmwarePackage[];
  focusedKey: string | null;
  onFocus: (dbId: string, entry: EntryNode) => void;
  onRemove: (dbId: string, id: string) => void;
}

const th = "border-b border-line px-3 py-2 text-left text-[11px] font-semibold text-muted";
const td = "border-b border-line/70 px-3 py-2";

export function SelectionTable({ rows, showFile, packages, focusedKey, onFocus, onRemove }: SelectionTableProps) {
  if (rows.length === 0) return <p className="py-12 text-center text-[13px] text-muted">Noch nichts ausgewählt</p>;
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th className={th}>Gerät</th>
            {showFile && <th className={th}>Datei</th>}
            <th className={th}>Seriennummer</th>
            <th className={th}>Firmware</th>
            <th className={th}>Status</th>
            <th className={th} />
          </tr>
        </thead>
        <tbody>
          {rows.map(({ dbId, filename, entry: e, status: s }) => {
            const conn = s ? CONNECTION[s.connection] : CONNECTION.not_checked;
            const fw = availableFirmware(e, packages);
            const key = `${dbId}:${e.id}`;
            return (
              <tr key={key} onClick={() => onFocus(dbId, e)} className={cx("cursor-pointer", focusedKey === key ? "bg-ads-blue-light" : "hover:bg-surface")}>
                <td className={cx(td, "font-medium")}>{e.title}</td>
                {showFile && <td className={cx(td, "max-w-[160px] truncate text-xs text-muted")}>{filename}</td>}
                <td className={cx(td, "font-mono text-xs", e.serial_status !== "ok" && "text-red-700")}>{e.serial_number ?? "fehlt"}</td>
                <td className={cx(td, "font-mono text-xs")}>
                  {s?.installed_version ?? "–"} → {fw?.released ? fw.text : "–"}
                </td>
                <td className={td}>
                  <StatusDot tone={conn.tone}>{conn.label}</StatusDot>
                </td>
                <td className={cx(td, "w-8")}>
                  <button
                    type="button"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onRemove(dbId, e.id);
                    }}
                    className="rounded p-0.5 text-muted hover:text-red-700"
                    aria-label={`${e.title} entfernen`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
