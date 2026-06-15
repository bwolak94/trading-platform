import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** Optional component name for structured error reporting */
  componentName?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/** F2: Report errors to the backend monitoring endpoint for server-side logging. */
function reportErrorToBackend(error: Error, componentName?: string): void {
  try {
    fetch("/api/v1/monitoring/frontend-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        errors: [
          {
            message: error.message,
            stack: error.stack ?? null,
            url: window.location.href,
            component: componentName ?? null,
          },
        ],
      }),
      keepalive: true,
    }).catch(() => {
      // Non-fatal — don't surface reporting failures to the user
    });
  } catch {
    // ignore
  }
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
    // F2: Send error to backend for server-side aggregation
    reportErrorToBackend(error, this.props.componentName);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="flex min-h-[200px] items-center justify-center rounded-lg border border-bearish/30 bg-bearish/5 p-8">
            <div className="text-center">
              <h3 className="text-lg font-semibold text-bearish">
                Something went wrong
              </h3>
              <p className="mt-2 text-sm text-gray-400">
                {this.state.error?.message}
              </p>
              <button
                onClick={() => { this.setState({ hasError: false, error: null }); }}
                className="mt-4 rounded bg-accent px-4 py-2 text-sm text-white hover:bg-accent/80"
                aria-label="Try again"
              >
                Try Again
              </button>
            </div>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
