import { LogOut, UserRound } from "lucide-react";
import type { ReactNode } from "react";

import type { User } from "../api/types";
import { BrandMark, Button } from "./ui";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  loggingOut: boolean;
  children: ReactNode;
}

export function AppShell({ user, onLogout, loggingOut, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-navy-900 text-white shadow-lg shadow-navy-950/20">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <BrandMark className="h-9 w-9 shrink-0" />
          <div className="min-w-0 leading-tight">
            <div className="truncate text-[15px] font-semibold tracking-tight">
              ADS-TEC <span className="brand-gradient-text">Security Manager</span>
            </div>
            <div className="hidden truncate text-xs text-slate-400 sm:block">Industrial Device &amp; Credential Management</div>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <div className="hidden items-center gap-2 rounded-full bg-white/5 py-1.5 pl-2 pr-3 text-sm ring-1 ring-white/10 sm:flex">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-teal-500 text-navy-950">
                <UserRound className="h-3.5 w-3.5" />
              </span>
              <span className="max-w-40 truncate font-medium">{user.username}</span>
            </div>
            <Button
              variant="ghost"
              onClick={onLogout}
              loading={loggingOut}
              icon={<LogOut className="h-4 w-4" />}
              className="text-slate-300 hover:bg-white/10 hover:text-white"
            >
              <span className="hidden sm:inline">Abmelden</span>
            </Button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-brand-cyan via-brand-teal to-transparent" />
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-500">
        ADS-TEC Security Manager · Lokale Instanz · Keine Daten verlassen diesen Rechner
      </footer>
    </div>
  );
}

export function PageTitle({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-700">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-navy-900 sm:text-[28px]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
