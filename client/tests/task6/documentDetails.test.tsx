import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import DocumentDetails from "@/components/documentDetails";
import { fail, field, ok, sampleDocument, sampleInvoice, startFakeBackend } from "./fakeBackend";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } })); // record the pop-up messages

const fieldRow = (label: string) => screen.getByRole("cell", { name: new RegExp(`(^| )${label}$`) }).closest("tr") as HTMLElement;

describe("Step 4 — Document page: what was found", () => {
  it("Shows each field with its value, status and the evidence from the document", async () => {
    startFakeBackend(() => ok(sampleDocument()));
    render(<DocumentDetails id="5" />);

    expect(await screen.findByRole("heading", { name: "october.pdf" })).toBeTruthy();
    const total = within(fieldRow("Total"));
    expect(total.getByText("1150.00")).toBeTruthy(); // exactly as stored, never rounded
    expect(total.getByText("Found")).toBeTruthy();
    expect(total.getByText("Total: $1,150.00")).toBeTruthy(); // the evidence
    expect(screen.getByText("1 invoice found")).toBeTruthy();
    expect(screen.getByText("No open problems")).toBeTruthy();
  });

  it("Shows missing, uncertain and corrected fields with their own label", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [sampleInvoice({ fields: {
      ...sampleInvoice().fields,
      customer_name: field(null),
      invoice_date: field("2026-10-15", { status: "uncertain", note: "The date could be 10 March or 3 October" }),
      tax: field("150.00", { status: "corrected", note: "corrected by hand" }),
    } })] })));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    expect(within(fieldRow("Customer")).getByText("Missing")).toBeTruthy();
    expect(within(fieldRow("Invoice date")).getByText("Uncertain")).toBeTruthy();
    expect(within(fieldRow("Invoice date")).getByText("The date could be 10 March or 3 October")).toBeTruthy();
    expect(within(fieldRow("Tax")).getByText("Corrected")).toBeTruthy();
  });

  it("Shows the problems found, marks the field with a problem, and says it needs review", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [sampleInvoice({
      needs_review: true,
      validation_errors: [{ id: 1, field: "total", rule: "totals_match", message: "subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,180.00" }],
    })] })));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    expect(screen.getByText("Problems found (1)")).toBeTruthy();
    expect(screen.getByText(/but the total says 1,180.00/)).toBeTruthy();
    expect(within(fieldRow("Total")).getByLabelText("has a problem")).toBeTruthy();
    expect(within(fieldRow("Subtotal")).queryByLabelText("has a problem")).toBeNull();
    expect(screen.getByText("Needs review")).toBeTruthy();
    expect(screen.getByText(/1 needs review/)).toBeTruthy();
  });

  it("Does not repeat the field name when the problem already starts with it", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [sampleInvoice({
      needs_review: true,
      validation_errors: [{ id: 1, field: "line item 1", rule: "line_math", message: "line item 1: 2 × 35.66 = 71.32, but the amount says 70.00" }],
    })] })));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    const problem = screen.getByText(/2 × 35.66 = 71.32/).closest("li") as HTMLElement;
    expect(problem.textContent).toBe("line item 1: 2 × 35.66 = 71.32, but the amount says 70.00");
  });

  it("Shows the line items, with the problem of a wrong line", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [sampleInvoice({ line_items: [
      { position: 1, description: "Office chairs", quantity: "10", unit_price: "100.00", amount: "1000.00", evidence: null, problems: [] },
      { position: 2, description: "Desk lamps", quantity: "2", unit_price: "25.00", amount: "60.00", evidence: null, problems: ["2 x 25.00 = 50.00, but the line says 60.00"] },
    ] })] })));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    expect(screen.getByText("Line items (2)")).toBeTruthy();
    expect(screen.getByText("Office chairs")).toBeTruthy();
    expect(screen.getByText("2 x 25.00 = 50.00, but the line says 60.00")).toBeTruthy();
  });

  it("Shows the history of the document", async () => {
    startFakeBackend(() => ok(sampleDocument()));
    render(<DocumentDetails id="5" />);

    expect(await screen.findByText("Done in 4.2 seconds: 1 invoice found, 0 need review")).toBeTruthy();
    expect(screen.getByText('Uploaded "october.pdf" (118 KB)')).toBeTruthy();
  });

  it("Shows document text as plain text, never as HTML", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [sampleInvoice({ fields: {
      ...sampleInvoice().fields, supplier_name: field('<img src=x onerror="alert(1)">Evil Ltd'),
    } })] })));
    const { container } = render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    expect(screen.getAllByText('<img src=x onerror="alert(1)">Evil Ltd').length).toBeGreaterThan(0);
    expect(container.querySelector("img")).toBeNull(); // the text was not turned into a picture with code
  });

  it("Shows why a document failed, and processes it again on request", async () => {
    let status: "failed" | "pending" = "failed";
    const backend = startFakeBackend((call) => {
      if (call.method === "POST") {
        status = "pending";
        return ok({ id: 5, filename: "october.pdf", status: "pending" }, 202);
      }
      return ok(sampleDocument({ status, error: status === "failed" ? "AI extraction failed: Gemini is busy. Try again later." : null, invoices: [] }));
    });
    render(<DocumentDetails id="5" />);
    expect((await screen.findByText(/Gemini is busy/)).textContent).toContain("AI extraction failed");

    await userEvent.click(screen.getByRole("button", { name: "Process again" }));

    expect(backend.calls.some((call) => call.method === "POST" && call.path === "/api/v1/documents/5/reprocess")).toBe(true);
    expect(toast.success).toHaveBeenCalledWith("The document will be processed again.");
    expect(await screen.findByText(/Waiting to be processed/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Process again" })).toBeNull();
  });

  it("Offers Process again only when something failed", async () => {
    startFakeBackend(() => ok(sampleDocument({ invoices: [
      sampleInvoice(), sampleInvoice({ id: 12, error: "AI extraction failed: Gemini is busy. Try again later." }),
    ] })));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");
    expect(screen.getByRole("button", { name: "Process again" })).toBeTruthy(); // one invoice could not be read
    expect(screen.getByText("AI extraction failed: Gemini is busy. Try again later.")).toBeTruthy();
  });

  it("Does not offer Process again for a document without failures", async () => {
    startFakeBackend(() => ok(sampleDocument()));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    expect(screen.queryByRole("button", { name: "Process again" })).toBeNull();
  });

  it("Updates by itself while the document is being processed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend = startFakeBackend(() => ok(backend.calls.length === 1 ? sampleDocument({ status: "processing", invoices: [] }) : sampleDocument()));
    render(<DocumentDetails id="5" />);
    expect(await screen.findByText(/Reading the file and extracting the invoices/)).toBeTruthy();

    await act(() => vi.advanceTimersByTimeAsync(2000));

    expect(screen.getByText("1 invoice found")).toBeTruthy();
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(backend.calls).toHaveLength(2); // done: it stopped asking
  });

  it("Shows the backend's message for a document that doesn't exist", async () => {
    startFakeBackend(() => fail(404, "Document 9999 was not found"));
    render(<DocumentDetails id="9999" />);

    expect((await screen.findByRole("alert")).textContent).toContain("Document 9999 was not found");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /All documents/ }).getAttribute("href")).toBe("/documents");
  });
});
