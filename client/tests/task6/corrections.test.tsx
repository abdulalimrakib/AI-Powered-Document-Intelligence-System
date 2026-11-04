import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import DocumentDetails from "@/components/documentDetails";
import type { Invoice } from "@/lib/api";
import { Call, fail, field, ok, sampleDocument, sampleInvoice, startFakeBackend } from "./fakeBackend";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } })); // record the pop-up messages

const wrongTotal = () => sampleInvoice({
  needs_review: true,
  fields: { ...sampleInvoice().fields, total: field("1180.00") },
  validation_errors: [{ id: 1, field: "total", rule: "totals_match", message: "subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,180.00" }],
});

/*--A fake backend that keeps one invoice and changes it like the real one does--*/
const backendWithInvoice = (invoice: Invoice, answerPatch?: (call: Call) => ReturnType<typeof fail> | undefined) => {
  let current = invoice;
  const backend = startFakeBackend((call) => {
    if (call.method === "PATCH") {
      const refused = answerPatch?.(call);
      if (refused) return refused;
      const body = call.body as { fields?: Record<string, string | null>; reviewed?: boolean };
      if (body.fields?.total) {
        current = { ...current, needs_review: false, validation_errors: [], fields: { ...current.fields, total: field(body.fields.total, { status: "corrected", note: "corrected by hand" }) } };
      }
      if (body.reviewed === true) current = { ...current, needs_review: false, reviewed_at: "2026-11-04T09:00:00Z" };
      if (body.reviewed === false) current = { ...current, needs_review: true, reviewed_at: null };
      return ok(current);
    }
    return ok(sampleDocument({ invoices: [current] }));
  });
  return backend;
};

const fieldRow = (label: string) => screen.getByRole("cell", { name: new RegExp(`(^| )${label}$`) }).closest("tr") as HTMLElement;
const patches = (calls: Call[]) => calls.filter((call) => call.method === "PATCH");

describe("Step 5 — Correcting values and marking invoices as checked", () => {
  it("Corrects a value, and shows the result of the new check", async () => {
    const backend = backendWithInvoice(wrongTotal());
    render(<DocumentDetails id="5" />);
    await screen.findByText(/but the total says 1,180.00/);

    await userEvent.click(screen.getByRole("button", { name: "Correct Total" }));
    const box = screen.getByLabelText("New value for Total");
    await userEvent.clear(box);
    await userEvent.type(box, "1150.00{Enter}"); // Enter saves

    expect(patches(backend.calls)[0]).toMatchObject({ path: "/api/v1/invoices/11", body: { fields: { total: "1150.00" } } });
    expect(await screen.findByText("No open problems")).toBeTruthy(); // the page loaded the document again
    expect(within(fieldRow("Total")).getByText("Corrected")).toBeTruthy();
    expect(screen.queryByText(/but the total says/)).toBeNull();
    expect(toast.success).toHaveBeenCalledWith("Saved. The invoice has no open problems.");
  });

  it("Starts with the current value in the box, and Cancel or Esc changes nothing", async () => {
    const backend = backendWithInvoice(wrongTotal());
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    await userEvent.click(screen.getByRole("button", { name: "Correct Total" }));
    expect((screen.getByLabelText("New value for Total") as HTMLInputElement).value).toBe("1180.00");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("New value for Total")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Correct Total" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByLabelText("New value for Total")).toBeNull();
    expect(patches(backend.calls)).toHaveLength(0);
  });

  it("Removes a value when the box is left empty", async () => {
    const backend = backendWithInvoice(sampleInvoice());
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    await userEvent.click(screen.getByRole("button", { name: "Correct Customer" }));
    await userEvent.clear(screen.getByLabelText("New value for Customer"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(patches(backend.calls)[0].body).toEqual({ fields: { customer_name: null } });
  });

  it("Shows the backend's reason under the field when a value is refused, so it can be fixed there", async () => {
    backendWithInvoice(wrongTotal(), () => fail(400, "total: 'abc' is not an amount"));
    render(<DocumentDetails id="5" />);
    await screen.findByText("october.pdf");

    await userEvent.click(screen.getByRole("button", { name: "Correct Total" }));
    await userEvent.clear(screen.getByLabelText("New value for Total"));
    await userEvent.type(screen.getByLabelText("New value for Total"), "abc{Enter}");

    expect(within(fieldRow("Total")).getByRole("alert").textContent).toBe("total: 'abc' is not an amount");
    expect(screen.getByLabelText("New value for Total")).toBeTruthy(); // still open, to try again
  });

  it("Marks an invoice as checked by a person, and can undo it", async () => {
    const backend = backendWithInvoice(wrongTotal());
    render(<DocumentDetails id="5" />);
    await screen.findByText("Needs review");

    await userEvent.click(screen.getByRole("button", { name: "Mark as checked" }));
    expect(patches(backend.calls)[0].body).toEqual({ reviewed: true });
    expect(await screen.findByText(/Checked by a person/)).toBeTruthy();
    expect(screen.getByText(/but the total says 1,180.00/)).toBeTruthy(); // the problem is still shown

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(patches(backend.calls)[1].body).toEqual({ reviewed: false });
    expect(await screen.findByText("Needs review")).toBeTruthy();
  });

  it("Shows a pop-up message when marking as checked fails", async () => {
    backendWithInvoice(wrongTotal(), () => fail(503, "The correction can't be checked right now: the AI service is not running at http://localhost:8000. Please try again later."));
    render(<DocumentDetails id="5" />);
    await screen.findByText("Needs review");

    await userEvent.click(screen.getByRole("button", { name: "Mark as checked" }));

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("the AI service is not running"));
  });

  it("Does not offer Mark as checked for an invoice without problems", async () => {
    backendWithInvoice(sampleInvoice());
    render(<DocumentDetails id="5" />);
    await screen.findByText("No open problems");

    expect(screen.queryByRole("button", { name: "Mark as checked" })).toBeNull();
  });
});
