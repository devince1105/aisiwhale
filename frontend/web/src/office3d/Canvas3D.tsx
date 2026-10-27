"use client";

// The WebGL part of the office, loaded only on the client (next/dynamic, ssr: false) and only
// when 3D was chosen: the canvas, camera and context-loss wiring; the scene is OfficeScene.
import { useProgress } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { NeutralToneMapping } from "three";

import { uiStore } from "@/stores/ui";

import type { ThemeId } from "./palette";
import { OfficeScene } from "./scene/OfficeScene";

export const CANVAS_DPR: [number, number] = [1, 1.5];
/** The camera starts isometric; CameraRig (T-409) frames the room and takes it from there. */
const CAMERA_POSITION: [number, number, number] = [40, 46, 40];

export interface Canvas3DProps {
  frameloop: "always" | "never";
  /** Pixels covered on the right while an agent is selected (the detail panel). */
  insetRight?: number;
  /** The office's look (T-413). */
  theme?: ThemeId;
  onContextLost: () => void;
  onContextRestored: () => void;
  /** The office is on screen: its models have loaded and a frame has been drawn with them. */
  onReady?: () => void;
  /** How much of the office's models and textures has loaded, 0–100 (D-158). */
  onProgress?: (percent: number) => void;
}

/** Report this canvas losing its context — and stop reporting the moment it is taken down.
 *
 * Tearing the canvas down *is* a lost context as far as the browser is concerned, and the event
 * arrives after React has moved on: switching to the 2D board and back used to put "3D 暫停"
 * over a canvas that had only just been built, because the dying one was still being listened
 * to. Listening from inside the canvas gives the listener the canvas's own lifetime.
 */
function ContextWatch({ onLost, onRestored }: { onLost: () => void; onRestored: () => void }) {
  const gl = useThree((state) => state.gl);
  useEffect(() => {
    const canvas = gl.domElement;
    let alive = true;
    const lost = (event: Event) => {
      event.preventDefault(); // allow a restore instead of a dead canvas
      if (alive) onLost();
    };
    const restored = () => {
      if (alive) onRestored();
    };
    canvas.addEventListener("webglcontextlost", lost);
    canvas.addEventListener("webglcontextrestored", restored);
    return () => {
      alive = false;
      canvas.removeEventListener("webglcontextlost", lost);
      canvas.removeEventListener("webglcontextrestored", restored);
    };
  }, [gl, onLost, onRestored]);
  return null;
}


/** Says when the office is really on screen (D-158): nothing is loading any more — the people's
 * models and the textures, all through three's default loading manager — and frames have been
 * drawn since. An office with nobody to load is ready after a short while all the same, and any
 * office after at most 12 seconds of drawing. */
function ReadyWatch({ onReady, onProgress }: { onReady?: () => void; onProgress?: (percent: number) => void }) {
  const active = useProgress((s) => s.active);
  const total = useProgress((s) => s.total);
  const progress = useProgress((s) => s.progress);
  // Reported when the number changes, never because the page re-rendered: the page re-renders on
  // each report and hands down a new callback, and reacting to that would never stop.
  const report = useRef(onProgress);
  report.current = onProgress;
  useEffect(() => report.current?.(progress), [progress]);
  const frames = useRef(0);
  const done = useRef(false);
  const born = useRef<number | null>(null);
  useFrame(() => {
    if (done.current || !onReady) return;
    born.current ??= performance.now();
    frames.current += 1;
    const waited = performance.now() - born.current;
    // a model that never arrives must not keep the office covered for good
    const settled = (!active && (total > 0 || waited > EMPTY_READY_MS)) || waited > MAX_LOADING_MS;
    if (settled && frames.current > 2) {
      done.current = true;
      onReady();
    }
  });
  return null;
}

/** When the canvas measures itself again on its own, in ms after it starts watching its box. */
export const MEASURE_AGAIN_MS = [0, 250, 1000] as const;

/**
 * The canvas draws nothing until it knows its size, and it learns its size from a
 * ResizeObserver's first report (D-173). The 5% stall blamed on that report never coming was
 * the page's scrolls drowning it out (D-259, CANVAS_RESIZE); this observer, which asks to be
 * measured again a few times on timers too, stays as a fallback: a measurement that finds the
 * same box changes nothing.
 */
export function measuringObserver(Base: typeof ResizeObserver | undefined = globalThis.ResizeObserver) {
  if (!Base) return undefined;
  return class MeasuringObserver extends Base {
    private readonly report: ResizeObserverCallback;
    private timers: ReturnType<typeof setTimeout>[] = [];
    constructor(report: ResizeObserverCallback) {
      super(report);
      this.report = report;
    }
    override observe(target: Element, options?: ResizeObserverOptions) {
      super.observe(target, options);
      this.timers.push(...MEASURE_AGAIN_MS.map((ms) => setTimeout(() => this.report([], this), ms)));
    }
    override disconnect() {
      this.timers.forEach(clearTimeout);
      this.timers = [];
      super.disconnect();
    }
  };
}

const MeasuringObserver = measuringObserver();

/**
 * How the canvas measures itself (D-259): on its own box's resize reports, not on the page's
 * scrolls. The measuring waits for 50 ms without a report, and with every scroll on the page
 * counted as one, the price strip at the top — which scrolls itself about 30 times a second —
 * never left it those 50 ms: the canvas stayed at 300×150 and the loading bar at 5%, on most
 * loads in a fresh browser. Its place on the page is never needed: a click is placed by its
 * offset inside the canvas.
 */
export const CANVAS_RESIZE = { scroll: false, polyfill: MeasuringObserver } as const;

const EMPTY_READY_MS = 1500;
const MAX_LOADING_MS = 12_000;

export default function Canvas3D({ frameloop, insetRight, theme, onContextLost, onContextRestored, onReady, onProgress }: Canvas3DProps) {
  return (
    <Canvas
      dpr={CANVAS_DPR}
      resize={CANVAS_RESIZE}
      orthographic
      // PCF (three removed the soft variant and warned on every shader compile)
      shadows="percentage"
      frameloop={frameloop}
      camera={{ position: CAMERA_POSITION, zoom: 30, near: 0.1, far: 500 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      // a click on nothing (not a drag) clears the selection
      onPointerMissed={() => uiStore.getState().selectAgent(null)}
      onCreated={({ gl }) => {
        // Neutral tone mapping keeps the palette's colours (filmic ACES greys them out).
        gl.toneMapping = NeutralToneMapping;
      }}
    >
      <ContextWatch onLost={onContextLost} onRestored={onContextRestored} />
      <ReadyWatch onReady={onReady} onProgress={onProgress} />
      <OfficeScene insetRight={insetRight} theme={theme} />
    </Canvas>
  );
}
