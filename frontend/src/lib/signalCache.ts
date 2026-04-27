/**
 * A4: IndexedDB-backed signal cache.
 *
 * Persists the last 1 000 signals locally so the React Query cache can be
 * hydrated instantly on page load, eliminating the loading flash.
 *
 * Uses the native IndexedDB API directly (no extra dependency) wrapped in
 * Promises so it integrates cleanly with async/await callers.
 */

import type { Signal } from "../types";

const DB_NAME = "trading-signals";
const DB_VERSION = 1;
const STORE_NAME = "signals";
const MAX_SIGNALS = 1000;

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("created_at", "created_at", { unique: false });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Persist signals to IndexedDB, keeping only the newest MAX_SIGNALS entries. */
export async function cacheSignals(signals: Signal[]): Promise<void> {
  if (!signals.length) return;
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);

    for (const signal of signals) {
      store.put(signal);
    }

    // Trim to MAX_SIGNALS — delete oldest entries by created_at
    const countReq = store.count();
    countReq.onsuccess = () => {
      const excess = countReq.result - MAX_SIGNALS;
      if (excess <= 0) return;
      const cursor = store.index("created_at").openCursor(null, "next");
      let deleted = 0;
      cursor.onsuccess = (e) => {
        const c = (e.target as IDBRequest).result as IDBCursorWithValue | null;
        if (c && deleted < excess) {
          c.delete();
          deleted++;
          c.continue();
        }
      };
    };

    await new Promise<void>((res, rej) => {
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
    db.close();
  } catch (err) {
    // Non-fatal — degrade gracefully if IndexedDB is unavailable
    console.warn("[signalCache] write failed:", err);
  }
}

/** Load all cached signals sorted by created_at descending. */
export async function loadCachedSignals(): Promise<Signal[]> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const index = store.index("created_at");

    const signals: Signal[] = await new Promise((resolve, reject) => {
      const results: Signal[] = [];
      const request = index.openCursor(null, "prev");
      request.onsuccess = (e) => {
        const cursor = (e.target as IDBRequest).result as IDBCursorWithValue | null;
        if (cursor) {
          results.push(cursor.value as Signal);
          cursor.continue();
        } else {
          resolve(results);
        }
      };
      request.onerror = () => reject(request.error);
    });

    db.close();
    return signals;
  } catch (err) {
    console.warn("[signalCache] read failed:", err);
    return [];
  }
}

/** Clear all cached signals (e.g. on logout or full reset). */
export async function clearSignalCache(): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).clear();
    await new Promise<void>((res, rej) => {
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
    db.close();
  } catch (err) {
    console.warn("[signalCache] clear failed:", err);
  }
}
