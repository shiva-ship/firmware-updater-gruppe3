import { Check, ChevronRight, Copy, Cpu, FolderTree, Lock, MousePointerClick, PackageCheck, Router, ShieldCheck, StickyNote, Tag } from "lucide-react";
import { useState } from "react";

import type { EntryNode } from "../api/types";
import { cx } from "./ui";

interface DeviceDetailsProps {
  entry: EntryNode | null;
  path: string[];
}

/** Geplante Freigabekette für Firmwareupdates (siehe backend/services/firmware). */
const FIRMWARE_STEPS = [
  { icon: MousePointerClick, label: "Gerät ausgewählt" },
  { icon: Cpu, label: "Treiberprüfung" },
  { icon: PackageCheck, label: "Kompatibilitätsprüfung" },
  { icon: ShieldCheck, label: "Ausdrückliche Bestätigung" },
  { icon: Lock, label: "Freigabe mit Masterpasswort" },
];

export function DeviceDetails({ entry, path }: DeviceDetailsProps) {
  const [copied, setCopied] = useState(false);

  if (!entry) {
    return (
      <div className="flex h-full min-h-[240px] flex-col items-center justify-center px-6 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
          <Router className="h-6 w-6" aria-hidden="true" />
        </span>
        <p className="mt-3 text-sm font-medium text-navy-900">Kein Gerät ausgewählt</p>
        <p className="mt-1 text-xs text-slate-500">Wählen Sie links ein Gerät, um Details anzuzeigen.</p>
      </div>
    );
  }

  async function copySerial() {
    if (!entry?.serial_number) return;
    try {
      await navigator.clipboard.writeText(entry.serial_number);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* Zwischenablage nicht verfügbar */
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="relative overflow-hidden rounded-t-xl bg-navy-900 px-5 py-5 text-white">
        <div className="circuit-pattern pointer-events-none absolute inset-0 opacity-50" aria-hidden="true" />
        <div className="relative flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-brand-cyan to-brand-teal text-navy-950 shadow-lg shadow-cyan-500/20">
            <Router className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-300">Gerät</div>
            <h3 className="truncate text-lg font-semibold tracking-tight">{entry.title}</h3>
          </div>
        </div>
      </div>

      <dl className="divide-y divide-slate-100 px-5">
        <div className="py-4">
          <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <Tag className="h-3 w-3" /> Seriennummer
          </dt>
          <dd className="mt-1.5">
            {entry.serial_number ? (
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-navy-900 px-2.5 py-1.5 font-mono text-[15px] font-semibold tracking-wider text-cyan-100">
                  {entry.serial_number}
                </span>
                <button
                  type="button"
                  onClick={copySerial}
                  className="rounded-md p-2 text-slate-400 ring-1 ring-slate-200 transition hover:text-cyan-700 hover:ring-cyan-300"
                  aria-label="Seriennummer kopieren"
                  title="Kopieren"
                >
                  {copied ? <Check className="h-4 w-4 text-teal-600" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>
            ) : (
              <span className="text-sm italic text-slate-400">Nicht hinterlegt</span>
            )}
            {entry.serial_source && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                {entry.serial_source === "notes" ? <StickyNote className="h-3 w-3" /> : <Tag className="h-3 w-3" />}
                {entry.serial_source === "notes" ? "Aus den KeePass-Notizen erkannt" : "Aus KeePass-Feld „SerialNumber“"}
              </p>
            )}
          </dd>
        </div>
        <div className="py-4">
          <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <FolderTree className="h-3 w-3" /> Gruppe
          </dt>
          <dd className="mt-1.5 flex flex-wrap items-center gap-1 text-sm text-navy-900">
            {path.length === 0 ? (
              <span className="text-slate-400">Stammgruppe</span>
            ) : (
              path.map((part, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="h-3 w-3 text-slate-300" />}
                  <span className={cx(i === path.length - 1 && "font-semibold")}>{part}</span>
                </span>
              ))
            )}
          </dd>
        </div>
        <div className="py-4">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">KeePass-UUID</dt>
          <dd className="mt-1.5 break-all font-mono text-xs text-slate-600">{entry.id}</dd>
        </div>
      </dl>

      <div className="m-5 mt-1 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-navy-800">Firmwareupdate</span>
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
            In Vorbereitung
          </span>
        </div>
        <ol className="mt-3 space-y-1.5">
          {FIRMWARE_STEPS.map(({ icon: Icon, label }, i) => (
            <li key={label} className="flex items-center gap-2 text-xs text-slate-500">
              <span
                className={cx(
                  "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold",
                  i === 0 ? "bg-teal-500 text-white" : "bg-white text-slate-400 ring-1 ring-slate-300",
                )}
              >
                {i === 0 ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <Icon className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
              {label}
            </li>
          ))}
        </ol>
        <button
          type="button"
          disabled
          className="mt-4 w-full cursor-not-allowed rounded-lg bg-slate-200 px-3 py-2 text-xs font-semibold text-slate-500"
          title="Firmwareupdates folgen in einer späteren Version"
        >
          Firmwareupdate starten (noch nicht verfügbar)
        </button>
      </div>
    </div>
  );
}
