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

export type DeviceType = "balluff" | "adstec" | "siemens";
export type DeviceMode = "demo" | "live";

export interface EntryNode {
  id: string;
  title: string;
  serial_number: string | null;
  serial_source: "field" | "notes" | null;
  serial_status: "ok" | "missing" | "duplicate";
  device_type: DeviceType | null;
  host: string | null;
  mac_address: string | null;
  model: string | null;
  update_order: number | null;
  has_notes: boolean;
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
  stats: { groups: number; entries: number; entries_without_serial: number; serials_from_notes: number; duplicate_serials: number };
}

export interface FirmwareFile {
  name: string;
  size_bytes: number;
  device_type: DeviceType;
}

export interface FirmwarePackage {
  name: string;
  size_bytes: number;
  vendor: DeviceType;
  sha256: string;
  filename_version: string | null;
  status: "released" | "unreleased" | "hash_mismatch";
  version: string | null;
  models: string[];
  vendor_checksum_verified: boolean;
  released_by: string | null;
  released_at: string | null;
  notes: string | null;
}

export interface DriverInfo {
  vendor: DeviceType;
  label: string;
  driver_module: string;
  firmware_suffixes: string[];
  supports_read: boolean;
  supports_update: boolean;
  driver_available: boolean;
  driver_error: string | null;
  notes: string;
}

export interface SystemInfo {
  mode: DeviceMode;
  version: string;
  drivers: DriverInfo[];
}

export type ConnectionState = "online" | "offline" | "error" | "not_checked";

export interface DeviceStatus {
  connection: ConnectionState;
  installed_version: string | null;
  model: string | null;
  serial_number: string | null;
  mac_address: string | null;
  message: string | null;
  simulated: boolean;
  checked_at: string;
}

export interface Inventory {
  mode: DeviceMode;
  devices: Record<string, DeviceStatus>;
}

export type PlanStatus = "ready" | "up_to_date" | "blocked" | "no_driver";

export interface PlanCheck {
  key: string;
  label: string;
  status: "ok" | "warn" | "fail" | "skip";
  message: string;
}

export interface PlanItem {
  position: number;
  entry_id: string;
  title: string;
  path: string[];
  vendor: DeviceType | null;
  vendor_label: string;
  serial_number: string | null;
  serial_status: string;
  host: string | null;
  model: string | null;
  installed_version: string | null;
  target_version: string | null;
  package: string | null;
  driver_module: string | null;
  status: PlanStatus;
  checks: PlanCheck[];
  effects: string[];
  order_reason: string;
  simulated: boolean;
  warnings: string[];
  blockers: string[];
}

export interface UpdatePlan {
  id: string;
  db_id: string;
  mode: DeviceMode;
  simulated: boolean;
  created_at: string;
  items: PlanItem[];
  counts: Record<PlanStatus, number>;
  requires_stop_run: boolean;
  /** LIVE: Zugangsdaten aus dem Vorbereiten liegen noch vor – Freigabe ohne erneute Passworteingabe. */
  credentials_ready: boolean;
}

export type JobItemState = "pending" | "running" | "succeeded" | "dry_run_ok" | "failed" | "skipped" | "aborted";
export type JobState = "running" | "completed" | "completed_with_errors" | "aborted" | "cancelled";

export interface JobItem {
  entry_id: string;
  title: string;
  vendor_label: string;
  serial_number: string | null;
  position: number;
  plan_status: PlanStatus;
  from_version: string | null;
  to_version: string | null;
  package: string | null;
  state: JobItemState;
  step: string | null;
  progress: number;
  message: string | null;
  verified_version: string | null;
  started_at: string | null;
  finished_at: string | null;
  log: { at: string; level: "info" | "warn" | "error"; message: string }[];
}

export interface UpdateJob {
  id: string;
  plan_id: string;
  dry_run: boolean;
  simulated: boolean;
  state: JobState;
  created_at: string;
  finished_at: string | null;
  abort_reason: string | null;
  cancel_requested: boolean;
  summary: Record<JobItemState, number>;
  items: JobItem[];
}
