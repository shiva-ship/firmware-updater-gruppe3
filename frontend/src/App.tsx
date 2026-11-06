import { useCallback, useEffect, useState } from "react";

import { api, onUnauthorized } from "./api/client";
import type { SystemInfo, User } from "./api/types";
import { AppShell, type View } from "./components/AppShell";
import { Logo, Spinner } from "./components/ui";
import { FirmwarePage } from "./pages/FirmwarePage";
import { LoginPage } from "./pages/LoginPage";
import { SetupPage } from "./pages/SetupPage";
import { WorkspacePage } from "./pages/WorkspacePage";

// Einrichtungsschlüssel aus dem URL-Fragment (#setup=…) lesen und sofort aus der Adresszeile entfernen.
const setupTokenFromUrl = (() => {
  const match = window.location.hash.match(/^#setup=([A-Za-z0-9_-]{16,256})$/);
  if (window.location.hash) history.replaceState(null, "", window.location.pathname + window.location.search);
  return match ? match[1] : null;
})();

export default function App() {
  const [setup, setSetup] = useState<{ token: string | null; minLength: number } | null>(null);
  const [booting, setBooting] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [view, setView] = useState<View>("devices");
  const [ready, setReady] = useState(false);
  const onReadyChange = useCallback((value: boolean) => {
    setReady(value);
    if (!value) setView("devices");
  }, []);

  useEffect(() => {
    if (!user) {
      setSystem(null);
      return;
    }
    api
      .getSystem()
      .then(setSystem)
      .catch(() => setSystem(null));
  }, [user]);

  const resetToLogin = useCallback((message: string | null) => {
    setUser(null);
    setNotice(message);
  }, []);

  useEffect(() => {
    onUnauthorized(() => resetToLogin("Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an."));
    (async () => {
      try {
        const s = await api.getSession();
        if (s.authenticated) {
          setUser(s.user);
          return;
        }
        const status = await api.setupStatus();
        if (status.setup_required) setSetup({ token: setupTokenFromUrl, minLength: status.min_password_length });
      } catch {
        setUser(null);
      } finally {
        setBooting(false);
      }
    })();
    return () => onUnauthorized(null);
  }, [resetToLogin]);

  async function logout() {
    setLoggingOut(true);
    try {
      await api.logout();
    } catch {
      /* Sitzung ist ggf. bereits abgelaufen */
    } finally {
      setLoggingOut(false);
      resetToLogin("Sie wurden abgemeldet. Alle geöffneten Datenbanken wurden geschlossen.");
    }
  }

  if (booting) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 text-muted">
        <Logo className="h-9" />
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  if (!user && setup) {
    return (
      <SetupPage
        setupToken={setup.token}
        minPasswordLength={setup.minLength}
        onDone={(u) => {
          setSetup(null);
          setUser(u);
        }}
      />
    );
  }

  if (!user) {
    return (
      <LoginPage
        notice={notice}
        onLoggedIn={(u) => {
          setNotice(null);
          setUser(u);
        }}
      />
    );
  }

  return (
    <AppShell user={user} mode={system?.mode ?? null} view={view} onNavigate={setView} showFirmware={ready} onLogout={logout} loggingOut={loggingOut}>
      {/* Beide Ansichten bleiben gemountet, damit Plan und laufender Auftrag erhalten bleiben. */}
      <div hidden={view !== "devices"}>
        <WorkspacePage system={system} active={view === "devices"} onReadyChange={onReadyChange} />
      </div>
      {ready && view === "firmware" && <FirmwarePage system={system} />}
    </AppShell>
  );
}
