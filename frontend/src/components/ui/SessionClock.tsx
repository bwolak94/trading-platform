import { useEffect, useState } from "react";

interface Session {
  name: string;
  short: string;
  openHourUTC: number;
  closeHourUTC: number;
  color: string;
  bgColor: string;
}

const SESSIONS: Session[] = [
  { name: "Asian", short: "AS", openHourUTC: 0, closeHourUTC: 9, color: "text-yellow-400", bgColor: "bg-yellow-400/15 border-yellow-400/30" },
  { name: "London", short: "LN", openHourUTC: 8, closeHourUTC: 17, color: "text-blue-400", bgColor: "bg-blue-400/15 border-blue-400/30" },
  { name: "New York", short: "NY", openHourUTC: 13, closeHourUTC: 22, color: "text-green-400", bgColor: "bg-green-400/15 border-green-400/30" },
];

function isSessionActive(session: Session, utcHour: number): boolean {
  if (session.openHourUTC < session.closeHourUTC) {
    return utcHour >= session.openHourUTC && utcHour < session.closeHourUTC;
  }
  return utcHour >= session.openHourUTC || utcHour < session.closeHourUTC;
}

function formatUTCTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
}

export function SessionClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const utcHour = now.getUTCHours();
  const activeSessions = SESSIONS.filter((s) => isSessionActive(s, utcHour));

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Trading session clock">
      <span className="font-mono text-sm text-muted-foreground" title="Current UTC time">
        {formatUTCTime(now)} UTC
      </span>
      {SESSIONS.map((session) => {
        const active = isSessionActive(session, utcHour);
        return (
          <div
            key={session.name}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all duration-300 ${
              active
                ? `${session.bgColor} ${session.color}`
                : "border-border/30 text-muted-foreground/50"
            }`}
            title={`${session.name}: ${session.openHourUTC}:00–${session.closeHourUTC}:00 UTC`}
            aria-label={`${session.name} session ${active ? "open" : "closed"}`}
          >
            {active && (
              <span
                className={`h-1.5 w-1.5 rounded-full animate-pulse ${session.color.replace("text-", "bg-")}`}
                aria-hidden="true"
              />
            )}
            {session.short}
          </div>
        );
      })}
      {activeSessions.length === 0 && (
        <span className="text-xs text-muted-foreground/50">No major session</span>
      )}
    </div>
  );
}
