import type { DeviceType, EntryNode, GroupNode } from "../api/types";

/**
 * Geräteauswahl als reine Funktionen auf einem Set von KeePass-UUIDs.
 * Die Auswahl selbst löst niemals ein Update aus.
 */

export type SelectionState = "none" | "some" | "all";

export function entriesOf(group: GroupNode, acc: EntryNode[] = []): EntryNode[] {
  acc.push(...group.entries);
  group.groups.forEach((g) => entriesOf(g, acc));
  return acc;
}

export function idsOf(group: GroupNode): string[] {
  return entriesOf(group).map((e) => e.id);
}

export function groupState(group: GroupNode, selected: ReadonlySet<string>): SelectionState {
  const ids = idsOf(group);
  if (ids.length === 0) return "none";
  const count = ids.reduce((n, id) => n + (selected.has(id) ? 1 : 0), 0);
  return count === 0 ? "none" : count === ids.length ? "all" : "some";
}

/** Standort/Gruppe: Sind alle (sichtbaren) Geräte gewählt, wird die Gruppe abgewählt, sonst vollständig gewählt. */
export function toggleGroup(group: GroupNode, selected: ReadonlySet<string>): Set<string> {
  const next = new Set(selected);
  const ids = idsOf(group);
  if (groupState(group, selected) === "all") ids.forEach((id) => next.delete(id));
  else ids.forEach((id) => next.add(id));
  return next;
}

export function toggleEntry(id: string, selected: ReadonlySet<string>): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** Alle Geräte eines Herstellers zur bestehenden Auswahl hinzufügen. */
export function selectVendor(root: GroupNode, vendor: DeviceType | "unknown", selected: ReadonlySet<string>): Set<string> {
  const next = new Set(selected);
  entriesOf(root)
    .filter((e) => (vendor === "unknown" ? e.device_type === null : e.device_type === vendor))
    .forEach((e) => next.add(e.id));
  return next;
}

export function selectAll(root: GroupNode, selected: ReadonlySet<string> = new Set()): Set<string> {
  const next = new Set(selected);
  idsOf(root).forEach((id) => next.add(id));
  return next;
}

/** Entfernt IDs, die im (neu geladenen) Baum nicht mehr existieren. */
export function pruneSelection(root: GroupNode, selected: ReadonlySet<string>): Set<string> {
  const valid = new Set(idsOf(root));
  return new Set([...selected].filter((id) => valid.has(id)));
}

export function vendorCounts(root: GroupNode): Record<DeviceType | "unknown", number> {
  const counts: Record<DeviceType | "unknown", number> = { adstec: 0, balluff: 0, siemens: 0, unknown: 0 };
  entriesOf(root).forEach((e) => counts[e.device_type ?? "unknown"]++);
  return counts;
}
