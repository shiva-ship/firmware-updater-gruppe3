export interface User {
  id: number;
  username: string;
  role: string;
}

export interface SessionInfo {
  authenticated: boolean;
  user: User | null;
  csrf_token: string | null;
  expires_at: string | null;
}

export type DatabaseStatus = "locked" | "unlocked";

export interface DatabaseInfo {
  id: string;
  filename: string;
  size_bytes: number;
  status: DatabaseStatus;
  uploaded_at: string;
  unlocked_at: string | null;
}

export interface DatabaseList {
  databases: DatabaseInfo[];
  max_upload_bytes: number;
  max_databases: number;
}

export interface EntryNode {
  id: string;
  title: string;
  serial_number: string | null;
  serial_source: "field" | "notes" | null;
}

export interface GroupNode {
  id: string;
  name: string;
  entry_count: number;
  total_entry_count: number;
  entries: EntryNode[];
  groups: GroupNode[];
}

export interface TreeResponse {
  database: DatabaseInfo;
  root: GroupNode;
  stats: { groups: number; entries: number; entries_without_serial: number; serials_from_notes: number };
}
