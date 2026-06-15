import { useQuery } from "@tanstack/react-query";
import { fetchFearGreed } from "../../api/client";

function getColor(value: number): string {
  if (value <= 25) return "#f87171"; // extreme fear - red
  if (value <= 45) return "#fb923c"; // fear - orange
  if (value <= 55) return "#facc15"; // neutral - yellow
  if (value <= 75) return "#86efac"; // greed - light green
  return "#4ade80"; // extreme greed - green
}

function CircularGauge({ value }: { value: number }) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const progress = (value / 100) * circumference;
  const color = getColor(value);

  return (
    <div className="relative flex h-24 w-24 items-center justify-center">
      <svg width="96" height="96" viewBox="0 0 96 96" className="-rotate-90">
        <circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth="8"
        />
        <circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-xl font-bold" style={{ color }}>
          {value}
        </span>
      </div>
    </div>
  );
}

export function FearGreedWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ["fear-greed"],
    queryFn: fetchFearGreed,
    refetchInterval: 5 * 60 * 1000, // refetch every 5 min (API cached 1h server-side)
  });

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-background p-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Fear &amp; Greed Index</h3>
        <p className="text-xs text-muted-foreground">Crypto market sentiment</p>
      </div>

      {isLoading ? (
        <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
          Loading...
        </div>
      ) : data ? (
        <div className="flex items-center gap-4">
          <CircularGauge value={data.value} />
          <div className="flex flex-col gap-1">
            <span
              className="text-base font-semibold"
              style={{ color: getColor(data.value) }}
            >
              {data.value_classification}
            </span>
            <span className="text-xs text-muted-foreground">
              Updated{" "}
              {new Date(parseInt(data.timestamp) * 1000).toLocaleDateString()}
            </span>
            {data.error && (
              <span className="text-xs text-amber-400">Cached data</span>
            )}
          </div>
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">Unavailable</div>
      )}
    </div>
  );
}
