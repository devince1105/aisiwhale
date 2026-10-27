// @vitest-environment jsdom
// D-259: the canvas measures itself while something on the page keeps scrolling — the price strip
// at the top scrolls itself about every 33 ms.
import type { CanvasProps } from "@react-three/fiber";
import { act, cleanup, render } from "@testing-library/react";
import { createRequire } from "node:module";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CANVAS_RESIZE } from "./Canvas3D";

vi.mock("./scene/OfficeScene", () => ({ OfficeScene: () => null }));

type Options = NonNullable<CanvasProps["resize"]>;
// the measuring hook <Canvas> uses, from where <Canvas> finds it (it is not this package's own)
const fromFiber = createRequire(createRequire(import.meta.url).resolve("@react-three/fiber"));
const measuring = fromFiber("react-use-measure");
const useMeasure: (options: Options) => [(element: HTMLElement | null) => void, { width: number }] = measuring.default ?? measuring;

class ReportingObserver {
  // a browser that reports the box as soon as it is watched
  constructor(public callback: ResizeObserverCallback) {}
  observe() {
    this.callback([], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}

/** What the office's <Canvas> asks of react-use-measure: its own defaults, then `resize`. */
const asCanvas = (resize: Options): Options => ({
  scroll: true,
  debounce: { scroll: 50, resize: 0 },
  ...resize,
  polyfill: ReportingObserver as unknown as Options["polyfill"],
});

function Box({ options, seen }: { options: Options; seen: (width: number) => void }) {
  const [ref, bounds] = useMeasure(options);
  seen(bounds.width);
  return <div ref={ref} />;
}

/** Mount a box measuring as `options` while a strip scrolls every 33 ms for 2 s; its last width. */
function widthWhileScrolling(options: Options): number {
  vi.useFakeTimers();
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1118, height: 628 } as DOMRect);
  const strip = document.body.appendChild(document.createElement("ul"));
  const widths: number[] = [];
  render(<Box options={options} seen={(width) => widths.push(width)} />);
  for (let i = 0; i < 60; i += 1) {
    act(() => {
      strip.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(33);
    });
  }
  return widths.at(-1) ?? 0;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("the canvas's size, with the price strip scrolling", () => {
  it("is measured all the same", () => {
    expect(widthWhileScrolling(asCanvas(CANVAS_RESIZE))).toBe(1118);
  });

  it("was never measured while the page's scrolls counted (the stall at 5%)", () => {
    expect(widthWhileScrolling(asCanvas({ ...CANVAS_RESIZE, scroll: true }))).toBe(0);
  });
});
