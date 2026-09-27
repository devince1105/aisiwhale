// @vitest-environment jsdom
// Projects on the admin dashboard (D-056): a paused project says who paused it and why and
// offers to resume it; a running one offers to pause it; the buttons call the right endpoints.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createApiClient } from "@/api/client";
import { decideProject, type ProjectLine } from "@/api/queries";

import { ProjectsView } from "./ProjectsPanel";

afterEach(cleanup);

const PAUSED: ProjectLine = {
  id: "p1",
  name: "持股動態與科技產業",
  state: "PAUSED",
  paused_at: "2026-09-26T19:00:45Z",
  paused_by: "ceo",
  pause_reason: "No revenue; pause to reduce burn.",
};

function show(projects: ProjectLine[]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProjectsView companyId="c1" projects={projects} />
    </QueryClientProvider>,
  );
}

describe("the projects panel", () => {
  it("says who paused a project and why, and offers to resume it", () => {
    show([PAUSED]);
    expect(screen.getByText("已暫停")).toBeTruthy();
    expect(screen.getByTestId("pause-note").textContent).toContain("由 CEO 暫停");
    expect(screen.getByTestId("pause-note").textContent).toContain("No revenue; pause to reduce burn.");
    expect(screen.getByRole("button", { name: "恢復專案" })).toBeTruthy();
  });

  it("offers to pause a running one, and nothing for a finished one", () => {
    show([
      { ...PAUSED, id: "p2", state: "ACTIVE", paused_at: null, paused_by: null, pause_reason: null },
      { ...PAUSED, id: "p3", name: "舊專案", state: "KILLED" },
    ]);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["暫停專案"]);
  });

  it("sends both directions where the API expects them", async () => {
    const urls: string[] = [];
    const api = createApiClient({
      baseUrl: "http://api",
      fetch: (async (r: Request) => {
        urls.push(`${r.method} ${r.url}`);
        return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
      }) as typeof fetch,
    });
    await decideProject("c1", "p1", "resume", null, api);
    await decideProject("c1", "p1", "pause", "先停", api);
    expect(urls).toEqual([
      "POST http://api/api/companies/c1/projects/p1/resume",
      "POST http://api/api/companies/c1/projects/p1/pause",
    ]);
  });
});
