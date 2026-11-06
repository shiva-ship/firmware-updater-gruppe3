import { KeyRound, LogIn, Lock, UserRound } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../api/types";
import { Alert, Button, Logo, PasswordField, TextField } from "../components/ui";

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
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="h-10" />
          <h1 className="mt-5 text-xl font-semibold text-ink">Firmware Management</h1>
        </div>

        <form
          key={shake}
          onSubmit={submit}
          noValidate
          className="rounded border border-line border-t-4 border-t-ads-blue bg-white p-6 shadow-sm sm:p-8"
        >
          <div className="mb-6 flex items-center gap-2 text-sm font-semibold text-ink">
            <Lock className="h-4 w-4 text-ads-blue" aria-hidden="true" />
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
              icon={<UserRound className="h-4 w-4" />}
            />
            <PasswordField
              id="password"
              label="Passwort"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              maxLength={1024}
              icon={<KeyRound className="h-4 w-4" />}
            />
            {error && <Alert>{error}</Alert>}
            <Button type="submit" loading={loading} icon={<LogIn className="h-4 w-4" />} className="h-10 w-full">
              {loading ? "Anmeldung läuft …" : "Anmelden"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
