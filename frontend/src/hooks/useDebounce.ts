import { useEffect, useState } from "react";

/**
 * Returns a debounced version of `value` that only updates after
 * `delay` ms of no new changes — prevents burst API calls on fast typing.
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
