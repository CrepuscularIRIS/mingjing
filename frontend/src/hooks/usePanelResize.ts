import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';

interface PanelResize {
  panelWidth: number;
  minWidth: number;
  maxWidth: number;
  /** Pointer drag (mouse + touch + pen). Listeners are attached only for the
   *  duration of the drag, and text selection / cursor are suppressed while
   *  dragging, then restored — no always-on global listeners, no mid-drag
   *  text-selection glitch. */
  handlePointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  /** Keyboard resize (arrow keys on the separator handle). */
  nudge: (deltaPx: number) => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function usePanelResize(initialWidth: number, minWidth: number, maxWidth: number): PanelResize {
  const [panelWidth, setPanelWidth] = useState(() => clamp(initialWidth, minWidth, maxWidth));
  // Holds the active drag's teardown so an unmount mid-drag cannot leak the
  // document listeners or leave body styles stuck.
  const endDragRef = useRef<(() => void) | null>(null);

  const nudge = useCallback(
    (deltaPx: number) => {
      setPanelWidth((w) => clamp(w + deltaPx, minWidth, maxWidth));
    },
    [minWidth, maxWidth],
  );

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = panelWidth;
      const prevUserSelect = document.body.style.userSelect;
      const prevCursor = document.body.style.cursor;
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';

      function onMove(e: PointerEvent): void {
        setPanelWidth(clamp(startWidth + e.clientX - startX, minWidth, maxWidth));
      }
      function onUp(): void {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        document.body.style.userSelect = prevUserSelect;
        document.body.style.cursor = prevCursor;
        endDragRef.current = null;
      }

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      endDragRef.current = onUp;
    },
    [panelWidth, minWidth, maxWidth],
  );

  // Safety net: tear down an in-flight drag if the component unmounts mid-drag.
  useEffect(() => () => endDragRef.current?.(), []);

  return { panelWidth, minWidth, maxWidth, handlePointerDown, nudge };
}
