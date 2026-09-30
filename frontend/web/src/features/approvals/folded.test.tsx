// @vitest-environment jsdom
// D-140: a long note on an approval card folds; a short one shows whole.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Folded, isLong } from "./Folded";

afterEach(cleanup);

describe("a long passage on an approval card", () => {
  it("folds past a few lines or a few hundred characters", () => {
    expect(isLong("退回：日期要寫年份。")).toBe(false);
    expect(isLong("字".repeat(241))).toBe(true);
    expect(isLong("a\nb\nc\nd\ne\nf\ng")).toBe(true);
  });

  it("shows a short note whole, with no button", () => {
    render(<Folded text="改標題" />);
    expect(screen.getByText("改標題")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("opens and closes a long one", () => {
    const { container } = render(<Folded text={"意見".repeat(500)} />);
    const button = screen.getByRole("button", { name: "展開全部（1,000 字）" });
    expect(
      container.querySelector("[data-folded]")?.getAttribute("data-folded"),
    ).toBe("closed");
    fireEvent.click(button);
    expect(
      container.querySelector("[data-folded]")?.getAttribute("data-folded"),
    ).toBe("open");
    fireEvent.click(screen.getByRole("button", { name: "收合" }));
    expect(
      container.querySelector("[data-folded]")?.getAttribute("data-folded"),
    ).toBe("closed");
  });
});
