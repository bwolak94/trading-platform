/**
 * AssetSearchSelect — searchable dropdown for all Binance USDT futures + forex pairs.
 *
 * Loads the full symbol list from the backend API (cached for 5 min via React Query).
 * Supports keyboard navigation and accessibility.
 */
import { useId, useRef, useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllSymbols } from "../../api/client";
import type { SymbolOption } from "../../api/client";

// Fallback static list so the select is usable before the API responds
const STATIC_FALLBACK: SymbolOption[] = [
  { label: "BTC/USDT", value: "BTCUSDT" },
  { label: "ETH/USDT", value: "ETHUSDT" },
  { label: "SOL/USDT", value: "SOLUSDT" },
  { label: "BNB/USDT", value: "BNBUSDT" },
  { label: "XRP/USDT", value: "XRPUSDT" },
];

interface AssetSearchSelectProps {
  /** Currently selected symbol value, e.g. "BTCUSDT" */
  value: string;
  /** Called with the new symbol value when the user selects */
  onChange: (value: string, label: string) => void;
  /** Additional class names for the trigger button */
  className?: string;
  /** Whether to include forex pairs in the list (default true) */
  includeForex?: boolean;
  /** Accessible label for the control */
  "aria-label"?: string;
}

export function AssetSearchSelect({
  value,
  onChange,
  className = "",
  includeForex = true,
  "aria-label": ariaLabel = "Select asset",
}: AssetSearchSelectProps) {
  const inputId = useId();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data } = useQuery({
    queryKey: ["all-symbols"],
    queryFn: fetchAllSymbols,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,
  });

  const allOptions: SymbolOption[] = [
    ...(data?.crypto ?? STATIC_FALLBACK),
    ...(includeForex ? (data?.forex ?? []) : []),
  ];

  const filtered = query.trim()
    ? allOptions.filter(
        (opt) =>
          opt.label.toLowerCase().includes(query.toLowerCase()) ||
          opt.value.toLowerCase().includes(query.toLowerCase()),
      )
    : allOptions;

  const currentLabel =
    allOptions.find((o) => o.value === value)?.label ??
    value.replace("USDT", "/USDT");

  const handleSelect = useCallback(
    (opt: SymbolOption) => {
      onChange(opt.value, opt.label);
      setOpen(false);
      setQuery("");
    },
    [onChange],
  );

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => { document.removeEventListener("mousedown", handleClick); };
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => { setOpen((v) => !v); }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        className="flex min-h-[36px] w-full min-w-[130px] items-center justify-between gap-2 rounded border border-border bg-background px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span className="truncate">{currentLabel}</span>
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-56 overflow-hidden rounded-lg border border-border bg-background shadow-xl">
          {/* Search input */}
          <div className="border-b border-border px-2 py-2">
            <label htmlFor={inputId} className="sr-only">
              Search {ariaLabel}
            </label>
            <input
              ref={inputRef}
              id={inputId}
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); }}
              placeholder="Search symbol…"
              className="w-full rounded border border-border bg-surface px-2 py-1 text-sm text-white placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-accent"
              aria-controls={listId}
              aria-autocomplete="list"
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setOpen(false);
                  setQuery("");
                }
                if (e.key === "Enter" && filtered.length > 0 && filtered[0]) {
                  handleSelect(filtered[0]);
                }
              }}
            />
          </div>

          {/* Count */}
          <div className="px-3 py-1 text-[10px] text-muted-foreground">
            {filtered.length} of {allOptions.length} pairs
          </div>

          {/* Options list */}
          <ul
            id={listId}
            role="listbox"
            aria-label={ariaLabel}
            className="max-h-60 overflow-y-auto"
          >
            {filtered.length === 0 ? (
              <li className="px-3 py-4 text-center text-sm text-muted-foreground">
                No matches
              </li>
            ) : (
              filtered.map((opt) => (
                <li
                  key={opt.value}
                  role="option"
                  aria-selected={opt.value === value}
                  onClick={() => { handleSelect(opt); }}
                  className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors hover:bg-surface ${
                    opt.value === value ? "bg-accent/20 text-accent" : "text-foreground"
                  }`}
                >
                  <span className="font-medium">{opt.label}</span>
                  {opt.value === value && (
                    <svg className="h-3.5 w-3.5 shrink-0 text-accent" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
