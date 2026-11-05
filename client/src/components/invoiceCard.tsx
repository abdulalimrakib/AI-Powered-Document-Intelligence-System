"use client";

import { useState } from "react";
import { AlertTriangle, Check, CheckCircle2, Loader2, Pencil, UserCheck, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, correctInvoice, FieldStatus, Invoice, INVOICE_FIELDS, InvoiceField } from "@/lib/api";
import { fieldLabel, readableDate } from "@/lib/format";

/*--How sure the system is about a value--*/
const FIELD_STATUS: Record<FieldStatus, { label: string; className: string }> = {
  found: { label: "Found", className: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300" },
  uncertain: { label: "Uncertain", className: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300" },
  missing: { label: "Missing", className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
  corrected: { label: "Corrected", className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
};

/*--One invoice: its problems, its fields with their evidence, and its line items--*/
// Everything from the document is shown as plain text (React never runs it as HTML), so a nasty invoice
// can't put code into the page.
// A person can correct a field, or mark the invoice as checked. The backend cleans the value and checks the
// invoice again (the same rules as before); then `onChanged` loads the document again, so the problems,
// the history and other invoices (e.g. a duplicate that is no longer one) are all up to date.
export default function InvoiceCard({ invoice, number, onChanged }: { invoice: Invoice; number: number; onChanged: () => void }) {
  const [editing, setEditing] = useState<InvoiceField | null>(null); // the field being corrected
  const [draft, setDraft] = useState(""); // what the person typed
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null); // e.g. "total: 'abc' is not an amount"

  const title = invoice.fields.invoice_number.value ?? `Invoice ${number}`;
  // The fields that have a problem get a red mark in the table
  const fieldsWithProblems = new Set(invoice.validation_errors.map((error) => error.field));

  const startEditing = (name: InvoiceField) => {
    setEditing(name);
    setDraft(invoice.fields[name].value ?? "");
    setEditError(null);
  };
  const stopEditing = () => {
    setEditing(null);
    setEditError(null);
  };

  /*--Send a correction or "checked" to the backend--*/
  // A problem with a typed value is shown under the field; any other problem as a pop-up message.
  const save = async (change: Parameters<typeof correctInvoice>[1], errorUnderField = false) => {
    setSaving(true);
    setEditError(null);
    try {
      const updated = await correctInvoice(invoice.id, change);
      toast.success(updated.needs_review ? "Saved. The invoice still needs review." : "Saved. The invoice has no open problems.");
      stopEditing();
      onChanged();
    } catch (problem) {
      const message = problem instanceof ApiError ? problem.message : "It could not be saved. Please try again.";
      if (errorUnderField) setEditError(message);
      else toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  // An empty box empties the field (the backend then marks it as missing)
  const saveField = () => editing && save({ fields: { [editing]: draft.trim() === "" ? null : draft } }, true);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {invoice.source} · read by {invoice.method === "gemini" ? `AI (${invoice.ai_model ?? "Gemini"})` : invoice.method}
          </p>
        </div>
        {!invoice.error && (
          <div className="flex flex-wrap items-center gap-2">
            {invoice.reviewed_at ? (
              <Badge className="bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300">
                <UserCheck aria-hidden /> Checked by a person · {readableDate(invoice.reviewed_at)}
              </Badge>
            ) : invoice.needs_review ? (
              <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300">
                <AlertTriangle aria-hidden /> Needs review
              </Badge>
            ) : (
              <Badge className="bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300">
                <CheckCircle2 aria-hidden /> No open problems
              </Badge>
            )}
            {/* For an invoice that is right although a check complained, e.g. because of a discount */}
            {invoice.needs_review && !invoice.reviewed_at && (
              <Button variant="outline" size="sm" disabled={saving} onClick={() => save({ reviewed: true })}>
                <Check /> Mark as checked
              </Button>
            )}
            {invoice.reviewed_at && (
              <Button variant="ghost" size="sm" disabled={saving} onClick={() => save({ reviewed: false })}>
                Undo
              </Button>
            )}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-6">
        {/* The AI could not read this invoice at all */}
        {invoice.error && (
          <p className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {invoice.error}
          </p>
        )}

        {/* The problems found by the checks */}
        {invoice.validation_errors.length > 0 && (
          <div className="space-y-2 rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/40">
            <p className="text-sm font-medium">Problems found ({invoice.validation_errors.length})</p>
            <ul className="space-y-1 text-sm">
              {invoice.validation_errors.map((error) => (
                <li key={error.id} className="flex items-start gap-2">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
                  <span>
                    {/* No label when the message already starts with it ("line item 1: line item 1: ...") */}
                    {error.field && !error.message.toLowerCase().startsWith(fieldLabel(error.field).toLowerCase()) && (
                      <span className="font-medium">{fieldLabel(error.field)}: </span>
                    )}
                    {error.message}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* The fields, each with how sure we are and the words in the document it comes from */}
        {!invoice.error && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Evidence (from the document)</TableHead>
                <TableHead><span className="sr-only">Correct</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {INVOICE_FIELDS.map((name) => {
                const field = invoice.fields[name];
                const { label, className } = FIELD_STATUS[field.status] ?? FIELD_STATUS.found;
                return (
                  <TableRow key={name} className={fieldsWithProblems.has(name) ? "bg-red-50 dark:bg-red-950/30" : undefined}>
                    <TableCell className="font-medium">
                      {fieldsWithProblems.has(name) && <XCircle className="mr-1 inline h-4 w-4 text-destructive" aria-label="has a problem" />}
                      {fieldLabel(name)}
                    </TableCell>
                    <TableCell className="min-w-40">
                      {editing === name ? (
                        <form
                          onSubmit={(event) => {
                            event.preventDefault(); // Enter saves
                            saveField();
                          }}
                          className="space-y-1"
                        >
                          <Input
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            onKeyDown={(event) => event.key === "Escape" && stopEditing()}
                            aria-label={`New value for ${fieldLabel(name)}`}
                            maxLength={500}
                            autoFocus
                          />
                          <div className="flex gap-2">
                            <Button type="submit" size="sm" disabled={saving}>
                              {saving && <Loader2 className="animate-spin" />} Save
                            </Button>
                            <Button type="button" variant="ghost" size="sm" onClick={stopEditing} disabled={saving}>Cancel</Button>
                          </div>
                          {editError ? (
                            <p className="text-xs text-destructive" role="alert">{editError}</p>
                          ) : (
                            <p className="text-xs text-muted-foreground">Leave it empty to remove the value.</p>
                          )}
                        </form>
                      ) : (
                        field.value ?? <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell><Badge className={className}>{label}</Badge></TableCell>
                    <TableCell className="max-w-md whitespace-normal">
                      {field.evidence && <q className="font-mono text-xs">{field.evidence}</q>}
                      {field.note && <div className="text-xs text-muted-foreground">{field.note}</div>}
                    </TableCell>
                    <TableCell className="text-right">
                      {editing !== name && (
                        <Button variant="ghost" size="sm" onClick={() => startEditing(name)} disabled={saving} aria-label={`Correct ${fieldLabel(name)}`}>
                          <Pencil /> Edit
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        {/* The line items */}
        {invoice.line_items.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Line items ({invoice.line_items.length})</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit price</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoice.line_items.map((item) => (
                  <TableRow key={item.position} className={item.problems.length ? "bg-red-50 dark:bg-red-950/30" : undefined}>
                    <TableCell>{item.position}</TableCell>
                    <TableCell className="max-w-md whitespace-normal">
                      {item.description ?? "—"}
                      {item.problems.map((problem) => (
                        <div key={problem} className="text-xs text-destructive">{problem}</div>
                      ))}
                    </TableCell>
                    <TableCell className="text-right">{item.quantity ?? "—"}</TableCell>
                    <TableCell className="text-right">{item.unit_price ?? "—"}</TableCell>
                    <TableCell className="text-right">{item.amount ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {invoice.warnings.length > 0 && (
          <ul className="space-y-1 text-sm text-muted-foreground">
            {invoice.warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {warning}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
