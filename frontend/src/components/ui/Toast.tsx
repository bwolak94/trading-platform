import {
  useState,
  useEffect,
  useCallback,
  createContext,
  useContext,
  type ReactNode,
} from "react";

interface Toast {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  duration: number;
}

interface ToastContextValue {
  addToast: (
    message: string,
    type?: Toast["type"],
    duration?: number,
  ) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback(
    (
      message: string,
      type: Toast["type"] = "info",
      duration = 5000,
    ) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, type, duration }]);
    },
    [],
  );

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
}

const typeStyles: Record<Toast["type"], string> = {
  info: "border-blue-500/40 bg-blue-500/10 text-blue-400",
  success: "border-bullish/40 bg-bullish/10 text-bullish",
  warning: "border-warning/40 bg-warning/10 text-warning",
  error: "border-bearish/40 bg-bearish/10 text-bearish",
};

function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[];
  onRemove: (id: number) => void;
}) {
  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast;
  onRemove: (id: number) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onRemove(toast.id);
    }, toast.duration);
    return () => { clearTimeout(timer); };
  }, [toast.id, toast.duration, onRemove]);

  return (
    <div
      className={`pointer-events-auto flex items-center gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur ${typeStyles[toast.type]}`}
      role="alert"
    >
      <span className="flex-1">{toast.message}</span>
      <button
        type="button"
        onClick={() => { onRemove(toast.id); }}
        className="shrink-0 opacity-60 hover:opacity-100"
        aria-label="Dismiss notification"
      >
        x
      </button>
    </div>
  );
}
