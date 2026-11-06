import type { DeviceType, EntryNode, GroupNode } from "../api/types";
import { VENDOR_LABELS } from "./labels";

export function normalize(text: string): string {
  return text.toLocaleLowerCase("de-DE").normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

function vendorText(vendor: DeviceType | null): string {
  return vendor ? `${vendor} ${VENDOR_LABELS[vendor]}` : "unbekannt";
}

/** Treffer bei Gerätename, Seriennummer, Hersteller oder IP-Adresse. */
export function entryMatches(entry: EntryNode, query: string): boolean {
  const q = normalize(query.trim());
  if (!q) return true;
  return [entry.title, entry.serial_number ?? "", vendorText(entry.device_type), entry.host ?? "", entry.model ?? ""].some((text) =>
    normalize(text).includes(q),
  );
}

/**
 * Filtert den Baum nach Suchbegriff und optional Hersteller. Gruppen bleiben erhalten, wenn sie
 * selbst oder eine Untergruppe Treffer enthalten. Zählwerte beziehen sich dann auf die Treffer.
 */
export function filterTree(group: GroupNode, query: string, vendor: DeviceType | "unknown" | "" = ""): GroupNode | null {
  if (!query.trim() && !vendor) return group;

  const walk = (node: GroupNode): GroupNode | null => {
    const entries = node.entries.filter(
      (e) => entryMatches(e, query) && (!vendor || (vendor === "unknown" ? e.device_type === null : e.device_type === vendor)),
    );
    const groups = node.groups.map(walk).filter((g): g is GroupNode => g !== null);
    if (entries.length === 0 && groups.length === 0) return null;
    return {
      ...node,
      entries,
      groups,
      entry_count: entries.length,
      total_entry_count: entries.length + groups.reduce((sum, g) => sum + g.total_entry_count, 0),
    };
  };
  return walk(group);
}

export function collectGroupIds(group: GroupNode, acc: string[] = []): string[] {
  acc.push(group.id);
  group.groups.forEach((g) => collectGroupIds(g, acc));
  return acc;
}

export function buildPathIndex(root: GroupNode): Map<string, string[]> {
  const index = new Map<string, string[]>();
  const walk = (group: GroupNode, path: string[]) => {
    group.entries.forEach((e) => index.set(e.id, path));
    group.groups.forEach((g) => walk(g, [...path, g.name]));
  };
  walk(root, []);
  return index;
}

export function buildEntryIndex(root: GroupNode): Map<string, EntryNode> {
  const index = new Map<string, EntryNode>();
  const walk = (group: GroupNode) => {
    group.entries.forEach((e) => index.set(e.id, e));
    group.groups.forEach(walk);
  };
  walk(root);
  return index;
}

export type SortKey = "name" | "serial";
export interface TreeSort {
  key: SortKey;
  dir: "asc" | "desc";
}

const collator = new Intl.Collator("de-DE", { numeric: true, sensitivity: "base" });

/**
 * Sortiert die Geräte innerhalb jeder Gruppe; die Gruppenstruktur bleibt erhalten.
 * Geräte ohne Seriennummer stehen bei Sortierung nach Seriennummer immer am Ende.
 */
export function sortTree(group: GroupNode, sort: TreeSort): GroupNode {
  const sign = sort.dir === "asc" ? 1 : -1;
  const compare = (a: EntryNode, b: EntryNode) => {
    if (sort.key === "serial") {
      if (!a.serial_number || !b.serial_number) {
        if (a.serial_number === b.serial_number) return collator.compare(a.title, b.title);
        return a.serial_number ? -1 : 1;
      }
      return sign * collator.compare(a.serial_number, b.serial_number) || collator.compare(a.title, b.title);
    }
    return sign * collator.compare(a.title, b.title);
  };
  return {
    ...group,
    entries: [...group.entries].sort(compare),
    groups: group.groups.map((g) => sortTree(g, sort)),
  };
}
