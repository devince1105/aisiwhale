// @vitest-environment jsdom
// D-176: the AI 編輯部 is kept between pages only on a computer that can afford it, and moves in
// and out of its page without being built again.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KEEP_MIN_CORES, KeptOffice, keepsOfficeAlive, keptOffice, OfficeSlot } from "./KeptOffice";

const mounted = vi.fn();
const actives: boolean[] = [];
vi.mock("./DemoOffice", async () => {
  const { useEffect } = await import("react");
  return {
    DemoOffice: ({ active = true }: { active?: boolean }) => {
      useEffect(() => mounted(), []);
      actives.push(active);
      return <div data-testid="demo-office" data-active={active} />;
    },
  };
});

afterEach(() => {
  cleanup();
  mounted.mockReset();
  actives.length = 0;
  keptOffice.setState({ wanted: false, slot: null });
});

function browser({ narrow = false, fine = true, cores = 8, memory }: { narrow?: boolean; fine?: boolean; cores?: number; memory?: number }) {
  return {
    navigator: { hardwareConcurrency: cores, deviceMemory: memory },
    matchMedia: (query: string) => ({ matches: query.includes("pointer: fine") ? fine : narrow }),
  } as unknown as Window;
}

describe("which computers keep the office", () => {
  it("a computer with the cores and the memory", () => {
    expect(keepsOfficeAlive(browser({ memory: 8 }))).toBe(true);
    expect(keepsOfficeAlive(browser({}))).toBe(true); // Safari, Firefox: memory unknown, cores decide
  });

  it("not a phone or a tablet, nor an older computer", () => {
    expect(keepsOfficeAlive(browser({ narrow: true }))).toBe(false);
    expect(keepsOfficeAlive(browser({ fine: false }))).toBe(false); // a touch screen
    expect(keepsOfficeAlive(browser({ cores: KEEP_MIN_CORES - 4 }))).toBe(false);
    expect(keepsOfficeAlive(browser({ memory: 4 }))).toBe(false);
  });
});

describe("the office kept between pages", () => {
  it("where it is not kept, the page has an office of its own, as before", async () => {
    render(<OfficeSlot lang="zh-TW" keep={() => false} />);
    expect(await screen.findByTestId("demo-office")).toBeTruthy();
    expect(keptOffice.getState().wanted).toBe(false);
  });

  it("where it is kept: built once, moved into its page, parked and paused away from it", async () => {
    const keep = () => true;
    render(<KeptOffice lang="zh-TW" />);
    expect(screen.queryByTestId("demo-office")).toBeNull(); // nobody asked for it yet

    const page = render(<OfficeSlot lang="zh-TW" keep={keep} />);
    const office = await screen.findByTestId("demo-office");
    expect(screen.getByTestId("office-slot").contains(office)).toBe(true);
    expect(office.dataset.active).toBe("true");

    // to another page: the office stays, out of sight, paused
    page.unmount();
    await act(async () => {});
    const parked = screen.getByTestId("demo-office");
    expect(parked).toBe(office);
    expect(parked.dataset.active).toBe("false");

    // and back: the same office, playing again, never built a second time
    render(<OfficeSlot lang="zh-TW" keep={keep} />);
    await act(async () => {});
    expect(screen.getByTestId("office-slot").contains(screen.getByTestId("demo-office"))).toBe(true);
    expect(screen.getByTestId("demo-office").dataset.active).toBe("true");
    expect(mounted).toHaveBeenCalledTimes(1);
  });
});
