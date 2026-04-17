interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`animate-pulse rounded bg-surface ${className}`} />;
}

export function CardSkeleton() {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

interface ChartSkeletonProps {
  height?: string;
  className?: string;
}

export function ChartSkeleton({ height = "h-80", className = "" }: ChartSkeletonProps) {
  return (
    <div className={`rounded-lg border border-border bg-surface p-4 space-y-3 ${className}`}>
      {/* Chart header area */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-1/4" />
        <div className="flex gap-2">
          <Skeleton className="h-6 w-16 rounded" />
          <Skeleton className="h-6 w-16 rounded" />
          <Skeleton className="h-6 w-16 rounded" />
        </div>
      </div>
      {/* Chart body - pulsing rectangle matching chart dimensions */}
      <Skeleton className={`${height} w-full rounded`} />
      {/* X-axis labels */}
      <div className="flex justify-between">
        <Skeleton className="h-3 w-10" />
        <Skeleton className="h-3 w-10" />
        <Skeleton className="h-3 w-10" />
        <Skeleton className="h-3 w-10" />
        <Skeleton className="h-3 w-10" />
      </div>
    </div>
  );
}

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  className?: string;
}

export function TableSkeleton({ rows = 5, columns = 4, className = "" }: TableSkeletonProps) {
  return (
    <div className={`rounded-lg border border-border bg-surface overflow-hidden ${className}`}>
      {/* Table header */}
      <div className="flex gap-4 border-b border-border p-4">
        {Array.from({ length: columns }, (_, i) => (
          <Skeleton key={`header-${i}`} className="h-4 flex-1" />
        ))}
      </div>
      {/* Table rows */}
      {Array.from({ length: rows }, (_, rowIdx) => (
        <div
          key={`row-${rowIdx}`}
          className="flex gap-4 border-b border-border/50 p-4 last:border-b-0"
        >
          {Array.from({ length: columns }, (_, colIdx) => (
            <Skeleton
              key={`cell-${rowIdx}-${colIdx}`}
              className={`h-3 flex-1 ${colIdx === 0 ? "max-w-[40%]" : ""}`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
