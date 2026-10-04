// @vitest-environment jsdom
// D-193: out of hours the office says it is closed, and when it opens again.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OffDuty } from "./OfficePage";

afterEach(cleanup);

describe("the office out of hours", () => {
  it("says it is off duty and when the next shift starts, in its own time zone", () => {
    render(<OffDuty hours={{ on_duty: false, next_start: "2026-10-05T23:00:00Z", timezone: "Asia/Taipei" }} />);
    const badge = screen.getByTestId("off-duty").textContent ?? "";
    expect(badge).toContain("下班中");
    expect(badge).toContain("07:00"); // 23:00 UTC is 07:00 the next morning in Taipei
  });

  it("at work, or before it is known, says nothing", () => {
    const { container, rerender } = render(<OffDuty hours={{ on_duty: true, next_start: null, timezone: "Asia/Taipei" }} />);
    expect(container.textContent).toBe("");
    rerender(<OffDuty hours={undefined} />);
    expect(container.textContent).toBe("");
  });
});
