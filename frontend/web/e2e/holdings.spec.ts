// 機構排行 in a real browser (HD-11, D-217): the institutions' tab ends with the ranking's top ten,
// the full ranking finds a filer by its filed name and says it was filed in thousands, a page
// opened for the first time is queued, and one worked out shows its ten largest holdings to
// anybody and the rest after signing in. Twelve filers seeded by backend/scripts/e2e_holdings.py.
import { execFileSync } from "node:child_process";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { API_URL, REPO, Stack } from "./stack";

test.describe.configure({ mode: "serial" });

let stack: Stack;

test.beforeAll(async () => {
  stack = await Stack.start();
  execFileSync(
    join(REPO, ".venv/bin/python"),
    [join(REPO, "backend/scripts/e2e_holdings.py")],
    {
      encoding: "utf8",
      env: { ...process.env, DATABASE_URL: stack.seeded.database_url },
    },
  );
});

test.afterAll(async () => {
  await stack?.stop();
});

test("the institutions' tab ends with the top ten, and the ranking finds a filer", async ({
  page,
}) => {
  await page.goto("/news/zh-TW?section=watch&view=groups");
  const top = page.getByTestId("top-ranking");
  await expect(
    top.getByRole("heading", { name: "機構持股排行前 10 名" }),
  ).toBeVisible();
  await expect(top.getByTestId("rank-row")).toHaveCount(10);
  await expect(top.getByTestId("rank-row").first()).toContainText("貝萊德");

  await top.getByRole("link", { name: /看完整排行/ }).click();
  await expect(page).toHaveURL(/\/news\/zh-TW\/holdings\/institutions$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "機構持股排行" }),
  ).toBeVisible();
  await expect(
    page.getByTestId("ranking-table").getByTestId("rank-row"),
  ).toHaveCount(12);

  await page.getByRole("searchbox").fill("rowe");
  await page.getByRole("button", { name: "搜尋" }).click();
  await expect(page).toHaveURL(/q=rowe/);
  const rows = page.getByTestId("ranking-table").getByTestId("rank-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("普徠仕");
  await expect(rows.first()).toContainText("以千美元申報，已換算");
  await expect(rows.first()).toContainText("9,991.25 億");

  // opened for the first time: queued, and the page says to come back
  await rows.first().getByRole("link", { name: "普徠仕" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "普徠仕" }),
  ).toBeVisible();
  await expect(page.getByTestId("queued")).toContainText("幾分鐘後再看");
  const queued = await page.request.get(
    `${API_URL}/api/public/institutions/80255?lang=zh-TW`,
  );
  expect((await queued.json()).status).toBe("queued");
});

test("a page worked out: its ten largest for anybody, the rest signed in", async ({
  page,
}) => {
  await page.goto("/news/zh-TW/holdings/institutions/2012383");
  await expect(
    page.getByRole("heading", { level: 1, name: "貝萊德" }),
  ).toBeVisible();
  await expect(page.getByTestId("institution-figures")).toContainText(
    "6.73 兆",
  );
  await expect(
    page.getByTestId("institution-table").locator("tbody tr"),
  ).toHaveCount(10);
  await expect(
    page.getByText(/登入（免費）就能看前 12 大持股與買賣明細。/),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "買進最多" })).toHaveCount(0);

  // a reader signs up and in (free), as the sign-in link offers; localhost: the API's cookie
  // counts for the web app too
  const email = `holdings-${Date.now()}@e2e.test`;
  const password = "e2e reader password";
  const post = (path: string) =>
    fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  expect((await post("/api/auth/register")).status).toBe(202);
  const login = await post("/api/auth/login");
  expect(login.status).toBe(200);
  const value = /autora_reader=([^;]+)/.exec(
    login.headers.get("set-cookie") ?? "",
  )?.[1];
  expect(value).toBeTruthy();
  await page
    .context()
    .addCookies([
      {
        name: "autora_reader",
        value: value!,
        url: API_URL,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

  await page.reload();
  await expect(
    page.getByTestId("institution-table").locator("tbody tr"),
  ).toHaveCount(12);
  await expect(page.getByRole("heading", { name: "買進最多" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "賣出最多" })).toBeVisible();
});
