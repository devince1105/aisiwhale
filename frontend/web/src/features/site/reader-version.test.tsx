// @vitest-environment jsdom
// A locked page is kept for everybody; the reader's own copy is asked from the browser with their
// cookie (readerVersion.tsx), and a COIN unlock asks for it again instead of the server's page.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useContext } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReaderRefresh, useReaderVersion } from "./readerVersion";

afterEach(cleanup);

function Probe({ ask, send }: { ask: boolean; send: typeof fetch }) {
  const [shown, refresh] = useReaderVersion({ text: "kept" }, "/api/public/x", ask, send);
  return (
    <ReaderRefresh.Provider value={refresh}>
      <p data-testid="shown">{shown.text}</p>
      <Unlock />
    </ReaderRefresh.Provider>
  );
}

function Unlock() {
  const refresh = useContext(ReaderRefresh);
  return (
    <button type="button" onClick={() => refresh?.()}>
      again
    </button>
  );
}

const answer = (text: string) => async () => new Response(JSON.stringify({ text }), { headers: { "Content-Type": "application/json" } });

describe("the reader's own version", () => {
  it("asks with the reader's cookie and shows the answer", async () => {
    const send = vi.fn(answer("whole"));
    render(<Probe ask send={send as unknown as typeof fetch} />);
    await waitFor(() => expect(screen.getByTestId("shown").textContent).toBe("whole"));
    expect(send).toHaveBeenCalledWith(expect.stringContaining("/api/public/x"), expect.objectContaining({ credentials: "include", cache: "no-store" }));
  });

  it("asks nothing for a page that holds nothing back, until asked again", async () => {
    const send = vi.fn(answer("whole"));
    render(<Probe ask={false} send={send as unknown as typeof fetch} />);
    expect(send).not.toHaveBeenCalled();
    expect(screen.getByTestId("shown").textContent).toBe("kept");
    await act(async () => screen.getByRole("button").click());
    await waitFor(() => expect(screen.getByTestId("shown").textContent).toBe("whole"));
  });

  it("keeps the page as it was when the API says no", async () => {
    const send = vi.fn(async () => new Response("{}", { status: 500 }));
    render(<Probe ask send={send as unknown as typeof fetch} />);
    await waitFor(() => expect(send).toHaveBeenCalled());
    expect(screen.getByTestId("shown").textContent).toBe("kept");
  });
});
