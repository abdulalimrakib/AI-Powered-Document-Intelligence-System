import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import UploadForm from "@/components/uploadForm";
import { checkFiles } from "@/lib/checkFiles";
import { fail, ok, startFakeBackend } from "./fakeBackend";

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);
// applyAccept: false = the test can also choose files the file picker would hide, to check our own rules
const user = () => userEvent.setup({ applyAccept: false });
const fileInput = (container: HTMLElement) => container.querySelector('input[type="file"]') as HTMLInputElement;

describe("Step 2 — Upload page", () => {
  it("Accepts the supported file types, with small or capital letters", () => {
    const names = ["a.pdf", "b.JPG", "c.jpeg", "d.png", "e.tif", "f.TIFF", "g.xlsx", "h.xls", "i.csv"];
    expect(checkFiles(names.map((name) => file(name)), []).accepted).toHaveLength(9);
  });

  it.each([
    { example: "Word file", files: [file("notes.docx")], reason: "This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV." },
    { example: "no extension", files: [file("invoice")], reason: "This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV." },
    { example: "empty file", files: [file("empty.csv", 0)], reason: "The file is empty." },
    { example: "bigger than 50 MB", files: [file("huge.pdf", 50 * 1024 * 1024 + 1)], reason: "The file is bigger than 50 MB." },
    { example: "the same file twice", files: [file("a.pdf"), file("a.pdf")], reason: "This file is already in the list." },
  ])("Refuses a file the server would refuse, and says why ($example)", ({ files, reason }) => {
    expect(checkFiles(files, []).rejected.at(-1)?.reason).toBe(reason);
  });

  it("Allows at most 20 files in one upload", () => {
    const twenty = Array.from({ length: 20 }, (_, i) => file(`f${i}.csv`));
    expect(checkFiles([file("one-more.csv")], twenty).rejected[0].reason).toBe("At most 20 files can be uploaded at once.");
  });

  it("Lists the chosen files and shows why others were not added", async () => {
    const { container } = render(<UploadForm />);

    await user().upload(fileInput(container), [file("october.pdf", 2048), file("notes.docx")]);

    expect(screen.getByText("october.pdf")).toBeTruthy();
    expect(screen.getByText("2 KB")).toBeTruthy();
    expect(screen.getByText(/notes\.docx/).closest("li")?.textContent).toContain("This file type is not supported");
    expect(screen.getByRole("button", { name: "Upload 1 file" })).toBeTruthy();
  });

  it("Adds dropped files", () => {
    render(<UploadForm />);

    fireEvent.drop(screen.getByText("Drop files here, or click to choose"), {
      dataTransfer: { files: [file("a.pdf"), file("b.csv")] },
    });

    expect(screen.getByRole("button", { name: "Upload 2 files" })).toBeTruthy();
  });

  it("Removes a chosen file", async () => {
    const { container } = render(<UploadForm />);
    await user().upload(fileInput(container), [file("a.pdf"), file("b.csv")]);

    await user().click(screen.getByRole("button", { name: "Remove a.pdf" }));

    expect(screen.queryByText("a.pdf")).toBeNull();
    expect(screen.getByRole("button", { name: "Upload 1 file" })).toBeTruthy();
  });

  it("Uploads the files and links to each document's progress", async () => {
    const backend = startFakeBackend(() => ok({
      documents: [
        { id: 7, filename: "a.pdf", file_size: 10, status: "pending", created_at: "2026-11-04T08:00:00Z" },
        { id: 8, filename: "b.csv", file_size: 10, status: "pending", created_at: "2026-11-04T08:00:00Z" },
      ],
      rejected: [],
    }, 201));
    const { container } = render(<UploadForm />);
    await user().upload(fileInput(container), [file("a.pdf"), file("b.csv")]);

    await user().click(screen.getByRole("button", { name: "Upload 2 files" }));

    expect(await screen.findByText("2 files were uploaded and will be processed in the background.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "a.pdf" }).getAttribute("href")).toBe("/documents/7");
    expect(screen.getByRole("link", { name: "b.csv" }).getAttribute("href")).toBe("/documents/8");
    expect(backend.calls).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Upload/ })).toBeNull(); // the list is empty again
  });

  it("Shows the server's reason for each refused file", async () => {
    startFakeBackend(() => fail(400, "None of the files can be processed.", {
      documents: [], rejected: [{ filename: "fake.pdf", reason: "The file is empty." }],
    }));
    const { container } = render(<UploadForm />);
    await user().upload(fileInput(container), [file("fake.pdf")]);

    await user().click(screen.getByRole("button", { name: "Upload 1 file" }));

    expect(await screen.findByText("None of the files can be processed.")).toBeTruthy();
    const refused = screen.getByText("Refused by the server:").parentElement; // the box with the refused files
    expect(refused?.textContent).toContain("fake.pdf: The file is empty.");
  });

  it("Keeps the chosen files and explains it when the backend is not running", async () => {
    startFakeBackend(() => "unreachable");
    const { container } = render(<UploadForm />);
    await user().upload(fileInput(container), [file("a.pdf")]);

    await user().click(screen.getByRole("button", { name: "Upload 1 file" }));

    expect((await screen.findByRole("alert")).textContent).toContain("The backend can't be reached");
    expect(screen.getByRole("button", { name: "Upload 1 file" })).toBeTruthy(); // try again without choosing again
  });
});
