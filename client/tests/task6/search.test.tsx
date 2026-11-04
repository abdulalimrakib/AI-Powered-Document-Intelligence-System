import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SearchPanel from "@/components/searchPanel";
import { fail, ok, page, sampleResult, startFakeBackend } from "./fakeBackend";

/*--A stand-in for the page address: the test sets it, and records where the page wants to go--*/
const address = vi.hoisted(() => ({ current: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: address.push }),
  useSearchParams: () => new URLSearchParams(address.current),
}));

const openPage = (current: string) => {
  address.current = current;
  return render(<SearchPanel />);
};
const resultRow = (invoiceNumber: string) => screen.getByRole("link", { name: invoiceNumber }).closest("tr") as HTMLElement;

describe("Step 6 — Search page", () => {
  beforeEach(() => {
    address.current = "";
  });

  it("Puts the search in the page address when Search is pressed", async () => {
    const backend = startFakeBackend(() => ok(page({ invoices: [], filters: {} }, 0)));
    openPage("");

    await userEvent.type(screen.getByLabelText("Search words"), "office furniture");
    await userEvent.click(screen.getByRole("radio", { name: "Meaning" }));
    await userEvent.type(screen.getByPlaceholderText("e.g. USD"), "usd");
    await userEvent.type(screen.getByPlaceholderText("e.g. 500"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(address.push).toHaveBeenCalledWith("/search?q=office+furniture&mode=meaning&total_min=500&currency=usd");
    expect(backend.calls).toHaveLength(0); // typing alone never searches (each meaning search uses a Gemini request)
  });

  it("Leaves keyword (the default) and empty filters out of the address", async () => {
    startFakeBackend(() => ok(page({ invoices: [], filters: {} }, 0)));
    openPage("");

    await userEvent.type(screen.getByLabelText("Search words"), "acme{Enter}");

    expect(address.push).toHaveBeenCalledWith("/search?q=acme");
  });

  it("Asks nothing and shows a hint when there is no search yet", () => {
    const backend = startFakeBackend(() => ok(page({ invoices: [], filters: {} }, 0)));
    openPage("");

    expect(screen.getByText("Type something to search for, or use a filter.")).toBeTruthy();
    expect(backend.calls).toHaveLength(0);
  });

  it("Shows keyword results with where the words were found", async () => {
    const backend = startFakeBackend(() => ok(page({ filters: {}, invoices: [
      sampleResult({ found_in: "line item", matched_text: "Office chairs" }),
      sampleResult({ id: 12, document_id: 6, invoice_number: "GX-77", found_in: "invoice text", matched_text: "...Ref: PO-5521 chairs...", needs_review: true }),
    ] }, 2)));
    openPage("q=chair");

    expect(await screen.findByText("2 invoices found")).toBeTruthy();
    expect(backend.calls[0].query.toString()).toBe("q=chair&page=1");
    expect(screen.getByRole("link", { name: "INV-001" }).getAttribute("href")).toBe("/documents/5");
    expect(within(resultRow("INV-001")).getByText("line item")).toBeTruthy();
    expect(within(resultRow("INV-001")).getByText("Office chairs")).toBeTruthy();
    expect(within(resultRow("INV-001")).getByText("1150.00 USD")).toBeTruthy();
    expect(within(resultRow("GX-77")).getByText("Needs review")).toBeTruthy();
  });

  it("Says 'filters only' when there were no search words", async () => {
    startFakeBackend(() => ok(page({ filters: { currency: "USD" }, invoices: [sampleResult({ found_in: null })] }, 1)));
    openPage("currency=USD");

    expect(await screen.findByText("filters only")).toBeTruthy();
  });

  it("Shows meaning results with their closeness, closest first", async () => {
    startFakeBackend(() => ok(page({ filters: {}, not_in_meaning_search: 2, invoices: [
      sampleResult({ found_in: "meaning", similarity: 0.67 }),
      sampleResult({ id: 12, invoice_number: "DESK-1", found_in: "meaning", similarity: 0.652 }),
    ] }, 2)));
    openPage("q=office+furniture&mode=meaning");

    expect(await screen.findByText(/by meaning, closest first/)).toBeTruthy();
    expect(within(resultRow("INV-001")).getByText("0.670")).toBeTruthy();
    expect(within(resultRow("DESK-1")).getByText("0.652")).toBeTruthy();
    expect(screen.getByText(/2 invoices are not in meaning search yet; keyword search still finds them/)).toBeTruthy();
  });

  it("Fills the form from the address (e.g. after pressing Back)", async () => {
    startFakeBackend(() => ok(page({ invoices: [], filters: {} }, 0)));
    openPage("q=chairs&mode=meaning&currency=EUR&needs_review=true");

    expect((screen.getByLabelText("Search words") as HTMLInputElement).value).toBe("chairs");
    expect(screen.getByRole("radio", { name: "Meaning" }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByPlaceholderText("e.g. USD") as HTMLInputElement).value).toBe("EUR");
    expect((screen.getByLabelText("Needs review") as HTMLSelectElement).value).toBe("true");
  });

  it("Offers keyword search when meaning search can't be used right now", async () => {
    startFakeBackend(() => fail(503, "Meaning search can't be used right now: the free Gemini limit for embeddings is used up for today. Try again in about 2 h 9 min. Keyword search still works: leave out mode=meaning."));
    openPage("q=chairs&mode=meaning&currency=USD");

    expect((await screen.findByRole("alert")).textContent).toContain("the free Gemini limit for embeddings is used up");
    await userEvent.click(screen.getByRole("button", { name: "Search by keyword instead" }));

    expect(address.push).toHaveBeenCalledWith("/search?q=chairs&currency=USD"); // the same search, by keyword
  });

  it("Shows the backend's message for a wrong filter", async () => {
    startFakeBackend(() => fail(400, "total_min must be an amount like 500 or 499.99"));
    openPage("q=chairs&total_min=abc");

    expect((await screen.findByRole("alert")).textContent).toBe("total_min must be an amount like 500 or 499.99");
    expect(screen.queryByRole("button", { name: "Search by keyword instead" })).toBeNull();
  });

  it("Goes to the next page of results, keeping the search", async () => {
    startFakeBackend(() => ok(page({ filters: {}, invoices: [sampleResult()] }, 45)));
    openPage("q=acme&currency=USD");
    await screen.findByText("Page 1 of 3");

    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(address.push).toHaveBeenCalledWith("/search?q=acme&currency=USD&page=2");
  });

  it("Clears the search with Clear all", async () => {
    startFakeBackend(() => ok(page({ invoices: [], filters: {} }, 0)));
    openPage("q=acme");

    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));

    expect(address.push).toHaveBeenCalledWith("/search");
  });
});
