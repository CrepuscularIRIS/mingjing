/**
 * Generic 2-second interval poller with cleanup on unmount.
 *
 * Usage:
 *   usePolling(async () => {
 *     const data = await fetchSomething();
 *     setState(data);
 *   }, active);
 *
 * The callback is called immediately on mount (when `active` is true) and
 * then every `interval` ms. The interval resets after each call completes,
 * so slow fetches don't pile up.
 *
 * @param onError  Optional handler called whenever the callback throws.
 *                 Polling continues regardless — transient network errors are
 *                 normal during a live run. The caller can use this to surface
 *                 a visible "retrying…" notice to the user.
 */

import { useEffect, useRef } from 'react';

export function usePolling(
  callback: () => Promise<void> | void,
  active: boolean = true,
  interval: number = 2000,
  onError?: (err: unknown) => void,
): void {
  // Keep stable refs so callers don't need to memoize either function.
  // Sync inside an effect (not during render) so the polling effect's
  // tick() always reads the latest callback/onError at call-time.
  const callbackRef = useRef(callback);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    callbackRef.current = callback;
    onErrorRef.current = onError;
  }, [callback, onError]);

  useEffect(() => {
    if (!active) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    async function tick(): Promise<void> {
      if (cancelled) return;
      try {
        await callbackRef.current();
      } catch (err) {
        // Polling errors do not stop the loop; transient errors are expected.
        // Notify the caller so they can surface a visible status to the user.
        onErrorRef.current?.(err);
      }
      if (!cancelled) {
        timeoutId = setTimeout(tick, interval);
      }
    }

    void tick();

    return () => {
      cancelled = true;
      if (timeoutId !== null) clearTimeout(timeoutId);
    };
  }, [active, interval]);
}
