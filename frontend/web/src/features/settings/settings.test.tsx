// @vitest-environment jsdom
// AD-11's page: each setting says whether it is the environment's or set here, saves what was
// typed (a number as a number, shifts as text), goes back to the environment's after asking,
// and shows its last changes, before → after.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/queries", async (original) => {
  const actual = await original<typeof import("@/api/queries")>();
  return { ...actual, saveSetting: vi.fn(), resetSetting: vi.fn() };
});

import { resetSetting, saveSetting, settingsQuery, type SettingView } from "@/api/queries";
import { ToastProvider } from "@/features/admin-ui/Toast";

import { SettingsPage } from "./SettingsPage";

afterEach(cleanup);

const SHIFTS: SettingView = {
  key: "worker.shifts",
  kind: "shifts",
  label: "AI 員工的上班時段",
  help: "例：mon-fri 15:00-21:00",
  minimum: null,
  maximum: null,
  value: "mon-fri 15:00-21:00",
  default: "mon-fri 15:00-21:00; sat-sun 18:00-21:00",
  overridden: true,
  updated_by: { kind: "human", id: "admin:r1" },
  updated_at: "2026-10-07T12:00:00Z",
  changes: [{ before: null, after: "mon-fri 15:00-21:00", actor: { kind: "human", id: "admin:r1" }, actor_label: "boss@aisiwhale.test", at: "2026-10-07T12:00:00Z" }],
};
const DAY: SettingView = {
  ...SHIFTS,
  key: "worker.overtime_day_hours",
  kind: "hours",
  label: "每日加班上限（小時）",
  minimum: 0,
  maximum: 4,
  value: 4,
  default: 4,
  overridden: false,
  updated_by: null,
  updated_at: null,
  changes: [],
};

function page() {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(settingsQuery().queryKey, [SHIFTS, DAY]);
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("the settings page", () => {
  it("says where each comes from and what it was", () => {
    page();
    const shifts = screen.getByRole("region", { name: "AI 員工的上班時段" });
    expect(within(shifts).getByText("後台設定")).toBeTruthy();
    expect(shifts.textContent).toContain("環境預設：mon-fri 15:00-21:00; sat-sun 18:00-21:00");
    expect(shifts.textContent).toContain("boss@aisiwhale.test：（環境預設） → mon-fri 15:00-21:00");
    const day = screen.getByRole("region", { name: "每日加班上限（小時）" });
    expect(within(day).getByText("環境預設")).toBeTruthy();
    expect(within(day).queryByRole("button", { name: "改回環境預設" })).toBeNull();
    expect((within(day).getByRole("button", { name: "儲存" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves a number as a number and shifts as text", async () => {
    vi.mocked(saveSetting).mockResolvedValue([SHIFTS, { ...DAY, value: 2, overridden: true }]);
    page();
    const day = screen.getByRole("region", { name: "每日加班上限（小時）" });
    fireEvent.change(within(day).getByRole("spinbutton"), { target: { value: "2" } });
    fireEvent.click(within(day).getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(saveSetting).toHaveBeenCalledWith("worker.overtime_day_hours", 2));
    expect(await screen.findByText("已儲存：每日加班上限（小時）")).toBeTruthy();

    const shifts = screen.getByRole("region", { name: "AI 員工的上班時段" });
    fireEvent.change(within(shifts).getByRole("textbox"), { target: { value: "mon-sun 09:00-18:00" } });
    fireEvent.click(within(shifts).getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(saveSetting).toHaveBeenLastCalledWith("worker.shifts", "mon-sun 09:00-18:00"));
  });

  it("goes back to the environment's after asking", async () => {
    vi.mocked(resetSetting).mockResolvedValue([{ ...SHIFTS, overridden: false, value: SHIFTS.default }, DAY]);
    page();
    fireEvent.click(within(screen.getByRole("region", { name: "AI 員工的上班時段" })).getByRole("button", { name: "改回環境預設" }));
    expect(resetSetting).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "改回" }));
    await waitFor(() => expect(resetSetting).toHaveBeenCalledWith("worker.shifts"));
  });
});
