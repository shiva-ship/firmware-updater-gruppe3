import { KeyRound, ShieldPlus, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../api/types";
import { Alert, Button, Logo, PasswordField, TextField } from "../components/ui";

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
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-[460px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="h-10" />
          <h1 className="mt-5 text-xl font-semibold text-ink">Firmware Management</h1>
          <p className="mt-1 text-sm text-muted">Ersteinrichtung</p>
        </div>

        <form
          onSubmit={submit}
          noValidate
          className="rounded border border-line border-t-4 border-t-ads-blue bg-white p-6 shadow-sm sm:p-8"
        >
          <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldPlus className="h-4 w-4 text-ads-blue" aria-hidden="true" />
            Administrator anlegen
          </div>

          {!setupToken ? (
            <Alert>
              Kein Einrichtungsschlüssel gefunden. Bitte starten Sie die Anwendung über <strong>start.cmd</strong>, dann öffnet
              sich diese Seite automatisch mit dem richtigen Link.
            </Alert>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Es existiert noch kein Benutzer. Legen Sie jetzt das Administratorkonto an. Dies ist nur einmal möglich.
              </p>
              <TextField
                id="setup-username"
                label="Benutzername"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                maxLength={64}
                icon={<UserRound className="h-4 w-4" />}
              />
              <PasswordField
                id="setup-password"
                label="Passwort"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                maxLength={1024}
                icon={<KeyRound className="h-4 w-4" />}
              />
              <PasswordField
                id="setup-repeat"
                label="Passwort wiederholen"
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                maxLength={1024}
                icon={<KeyRound className="h-4 w-4" />}
              />
              <p className="text-xs text-muted">
                Mindestens {minPasswordLength} Zeichen und mindestens drei von: Kleinbuchstaben, Großbuchstaben, Ziffern,
                Sonderzeichen. Der Benutzername darf nicht enthalten sein.
              </p>
              {error && <Alert>{error}</Alert>}
              <Button type="submit" loading={loading} icon={<ShieldPlus className="h-4 w-4" />} className="h-10 w-full">
                {loading ? "Wird angelegt …" : "Administrator anlegen & anmelden"}
              </Button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
