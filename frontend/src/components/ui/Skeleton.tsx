export function Skeleton({ className = "" }: { className?: string }) {
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
