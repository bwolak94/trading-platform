/**
 * CollapsiblePanel — wraps any panel with a collapse-to-title-bar toggle.
 * State persists in localStorage keyed by panelId.
 */

import { useState, useEffect, type ReactNode } from "react";

interface CollapsiblePanelProps {
  panelId: string;
  title: string;
  children: ReactNode;
  defaultCollapsed?: boolean;
  /** Extra classes applied to the outer container */
  className?: string;
}

export function CollapsiblePanel({
  panelId,
  title,
  children,
  defaultCollapsed = false,
  className = "",
}: CollapsiblePanelProps) {
  const storageKey = `panel_collapsed_${panelId}`;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored !== null ? stored === "true" : defaultCollapsed;
    } catch {
      return defaultCollapsed;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, String(collapsed));
    } catch {
      // storage unavailable — ignore
    }
  }, [collapsed, storageKey]);

  return (
    <div className={`rounded-lg border border-border bg-surface ${className}`}>
      <button
        type="button"
        onClick={() => { setCollapsed((c) => !c); }}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        aria-expanded={!collapsed}
        aria-controls={`panel-body-${panelId}`}
      >
        <span className="text-sm font-semibold text-white">{title}</span>
        <svg
          className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {!collapsed && (
        <div id={`panel-body-${panelId}`} className="px-4 pb-4">
          {children}
        </div>
      )}
    </div>
  );
}
