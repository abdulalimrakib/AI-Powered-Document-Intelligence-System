"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, FileUp, Loader2, X, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, UploadResult, uploadFiles } from "@/lib/api";
import { checkFiles, MAX_FILE_SIZE_MB, MAX_FILES, RejectedFile, SUPPORTED_EXTENSIONS } from "@/lib/checkFiles";
import { readableSize } from "@/lib/format";
import { cn } from "@/lib/utils";

/*--The upload form: choose or drop files, check them, upload them--*/
export default function UploadForm() {
  const [chosen, setChosen] = useState<File[]>([]); // the files that will be uploaded
  const [notAdded, setNotAdded] = useState<RejectedFile[]>([]); // files our own check refused
  const [dragging, setDragging] = useState(false); // true while files are dragged over the drop area
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null); // the backend's answer
  const [error, setError] = useState<string | null>(null);

  /*--New files from the file picker or from dropping them--*/
  const addFiles = (files: File[]) => {
    const { accepted, rejected } = checkFiles(files, chosen);
    setChosen([...chosen, ...accepted]);
    setNotAdded(rejected);
    setResult(null); // a new choice: the result of the last upload is no longer relevant
    setError(null);
  };

  const removeFile = (index: number) => setChosen(chosen.filter((_, i) => i !== index));

  /*--Send the chosen files to the backend--*/
  const upload = async () => {
    setUploading(true);
    setError(null);
    try {
      setResult(await uploadFiles(chosen));
      setChosen([]);
      setNotAdded([]);
    } catch (problem) {
      const apiError = problem instanceof ApiError ? problem : null;
      setError(apiError?.message ?? "The upload failed. Please try again.");
      // When none of the files could be accepted, the backend still says why for each one
      const data = apiError?.data as UploadResult | null;
      if (data?.rejected?.length) setResult(data);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* The drop area. It is a <label>, so clicking it (or Enter/Space on the hidden input) opens the file picker. */}
      <label
        onDragOver={(event) => {
          event.preventDefault(); // needed, or the browser opens the dropped file itself
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(Array.from(event.dataTransfer.files));
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors focus-within:ring-2 focus-within:ring-ring",
          dragging ? "border-primary bg-accent" : "hover:bg-accent/50"
        )}
      >
        <FileUp className="h-8 w-8 text-muted-foreground" aria-hidden />
        <span className="font-medium">Drop files here, or click to choose</span>
        <span className="text-sm text-muted-foreground">
          PDF, JPG, PNG, TIFF, XLSX, XLS or CSV · up to {MAX_FILE_SIZE_MB} MB each · up to {MAX_FILES} files
        </span>
        <input
          type="file"
          multiple
          accept={SUPPORTED_EXTENSIONS.join(",")}
          className="sr-only"
          onChange={(event) => {
            addFiles(Array.from(event.target.files ?? []));
            event.target.value = ""; // so choosing the same file again still works
          }}
        />
      </label>

      {/* Files our own check refused */}
      {notAdded.length > 0 && (
        <ProblemList title="Not added" items={notAdded.map((file) => ({ name: file.name, reason: file.reason }))} />
      )}

      {/* The chosen files */}
      {chosen.length > 0 && (
        <Card>
          <CardContent className="space-y-4">
            <ul className="divide-y">
              {chosen.map((file, index) => (
                <li key={`${file.name}-${file.size}`} className="flex items-center justify-between gap-4 py-2">
                  <span className="truncate">{file.name}</span>
                  <span className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
                    {readableSize(file.size)}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeFile(index)}
                      disabled={uploading}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X />
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
            <Button onClick={upload} disabled={uploading}>
              {uploading ? <Loader2 className="animate-spin" /> : <FileUp />}
              {uploading ? "Uploading..." : `Upload ${chosen.length} ${chosen.length === 1 ? "file" : "files"}`}
            </Button>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

      {/* The backend's answer: the files it accepted, and the ones it refused */}
      {result && result.documents.length > 0 && (
        <Card>
          <CardContent className="space-y-3">
            <p className="font-medium">
              {result.documents.length} {result.documents.length === 1 ? "file was" : "files were"} uploaded and
              will be processed in the background.
            </p>
            <ul className="space-y-1">
              {result.documents.map((document) => (
                <li key={document.id} className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" aria-hidden />
                  <Link href={`/documents/${document.id}`} className="truncate underline-offset-4 hover:underline">
                    {document.filename}
                  </Link>
                  <span className="text-sm text-muted-foreground">waiting to be processed</span>
                </li>
              ))}
            </ul>
            <Link href="/documents" className="inline-block text-sm underline underline-offset-4">
              See the progress of all documents
            </Link>
          </CardContent>
        </Card>
      )}
      {result && result.rejected.length > 0 && (
        <ProblemList title="Refused by the server" items={result.rejected.map((file) => ({ name: file.filename, reason: file.reason }))} />
      )}
    </div>
  );
}

/*--A list of files with the reason each one was refused--*/
function ProblemList({ title, items }: { title: string; items: { name: string; reason: string }[] }) {
  return (
    <div className="space-y-1" role="alert">
      <p className="text-sm font-medium">{title}:</p>
      <ul className="space-y-1">
        {items.map((item, index) => (
          <li key={`${item.name}-${index}`} className="flex items-start gap-2 text-sm">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
            <span>
              <span className="font-medium">{item.name}</span>: {item.reason}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
