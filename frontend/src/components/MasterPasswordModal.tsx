import { FileLock2, KeyRound, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { Alert, Button, Dialog, PasswordField } from "./ui";

interface MasterPasswordModalProps {
  open: boolean;
  title: string;
  description: ReactNode;
  fileName: string;
  confirmLabel: string;
  busyLabel: string;
  confirmIcon?: ReactNode;
  busyHint?: string;
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
  busyHint = "Schlüsselableitung läuft, das kann je nach Datenbank einige Sekunden dauern …",
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
    const id = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(id);
  }, [open, attempt]);

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
    <Dialog
      open={open}
      title={title}
      subtitle={description}
      onClose={onClose}
      closable={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Abbrechen
          </Button>
          <Button type="submit" form="master-password-form" loading={busy} icon={confirmIcon}>
            {busy ? busyLabel : confirmLabel}
          </Button>
        </>
      }
    >
      <form id="master-password-form" onSubmit={submit} noValidate className="space-y-3">
        <div className="flex items-center gap-2 rounded border border-line bg-surface px-3 py-2">
          <FileLock2 className="h-4 w-4 shrink-0 text-ads-blue" aria-hidden="true" />
          <span className="truncate text-[13px] font-medium">{fileName}</span>
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
        {busy && <p className="text-xs text-muted">{busyHint}</p>}
        <p className="flex items-start gap-2 text-xs text-muted">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ads-blue" aria-hidden="true" />
          Das Masterpasswort wird nur serverseitig für diesen Vorgang verwendet und weder gespeichert noch protokolliert.
        </p>
      </form>
    </Dialog>
  );
}
