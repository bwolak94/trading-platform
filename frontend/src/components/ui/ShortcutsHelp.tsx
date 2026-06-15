interface ShortcutItem {
  keys: string[];
  description: string;
}

const SHORTCUTS: ShortcutItem[] = [
  { keys: ["⌘", "K"], description: "Open Command Palette" },
  { keys: ["←", "→"], description: "Switch main tab" },
  { keys: ["1", "–", "6"], description: "Switch timeframe (1m, 5m, 15m, 1h, 4h, 1d)" },
  { keys: ["F"], description: "Toggle fullscreen chart" },
  { keys: ["R"], description: "Refresh data" },
  { keys: ["B"], description: "LONG bias" },
  { keys: ["S"], description: "SHORT bias" },
  { keys: ["N"], description: "Next signal" },
  { keys: ["P"], description: "Previous signal" },
  { keys: ["T"], description: "Toggle theme" },
  { keys: ["Tab"], description: "Toggle sidebar" },
  { keys: ["?"], description: "Show this help" },
  { keys: ["Esc"], description: "Close modals / drawers" },
];

interface ShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

export function ShortcutsHelp({ open, onClose }: ShortcutsHelpProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-sm rounded-xl border border-border bg-background p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">Keyboard Shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close shortcuts help"
          >
            ✕
          </button>
        </div>
        <ul className="space-y-3">
          {SHORTCUTS.map((shortcut, i) => (
            <li key={i} className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((k, j) => (
                  k === "–" ? (
                    <span key={j} className="text-xs text-muted-foreground">{k}</span>
                  ) : (
                    <kbd
                      key={j}
                      className="min-w-[24px] rounded border border-border bg-surface px-1.5 py-0.5 text-center text-xs font-medium text-foreground"
                    >
                      {k}
                    </kbd>
                  )
                ))}
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">
          Shortcuts are disabled when typing in input fields.
        </p>
      </div>
    </div>
  );
}
