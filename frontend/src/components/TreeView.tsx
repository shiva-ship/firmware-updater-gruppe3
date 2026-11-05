import { ChevronRight, Folder, FolderOpen, Network, Router, StickyNote } from "lucide-react";
import { memo } from "react";

import type { EntryNode, GroupNode } from "../api/types";
import { cx } from "./ui";

interface TreeContext {
  expanded: Set<string>;
  onToggle: (id: string) => void;
  forceExpanded: boolean;
  query: string;
  selectedId: string | null;
  onSelect: (entry: EntryNode) => void;
}

interface TreeViewProps extends TreeContext {
  root: GroupNode;
  rootLabel: string;
  rootSubtitle: string;
}

/** Hebt Treffer hervor, ohne HTML einzuschleusen (React escaped alle Texte). */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLocaleLowerCase("de-DE");
  if (!q) return <>{text}</>;
  const index = text.toLocaleLowerCase("de-DE").indexOf(q);
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-sm bg-cyan-200 px-0.5 text-navy-950">{text.slice(index, index + q.length)}</mark>
      {text.slice(index + q.length)}
    </>
  );
}

function CountBadge({ group, dark }: { group: GroupNode; dark?: boolean }) {
  const total = group.total_entry_count;
  return (
    <span
      title={`${group.entry_count} direkt · ${total} insgesamt`}
      className={cx(
        "ml-auto shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums",
        dark
          ? "bg-white/10 text-brand-cyan ring-1 ring-white/15"
          : total > 0
            ? "bg-navy-900/5 text-navy-700 ring-1 ring-navy-900/10"
            : "text-slate-400 ring-1 ring-slate-200",
      )}
    >
      {total}
    </span>
  );
}

/* Verbindungslinien: senkrechte Linie am <ul>, waagrechter Abzweig je <li>. */
const branch =
  "relative before:pointer-events-none before:absolute before:-left-[13px] before:top-[19px] before:w-[11px] before:border-t before:border-slate-300";

const EntryRow = memo(function EntryRow({ entry, ctx }: { entry: EntryNode; ctx: TreeContext }) {
  const selected = ctx.selectedId === entry.id;
  return (
    <li role="treeitem" aria-selected={selected} className={branch}>
      <button
        type="button"
        onClick={() => ctx.onSelect(entry)}
        className={cx(
          "group flex min-h-[38px] w-full items-center gap-2.5 rounded-md border-l-2 py-1 pl-2 pr-2 text-left transition-colors",
          "focus-visible:outline-2 focus-visible:outline-cyan-500",
          selected ? "border-brand-cyan bg-cyan-50" : "border-transparent hover:bg-slate-50",
        )}
      >
        <span
          className={cx(
            "flex h-6 w-6 shrink-0 items-center justify-center rounded",
            selected ? "bg-navy-900 text-brand-cyan" : "bg-slate-100 text-navy-700 group-hover:bg-navy-900 group-hover:text-brand-cyan",
          )}
        >
          <Router className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-navy-900">
          <Highlight text={entry.title} query={ctx.query} />
        </span>
        {entry.serial_number ? (
          <span className="flex shrink-0 items-center gap-1">
            {entry.serial_source === "notes" && (
              <StickyNote className="h-3 w-3 text-slate-400" aria-label="aus Notizen" />
            )}
            <span className="rounded bg-navy-900 px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-cyan-100">
              <Highlight text={entry.serial_number} query={ctx.query} />
            </span>
          </span>
        ) : (
          <span className="shrink-0 text-[11px] italic text-slate-400">Nicht hinterlegt</span>
        )}
      </button>
    </li>
  );
});

const GroupRow = memo(function GroupRow({ group, ctx }: { group: GroupNode; ctx: TreeContext }) {
  const hasChildren = group.groups.length > 0 || group.entries.length > 0;
  const isOpen = hasChildren && (ctx.forceExpanded || ctx.expanded.has(group.id));
  const FolderIcon = isOpen ? FolderOpen : Folder;

  return (
    <li role="treeitem" aria-expanded={hasChildren ? isOpen : undefined} className={branch}>
      <button
        type="button"
        onClick={() => hasChildren && ctx.onToggle(group.id)}
        disabled={!hasChildren}
        className={cx(
          "flex min-h-[38px] w-full items-center gap-2 rounded-md py-1 pl-1 pr-2 text-left transition-colors",
          "focus-visible:outline-2 focus-visible:outline-cyan-500",
          hasChildren ? "hover:bg-slate-50" : "cursor-default",
        )}
      >
        <ChevronRight
          className={cx(
            "h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200",
            isOpen && "rotate-90 text-cyan-600",
            !hasChildren && "invisible",
          )}
          aria-hidden="true"
        />
        <FolderIcon className={cx("h-[18px] w-[18px] shrink-0", hasChildren ? "text-cyan-600" : "text-slate-300")} aria-hidden="true" />
        <span className={cx("truncate text-[13px] font-semibold", hasChildren ? "text-navy-900" : "text-slate-400")}>{group.name}</span>
        {!hasChildren && <span className="text-[11px] italic text-slate-400">leer</span>}
        <CountBadge group={group} />
      </button>
      {isOpen && (
        <ul role="group" className="ml-[11px] border-l border-slate-300 pl-[13px] animate-fade-in">
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

export function TreeView({ root, rootLabel, rootSubtitle, ...ctx }: TreeViewProps) {
  return (
    <div>
      <div className="flex items-center gap-3 rounded-lg bg-navy-900 px-3 py-2.5 text-white">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-brand-cyan to-brand-teal text-navy-950">
          <Network className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{rootLabel}</div>
          <div className="truncate text-[11px] text-slate-400">{rootSubtitle}</div>
        </div>
        <CountBadge group={root} dark />
      </div>
      <ul role="tree" aria-label="KeePass-Gruppen" className="ml-[19px] border-l border-slate-300 pl-[13px] pt-1">
        {root.groups.map((group) => (
          <GroupRow key={group.id} group={group} ctx={ctx} />
        ))}
        {root.entries.map((entry) => (
          <EntryRow key={entry.id} entry={entry} ctx={ctx} />
        ))}
      </ul>
    </div>
  );
}
