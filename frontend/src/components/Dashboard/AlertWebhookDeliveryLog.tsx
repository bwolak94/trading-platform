/**
 * B8: Alert Webhook Delivery Log
 *
 * Table of outgoing webhook calls (Telegram, Discord, custom URL) with
 * timestamp, payload snippet, HTTP status, and retry count.
 */

import { useQuery } from "@tanstack/react-query";

interface WebhookEntry {
  id: string;
  channel: string;
  url: string;
  timestamp: string;
  payload_snippet: string;
  http_status: number | null;
  retry_count: number;
  success: boolean;
}

async function fetchWebhookLog(): Promise<WebhookEntry[]> {
  const resp = await fetch("/api/v1/notifications/webhook-log");
  if (!resp.ok) throw new Error("Failed to fetch webhook log");
  return resp.json();
}

function StatusBadge({ status, success }: { readonly status: number | null; readonly success: boolean }) {
  const cls = success
    ? "bg-bullish/20 text-bullish"
    : "bg-bearish/20 text-bearish";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold ${cls}`}>
      {status ?? "—"}
    </span>
  );
}

export function AlertWebhookDeliveryLog() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["webhook-delivery-log"],
    queryFn: fetchWebhookLog,
    staleTime: 30_000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Webhook Delivery Log</h3>
          <p className="text-xs text-gray-400">Outgoing alert deliveries with status and retry count</p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          className="rounded border border-border px-2 py-1 text-xs text-gray-400 transition-colors hover:border-accent hover:text-white"
          aria-label="Refresh webhook log"
        >
          Refresh
        </button>
      </div>

      {isLoading && (
        <div className="flex h-32 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-32 items-center justify-center text-xs text-bearish">Failed to load log</div>
      )}

      {!isLoading && !isError && data && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-gray-500">
                <th className="pb-2 text-left font-medium">Time</th>
                <th className="pb-2 text-left font-medium">Channel</th>
                <th className="pb-2 text-left font-medium">Payload</th>
                <th className="pb-2 text-center font-medium">Status</th>
                <th className="pb-2 text-center font-medium">Retries</th>
              </tr>
            </thead>
            <tbody>
              {data.map((entry) => (
                <tr key={entry.id} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 font-mono text-gray-400">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="py-1.5 font-medium text-gray-300">{entry.channel}</td>
                  <td className="max-w-[180px] truncate py-1.5 text-gray-400" title={entry.payload_snippet}>
                    {entry.payload_snippet}
                  </td>
                  <td className="py-1.5 text-center">
                    <StatusBadge status={entry.http_status} success={entry.success} />
                  </td>
                  <td className="py-1.5 text-center text-gray-500">{entry.retry_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length === 0 && (
            <div className="py-8 text-center text-xs text-gray-500">No webhook deliveries yet</div>
          )}
        </div>
      )}
    </div>
  );
}
