/**
 * Frontend error logger — ships uncaught JS errors to the backend
 * so they appear in server logs alongside API errors.
 */

interface FrontendErrorPayload {
  message: string;
  stack?: string;
  url: string;
  component?: string;
  extra?: Record<string, unknown>;
}

let _queue: FrontendErrorPayload[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;

function flushQueue() {
  if (_queue.length === 0) return;
  const batch = _queue.splice(0, _queue.length);
  // Fire-and-forget; don't await to avoid unhandled rejection chains
  void fetch("/api/v1/monitoring/frontend-errors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ errors: batch }),
    keepalive: true,
  }).catch(() => {
    // Silently ignore — logging failure must never crash the app
  });
}

export function logFrontendError(
  message: string,
  opts: { stack?: string; component?: string; extra?: Record<string, unknown> } = {},
): void {
  _queue.push({
    message,
    stack: opts.stack,
    url: window.location.pathname,
    component: opts.component,
    extra: opts.extra,
  });

  // Debounce: flush after 2s of inactivity (batches rapid errors)
  if (_flushTimer) clearTimeout(_flushTimer);
  _flushTimer = setTimeout(flushQueue, 2_000);
}

/** Install global window.onerror and unhandledrejection listeners. */
export function installGlobalErrorHandlers(): void {
  window.onerror = (message, _source, _line, _col, error) => {
    logFrontendError(String(message), { stack: error?.stack });
    return false; // Don't suppress default browser error handling
  };

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    const message =
      reason instanceof Error ? reason.message : String(reason ?? "Unhandled promise rejection");
    const stack = reason instanceof Error ? reason.stack : undefined;
    logFrontendError(message, { stack });
  });
}
