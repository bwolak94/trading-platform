/**
 * Macro Calendar Countdown Widget
 * Always-visible strip showing time until next high-impact macro event.
 * Red pulsing dot when < 1 hour away.
 */

import { useState, useEffect, useMemo } from "react";

interface MacroEvent {
  name: string;
  datetime: Date;
  impact: "HIGH" | "MEDIUM";
}

// Hardcoded upcoming events — in production these would come from the backend calendar
function buildUpcomingEvents(): MacroEvent[] {
  const now = new Date();

  // Generate a rolling set of plausible future dates for demo
  const raw: { name: string; dayOffset: number; hour: number; impact: "HIGH" | "MEDIUM" }[] = [
    { name: "FOMC Minutes",  dayOffset: 3,  hour: 18, impact: "HIGH" },
    { name: "CPI Release",   dayOffset: 7,  hour: 12, impact: "HIGH" },
    { name: "NFP",           dayOffset: 10, hour: 12, impact: "HIGH" },
    { name: "PPI Release",   dayOffset: 14, hour: 12, impact: "HIGH" },
    { name: "Fed Statement", dayOffset: 21, hour: 18, impact: "HIGH" },
    { name: "GDP Advance",   dayOffset: 25, hour: 12, impact: "HIGH" },
    { name: "ECB Decision",  dayOffset: 28, hour: 12, impact: "HIGH" },
  ];

  return raw.map(({ name, dayOffset, hour, impact }) => {
    const dt = new Date(now);
    dt.setDate(dt.getDate() + dayOffset);
    dt.setUTCHours(hour, 0, 0, 0);
    return { name, datetime: dt, impact };
  }).filter((e) => e.datetime > now).sort((a, b) => a.datetime.getTime() - b.datetime.getTime());
}

function formatCountdown(ms: number): string {
  if (ms <= 0) return "Now";
  const totalMin = Math.floor(ms / 60000);
  const days = Math.floor(totalMin / 1440);
  const hours = Math.floor((totalMin % 1440) / 60);
  const mins = totalMin % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export function MacroCountdownWidget() {
  const events = useMemo(buildUpcomingEvents, []);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => { setNow(Date.now()); }, 30_000);
    return () => { clearInterval(t); };
  }, []);

  const next = events[0];
  if (!next) return null;

  const msUntil = next.datetime.getTime() - now;
  const isImminent = msUntil < 3_600_000; // < 1 hour
  const isCritical = msUntil < 900_000;   // < 15 min

  return (
    <div className={`rounded-lg border px-4 py-2.5 ${
      isCritical
        ? "border-bearish/50 bg-bearish/10 animate-pulse"
        : isImminent
        ? "border-amber-500/40 bg-amber-500/10"
        : "border-border bg-surface"
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${
            isCritical ? "bg-bearish animate-ping" : isImminent ? "bg-amber-400" : "bg-gray-500"
          }`} />
          <span className="text-xs text-gray-400">Next event:</span>
          <span className={`text-xs font-semibold ${isCritical ? "text-bearish" : isImminent ? "text-amber-400" : "text-white"}`}>
            {next.name}
          </span>
        </div>

        <div className="flex items-center gap-4">
          <span className={`font-mono text-sm font-bold ${
            isCritical ? "text-bearish" : isImminent ? "text-amber-400" : "text-white"
          }`}>
            {formatCountdown(msUntil)}
          </span>
          <span className="text-[10px] text-gray-500">
            {next.datetime.toUTCString().slice(0, 22)} UTC
          </span>
        </div>
      </div>

      {/* Upcoming strip */}
      {events.length > 1 && (
        <div className="mt-2 flex gap-3 overflow-x-auto pb-1">
          {events.slice(1, 5).map((ev, i) => {
            const ms = ev.datetime.getTime() - now;
            return (
              <span key={i} className="shrink-0 text-[9px] text-gray-600">
                {ev.name} <span className="text-gray-500">{formatCountdown(ms)}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
