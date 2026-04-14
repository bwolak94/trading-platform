import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
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
                onClick={() => this.setState({ hasError: false, error: null })}
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
