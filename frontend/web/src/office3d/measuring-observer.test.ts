// D-173: the canvas learns its size even when the browser never sends the first resize report.
import { afterEach, describe, expect, it, vi } from "vitest";

import { MEASURE_AGAIN_MS, measuringObserver } from "./Canvas3D";

vi.mock("./scene/OfficeScene", () => ({ OfficeScene: () => null }));

class SilentObserver {
  // a browser that has not drawn a frame: observing reports nothing
  observed: Element[] = [];
  constructor(public callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.observed.push(target);
  }
  unobserve() {}
  disconnect() {}
}

afterEach(() => vi.useRealTimers());

describe("the canvas's resize observer", () => {
  it("asks to be measured on its own, a few times, after it starts watching", () => {
    vi.useFakeTimers();
    const Observer = measuringObserver(SilentObserver as unknown as typeof ResizeObserver)!;
    const report = vi.fn();
    new Observer(report).observe({} as Element);
    expect(report).not.toHaveBeenCalled();
    vi.advanceTimersByTime(MEASURE_AGAIN_MS.at(-1)!);
    expect(report).toHaveBeenCalledTimes(MEASURE_AGAIN_MS.length);
  });

  it("stops asking once it is let go", () => {
    vi.useFakeTimers();
    const Observer = measuringObserver(SilentObserver as unknown as typeof ResizeObserver)!;
    const report = vi.fn();
    const observer = new Observer(report);
    observer.observe({} as Element);
    observer.disconnect();
    vi.advanceTimersByTime(5000);
    expect(report).not.toHaveBeenCalled();
  });

  it("where there is no ResizeObserver at all, leaves the canvas to its own", () => {
    expect(measuringObserver(undefined)).toBeUndefined();
  });
});
