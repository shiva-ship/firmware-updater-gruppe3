import { KeyRound, LogIn, Lock, UserRound } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../api/types";
import { Alert, BrandMark, Button, PasswordField, TextField, cx } from "../components/ui";

interface LoginPageProps {
  onLoggedIn: (user: User) => void;
  notice?: string | null;
}

export function LoginPage({ onLoggedIn, notice }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(0);
  const userRef = useRef<HTMLInputElement>(null);

  useEffect(() => userRef.current?.focus(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Bitte Benutzername und Passwort eingeben.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const session = await api.login(username.trim(), password);
      setPassword("");
      if (session.user) onLoggedIn(session.user);
    } catch (err) {
      setPassword("");
      if (err instanceof ApiError && err.code === "too_many_attempts") {
        const minutes = err.retryAfter ? Math.ceil(err.retryAfter / 60) : null;
        setError(`Zu viele Fehlversuche. Bitte versuchen Sie es${minutes ? ` in ${minutes} Minute(n)` : " später"} erneut.`);
      } else {
        setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen.");
      }
      setShake((s) => s + 1);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="industrial-grid relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="w-full max-w-[420px] animate-rise">
        <div className="mb-8 flex flex-col items-center text-center">
          <BrandMark className="h-14 w-14 drop-shadow-[0_0_24px_rgba(34,211,238,0.35)]" />
          <h1 className="mt-5 text-[26px] font-semibold tracking-tight text-white">
            ADS-TEC <span className="brand-gradient-text">Security Manager</span>
          </h1>
          <p className="mt-1.5 text-sm text-slate-400">Industrial Device &amp; Credential Management</p>
        </div>

        <form
          key={shake}
          onSubmit={submit}
          noValidate
          className={cx(
            "rounded-2xl border border-white/10 bg-navy-900/80 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8",
            shake > 0 && "animate-shake",
          )}
        >
          <div className="mb-6 flex items-center gap-2 text-sm font-medium text-slate-200">
            <Lock className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            Anmeldung
          </div>

          <div className="space-y-4">
            {notice && !error && <Alert tone="info">{notice}</Alert>}
            <TextField
              ref={userRef}
              id="username"
              label="Benutzername"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              maxLength={64}
              dark
              icon={<UserRound className="h-4 w-4" />}
            />
            <PasswordField
              id="password"
              label="Passwort"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              maxLength={1024}
              dark
              icon={<KeyRound className="h-4 w-4" />}
            />
            {error && <Alert>{error}</Alert>}
            <Button type="submit" loading={loading} icon={<LogIn className="h-4 w-4" />} className="w-full py-3">
              {loading ? "Anmeldung läuft …" : "Anmelden"}
            </Button>
          </div>
        </form>

        <p className="mt-6 text-center text-xs text-slate-500">
          Lokale Instanz · Zugriff nur für autorisierte Benutzer
        </p>
      </div>
    </div>
  );
}
