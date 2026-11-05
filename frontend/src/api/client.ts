import type { DatabaseInfo, DatabaseList, SessionInfo, TreeResponse } from "./types";

/**
 * Das CSRF-Token wird ausschließlich im Arbeitsspeicher gehalten – niemals in
 * localStorage/sessionStorage. Das Sitzungscookie ist HttpOnly und für JS unsichtbar.
 */
let csrfToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly retryAfter?: number,
  ) {
    super(message);
  }
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  body?: BodyInit;
  headers?: Record<string, string>;
}

async function request<T>(path: string, { method = "GET", json, body, headers = {} }: RequestOptions = {}): Promise<T> {
  const finalHeaders: Record<string, string> = { Accept: "application/json", ...headers };
  if (method !== "GET" && csrfToken) finalHeaders["X-CSRF-Token"] = csrfToken;
  if (json !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  let response: Response;
  try {
    response = await fetch(path, { method, headers: finalHeaders, body, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "Der Server ist nicht erreichbar. Läuft das Backend?");
  }

  if (response.status === 204) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const code: string = data?.error?.code ?? `http_${response.status}`;
    const message: string = data?.error?.message ?? "Unerwarteter Fehler.";
    const retry = Number(response.headers.get("Retry-After") ?? "") || undefined;
    if (response.status === 401 && code === "not_authenticated") {
      csrfToken = null;
      unauthorizedHandler?.();
    }
    throw new ApiError(response.status, code, message, retry);
  }
  return data as T;
}

function remember(session: SessionInfo): SessionInfo {
  csrfToken = session.authenticated ? session.csrf_token : null;
  return session;
}

export const api = {
  async getSession() {
    return remember(await request<SessionInfo>("/api/auth/session"));
  },
  async login(username: string, password: string) {
    return remember(await request<SessionInfo>("/api/auth/login", { method: "POST", json: { username, password } }));
  },
  setupStatus() {
    return request<{ setup_required: boolean; min_password_length: number }>("/api/setup/status");
  },
  async completeSetup(setupToken: string, username: string, password: string) {
    return remember(
      await request<SessionInfo>("/api/setup", {
        method: "POST",
        json: { setup_token: setupToken, username, password },
      }),
    );
  },
  async logout() {
    try {
      await request<void>("/api/auth/logout", { method: "POST" });
    } finally {
      csrfToken = null;
    }
  },
  listDatabases() {
    return request<DatabaseList>("/api/databases");
  },
  uploadDatabase(file: File) {
    return request<DatabaseInfo>("/api/databases", {
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) },
    });
  },
  /** Entschlüsselt die Datei (erneut) mit dem Masterpasswort und baut die Baumstruktur neu auf. */
  refreshDatabase(id: string, masterPassword: string) {
    return request<DatabaseInfo>(`/api/databases/${encodeURIComponent(id)}/refresh`, {
      method: "POST",
      json: { master_password: masterPassword },
    });
  },
  getTree(id: string) {
    return request<TreeResponse>(`/api/databases/${encodeURIComponent(id)}/tree`);
  },
  closeDatabase(id: string) {
    return request<void>(`/api/databases/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
};
