import { describe, expect, it } from "vitest";

import type { EntryNode, GroupNode } from "../api/types";
import { groupState, idsOf, pruneSelection, selectAll, selectVendor, toggleEntry, toggleGroup, vendorCounts } from "./selection";
import { filterTree, sortTree } from "./tree";

function entry(id: string, device_type: EntryNode["device_type"], serial: string | null = `SN-${id}`): EntryNode {
  return {
    id,
    title: `Gerät ${id}`,
    serial_number: serial,
    serial_source: serial ? "notes" : null,
    serial_status: serial ? "ok" : "missing",
    device_type,
    host: `10.0.0.${id.length}`,
    mac_address: null,
    model: null,
    update_order: null,
    has_notes: false,
  };
}

function group(id: string, entries: EntryNode[], groups: GroupNode[] = []): GroupNode {
  const total = entries.length + groups.reduce((n, g) => n + g.total_entry_count, 0);
  return { id, name: id, entries, groups, entry_count: entries.length, total_entry_count: total };
}

// Wurzel → Standort A (Firewall, Balluff) und Standort B (Balluff, SPS, unbekannt)
const siteA = group("Standort A", [entry("fw1", "adstec", "AX20339256"), entry("b1", "balluff")]);
const siteB = group("Standort B", [entry("b2", "balluff"), entry("plc", "siemens"), entry("x", null, null)]);
const root = group("root", [], [siteA, siteB]);

describe("Geräteauswahl", () => {
  it("wählt ein einzelnes Gerät und hebt es wieder ab", () => {
    let s = toggleEntry("fw1", new Set());
    expect([...s]).toEqual(["fw1"]);
    s = toggleEntry("fw1", s);
    expect(s.size).toBe(0);
  });

  it("wählt mehrere Geräte unterschiedlicher Hersteller", () => {
    const s = toggleEntry("plc", toggleEntry("fw1", new Set()));
    expect(s).toEqual(new Set(["fw1", "plc"]));
    expect(groupState(siteA, s)).toBe("some");
  });

  it("wählt alle Geräte eines Herstellers über alle Standorte", () => {
    const s = selectVendor(root, "balluff", new Set(["fw1"]));
    expect(s).toEqual(new Set(["fw1", "b1", "b2"]));
    expect(selectVendor(root, "unknown", new Set())).toEqual(new Set(["x"]));
  });

  it("wählt alle Geräte eines Standorts und hebt sie wieder ab", () => {
    let s = toggleGroup(siteB, new Set(["fw1"]));
    expect(groupState(siteB, s)).toBe("all");
    expect(s.has("fw1")).toBe(true);
    s = toggleGroup(siteB, s);
    expect(groupState(siteB, s)).toBe("none");
    expect(s).toEqual(new Set(["fw1"]));
  });

  it("teilweise gewählte Gruppe wird beim Klick vollständig gewählt", () => {
    const s = toggleGroup(siteB, new Set(["b2"]));
    expect(groupState(siteB, s)).toBe("all");
  });

  it("wählt sämtliche Geräte und hebt die Auswahl vollständig auf", () => {
    const all = selectAll(root);
    expect(all.size).toBe(5);
    expect(groupState(root, all)).toBe("all");
    expect(groupState(root, new Set())).toBe("none");
  });

  it("entfernt nicht mehr vorhandene Geräte aus der Auswahl", () => {
    expect(pruneSelection(siteA, new Set(["fw1", "gone"]))).toEqual(new Set(["fw1"]));
  });

  it("zählt Geräte je Hersteller", () => {
    expect(vendorCounts(root)).toEqual({ adstec: 1, balluff: 2, siemens: 1, unknown: 1 });
  });
});

describe("Suche", () => {
  it("findet nach Seriennummer", () => {
    expect(idsOf(filterTree(root, "ax2033")!)).toEqual(["fw1"]);
  });
  it("findet nach Hersteller", () => {
    expect(idsOf(filterTree(root, "balluff")!)).toEqual(["b1", "b2"]);
    expect(idsOf(filterTree(root, "siemens")!)).toEqual(["plc"]);
  });
  it("findet nach Gerätename und filtert nach Hersteller", () => {
    expect(idsOf(filterTree(root, "Gerät b")!)).toEqual(["b1", "b2"]);
    expect(idsOf(filterTree(root, "", "adstec")!)).toEqual(["fw1"]);
    expect(filterTree(root, "gibt-es-nicht")).toBeNull();
  });
  it("Gruppenauswahl im Suchmodus betrifft nur Treffer", () => {
    const visible = filterTree(root, "balluff")!;
    const s = toggleGroup(visible, new Set());
    expect(s).toEqual(new Set(["b1", "b2"]));
  });
});

describe("Sortierung", () => {
  const flat = (g: GroupNode): string[] => [...g.entries.map((e) => e.serial_number ?? "-"), ...g.groups.flatMap(flat)];
  const site = group("S", [entry("a", "balluff", "BL10"), entry("b", "balluff", null), entry("c", "balluff", "AX2"), entry("d", "balluff", "BL9")]);

  it("sortiert nach Seriennummer aufsteigend, natürliche Zahlenfolge, fehlende am Ende", () => {
    expect(flat(sortTree(site, { key: "serial", dir: "asc" }))).toEqual(["AX2", "BL9", "BL10", "-"]);
  });
  it("sortiert absteigend, fehlende bleiben am Ende", () => {
    expect(flat(sortTree(site, { key: "serial", dir: "desc" }))).toEqual(["BL10", "BL9", "AX2", "-"]);
  });
  it("behält die Gruppenstruktur", () => {
    const sorted = sortTree(root, { key: "serial", dir: "asc" });
    expect(sorted.groups.map((g) => g.name)).toEqual(["Standort A", "Standort B"]);
  });
});
