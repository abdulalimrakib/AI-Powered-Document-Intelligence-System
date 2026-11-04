import { beforeEach, describe, expect, it } from "vitest";
import { aiInvoice, app, fakeAi, fileResult, request, uploadAndWait, useTestServices } from "../task4/helpers";

useTestServices();

const search = async (q: string) => (await request(app).get(`/api/v1/search?q=${encodeURIComponent(q)}`)).body;
const numbers = (body: any) => body.data.invoices.map((invoice: any) => invoice.invoice_number);

/*--A line item, as the AI service gives it back--*/
const line = (description: string, amount = "100.00") => ({
  description, quantity: "1", unit_price: amount, amount, evidence: description, problems: [],
});

describe("Step 2 — Keyword search also looks in the line items and the invoice text", () => {
  beforeEach(async () => {
    fakeAi.extract = (filename) => fileResult(filename, [
      aiInvoice({ invoice_number: "FURN-1", supplier_name: "Acme Ltd" }, {
        line_items: [line("Delivery"), line("Office chairs"), line("Chair cushions")],
        text: "INVOICE FURN-1\nAcme Ltd\nOffice chairs 10 x 100.00\nPayment due within 30 days by bank transfer.\n"
          + "Late payments are charged 2% interest per month. ".repeat(5), // a long text, to check that it is cut
      }),
      { ...aiInvoice({ invoice_number: "NET-1", supplier_name: "FastNet" }, {
        line_items: [line("Broadband, October")],
        text: "INVOICE NET-1\nFastNet\nBroadband, October\nThank you for choosing FastNet. Ref: PO-5521",
      }), source: "Page 2" },
      { ...aiInvoice({ invoice_number: "CHAIR-9", supplier_name: "Chairs R Us" }), source: "Page 3" },
    ]);
    await uploadAndWait("october.pdf");
  });

  it("Finds an invoice by what was bought (a line item)", async () => {
    const body = await search("broadband");

    expect(numbers(body)).toEqual(["NET-1"]);
    expect(body.data.invoices[0]).toMatchObject({ found_in: "line item", matched_text: "Broadband, October" });
  });

  it("Shows the first matching line when several lines match", async () => {
    const body = await search("chair");
    const furniture = body.data.invoices.find((invoice: any) => invoice.invoice_number === "FURN-1");

    expect(furniture).toMatchObject({ found_in: "line item", matched_text: "Office chairs" });
  });

  it("Finds an invoice by a word that is only in its text", async () => {
    const body = await search("po-5521");

    expect(numbers(body)).toEqual(["NET-1"]);
    expect(body.data.invoices[0].found_in).toBe("invoice text");
    expect(body.data.invoices[0].matched_text).toContain("Ref: PO-5521");
  });

  it("Shows only a short piece of the text around the match", async () => {
    const body = await search("bank transfer");
    const piece: string = body.data.invoices[0].matched_text;

    expect(piece).toContain("bank transfer");
    expect(piece.length).toBeLessThanOrEqual(100);
  });

  it("Shows the main field when the word is also in the text (supplier wins over text)", async () => {
    const body = await search("fastnet");

    expect(body.data.invoices[0]).toMatchObject({ invoice_number: "NET-1", found_in: "supplier", matched_text: null });
  });

  it("Puts matches in main fields before matches in line items", async () => {
    // A newer upload that has "chair" only in a line item: it must still come after the supplier match
    fakeAi.extract = (filename) => fileResult(filename, [
      aiInvoice({ invoice_number: "DESK-1", supplier_name: "Office World" }, { line_items: [line("Desk chair")] }),
    ]);
    await uploadAndWait("newer.pdf");

    // "Chairs R Us" (CHAIR-9) has "chair" in a main field; DESK-1 and FURN-1 have it only in a line item (newest first)
    expect(numbers(await search("chair"))).toEqual(["CHAIR-9", "DESK-1", "FURN-1"]);
  });

  it("Does not send the whole invoice text in the results", async () => {
    const body = await search("broadband");

    expect(body.data.invoices[0].text).toBeUndefined();
  });

  it("Counts line item and text matches in the total", async () => {
    const body = await search("chair");

    expect(body.data.total).toBe(2);
    expect(body.message).toBe('2 invoices found for "chair"');
  });
});
