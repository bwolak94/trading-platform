import { useQuery } from "@tanstack/react-query";
import {
  fetchHealth,
  fetchAgentStatus,
  fetchDayTradeStatus,
} from "../../api/client";
import { useWebSocket } from "../../hooks/useWebSocket";

interface ServiceStatus {
  label: string;
  status: "ok" | "error" | "unknown";
  detail: string;
}

export function SystemHealth() {
  const { isConnected } = useWebSocket();

  const { data: health, isError: healthError } = useQuery({
    queryKey: ["health-check"],
    queryFn: async () => {
      const start = performance.now();
      const result = await fetchHealth();
      const latency = Math.round(performance.now() - start);
      return { ...result, latency };
    },
    refetchInterval: 10_000,
  });

  const { data: swingStatus, isError: swingError } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    refetchInterval: 10_000,
  });

  const { data: dayStatus, isError: dayError } = useQuery({
    queryKey: ["day-trade-status"],
    queryFn: fetchDayTradeStatus,
    refetchInterval: 10_000,
  });

  const services: ServiceStatus[] = [
    {
      label: "API",
      status: healthError ? "error" : health?.status === "ok" ? "ok" : "unknown",
      detail: health ? `${(health as Record<string, unknown>).latency}ms latency` : "Checking...",
    },
    {
      label: "WebSocket",
      status: isConnected ? "ok" : "error",
      detail: isConnected ? "Connected" : "Disconnected",
    },
    {
      label: "Swing Agent",
      status: swingError ? "error" : swingStatus?.running ? "ok" : "unknown",
      detail: swingError
        ? "Unavailable"
        : swingStatus?.running
          ? `${swingStatus.scan_count} scans`
          : "Stopped",
    },
    {
      label: "Day Trading",
      status: dayError ? "error" : dayStatus ? "ok" : "unknown",
      detail: dayError
        ? "Unavailable"
        : dayStatus
          ? `Active`
          : "Unknown",
    },
  ];

  const statusIcon = (s: ServiceStatus["status"]) => {
    switch (s) {
      case "ok":
        return (
          <span
            className="inline-block h-2.5 w-2.5 rounded-full bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]"
            aria-label="OK"
          />
        );
      case "error":
        return (
          <span
            className="inline-block h-2.5 w-2.5 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]"
            aria-label="Error"
          />
        );
      default:
        return (
          <span
            className="inline-block h-2.5 w-2.5 rounded-full bg-yellow-500"
            aria-label="Unknown"
          />
        );
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4" aria-label="System health status">
      <h3 className="mb-3 text-sm font-semibold text-white">System Health</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {services.map((svc) => (
          <div
            key={svc.label}
            className="flex items-center justify-between rounded bg-background px-3 py-2"
          >
            <div className="flex items-center gap-2">
              {statusIcon(svc.status)}
              <span className="text-sm text-gray-300">{svc.label}</span>
            </div>
            <span className="text-xs text-gray-500">{svc.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
