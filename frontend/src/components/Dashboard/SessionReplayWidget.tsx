/**
 * Session Replay (Basic)
 * Records and replays key events from the current trading session
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../store";
import { useWebSocket } from "../../hooks/useWebSocket";

type EventType =
  | "NEW_SIGNAL"
  | "REGIME_CHANGE"
  | "POSITION_OPEN"
  | "POSITION_CLOSE"
  | "KILL_SWITCH"
  | "SYSTEM";

interface SessionEvent {
  id: string;
  type: EventType;
  timestamp: number;
  data: Record<string, unknown>;
  label: string;
}

type RecordingState = "idle" | "recording" | "replaying";

const EVENT_TYPE_STYLES: Record<EventType, { badge: string; icon: string }> = {
  NEW_SIGNAL: { badge: "bg-blue-400/10 text-blue-400 border-blue-400/30", icon: "S" },
  REGIME_CHANGE: { badge: "bg-purple-400/10 text-purple-400 border-purple-400/30", icon: "R" },
  POSITION_OPEN: { badge: "bg-bullish/10 text-bullish border-bullish/30", icon: "O" },
  POSITION_CLOSE: { badge: "bg-amber-400/10 text-amber-400 border-amber-400/30", icon: "C" },
  KILL_SWITCH: { badge: "bg-bearish/10 text-bearish border-bearish/30", icon: "K" },
  SYSTEM: { badge: "bg-gray-500/10 text-gray-400 border-gray-500/30", icon: "•" },
};

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function SessionReplayWidget() {
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [replayEvents, setReplayEvents] = useState<SessionEvent[]>([]);
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [replayIndex, setReplayIndex] = useState(0);
  const recordingRef = useRef(false);
  const replayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { lastMessage } = useWebSocket();
  const { activeSignals, systemPaused } = useAppStore();
  const prevSignalCountRef = useRef(0);
  const prevPausedRef = useRef(false);

  // Record WebSocket events
  useEffect(() => {
    if (!recordingRef.current || !lastMessage) return;
    let event: SessionEvent | null = null;

    if (lastMessage.type === "NEW_SIGNAL") {
      const p = lastMessage.payload;
      event = {
        id: generateId(),
        type: "NEW_SIGNAL",
        timestamp: Date.now(),
        data: p,
        label: `New Signal: ${String(p["asset"] ?? "")} ${String(p["direction"] ?? "")}`,
      };
    } else if (lastMessage.type === "REGIME_CHANGE") {
      const p = lastMessage.payload;
      event = {
        id: generateId(),
        type: "REGIME_CHANGE",
        timestamp: Date.now(),
        data: p,
        label: `Regime Change: ${String(p["asset"] ?? "")} → ${String(p["regime"] ?? "")}`,
      };
    } else if (lastMessage.type === "KILL_SWITCH_TRIGGERED") {
      event = {
        id: generateId(),
        type: "KILL_SWITCH",
        timestamp: Date.now(),
        data: lastMessage.payload,
        label: "Kill Switch Triggered",
      };
    }

    if (event) {
      setEvents((prev) => [event!, ...prev].slice(0, 200));
    }
  }, [lastMessage]);

  // Detect new signals from store
  useEffect(() => {
    if (!recordingRef.current) return;
    if (activeSignals.length > prevSignalCountRef.current) {
      const newest = activeSignals[0];
      if (newest) {
        const event: SessionEvent = {
          id: generateId(),
          type: "NEW_SIGNAL",
          timestamp: Date.now(),
          data: newest as unknown as Record<string, unknown>,
          label: `Signal: ${newest.asset} ${newest.direction} (${newest.confidence}%)`,
        };
        setEvents((prev) => [event, ...prev].slice(0, 200));
      }
    }
    prevSignalCountRef.current = activeSignals.length;
  }, [activeSignals]);

  // Detect kill switch toggle
  useEffect(() => {
    if (!recordingRef.current) return;
    if (systemPaused && !prevPausedRef.current) {
      const event: SessionEvent = {
        id: generateId(),
        type: "KILL_SWITCH",
        timestamp: Date.now(),
        data: {},
        label: "System Paused (Kill Switch)",
      };
      setEvents((prev) => [event, ...prev].slice(0, 200));
    }
    prevPausedRef.current = systemPaused;
  }, [systemPaused]);

  // Auto-scroll to top when recording
  useEffect(() => {
    if (recordingState === "recording" && listRef.current) {
      listRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [events, recordingState]);

  const handleStartRecording = useCallback(() => {
    recordingRef.current = true;
    setRecordingState("recording");
    setEvents([]);
    const systemEvent: SessionEvent = {
      id: generateId(),
      type: "SYSTEM",
      timestamp: Date.now(),
      data: {},
      label: "Recording started",
    };
    setEvents([systemEvent]);
  }, []);

  const handleStopRecording = useCallback(() => {
    recordingRef.current = false;
    setRecordingState("idle");
  }, []);

  const handleReplay = useCallback(() => {
    if (events.length === 0) return;
    const sorted = [...events].sort((a, b) => a.timestamp - b.timestamp);
    setReplayEvents(sorted);
    setReplayIndex(0);
    setRecordingState("replaying");

    let idx = 0;
    const step = () => {
      setReplayIndex(idx);
      idx++;
      if (idx < sorted.length) {
        replayTimerRef.current = setTimeout(step, 200); // 5x speed
      } else {
        setRecordingState("idle");
      }
    };
    replayTimerRef.current = setTimeout(step, 200);
  }, [events]);

  const handleStopReplay = useCallback(() => {
    if (replayTimerRef.current) clearTimeout(replayTimerRef.current);
    setRecordingState("idle");
  }, []);

  useEffect(() => {
    return () => {
      if (replayTimerRef.current) clearTimeout(replayTimerRef.current);
    };
  }, []);

  const handleExport = useCallback(() => {
    const json = JSON.stringify(events, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session_replay_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [events]);

  const displayEvents =
    recordingState === "replaying"
      ? replayEvents.slice(0, replayIndex + 1)
      : events;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-white">Session Replay</h2>
          {recordingState === "recording" && (
            <span className="flex items-center gap-1 rounded bg-bearish/10 px-1.5 py-0.5 text-[10px] text-bearish">
              <span className="h-1.5 w-1.5 rounded-full bg-bearish animate-pulse" />
              REC
            </span>
          )}
          {recordingState === "replaying" && (
            <span className="rounded bg-blue-400/10 px-1.5 py-0.5 text-[10px] text-blue-400">
              REPLAY {replayIndex + 1}/{replayEvents.length}
            </span>
          )}
        </div>
        <div className="flex gap-1.5">
          {recordingState === "idle" && (
            <>
              <button
                type="button"
                onClick={handleStartRecording}
                className="rounded border border-bearish/40 bg-bearish/10 px-2 py-0.5 text-[10px] font-medium text-bearish transition-colors hover:bg-bearish/20"
                aria-label="Start recording session"
              >
                Record
              </button>
              {events.length > 0 && (
                <>
                  <button
                    type="button"
                    onClick={handleReplay}
                    className="rounded border border-blue-400/40 bg-blue-400/10 px-2 py-0.5 text-[10px] font-medium text-blue-400 transition-colors hover:bg-blue-400/20"
                    aria-label="Replay recorded session"
                  >
                    Replay
                  </button>
                  <button
                    type="button"
                    onClick={handleExport}
                    className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-gray-400 transition-colors hover:text-white"
                    aria-label="Export session events as JSON"
                  >
                    Export
                  </button>
                </>
              )}
            </>
          )}
          {recordingState === "recording" && (
            <button
              type="button"
              onClick={handleStopRecording}
              className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-gray-400 transition-colors hover:text-white"
              aria-label="Stop recording"
            >
              Stop
            </button>
          )}
          {recordingState === "replaying" && (
            <button
              type="button"
              onClick={handleStopReplay}
              className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-gray-400 transition-colors hover:text-white"
              aria-label="Stop replay"
            >
              Stop
            </button>
          )}
        </div>
      </div>

      <div
        ref={listRef}
        className="max-h-64 overflow-y-auto space-y-1 pr-1"
        aria-live="polite"
        aria-label="Session events timeline"
      >
        {displayEvents.length === 0 ? (
          <p className="py-6 text-center text-xs text-gray-500">
            {recordingState === "idle"
              ? "Click Record to start capturing session events"
              : "No events recorded yet"}
          </p>
        ) : (
          displayEvents.map((event) => {
            const styles = EVENT_TYPE_STYLES[event.type];
            return (
              <div
                key={event.id}
                className="flex items-start gap-2 rounded border border-border/20 px-2 py-1.5"
              >
                <span
                  className={`shrink-0 rounded border px-1 py-0.5 text-[9px] font-bold ${styles.badge}`}
                  aria-hidden="true"
                >
                  {styles.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-gray-200">{event.label}</p>
                </div>
                <span className="shrink-0 text-[10px] text-gray-600">
                  {formatTime(event.timestamp)}
                </span>
              </div>
            );
          })
        )}
      </div>

      {events.length > 0 && (
        <p className="mt-2 text-[10px] text-gray-600">
          {events.length} event{events.length !== 1 ? "s" : ""} recorded
        </p>
      )}
    </div>
  );
}
