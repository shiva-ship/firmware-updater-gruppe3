import { KeyRound, ShieldPlus, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../api/types";
import { Alert, BrandMark, Button, PasswordField, TextField } from "../components/ui";

interface SetupPageProps {
  setupToken: string | null;
  minPasswordLength: number;
  onDone: (user: User) => void;
}

export function SetupPage({ setupToken, minPasswordLength, onDone }: SetupPageProps) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!setupToken) return;
    if (password !== repeat) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    if (password.length < minPasswordLength) {
      setError(`Das Passwort muss mindestens ${minPasswordLength} Zeichen lang sein.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const session = await api.completeSetup(setupToken, username.trim(), password);
      setPassword("");
      setRepeat("");
      if (session.user) onDone(session.user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einrichtung fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="industrial-grid flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[460px] animate-rise">
        <div className="mb-8 flex flex-col items-center text-center">
          <BrandMark className="h-14 w-14 drop-shadow-[0_0_24px_rgba(34,211,238,0.35)]" />
          <h1 className="mt-5 text-[26px] font-semibold tracking-tight text-white">
            ADS-TEC <span className="brand-gradient-text">Security Manager</span>
          </h1>
          <p className="mt-1.5 text-sm text-slate-400">Ersteinrichtung</p>
        </div>

        <form
          onSubmit={submit}
          noValidate
          className="rounded-2xl border border-white/10 bg-navy-900/80 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8"
        >
          <div className="mb-5 flex items-center gap-2 text-sm font-medium text-slate-200">
            <ShieldPlus className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            Administrator anlegen
          </div>

          {!setupToken ? (
            <Alert>
              Kein Einrichtungsschlüssel gefunden. Bitte starten Sie die Anwendung über <strong>start.cmd</strong>, dann öffnet
              sich diese Seite automatisch mit dem richtigen Link.
            </Alert>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-slate-400">
                Es existiert noch kein Benutzer. Legen Sie jetzt das Administratorkonto an. Dies ist nur einmal möglich.
              </p>
              <TextField
                id="setup-username"
                label="Benutzername"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                maxLength={64}
                dark
                icon={<UserRound className="h-4 w-4" />}
              />
              <PasswordField
                id="setup-password"
                label="Passwort"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                maxLength={1024}
                dark
                icon={<KeyRound className="h-4 w-4" />}
              />
              <PasswordField
                id="setup-repeat"
                label="Passwort wiederholen"
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                maxLength={1024}
                dark
                icon={<KeyRound className="h-4 w-4" />}
              />
              <p className="text-xs text-slate-500">
                Mindestens {minPasswordLength} Zeichen und mindestens drei von: Kleinbuchstaben, Großbuchstaben, Ziffern,
                Sonderzeichen. Der Benutzername darf nicht enthalten sein.
              </p>
              {error && <Alert>{error}</Alert>}
              <Button type="submit" loading={loading} icon={<ShieldPlus className="h-4 w-4" />} className="w-full py-3">
                {loading ? "Wird angelegt …" : "Administrator anlegen & anmelden"}
              </Button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
