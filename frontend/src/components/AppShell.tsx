import { LogOut, UserRound } from "lucide-react";
import type { ReactNode } from "react";

import type { DeviceMode, User } from "../api/types";
import { Button, Logo, cx } from "./ui";

export type View = "devices" | "firmware";

interface AppShellProps {
  user: User;
  mode: DeviceMode | null;
  view: View;
  onNavigate: (view: View) => void;
  showFirmware: boolean;
  onLogout: () => void;
  loggingOut: boolean;
  children: ReactNode;
}

const NAV: { id: View; label: string }[] = [
  { id: "devices", label: "Geräte" },
  { id: "firmware", label: "Firmware & Treiber" },
];

export function ModeBadge({ mode }: { mode: DeviceMode | null }) {
  if (!mode) return null;
  return mode === "demo" ? (
    <span className="rounded-sm bg-amber-100 px-2 py-1 text-[11px] font-bold tracking-wider text-amber-900 ring-1 ring-inset ring-amber-300" title="Simulierte Geräte – keine Geräteänderungen">
      DEMO
    </span>
  ) : (
    <span className="rounded-sm bg-red-700 px-2 py-1 text-[11px] font-bold tracking-wider text-white" title="Reale Geräte im Industrienetz">
      LIVE
    </span>
  );
}

export function AppShell({ user, mode, view, onNavigate, showFirmware, onLogout, loggingOut, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30">
        <div className="border-b border-line bg-white">
          <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4">
            <Logo className="h-7" />
            <div className="hidden h-7 border-l border-line sm:block" />
            <div className="hidden leading-tight sm:block">
              <div className="text-[15px] font-semibold text-ink">Firmware Management</div>
            </div>
            <div className="ml-auto flex items-center gap-3">
              <ModeBadge mode={mode} />
              <span className="hidden items-center gap-1.5 text-[13px] text-muted md:flex">
                <UserRound className="h-4 w-4" aria-hidden="true" />
                {user.username}
              </span>
              <Button variant="ghost" size="sm" onClick={onLogout} loading={loggingOut} icon={<LogOut className="h-4 w-4" />}>
                <span className="hidden sm:inline">Abmelden</span>
              </Button>
            </div>
          </div>
        </div>
        {showFirmware && (
        <nav className="bg-ads-blue" aria-label="Hauptnavigation">
          <div className="mx-auto flex max-w-[1600px] px-4">
            {NAV.filter((item) => item.id === "devices" || showFirmware).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                aria-current={view === item.id ? "page" : undefined}
                className={cx(
                  "h-10 border-b-[3px] px-4 text-[13px] font-semibold",
                  view === item.id ? "border-ads-cyan text-white" : "border-transparent text-white/75 hover:text-white",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        </nav>
        )}
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-4">{children}</main>
    </div>
  );
}
