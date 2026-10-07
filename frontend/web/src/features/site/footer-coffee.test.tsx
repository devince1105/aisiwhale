// @vitest-environment jsdom
// D-250: the footer's "Buy me a coffee" — a plain link to the operator's page, in a new tab, said
// in the reader's language around the service's own name.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { COFFEE_URL, SiteFooter } from "./SiteFooter";

afterEach(cleanup);

describe("the footer's coffee", () => {
  it("links to the operator's page in a new tab, and says so", () => {
    render(<SiteFooter lang="zh-TW" />);
    const coffee = screen.getByTestId("site-coffee");
    expect(coffee.textContent).toContain("覺得有幫助，請我喝咖啡");
    const link = within(coffee).getByRole("link", { name: /Buy me a coffee/ });
    expect(link.getAttribute("href")).toBe(COFFEE_URL);
    expect(COFFEE_URL).toBe("https://buymeacoffee.com/vince115");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.textContent).toContain("（另開新分頁）");
  });

  it("in English too, and before the disclaimer strip, which stays the footer's last row", () => {
    render(<SiteFooter lang="en" />);
    expect(screen.getByTestId("site-coffee").textContent).toContain(
      "Like what you read? Support the site.",
    );
    expect(screen.getByTestId("site-footer").lastElementChild).toBe(
      screen.getByTestId("site-disclaimer"),
    );
  });
});
