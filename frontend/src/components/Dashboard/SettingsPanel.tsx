/**
 * SettingsPanel — modal drawer for user preferences.
 *
 * Combines:
 *  - Theme selector (Dark / Light / Terminal)
 *  - Sound alerts toggle + volume slider
 *  - Push notification toggle
 *
 * Opened by a gear icon button in the Dashboard header.
 */

import { useCallback, useEffect, useRef } from "react";
import { useSoundAlert } from "../hooks/useSoundAlert";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { useTheme } from "../hooks/useTheme";
import type { Theme } from "../hooks/useTheme";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

const THEME_OPTIONS: { value: Theme; label: string; description: string }[] = [
  { value: "dark",     label: "Dark",     description: "Dark background, light text" },
  { value: "light",    label: "Light",    description: "Light background, dark text" },
  { value: "terminal", label: "Terminal", description: "Green-on-black Matrix style" },
];

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { theme, setTheme } = useTheme();
  const { enabled, toggleEnabled, volume, setVolume, play } = useSoundAlert();
  const { permission, requestPermission } = usePushNotifications();
  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  // Trap focus inside panel while open
  useEffect(() => {
    if (open) {
      panelRef.current?.focus();
    }
  }, [open]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose],
  );

  const handleVolumeChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setVolume(parseFloat(e.target.value));
    },
    [setVolume],
  );

  const handleTestSound = useCallback(() => {
    play("signal");
  }, [play]);

  const handleRequestNotifications = useCallback(async () => {
    await requestPermission();
  }, [requestPermission]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-end justify-end bg-black/60 backdrop-blur-sm sm:items-start sm:pt-16 sm:pr-4"
      role="dialog"
      aria-modal="true"
      aria-label="Settings panel"
      onClick={handleOverlayClick}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="w-full max-w-sm rounded-t-xl border border-border bg-surface p-5 shadow-2xl outline-none sm:rounded-xl"
      >
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted hover:text-foreground transition-colors"
            aria-label="Close settings"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Theme ──────────────────────────────────────────────── */}
        <section className="mb-5" aria-labelledby="settings-theme-label">
          <p id="settings-theme-label" className="mb-2.5 text-xs font-medium uppercase tracking-wide text-muted">
            Theme
          </p>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Choose theme">
            {THEME_OPTIONS.map(({ value, label, description }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={theme === value}
                aria-label={`${label} theme — ${description}`}
                onClick={() => setTheme(value)}
                className={[
                  "flex flex-col items-center gap-1 rounded-lg border px-2 py-3 text-xs font-medium transition-colors",
                  theme === value
                    ? "border-accent bg-accent/10 text-foreground"
                    : "border-border bg-background text-muted hover:border-border/80 hover:text-foreground",
                  value === "terminal" ? "font-mono" : "",
                ].join(" ")}
              >
                <ThemeIcon variant={value} active={theme === value} />
                {label}
              </button>
            ))}
          </div>
        </section>

        <div className="mb-5 border-t border-border" />

        {/* ── Sound Alerts ───────────────────────────────────────── */}
        <section className="mb-5" aria-labelledby="settings-sound-label">
          <div className="mb-2.5 flex items-center justify-between">
            <p id="settings-sound-label" className="text-xs font-medium uppercase tracking-wide text-muted">
              Sound Alerts
            </p>
            <ToggleSwitch
              enabled={enabled}
              onToggle={toggleEnabled}
              ariaLabel="Toggle sound alerts"
            />
          </div>

          {enabled && (
            <div className="space-y-3">
              <div>
                <label htmlFor="volume-slider" className="mb-1.5 flex items-center justify-between text-xs text-muted">
                  <span>Volume</span>
                  <span className="font-mono text-foreground">{Math.round(volume * 100)}%</span>
                </label>
                <input
                  id="volume-slider"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={volume}
                  onChange={handleVolumeChange}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-accent"
                  aria-label="Sound volume"
                />
              </div>
              <button
                type="button"
                onClick={handleTestSound}
                className="rounded border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:border-accent hover:text-foreground"
              >
                Test Sound
              </button>
            </div>
          )}
        </section>

        <div className="mb-5 border-t border-border" />

        {/* ── Push Notifications ─────────────────────────────────── */}
        <section aria-labelledby="settings-push-label">
          <div className="mb-2.5 flex items-center justify-between">
            <p id="settings-push-label" className="text-xs font-medium uppercase tracking-wide text-muted">
              Push Notifications
            </p>
            <PermissionBadge permission={permission} />
          </div>
          <p className="mb-3 text-xs text-muted">
            Receive browser notifications for new signals when this tab is in the background.
          </p>
          {permission === "default" && (
            <button
              type="button"
              onClick={() => { void handleRequestNotifications(); }}
              className="rounded border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent/20"
            >
              Enable Notifications
            </button>
          )}
          {permission === "denied" && (
            <p className="text-xs text-bearish">
              Notifications are blocked. Allow them in your browser settings to enable this feature.
            </p>
          )}
          {permission === "granted" && (
            <p className="text-xs text-bullish">Notifications are enabled.</p>
          )}
        </section>
      </div>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────── */

interface ToggleSwitchProps {
  enabled: boolean;
  onToggle: () => void;
  ariaLabel: string;
}

function ToggleSwitch({ enabled, onToggle, ariaLabel }: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={ariaLabel}
      onClick={onToggle}
      className={[
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200",
        enabled ? "bg-accent" : "bg-border",
      ].join(" ")}
    >
      <span
        className={[
          "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow ring-0 transition-transform duration-200",
          enabled ? "translate-x-4" : "translate-x-0",
        ].join(" ")}
        aria-hidden="true"
      />
    </button>
  );
}

interface PermissionBadgeProps {
  permission: "default" | "granted" | "denied";
}

function PermissionBadge({ permission }: PermissionBadgeProps) {
  const variants: Record<string, string> = {
    default: "bg-warning/20 text-warning",
    granted: "bg-bullish/20 text-bullish",
    denied:  "bg-bearish/20 text-bearish",
  };
  const labels: Record<string, string> = {
    default: "Not set",
    granted: "Granted",
    denied:  "Blocked",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${variants[permission]}`}>
      {labels[permission]}
    </span>
  );
}

interface ThemeIconProps {
  variant: Theme;
  active: boolean;
}

function ThemeIcon({ variant, active }: ThemeIconProps) {
  const baseClass = "h-5 w-5 rounded";
  if (variant === "dark") {
    return (
      <span
        className={`${baseClass} bg-gray-900 border ${active ? "border-accent" : "border-border"}`}
        aria-hidden="true"
      />
    );
  }
  if (variant === "light") {
    return (
      <span
        className={`${baseClass} bg-white border ${active ? "border-accent" : "border-border"}`}
        aria-hidden="true"
      />
    );
  }
  // terminal
  return (
    <span
      className={`${baseClass} bg-black border ${active ? "border-green-500" : "border-green-900"} flex items-center justify-center`}
      aria-hidden="true"
    >
      <span className="text-green-400" style={{ fontSize: 8, fontFamily: "monospace" }}>{">"}_</span>
    </span>
  );
}
