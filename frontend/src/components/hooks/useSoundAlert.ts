/**
 * Sound Alert Hook — plays Web Audio API tones on trading events.
 * No external library required; uses AudioContext directly.
 *
 * Usage:
 *   const { play, playSignalAlert, enabled, toggleEnabled, volume, setVolume } = useSoundAlert();
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type SoundType = "signal" | "warning" | "success" | "error";

interface SoundConfig {
  frequency: number;
  duration: number;   // ms
  type: OscillatorType;
}

const SOUNDS: Record<SoundType, SoundConfig> = {
  signal:  { frequency: 880, duration: 180, type: "sine"     },
  warning: { frequency: 440, duration: 350, type: "triangle" },
  success: { frequency: 660, duration: 250, type: "sine"     },
  error:   { frequency: 220, duration: 400, type: "sawtooth" },
};

const STORAGE_KEY_ENABLED = "trading-sound-enabled";
const STORAGE_KEY_VOLUME  = "trading-sound-volume";

export function useSoundAlert() {
  const ctxRef = useRef<AudioContext | null>(null);

  const [enabled, setEnabledState] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY_ENABLED) !== "false";
    } catch {
      return true;
    }
  });

  const [volume, setVolumeState] = useState<number>(() => {
    try {
      const stored = parseFloat(localStorage.getItem(STORAGE_KEY_VOLUME) ?? "");
      return Number.isFinite(stored) ? Math.min(1, Math.max(0, stored)) : 0.3;
    } catch {
      return 0.3;
    }
  });

  // Persist enabled preference
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY_ENABLED, enabled ? "true" : "false");
    } catch {
      // ignore
    }
  }, [enabled]);

  // Persist volume preference
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY_VOLUME, String(volume));
    } catch {
      // ignore
    }
  }, [volume]);

  const getCtx = useCallback((): AudioContext | null => {
    if (typeof window === "undefined" || !window.AudioContext) return null;
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    return ctxRef.current;
  }, []);

  const play = useCallback(
    (type: SoundType) => {
      if (!enabled) return;
      const ctx = getCtx();
      if (!ctx) return;

      const cfg = SOUNDS[type];

      // Resume context if suspended (browser autoplay policy)
      if (ctx.state === "suspended") {
        void ctx.resume();
      }

      try {
        const oscillator = ctx.createOscillator();
        const gainNode = ctx.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(ctx.destination);

        oscillator.type = cfg.type;
        oscillator.frequency.setValueAtTime(cfg.frequency, ctx.currentTime);

        // Envelope: quick attack, short decay — scaled by user volume
        gainNode.gain.setValueAtTime(0, ctx.currentTime);
        gainNode.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.01);
        gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + cfg.duration / 1000);

        oscillator.start(ctx.currentTime);
        oscillator.stop(ctx.currentTime + cfg.duration / 1000 + 0.05);
      } catch {
        // AudioContext may not be available in all browsers
      }
    },
    [enabled, volume, getCtx],
  );

  const toggleEnabled = useCallback(() => {
    setEnabledState((prev) => !prev);
  }, []);

  const setVolume = useCallback((v: number) => {
    setVolumeState(Math.min(1, Math.max(0, v)));
  }, []);

  return {
    /** Generic play function — preferred API */
    play,
    /** Convenience aliases */
    playSignalAlert: useCallback(() => play("signal"), [play]),
    playWarning:     useCallback(() => play("warning"), [play]),
    playSuccess:     useCallback(() => play("success"), [play]),
    playError:       useCallback(() => play("error"), [play]),
    /** State */
    enabled,
    /** @deprecated use enabled — kept for backwards compatibility */
    isEnabled: enabled,
    toggleEnabled,
    /** @deprecated use toggleEnabled — kept for backwards compatibility */
    setEnabled: setEnabledState,
    volume,
    setVolume,
  };
}
