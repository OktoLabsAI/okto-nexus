// Right-hand inspector panel with a draggable resize handle on its left
// edge. Width persists per `storageKey` so the operator's preferred layout
// survives reloads.

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

const MIN_WIDTH = 320;
const MAX_WIDTH = 760;

export function ResizablePanel({
  children,
  storageKey = "okto-nexus-panel-width",
  defaultWidth = 416,
  testId,
}: {
  children: ReactNode;
  storageKey?: string;
  defaultWidth?: number;
  testId?: string;
}) {
  const [width, setWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem(storageKey));
    return Number.isFinite(stored) && stored >= MIN_WIDTH && stored <= MAX_WIDTH
      ? stored
      : defaultWidth;
  });
  const dragging = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const next = Math.min(
        MAX_WIDTH,
        Math.max(MIN_WIDTH, window.innerWidth - e.clientX),
      );
      setWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setWidth((w) => {
        localStorage.setItem(storageKey, String(w));
        return w;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [storageKey]);

  return (
    <aside
      className="relative shrink-0 border-l border-surface-200 dark:border-surface-700/60
        bg-white/90 dark:bg-surface-900/90 backdrop-blur-md overflow-y-auto animate-slide-in-right"
      style={{ width }}
      data-testid={testId}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        title="Drag to resize"
        onMouseDown={onMouseDown}
        className="absolute left-0 top-0 h-full w-1.5 cursor-col-resize z-10
          hover:bg-accent-500/40 active:bg-accent-500/60 transition-colors"
        data-testid="panel-resize-handle"
      />
      <div className="p-4">{children}</div>
    </aside>
  );
}
