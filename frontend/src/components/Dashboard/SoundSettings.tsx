/**
 * Sound Profile Settings
 * Configure alert sounds per signal type using Web Audio API
 */

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "sound_preferences";

type SoundCategory = "NEW_SIGNAL_LONG" | "NEW_SIGNAL_SHORT" | "HIGH_CONFIDENCE" | "KILL_SWITCH";

interface SoundPreferences {
  enabled: Record<SoundCategory, boolean>;
  volume: number;
}

const CATEGORY_LABELS: Record<SoundCategory, string> = {
  NEW_SIGNAL_LONG: "New Long Signal",
  NEW_SIGNAL_SHORT: "New Short Signal",
  HIGH_CONFIDENCE: "High Confidence Alert",
  KILL_SWITCH: "Kill Switch Trigger",
};

const CATEGORY_DESCRIPTIONS: Record<SoundCategory, string> = {
  NEW_SIGNAL_LONG: "880Hz sine — ascending tone",
  NEW_SIGNAL_SHORT: "440Hz sine — descending tone",
  HIGH_CONFIDENCE: "1000Hz + 1200Hz sequence",
  KILL_SWITCH: "200Hz alarm pattern",
};

function loadPreferences(): SoundPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SoundPreferences>;
      return {
        enabled: {
          NEW_SIGNAL_LONG: parsed.enabled?.NEW_SIGNAL_LONG ?? true,
          NEW_SIGNAL_SHORT: parsed.enabled?.NEW_SIGNAL_SHORT ?? true,
          HIGH_CONFIDENCE: parsed.enabled?.HIGH_CONFIDENCE ?? true,
          KILL_SWITCH: parsed.enabled?.KILL_SWITCH ?? true,
        },
        volume: parsed.volume ?? 50,
      };
    }
  } catch {
    // fall through
  }
  return {
    enabled: {
      NEW_SIGNAL_LONG: true,
      NEW_SIGNAL_SHORT: true,
      HIGH_CONFIDENCE: true,
      KILL_SWITCH: true,
    },
    volume: 50,
  };
}

function savePreferences(prefs: SoundPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore
  }
}

function playTone(
  ctx: AudioContext,
  frequency: number,
  duration: number,
  volumePct: number,
  type: OscillatorType = "sine",
  startOffset = 0,
): void {
  const gain = volumePct / 100;
  const oscillator = ctx.createOscillator();
  const gainNode = ctx.createGain();

  oscillator.connect(gainNode);
  gainNode.connect(ctx.destination);

  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, ctx.currentTime + startOffset);

  gainNode.gain.setValueAtTime(0, ctx.currentTime + startOffset);
  gainNode.gain.linearRampToValueAtTime(gain, ctx.currentTime + startOffset + 0.01);
  gainNode.gain.exponentialRampToValueAtTime(
    0.001,
    ctx.currentTime + startOffset + duration / 1000,
  );

  oscillator.start(ctx.currentTime + startOffset);
  oscillator.stop(ctx.currentTime + startOffset + duration / 1000 + 0.05);
}

function playPreview(category: SoundCategory, volumePct: number): void {
  if (typeof window === "undefined" || !window.AudioContext) return;
  const ctx = new AudioContext();

  try {
    switch (category) {
      case "NEW_SIGNAL_LONG":
        playTone(ctx, 880, 200, volumePct);
        break;
      case "NEW_SIGNAL_SHORT":
        playTone(ctx, 440, 200, volumePct);
        break;
      case "HIGH_CONFIDENCE":
        playTone(ctx, 1000, 150, volumePct);
        playTone(ctx, 1200, 150, volumePct, "sine", 0.18);
        break;
      case "KILL_SWITCH":
        for (let i = 0; i < 3; i++) {
          playTone(ctx, 200, 150, volumePct, "sawtooth", i * 0.2);
        }
        break;
    }
  } catch {
    // AudioContext may not be available
  }
}

export function SoundSettings() {
  const [prefs, setPrefs] = useState<SoundPreferences>(loadPreferences);
  const [saved, setSaved] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-save on changes with debounce
  useEffect(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      savePreferences(prefs);
    }, 300);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [prefs]);

  const toggleCategory = useCallback((category: SoundCategory) => {
    setPrefs((prev) => ({
      ...prev,
      enabled: { ...prev.enabled, [category]: !prev.enabled[category] },
    }));
  }, []);

  const handleVolumeChange = useCallback((value: number) => {
    setPrefs((prev) => ({ ...prev, volume: value }));
  }, []);

  const handleSave = useCallback(() => {
    savePreferences(prefs);
    setSaved(true);
    setTimeout(() => { setSaved(false); }, 2000);
  }, [prefs]);

  const handleTest = useCallback(
    (category: SoundCategory) => {
      playPreview(category, prefs.volume);
    },
    [prefs.volume],
  );

  const CATEGORIES: SoundCategory[] = [
    "NEW_SIGNAL_LONG",
    "NEW_SIGNAL_SHORT",
    "HIGH_CONFIDENCE",
    "KILL_SWITCH",
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Sound Settings</h2>
        <button
          type="button"
          onClick={handleSave}
          className="rounded border border-border px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-accent hover:text-white"
          aria-label="Save sound preferences"
        >
          {saved ? "Saved!" : "Save"}
        </button>
      </div>

      {/* Volume slider */}
      <div className="mb-5">
        <div className="mb-1.5 flex items-center justify-between">
          <label htmlFor="sound-volume" className="text-xs font-medium text-gray-400">
            Master Volume
          </label>
          <span className="text-xs text-gray-300">{prefs.volume}%</span>
        </div>
        <input
          id="sound-volume"
          type="range"
          min={0}
          max={100}
          step={5}
          value={prefs.volume}
          onChange={(e) => { handleVolumeChange(Number(e.target.value)); }}
          className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-accent"
          aria-label="Master volume control"
        />
      </div>

      {/* Category toggles */}
      <div className="space-y-3">
        {CATEGORIES.map((category) => (
          <div
            key={category}
            className="flex items-center justify-between gap-3 rounded border border-border/50 p-3"
          >
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-gray-200">
                {CATEGORY_LABELS[category]}
              </p>
              <p className="mt-0.5 text-[10px] text-gray-500">
                {CATEGORY_DESCRIPTIONS[category]}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => { handleTest(category); }}
                className="rounded border border-border px-2 py-0.5 text-[10px] font-medium text-gray-400 transition-colors hover:border-accent hover:text-white"
                aria-label={`Test ${CATEGORY_LABELS[category]} sound`}
              >
                Test
              </button>
              <button
                type="button"
                role="switch"
                aria-checked={prefs.enabled[category]}
                onClick={() => { toggleCategory(category); }}
                className={`relative h-5 w-9 rounded-full transition-colors ${
                  prefs.enabled[category] ? "bg-accent" : "bg-border"
                }`}
                aria-label={`Toggle ${CATEGORY_LABELS[category]}`}
              >
                <span
                  className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    prefs.enabled[category] ? "translate-x-4" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
