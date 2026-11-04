"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, RotateCcw, XCircle } from "lucide-react";
import { toast } from "sonner";
import { REFRESH_EVERY_MS } from "@/components/documentList";
import InvoiceCard from "@/components/invoiceCard";
import StatusBadge from "@/components/statusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, DocumentDetail, getDocument, reprocessDocument } from "@/lib/api";
import { readableDate, readableSeconds, readableSize } from "@/lib/format";

const isUnfinished = (document: DocumentDetail) => document.status === "pending" || document.status === "processing";

/*--One document: its status, what was found in it, its problems and its history--*/
export default function DocumentDetails({ id }: { id: string }) {
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0); // +1 = load again now
  const [reprocessing, setReprocessing] = useState(false);

  /*--Load the document, and keep loading it every 2 seconds while it is waiting or processing--*/
  // The same idea as in documentList.tsx
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const data = await getDocument(id);
        if (stopped) return;
        setDocument(data);
        setError(null);
        if (isUnfinished(data)) timer = setTimeout(load, REFRESH_EVERY_MS);
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof ApiError ? problem.message : "The document could not be loaded.");
      }
    };

    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id, reloads]);

  /*--"Process again": for a failed document, or one with invoices the AI could not read--*/
  const processAgain = async () => {
    setReprocessing(true);
    try {
      await reprocessDocument(Number(id));
      toast.success("The document will be processed again.");
      setReloads(reloads + 1); // shows "Waiting", then updates by itself
    } catch (problem) {
      toast.error(problem instanceof ApiError ? problem.message : "It could not be sent again.");
    } finally {
      setReprocessing(false);
    }
  };

  const backLink = (
    <Link href="/documents" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden /> All documents
    </Link>
  );

  if (!document) {
    return (
      <div className="space-y-4">
        {backLink}
        {error ? (
          <div className="flex items-center gap-4 text-sm" role="alert">
            <span className="text-destructive">{error}</span>
            <Button variant="outline" size="sm" onClick={() => setReloads(reloads + 1)}>Try again</Button>
          </div>
        ) : (
          <p className="text-muted-foreground">Loading the document...</p>
        )}
      </div>
    );
  }

  const failedInvoices = document.invoices.filter((invoice) => invoice.error).length;
  const canProcessAgain = document.status === "failed" || (document.status === "done" && failedInvoices > 0);
  const needReview = document.invoices.filter((invoice) => invoice.needs_review).length;

  return (
    <div className="space-y-6">
      {backLink}

      {/* The document itself */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <h1 className="break-all text-2xl font-semibold tracking-tight">{document.filename}</h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <StatusBadge status={document.status} />
            {document.file_type && <span>{document.file_type.toUpperCase()}</span>}
            <span>{readableSize(document.file_size)}</span>
            <span>Uploaded {readableDate(document.created_at)}</span>
            {document.processing_seconds && <span>Read in {readableSeconds(document.processing_seconds)}</span>}
          </div>
        </div>
        {canProcessAgain && (
          <Button onClick={processAgain} disabled={reprocessing}>
            {reprocessing ? <Loader2 className="animate-spin" /> : <RotateCcw />} Process again
          </Button>
        )}
      </div>

      {/* Problems with the whole file */}
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {document.error && (
        <p className="flex items-start gap-2 rounded-md border border-destructive/50 p-3 text-sm text-destructive" role="alert">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {document.error}
        </p>
      )}
      {document.warnings.length > 0 && (
        <ul className="space-y-1 rounded-md border p-3 text-sm">
          {document.warnings.map((warning) => (
            <li key={warning} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden /> {warning}
            </li>
          ))}
        </ul>
      )}

      {isUnfinished(document) && (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {document.status === "pending" ? "Waiting to be processed..." : "Reading the file and extracting the invoices..."}
          {" "}This page updates by itself.
        </p>
      )}

      {/* The invoices */}
      {document.status === "done" && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">
            {document.invoices.length} {document.invoices.length === 1 ? "invoice" : "invoices"} found
            {needReview > 0 && <span className="font-normal text-muted-foreground"> · {needReview} need{needReview === 1 ? "s" : ""} review</span>}
          </h2>
          {document.invoices.length === 0 && <p className="text-muted-foreground">No invoices were found in this file.</p>}
          {document.invoices.map((invoice, index) => (
            <InvoiceCard key={invoice.id} invoice={invoice} number={index + 1} onChanged={() => setReloads(reloads + 1)} />
          ))}
        </div>
      )}

      {/* What happened, and when */}
      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2 text-sm">
            {document.history.map((entry) => (
              <li key={entry.id} className="grid gap-x-4 sm:grid-cols-[10rem_7rem_1fr]">
                <span className="text-muted-foreground">{readableDate(entry.created_at)}</span>
                <span className="font-medium capitalize">{entry.step}</span>
                <span>{entry.message}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
