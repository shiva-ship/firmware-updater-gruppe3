import { AlertTriangle, CheckCircle2, Eye, EyeOff, Info, Loader2 } from "lucide-react";
import { forwardRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

/** Eigenes Signet (Schild mit Prüfhaken) – kein Firmenlogo. */
export function BrandMark({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="#0b2547" />
      <path
        d="M16 5l9 3.5v6.6c0 5.6-3.8 10-9 11.9-5.2-1.9-9-6.3-9-11.9V8.5z"
        fill="none"
        stroke="url(#bm-g)"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path d="M12 15.5l3 3 5.5-6" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={cx("animate-spin", className)} aria-hidden="true" />;
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-cyan-500 to-teal-500 text-white shadow-lg shadow-cyan-500/20 hover:from-cyan-400 hover:to-teal-400 focus-visible:outline-cyan-400",
  secondary:
    "bg-white text-navy-800 ring-1 ring-slate-300 hover:bg-slate-50 hover:ring-slate-400 focus-visible:outline-cyan-500",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-navy-800 focus-visible:outline-cyan-500",
  danger: "bg-white text-red-700 ring-1 ring-red-200 hover:bg-red-50 hover:ring-red-300 focus-visible:outline-red-500",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
        buttonStyles[variant],
        className,
      )}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

type AlertTone = "error" | "info" | "success";

export function Alert({ tone = "error", children, className }: { tone?: AlertTone; children: ReactNode; className?: string }) {
  const styles: Record<AlertTone, string> = {
    error: "border-red-200 bg-red-50 text-red-800",
    info: "border-cyan-200 bg-cyan-50 text-navy-800",
    success: "border-teal-200 bg-teal-50 text-teal-900",
  };
  const Icon = tone === "error" ? AlertTriangle : tone === "success" ? CheckCircle2 : Info;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx("flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm animate-fade-in", styles[tone], className)}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon?: ReactNode;
  dark?: boolean;
}

const fieldBase =
  "block w-full rounded-lg py-2.5 pr-3 text-sm transition focus:outline-none focus:ring-2 disabled:opacity-60";
const fieldLight = "bg-white text-slate-900 ring-1 ring-slate-300 placeholder:text-slate-400 focus:ring-cyan-500";
const fieldDark =
  "bg-navy-950/60 text-white ring-1 ring-white/15 placeholder:text-slate-500 focus:ring-brand-cyan";

export const TextField = forwardRef<HTMLInputElement, FieldProps>(function TextField(
  { label, icon, dark, className, id, ...rest },
  ref,
) {
  return (
    <label className="block" htmlFor={id}>
      <span className={cx("mb-1.5 block text-xs font-semibold uppercase tracking-wider", dark ? "text-slate-300" : "text-slate-600")}>
        {label}
      </span>
      <span className="relative block">
        {icon && <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">{icon}</span>}
        <input
          ref={ref}
          id={id}
          {...rest}
          className={cx(fieldBase, dark ? fieldDark : fieldLight, icon ? "pl-10" : "pl-3", className)}
        />
      </span>
    </label>
  );
});

export const PasswordField = forwardRef<HTMLInputElement, Omit<FieldProps, "type">>(function PasswordField(
  { label, icon, dark, className, id, ...rest },
  ref,
) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="block" htmlFor={id}>
      <span className={cx("mb-1.5 block text-xs font-semibold uppercase tracking-wider", dark ? "text-slate-300" : "text-slate-600")}>
        {label}
      </span>
      <span className="relative block">
        {icon && <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">{icon}</span>}
        <input
          ref={ref}
          id={id}
          type={visible ? "text" : "password"}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          {...rest}
          className={cx(fieldBase, dark ? fieldDark : fieldLight, icon ? "pl-10" : "pl-3", "pr-11", className)}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute inset-y-0 right-1 my-1 flex items-center rounded-md px-2.5 text-slate-400 transition hover:text-cyan-600 focus-visible:outline-2 focus-visible:outline-cyan-500"
          aria-label={visible ? "Passwort verbergen" : "Passwort anzeigen"}
          aria-pressed={visible}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </span>
    </label>
  );
});
