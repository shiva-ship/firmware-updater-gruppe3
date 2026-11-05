import type { GroupNode } from "../api/types";

export function normalize(text: string): string {
  return text.toLocaleLowerCase("de-DE").normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

/**
 * Filtert den Baum nach Gerätename oder Seriennummer. Gruppen bleiben erhalten,
 * wenn sie selbst oder eine Untergruppe Treffer enthalten. Zählwerte beziehen sich
 * im Suchmodus auf die Treffer.
 */
export function filterTree(group: GroupNode, query: string): GroupNode | null {
  const q = normalize(query.trim());
  if (!q) return group;

  const walk = (node: GroupNode): GroupNode | null => {
    const entries = node.entries.filter(
      (e) => normalize(e.title).includes(q) || (e.serial_number !== null && normalize(e.serial_number).includes(q)),
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
