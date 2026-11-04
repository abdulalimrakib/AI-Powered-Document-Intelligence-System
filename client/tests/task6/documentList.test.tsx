import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DocumentList from "@/components/documentList";
import { fail, ok, page, sampleSummary, startFakeBackend } from "./fakeBackend";

/*--Let the fake clock run on: e.g. 2 seconds later (the list refreshes every 2 seconds)--*/
const wait = (milliseconds: number) => act(() => vi.advanceTimersByTimeAsync(milliseconds));
const row = (filename: string) => screen.getByRole("link", { name: filename }).closest("tr") as HTMLElement;

describe("Step 3 — Documents list with live progress", () => {
  it("Shows every document with its status, invoices and review count", async () => {
    startFakeBackend(() => ok(page({ documents: [
      sampleSummary({ id: 1, filename: "october.pdf", status: "done", invoice_count: 3, review_count: 2 }),
      sampleSummary({ id: 2, filename: "broken.pdf", status: "failed", error: "The PDF is damaged and cannot be opened." }),
      sampleSummary({ id: 3, filename: "clean.csv", status: "done", invoice_count: 1, review_count: 0 }),
    ] }, 3)));
    render(<DocumentList />);

    expect(await screen.findByText("october.pdf")).toBeTruthy();
    expect(within(row("october.pdf")).getByText("Done")).toBeTruthy();
    expect(within(row("october.pdf")).getByText("2 need review")).toBeTruthy();
    expect(within(row("broken.pdf")).getByText("Failed")).toBeTruthy();
    expect(within(row("broken.pdf")).getByText("The PDF is damaged and cannot be opened.")).toBeTruthy();
    expect(within(row("clean.csv")).getByText("All fine")).toBeTruthy();
    expect(row("october.pdf").querySelector("a")?.getAttribute("href")).toBe("/documents/1");
  });

  it("Updates by itself every 2 seconds while a document is processing, and stops when all are finished", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const answers = ["pending", "processing", "done"] as const;
    const backend = startFakeBackend(() =>
      ok(page({ documents: [sampleSummary({ status: answers[Math.min(backend.calls.length - 1, 2)] })] }, 1)));
    render(<DocumentList />);

    await screen.findByText("october.pdf");
    expect(within(row("october.pdf")).getByText("Waiting")).toBeTruthy();
    expect(screen.getByText(/updating every 2 seconds/)).toBeTruthy();
    await wait(2000);
    expect(within(row("october.pdf")).getByText("Processing")).toBeTruthy();
    await wait(2000);
    expect(within(row("october.pdf")).getByText("Done")).toBeTruthy();

    await wait(10_000); // everything is finished: no more requests
    expect(backend.calls).toHaveLength(3);
  });

  it("Does not ask again when every document is finished", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend = startFakeBackend(() => ok(page({ documents: [sampleSummary({ status: "done" })] }, 1)));
    render(<DocumentList />);
    await screen.findByText("october.pdf");

    await wait(10_000);
    expect(backend.calls).toHaveLength(1);
  });

  it("Filters by status and by needs review, starting again on page 1", async () => {
    const backend = startFakeBackend(() => ok(page({ documents: [sampleSummary()] }, 45, 1)));
    render(<DocumentList />);
    await screen.findByText("Page 1 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(backend.calls.at(-1)?.query.get("page")).toBe("2");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    expect(backend.calls.at(-1)?.query.toString()).toBe("status=failed&page=1");

    await userEvent.click(screen.getByLabelText("Only documents that need review"));
    expect(backend.calls.at(-1)?.query.toString()).toBe("status=failed&needs_review=true&page=1");
  });

  it("Says when there are no documents yet, or none that match the filters", async () => {
    startFakeBackend(() => ok(page({ documents: [] }, 0)));
    render(<DocumentList />);

    expect((await screen.findByText(/No documents yet/)).textContent).toContain("Upload some");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    expect(await screen.findByText("No documents match these filters.")).toBeTruthy();
  });

  it("Explains when the backend can't be reached, and loads again with Try again", async () => {
    let reachable = false;
    startFakeBackend(() => (reachable ? ok(page({ documents: [sampleSummary()] }, 1)) : "unreachable"));
    render(<DocumentList />);

    expect((await screen.findByRole("alert")).textContent).toContain("The backend can't be reached");
    reachable = true;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("october.pdf")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Shows the backend's message when it refuses the request", async () => {
    startFakeBackend(() => fail(500, "Internal server error"));
    render(<DocumentList />);

    expect((await screen.findByRole("alert")).textContent).toContain("Internal server error");
  });
});
