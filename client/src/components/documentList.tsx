"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import StatusBadge from "@/components/statusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, DocumentStatus, DocumentSummary, getDocuments, Page } from "@/lib/api";
import { readableDate, readableSeconds, readableSize } from "@/lib/format";

// While a document is waiting or processing, we ask the backend again after this many milliseconds
export const REFRESH_EVERY_MS = 2000;

type Answer = Page<{ documents: DocumentSummary[] }>;

const isUnfinished = (document: DocumentSummary) => document.status === "pending" || document.status === "processing";

/*--The list of uploaded documents, with live progress--*/
export default function DocumentList() {
  const [status, setStatus] = useState<DocumentStatus | "">(""); // "" = all
  const [onlyNeedsReview, setOnlyNeedsReview] = useState(false);
  const [page, setPage] = useState(1);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0); // +1 = load again now (the "Refresh" and "Try again" buttons)

  /*--Load the list, and keep loading it every 2 seconds while something is still unfinished--*/
  useEffect(() => {
    let stopped = false; // set when the filters change or the page is closed: then old answers are ignored
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const data = await getDocuments({ status, needs_review: onlyNeedsReview ? "true" : "", page });
        if (stopped) return;
        setAnswer(data);
        setError(null);
        // Ask again only after this answer arrived, so two requests never run at the same time
        if (data.documents.some(isUnfinished)) timer = setTimeout(load, REFRESH_EVERY_MS);
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof ApiError ? problem.message : "The documents could not be loaded.");
      }
    };

    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [status, onlyNeedsReview, page, reloads]);

  const filtered = status !== "" || onlyNeedsReview;
  const refreshing = answer?.documents.some(isUnfinished) ?? false;

  return (
    <div className="space-y-4">
      {/* Filters. Changing a filter goes back to page 1. */}
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as DocumentStatus | "");
              setPage(1);
            }}
            className="h-9 rounded-md border bg-background px-2"
          >
            <option value="">All</option>
            <option value="pending">Waiting</option>
            <option value="processing">Processing</option>
            <option value="done">Done</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={onlyNeedsReview}
            onChange={(event) => {
              setOnlyNeedsReview(event.target.checked);
              setPage(1);
            }}
          />
          Only documents that need review
        </label>
        <Button variant="outline" size="sm" onClick={() => setReloads(reloads + 1)} className="ml-auto">
          <RefreshCw /> Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-4 rounded-md border border-destructive/50 p-3 text-sm" role="alert">
          <span className="text-destructive">{error}</span>
          <Button variant="outline" size="sm" onClick={() => setReloads(reloads + 1)}>Try again</Button>
        </div>
      )}

      {!answer && !error && <p className="text-muted-foreground">Loading documents...</p>}

      {answer && answer.total === 0 && (
        <p className="text-muted-foreground">
          {filtered ? "No documents match these filters." : <>No documents yet. <Link href="/upload" className="underline underline-offset-4">Upload some</Link>.</>}
        </p>
      )}

      {answer && answer.documents.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Invoices</TableHead>
                <TableHead>Review</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="text-right">Time taken</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {answer.documents.map((document) => (
                <TableRow key={document.id}>
                  <TableCell className="max-w-xs whitespace-normal">
                    <Link href={`/documents/${document.id}`} className="font-medium underline-offset-4 hover:underline">
                      {document.filename}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {[document.file_type?.toUpperCase(), readableSize(document.file_size)].filter(Boolean).join(" · ")}
                    </div>
                    {document.error && <div className="mt-1 text-xs text-destructive">{document.error}</div>}
                  </TableCell>
                  <TableCell><StatusBadge status={document.status} /></TableCell>
                  <TableCell className="text-right">{document.status === "done" ? document.invoice_count : "—"}</TableCell>
                  <TableCell>
                    {document.review_count > 0 ? (
                      <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300">
                        {document.review_count} need{document.review_count === 1 ? "s" : ""} review
                      </Badge>
                    ) : document.status === "done" ? (
                      <span className="text-sm text-muted-foreground">All fine</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-sm">{readableDate(document.created_at)}</TableCell>
                  <TableCell className="text-right text-sm">{readableSeconds(document.processing_seconds)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pages */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
            <span>
              {answer.total} {answer.total === 1 ? "document" : "documents"}
              {refreshing && " · updating every 2 seconds while documents are being processed"}
            </span>
            {answer.total_pages > 1 && (
              <span className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                Page {answer.page} of {answer.total_pages}
                <Button variant="outline" size="sm" disabled={page >= answer.total_pages} onClick={() => setPage(page + 1)}>Next</Button>
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
