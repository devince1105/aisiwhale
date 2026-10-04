// @vitest-environment jsdom
// D-094: the watchlist in drawers — by kind, each folded with a click and remembered.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GroupedList } from "./GroupedList";
import { groupOf } from "./quote";
import type { WatchedStock } from "./watchlistStore";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const item = (key: string, name: string): WatchedStock => ({ key, name, symbol: key, market: key.split(":")[0] });
const ITEMS = [
  item("us:NVDA", "輝達"),
  item("tw:2330", "台積電"),
  item("usdtwd", "美金"),
  item("us:CORN", "Teucrium Corn"),
  item("xau", "黃金"),
  item("nasdaq", "那斯達克"),
  item("btc", "比特幣"),
  item("us:AAPL", "蘋果"),
];

describe("觀察清單分類 (D-094)", () => {
  it("each kind its drawer: a commodity's fund with the futures, not the stocks", () => {
    expect(ITEMS.map((i) => groupOf(i.key))).toEqual(["us", "tw", "fx", "commodity", "commodity", "index", "crypto", "us"]);
    expect(groupOf("us10y")).toBe("index");
    expect(groupOf("us:USO")).toBe("commodity");
    expect(groupOf("txf1")).toBe("tw"); // 台指期, with the Taiwan stocks (D-190)
    expect(groupOf("taiex")).toBe("tw"); // and the index itself (D-191)
    expect(groupOf("nasdaq")).toBe("index");
  });

  it("drawers in a fixed order, the reader's order inside, not counted; one folds and stays folded", () => {
    render(<GroupedList items={ITEMS} lang="zh-TW" row={(i) => <span>{i.name}</span>} />);
    const drawers = screen.getByTestId("watchlist-groups").querySelectorAll("section");
    expect([...drawers].map((d) => d.getAttribute("data-group"))).toEqual(["tw", "us", "index", "commodity", "fx", "crypto"]);
    const us = within(drawers[1] as HTMLElement);
    expect(us.getByRole("button").textContent).toBe("美股"); // no count on the list to watch (D-095)
    expect(us.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["輝達", "蘋果"]);

    fireEvent.click(us.getByRole("button", { name: /美股/ }));
    expect(screen.queryByText("輝達")).toBeNull();
    expect(us.getByRole("button").getAttribute("aria-expanded")).toBe("false");
    cleanup();
    render(<GroupedList items={ITEMS} lang="zh-TW" row={(i) => <span>{i.name}</span>} />);
    expect(screen.queryByText("輝達")).toBeNull(); // remembered
    expect(screen.getByText("台積電")).toBeTruthy();
  });
});

describe("編輯清單 (D-095)", () => {
  it("counted in its drawers", () => {
    render(<GroupedList items={ITEMS} lang="zh-TW" counted row={(i) => <span>{i.name}</span>} />);
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons).toEqual(["台股1", "美股2", "指數・利率1", "黃金・期貨2", "外匯1", "加密貨幣1"]);
  });
});
