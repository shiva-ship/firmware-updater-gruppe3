import { ChevronRight, Cpu, FileLock2, Folder, FolderOpen, Network, Router, Server } from "lucide-react";
import { memo, type ReactNode } from "react";

import type { DeviceStatus, DeviceType, EntryNode, GroupNode } from "../api/types";
import { vendorLabel } from "../lib/labels";
import { groupState } from "../lib/selection";
import { Checkbox, cx } from "./ui";

interface TreeContext {
  expanded: Set<string>;
  onToggleExpand: (id: string) => void;
  forceExpanded: boolean;
  query: string;
  focusedId: string | null;
  onFocus: (entry: EntryNode) => void;
  selected: ReadonlySet<string>;
  onToggleEntry: (id: string) => void;
  onToggleGroup: (group: GroupNode) => void;
  inventory: Record<string, DeviceStatus>;
}

interface TreeViewProps extends TreeContext {
  root: GroupNode;
  rootLabel: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  rootActions?: ReactNode;
}

/** Breite der Seriennummern-Spalte – auch für die Kopfzeile über dem Baum verwendet. */
export const SERIAL_COL = "w-[128px] shrink-0 text-left";

const DEVICE_ICON: Record<DeviceType, typeof Router> = { adstec: Router, balluff: Network, siemens: Cpu };

function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLocaleLowerCase("de-DE");
  const index = q ? text.toLocaleLowerCase("de-DE").indexOf(q) : -1;
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="bg-ads-cyan-light text-ink">{text.slice(index, index + q.length)}</mark>
      {text.slice(index + q.length)}
    </>
  );
}

function dotColor(status: DeviceStatus | undefined) {
  if (!status || status.connection === "not_checked") return "bg-slate-300";
  return status.connection === "online" ? "bg-emerald-600" : "bg-red-600";
}

/*
 * Baumlinien: Jede Unterebene hat eine senkrechte Linie (border-l am <ul>),
 * jeder Knoten einen waagrechten Abzweig (::before). Beim letzten Knoten
 * verdeckt ::after die senkrechte Linie unterhalb des Abzweigs.
 */
const branch = cx(
  "relative",
  "before:pointer-events-none before:absolute before:-left-3 before:top-4 before:w-3 before:border-t before:border-slate-300",
  "last:after:pointer-events-none last:after:absolute last:after:-left-[13px] last:after:top-4 last:after:bottom-0 last:after:w-[2px] last:after:bg-white",
);
const childList = "ml-[19px] border-l border-slate-300 pl-3";

/** Seriennummer als gut lesbares Kennzeichen in fester Spalte (siehe SERIAL_COL). */
function SerialTag({ entry, query, focused }: { entry: EntryNode; query: string; focused: boolean }) {
  if (!entry.serial_number) {
    return (
      <span className={cx(SERIAL_COL, "text-[11px] font-semibold", focused ? "text-white" : "text-amber-700")} title="Keine Seriennummer – kein Update möglich">
        fehlt
      </span>
    );
  }
  const duplicate = entry.serial_status === "duplicate";
  return (
    <span className={SERIAL_COL} title={duplicate ? "Seriennummer mehrfach vergeben – kein Update möglich" : `Seriennummer ${entry.serial_number}`}>
      <span
        className={cx(
          "inline-block max-w-full truncate rounded-sm px-1.5 py-px font-mono text-[12px] font-medium tracking-wide ring-1 ring-inset",
          focused ? "bg-white text-ads-blue ring-white" : duplicate ? "bg-red-50 text-red-800 ring-red-300" : "bg-ads-blue-light text-ads-blue ring-ads-blue/20",
        )}
      >
        <Highlight text={entry.serial_number} query={query} />
      </span>
    </span>
  );
}

const EntryRow = memo(function EntryRow({ entry, ctx }: { entry: EntryNode; ctx: TreeContext }) {
  const focused = ctx.focusedId === entry.id;
  const Icon = entry.device_type ? DEVICE_ICON[entry.device_type] : Server;
  return (
    <li role="treeitem" aria-selected={ctx.selected.has(entry.id)} className={branch}>
      <div
        onClick={() => ctx.onFocus(entry)}
        title={`${entry.title} · ${vendorLabel(entry.device_type)}`}
        className={cx("flex h-8 cursor-pointer items-center gap-2 rounded px-1.5", focused ? "bg-ads-blue text-white" : "hover:bg-ads-blue-light")}
      >
        <Checkbox checked={ctx.selected.has(entry.id)} onChange={() => ctx.onToggleEntry(entry.id)} label={`${entry.title} auswählen`} />
        <Icon className={cx("h-4 w-4 shrink-0", focused ? "text-white" : "text-ads-blue")} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-[13px]">
          <Highlight text={entry.title} query={ctx.query} />
        </span>
        <span className={cx("h-2 w-2 shrink-0 rounded-full", dotColor(ctx.inventory[entry.id]))} aria-hidden="true" />
        <SerialTag entry={entry} query={ctx.query} focused={focused} />
      </div>
    </li>
  );
});

const GroupRow = memo(function GroupRow({ group, ctx }: { group: GroupNode; ctx: TreeContext }) {
  const hasChildren = group.groups.length > 0 || group.entries.length > 0;
  const isOpen = hasChildren && (ctx.forceExpanded || ctx.expanded.has(group.id));
  const FolderIcon = isOpen ? FolderOpen : Folder;
  const state = groupState(group, ctx.selected);

  return (
    <li role="treeitem" aria-expanded={hasChildren ? isOpen : undefined} className={branch}>
      <div className="flex h-8 cursor-pointer items-center gap-1.5 rounded px-1 hover:bg-ads-blue-light" onClick={() => hasChildren && ctx.onToggleExpand(group.id)}>
        <ChevronRight className={cx("h-4 w-4 shrink-0 text-muted", isOpen && "rotate-90", !hasChildren && "invisible")} aria-hidden="true" />
        <Checkbox
          checked={state === "all"}
          indeterminate={state === "some"}
          disabled={group.total_entry_count === 0}
          onChange={() => ctx.onToggleGroup(group)}
          label={`Alle Geräte in ${group.name} auswählen`}
        />
        <FolderIcon className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{group.name}</span>
        <span className="rounded-sm bg-surface px-1.5 font-mono text-[11px] tabular-nums text-muted">{group.total_entry_count}</span>
      </div>
      {isOpen && (
        <ul role="group" className={childList}>
          {group.groups.map((child) => (
            <GroupRow key={child.id} group={child} ctx={ctx} />
          ))}
          {group.entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} ctx={ctx} />
          ))}
        </ul>
      )}
    </li>
  );
});

export function TreeView({ root, rootLabel, collapsed = false, onToggleCollapsed, rootActions, ...ctx }: TreeViewProps) {
  const state = groupState(root, ctx.selected);
  return (
    <div className="p-2">
      <div className="group flex h-8 cursor-pointer items-center gap-1.5 rounded px-1 hover:bg-ads-blue-light" onClick={onToggleCollapsed}>
        <ChevronRight className={cx("h-4 w-4 shrink-0 text-muted", !collapsed && "rotate-90")} aria-hidden="true" />
        <Checkbox
          checked={state === "all"}
          indeterminate={state === "some"}
          disabled={root.total_entry_count === 0}
          onChange={() => ctx.onToggleGroup(root)}
          label="Alle Geräte auswählen"
        />
        <FileLock2 className="h-4 w-4 shrink-0 text-ads-blue" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{rootLabel}</span>
        {rootActions && (
          <span className="flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
            {rootActions}
          </span>
        )}
        <span className="rounded-sm bg-surface px-1.5 font-mono text-[11px] tabular-nums text-muted">{root.total_entry_count}</span>
      </div>
      {!collapsed && (
      <ul role="tree" aria-label="Geräte" aria-multiselectable="true" className={childList}>
        {root.groups.map((group) => (
          <GroupRow key={group.id} group={group} ctx={ctx} />
        ))}
        {root.entries.map((entry) => (
          <EntryRow key={entry.id} entry={entry} ctx={ctx} />
        ))}
      </ul>
      )}
    </div>
  );
}
