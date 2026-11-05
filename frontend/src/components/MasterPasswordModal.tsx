import { FileLock2, KeyRound, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { Alert, Button, PasswordField, cx } from "./ui";

interface MasterPasswordModalProps {
  open: boolean;
  /** z. B. „Datenbank aktualisieren“ – später auch „Firmwareupdate freigeben“ */
  title: string;
  description: ReactNode;
  fileName: string;
  confirmLabel: string;
  busyLabel: string;
  confirmIcon?: ReactNode;
  /** Muss bei falschem Passwort einen ApiError werfen. */
  onSubmit: (masterPassword: string) => Promise<void>;
  onClose: () => void;
}

/**
 * Wiederverwendbare Masterpasswort-Abfrage. Das Passwort lebt nur in diesem Komponenten-
 * zustand und wird nach jedem Versuch sowie beim Schließen sofort geleert.
 */
export function MasterPasswordModal({
  open,
  title,
  description,
  fileName,
  confirmLabel,
  busyLabel,
  confirmIcon,
  onSubmit,
  onClose,
}: MasterPasswordModalProps) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setPassword("");
      setError(null);
      setAttempt(0);
      return;
    }
    const id = window.setTimeout(() => inputRef.current?.focus(), 50);
    return () => window.clearTimeout(id);
  }, [open, attempt]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password) {
      setError("Bitte geben Sie das Masterpasswort ein.");
      return;
    }
    const value = password;
    setPassword("");
    setBusy(true);
    setError(null);
    try {
      await onSubmit(value);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Vorgang fehlgeschlagen.");
      setAttempt((a) => a + 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <div
        className="absolute inset-0 bg-navy-950/70 backdrop-blur-sm animate-fade-in"
        onClick={() => !busy && onClose()}
        aria-hidden="true"
      />
      <form
        key={attempt}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mpm-title"
        onSubmit={submit}
        noValidate
        className={cx(
          "relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl shadow-navy-950/50 animate-rise",
          attempt > 0 && error && "animate-shake",
        )}
      >
        <div className="relative overflow-hidden bg-navy-900 px-6 pb-5 pt-6 text-white">
          <div className="circuit-pattern pointer-events-none absolute inset-0 opacity-60" aria-hidden="true" />
          <div className="relative flex items-start gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-cyan to-brand-teal text-navy-950 shadow-lg shadow-cyan-500/30">
              <KeyRound className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 id="mpm-title" className="text-lg font-semibold tracking-tight">
                {title}
              </h2>
              <div className="mt-0.5 text-sm text-slate-300">{description}</div>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="-mr-2 -mt-1 rounded-md p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
              aria-label="Schließen"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-brand-cyan via-brand-teal to-transparent" />

        <div className="space-y-4 px-6 py-6">
          <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5">
            <FileLock2 className="h-4 w-4 shrink-0 text-cyan-700" aria-hidden="true" />
            <span className="truncate text-sm font-medium text-navy-900">{fileName}</span>
          </div>
          <PasswordField
            ref={inputRef}
            id="master-password"
            label="KeePass-Masterpasswort"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            maxLength={4096}
            icon={<KeyRound className="h-4 w-4" />}
          />
          {error && <Alert>{error}</Alert>}
          {busy && (
            <p className="text-xs text-slate-500 animate-fade-in">
              Schlüsselableitung läuft, das kann je nach Datenbank einige Sekunden dauern …
            </p>
          )}
          <p className="flex items-start gap-2 text-xs text-slate-500">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-600" aria-hidden="true" />
            Das Masterpasswort wird nur für diesen Vorgang verwendet und weder gespeichert noch protokolliert.
          </p>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-slate-100 bg-slate-50/70 px-6 py-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Abbrechen
          </Button>
          <Button type="submit" loading={busy} icon={confirmIcon}>
            {busy ? busyLabel : confirmLabel}
          </Button>
        </div>
      </form>
    </div>
  );
}
