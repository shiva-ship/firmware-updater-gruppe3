import { AlertTriangle, CheckCircle2, Eye, EyeOff, Info, Loader2, X } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

/** ADS-TEC-Logo (lokal bereitgestellt, auf den sichtbaren Bereich zugeschnitten). */
export function Logo({ className = "h-7" }: { className?: string }) {
  return <img src="/adstec-logo.png" alt="ads-tec" className={cx("w-auto select-none", className)} draggable={false} />;
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={cx("animate-spin", className)} aria-hidden="true" />;
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonStyles: Record<ButtonVariant, string> = {
  primary: "bg-ads-blue text-white hover:bg-ads-blue-dark focus-visible:outline-ads-cyan",
  secondary: "bg-white text-ads-blue ring-1 ring-inset ring-line hover:bg-ads-blue-light focus-visible:outline-ads-cyan",
  ghost: "text-muted hover:bg-ads-blue-light hover:text-ads-blue focus-visible:outline-ads-cyan",
  danger: "bg-red-700 text-white hover:bg-red-800 focus-visible:outline-red-500",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded font-semibold transition-colors",
        size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-4 text-sm",
        "focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        buttonStyles[variant],
        className,
      )}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

type AlertTone = "error" | "info" | "success" | "warning";

export function Alert({ tone = "error", children, className, onClose }: { tone?: AlertTone; children: ReactNode; className?: string; onClose?: () => void }) {
  const styles: Record<AlertTone, string> = {
    error: "border-red-300 bg-red-50 text-red-900",
    info: "border-ads-cyan/40 bg-ads-cyan-light text-ink",
    success: "border-emerald-300 bg-emerald-50 text-emerald-900",
    warning: "border-amber-300 bg-amber-50 text-amber-900",
  };
  const Icon = tone === "error" || tone === "warning" ? AlertTriangle : tone === "success" ? CheckCircle2 : Info;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex items-start gap-2.5 rounded border px-3 py-2.5 text-sm", styles[tone], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">{children}</div>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Meldung schließen" className="shrink-0 opacity-60 hover:opacity-100">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export type BadgeTone = "neutral" | "blue" | "green" | "amber" | "red" | "cyan";

const badgeStyles: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-300",
  blue: "bg-ads-blue-light text-ads-blue ring-ads-blue/25",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  amber: "bg-amber-50 text-amber-900 ring-amber-300",
  red: "bg-red-50 text-red-800 ring-red-300",
  cyan: "bg-ads-cyan-light text-[#00618b] ring-ads-cyan/40",
};

export function Badge({ tone = "neutral", children, className, title }: { tone?: BadgeTone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset", badgeStyles[tone], className)}
    >
      {children}
    </span>
  );
}

/** Statuspunkt mit Text – sachliche Zustandsanzeige. */
export function StatusDot({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  const dot: Record<BadgeTone, string> = {
    neutral: "bg-slate-400",
    blue: "bg-ads-blue",
    green: "bg-emerald-600",
    amber: "bg-amber-500",
    red: "bg-red-600",
    cyan: "bg-ads-cyan",
  };
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={cx("h-2 w-2 shrink-0 rounded-full", dot[tone])} aria-hidden="true" />
      {children}
    </span>
  );
}

/** Checkbox mit Zwischenzustand („teilweise ausgewählt“). */
export function Checkbox({
  checked,
  indeterminate = false,
  onChange,
  label,
  className,
  disabled,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  className?: string;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      title={label}
      checked={checked}
      disabled={disabled}
      aria-checked={indeterminate && !checked ? "mixed" : checked}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
      className={cx("h-4 w-4 shrink-0 cursor-pointer rounded-sm border-line", className)}
    />
  );
}

export function Panel({ title, actions, children, className, bodyClassName }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string }) {
  return (
    <section className={cx("flex min-h-0 flex-col rounded border border-line bg-white", className)}>
      {(title || actions) && (
        <header className="flex min-h-11 items-center justify-between gap-3 border-b border-line px-4 py-2">
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ads-blue">{title}</h2>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Modaler Dialog im Anwendungsstil (ohne Einblend-Animation). */
export function Dialog({
  open,
  title,
  subtitle,
  onClose,
  closable = true,
  width = "max-w-lg",
  children,
  footer,
}: {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  closable?: boolean;
  width?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open || !closable) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closable, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/45 p-4 sm:p-8" role="presentation">
      <div role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} className={cx("w-full rounded border border-line bg-white shadow-xl", width)}>
        <header className="flex items-start gap-3 border-b-2 border-ads-blue px-5 py-3.5">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
          </div>
          {closable && (
            <button type="button" onClick={onClose} className="-mr-1 rounded p-1 text-muted hover:bg-surface hover:text-ink" aria-label="Schließen">
              <X className="h-5 w-5" />
            </button>
          )}
        </header>
        <div className="px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-surface px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon?: ReactNode;
  hint?: ReactNode;
}

const fieldBase =
  "block h-9 w-full rounded bg-white pr-3 text-sm text-ink ring-1 ring-inset ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-ads-cyan disabled:opacity-60";

export const TextField = forwardRef<HTMLInputElement, FieldProps>(function TextField({ label, icon, hint, className, id, ...rest }, ref) {
  return (
    <label className="block" htmlFor={id}>
      <span className="mb-1 block text-xs font-semibold text-muted">{label}</span>
      <span className="relative block">
        {icon && <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">{icon}</span>}
        <input ref={ref} id={id} {...rest} className={cx(fieldBase, icon ? "pl-9" : "pl-3", className)} />
      </span>
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
});

export const PasswordField = forwardRef<HTMLInputElement, Omit<FieldProps, "type">>(function PasswordField({ label, icon, hint, className, id, ...rest }, ref) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="block" htmlFor={id}>
      <span className="mb-1 block text-xs font-semibold text-muted">{label}</span>
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
          className={cx(fieldBase, icon ? "pl-9" : "pl-3", "pr-10", className)}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute inset-y-0 right-1 my-1 flex items-center rounded px-2 text-slate-400 hover:text-ads-blue focus-visible:outline-2 focus-visible:outline-ads-cyan"
          aria-label={visible ? "Passwort verbergen" : "Passwort anzeigen"}
          aria-pressed={visible}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </span>
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
});

export function ProgressBar({ value, tone = "blue", label }: { value: number; tone?: "blue" | "green" | "red" | "amber"; label?: string }) {
  const color = { blue: "bg-ads-blue", green: "bg-emerald-600", red: "bg-red-600", amber: "bg-amber-500" }[tone];
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="h-2 w-full overflow-hidden rounded-sm bg-slate-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={cx("h-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
