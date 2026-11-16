"use client";

import { useEffect, useEffectEvent, useMemo, useRef, useState, type Dispatch, type PointerEvent, type RefObject, type SetStateAction } from "react";
import { fitTransform, zoomAt, type Bounds, type Point, type ViewTransform } from "@/lib/kb/layout";

const ZOOM_STEP = 1.4;
/** A press that moves less than this is a click, not a drag. */
const DRAG_THRESHOLD = 4;

interface Drag {
  pointer: number;
  x: number;
  y: number;
  moved: boolean;
}

/** Size of the element, followed by a ResizeObserver; 0 × 0 while its panel is hidden. */
function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize((current) => (current.width === width && current.height === height ? current : { width, height }));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, size };
}

/** Ctrl (or ⌘) with the wheel, and the trackpad pinch, zoom around the pointer; a plain wheel keeps scrolling the page. */
function useWheelZoom(ref: RefObject<HTMLDivElement | null>, zoom: (factor: number, center: Point) => void) {
  const onWheel = useEffectEvent((event: WheelEvent) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const box = ref.current?.getBoundingClientRect();
    if (box) zoom(Math.exp(-event.deltaY * 0.01), { x: event.clientX - box.left, y: event.clientY - box.top });
  });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const listener = (event: WheelEvent) => onWheel(event);
    element.addEventListener("wheel", listener, { passive: false });
    return () => element.removeEventListener("wheel", listener);
  }, [ref]);
}

/** Drag to pan. The pointer is captured only once the press moves: a plain click keeps reaching the node under it. */
function usePan(fit: ViewTransform, setCustom: Dispatch<SetStateAction<ViewTransform | null>>) {
  const drag = useRef<Drag | null>(null);
  const pan = {
    onPointerDown: (event: PointerEvent<SVGSVGElement>) => {
      if (event.button === 0) drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    },
    onPointerMove: (event: PointerEvent<SVGSVGElement>) => {
      const current = drag.current;
      if (!current || current.pointer !== event.pointerId) return;
      const dx = event.clientX - current.x;
      const dy = event.clientY - current.y;
      if (!current.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      if (!current.moved) event.currentTarget.setPointerCapture(event.pointerId);
      drag.current = { ...current, x: event.clientX, y: event.clientY, moved: true };
      setCustom((previous) => {
        const base = previous ?? fit;
        return { ...base, x: base.x + dx, y: base.y + dy };
      });
    },
    // The click that ends a drag fires right after this: clear the drag once it has seen it.
    onPointerUp: () => {
      window.setTimeout(() => {
        drag.current = null;
      });
    },
  };
  return { pan, dragging: () => drag.current?.moved === true };
}

/**
 * Zoom and pan of the graph: the layout is fitted to the element until the reader zooms or drags,
 * and `reset` fits it again. Returns the ref of the element to measure, then the controls.
 */
export function useGraphViewport(bounds: Bounds) {
  const { ref, size } = useElementSize();
  const [custom, setCustom] = useState<ViewTransform | null>(null);
  const fit = useMemo(() => fitTransform(bounds, size.width, size.height), [bounds, size]);
  const view = custom ?? fit;
  const zoom = (factor: number, center: Point = { x: size.width / 2, y: size.height / 2 }) =>
    setCustom(zoomAt(view, factor, center, { min: fit.k * 0.5, max: fit.k * 10 }));
  useWheelZoom(ref, zoom);
  const { pan, dragging } = usePan(fit, setCustom);
  const controls = {
    size,
    view,
    pan,
    /** True while the current press is a drag: its click must not select or clear anything. */
    dragging,
    zoomIn: () => zoom(ZOOM_STEP),
    zoomOut: () => zoom(1 / ZOOM_STEP),
    reset: () => setCustom(null),
    custom: custom !== null,
  };
  return [ref, controls] as const;
}

export type GraphViewport = ReturnType<typeof useGraphViewport>[1];
