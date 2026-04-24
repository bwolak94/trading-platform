/**
 * Crypto Events & Earnings Calendar
 * Shows upcoming events that may impact trading
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";

type ImpactLevel = "HIGH" | "MEDIUM" | "LOW";

interface CalendarEvent {
  id: string;
  date: string;
  event_name: string;
  affected_asset: string | null;
  impact: ImpactLevel;
  description: string | null;
}

interface CalendarEventsResponse {
  events: CalendarEvent[];
  total: number;
}

async function fetchCalendarEvents(daysAhead: number): Promise<CalendarEventsResponse> {
  const { data } = await axios.get<CalendarEventsResponse>("/api/v1/calendar/events", {
    params: { days_ahead: daysAhead },
  });
  return data;
}

const IMPACT_STYLES: Record<ImpactLevel, { badge: string; dot: string }> = {
  HIGH: {
    badge: "bg-bearish/10 text-bearish border-bearish/30",
    dot: "bg-bearish",
  },
  MEDIUM: {
    badge: "bg-amber-400/10 text-amber-400 border-amber-400/30",
    dot: "bg-amber-400",
  },
  LOW: {
    badge: "bg-gray-500/10 text-gray-400 border-gray-500/30",
    dot: "bg-gray-500",
  },
};

function getDaysUntil(dateStr: string): number {
  const event = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  event.setHours(0, 0, 0, 0);
  return Math.round((event.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function formatDaysLabel(days: number): string {
  if (days < 0) return `${Math.abs(days)}d ago`;
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  return `in ${days}d`;
}

function EventSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-white/5" />
      ))}
    </div>
  );
}

function EventRow({ event }: { event: CalendarEvent }) {
  const daysUntil = getDaysUntil(event.date);
  const isToday = daysUntil === 0;
  const styles = IMPACT_STYLES[event.impact];

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-2.5 ${
        isToday && event.impact === "HIGH"
          ? "border-bearish/40 bg-bearish/5"
          : "border-border/40 bg-surface/50"
      }`}
    >
      <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${styles.dot}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-medium text-gray-200">{event.event_name}</span>
          {isToday && event.impact === "HIGH" && (
            <span className="rounded bg-bearish/20 px-1 py-0.5 text-[9px] font-bold text-bearish">
              AVOID TRADING
            </span>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-500">
          <span>{event.affected_asset ?? "MACRO"}</span>
          <span>•</span>
          <span>
            {new Date(event.date).toLocaleDateString([], {
              month: "short",
              day: "numeric",
            })}
          </span>
        </div>
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1">
        <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${styles.badge}`}>
          {event.impact}
        </span>
        <span className="text-[10px] text-gray-500">{formatDaysLabel(daysUntil)}</span>
      </div>
    </div>
  );
}

export function EarningsCalendarPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["calendar-events"],
    queryFn: () => fetchCalendarEvents(14),
    refetchInterval: 5 * 60_000,
    retry: false,
  });

  const events = [...(data?.events ?? [])].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );

  const todayHighImpact = events.filter(
    (e) => getDaysUntil(e.date) === 0 && e.impact === "HIGH",
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Events Calendar</h2>
        <span className="text-xs text-gray-500">Next 14 days</span>
      </div>

      {todayHighImpact.length > 0 && (
        <div className="mb-3 rounded border border-bearish/30 bg-bearish/10 px-3 py-2 text-xs text-bearish">
          {todayHighImpact.length} high-impact event{todayHighImpact.length > 1 ? "s" : ""} today
          — consider reducing exposure
        </div>
      )}

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Calendar data unavailable
        </div>
      )}

      {isLoading ? (
        <EventSkeleton />
      ) : events.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-500">
          No upcoming events in the next 14 days
        </p>
      ) : (
        <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
          {events.map((event) => (
            <EventRow key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}
