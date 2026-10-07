// @vitest-environment jsdom
// AD-06's page: each back-office change by its name, its target linked where it can be opened,
// done or refused, what was sent folded away — and a name for every route that exists.
import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { AdminAction } from "@/api/queries";
import { DataTable } from "@/features/admin-ui/DataTable";

import { ACTION_LABEL, COLUMNS } from "./AuditPage";

afterEach(cleanup);

const ROW: AdminAction = {
  id: "x1",
  created_at: "2026-10-07T07:00:00Z",
  actor: { kind: "human", id: "admin:r1" },
  actor_label: "admin@aisiwhale.test",
  method: "POST",
  route: "/api/articles/{article_id}/unpublish",
  action: "post_unpublish",
  target_type: "article",
  target_id: "0192aaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  company_id: "c1",
  status: 200,
  input: { body: { reason: "用字要改" } },
  ip: "127.0.0.1",
};

describe("the record", () => {
  it("names the change, links the article, says how it ended", () => {
    render(
      <DataTable
        label="操作紀錄"
        rows={[ROW, { ...ROW, id: "x2", status: 409, route: "/api/approvals/{approval_id}/decide", target_type: "approval" }]}
        columns={COLUMNS}
        rowKey={(a) => a.id}
        empty=""
      />,
    );
    const [, done, refused] = screen.getAllByRole("row");
    expect(within(done).getByText("下架")).toBeTruthy();
    expect(within(done).getByText("admin@aisiwhale.test")).toBeTruthy();
    expect(within(done).getByRole("link", { name: "文章 0192aaaa" }).getAttribute("href")).toBe(`/admin/newsroom/articles/${ROW.target_id}`);
    expect(within(done).getByText("完成")).toBeTruthy();
    expect(within(done).getByText(/用字要改/)).toBeTruthy();
    expect(within(refused).getByText("審批決定")).toBeTruthy();
    expect(within(refused).getByText("被拒 409")).toBeTruthy();
    expect(within(refused).queryByRole("link")).toBeNull(); // an approval has no page of its own
  });

  it("names only routes that exist", () => {
    const paths = Object.keys(JSON.parse(readFileSync(join(process.cwd(), "src/api/openapi.json"), "utf8")).paths);
    expect(Object.keys(ACTION_LABEL).filter((route) => !paths.includes(route))).toEqual([]);
  });
});
