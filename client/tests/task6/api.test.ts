import { describe, expect, it } from "vitest";
import { ApiError, getDocument, getDocuments, searchInvoices, uploadFiles } from "@/lib/api";
import { fail, ok, startFakeBackend } from "./fakeBackend";

describe("Step 1 — Talking to the backend (src/lib/api.ts)", () => {
  it("Gives back the data of a good answer", async () => {
    startFakeBackend(() => ok({ documents: [], page: 1, limit: 20, total: 0, total_pages: 0 }));

    expect(await getDocuments()).toEqual({ documents: [], page: 1, limit: 20, total: 0, total_pages: 0 });
  });

  it("Turns a refused request into an error with the backend's message", async () => {
    startFakeBackend(() => fail(404, "Document 9999 was not found"));

    const error = await getDocument(9999).catch((problem) => problem);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: "Document 9999 was not found", statusCode: 404 });
  });

  it("Explains clearly when the backend is not running", async () => {
    startFakeBackend(() => "unreachable");

    await expect(getDocuments()).rejects.toMatchObject({
      statusCode: 0,
      message: "The backend can't be reached at http://localhost:3002. Is it running? (cd backend && npm run dev)",
    });
  });

  it("Explains an answer that is not JSON instead of crashing", async () => {
    startFakeBackend(() => undefined);
    globalThis.fetch = async () => new Response("<html>Bad gateway</html>", { status: 502 });

    await expect(getDocuments()).rejects.toMatchObject({ message: "The backend gave an answer that can't be read (error 502)" });
  });

  it("Leaves empty filters out of the address", async () => {
    const backend = startFakeBackend(() => ok({ invoices: [] }));

    await searchInvoices({ q: " chairs ", mode: "meaning", currency: "", supplier: "  ", page: 2 });

    expect(backend.calls[0].path).toBe("/api/v1/search");
    expect(backend.calls[0].query.toString()).toBe("q=chairs&mode=meaning&page=2");
  });

  it("Sends uploaded files in the form field 'files'", async () => {
    const backend = startFakeBackend(() => ok({ documents: [], rejected: [] }, 201));

    await uploadFiles([new File(["a"], "a.pdf"), new File(["b"], "b.csv")]);

    const form = backend.calls[0].body as FormData;
    expect(backend.calls[0].method).toBe("POST");
    expect(form.getAll("files").map((file) => (file as File).name)).toEqual(["a.pdf", "b.csv"]);
  });
});
