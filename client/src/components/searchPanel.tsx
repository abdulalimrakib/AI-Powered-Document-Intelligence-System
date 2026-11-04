"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Loader2, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, SearchAnswer, SearchMode, searchInvoices } from "@/lib/api";
import { cn } from "@/lib/utils";

/*--Everything in the search form. The same names as the backend's search options.--*/
const FORM_NAMES = ["q", "mode", "date_from", "date_to", "total_min", "total_max", "currency", "supplier", "needs_review"] as const;
type FormValues = Record<(typeof FORM_NAMES)[number], string>;

// The page address is where the search lives (e.g. /search?q=chairs&mode=meaning), so the browser's Back button
// and bookmarks keep it. The form is filled from the address, and the results are loaded from it.
const formFromAddress = (params: URLSearchParams): FormValues =>
  Object.fromEntries(FORM_NAMES.map((name) => [name, params.get(name) ?? ""])) as FormValues;

// The form -> "q=chairs&mode=meaning" (empty values are left out; keyword is the default mode)
const addressFromForm = (form: FormValues, page = 1) => {
  const params = new URLSearchParams();
  for (const name of FORM_NAMES) {
    const value = form[name].trim();
    if (value && !(name === "mode" && value === "keyword")) params.set(name, value);
  }
  if (page > 1) params.set("page", String(page));
  return params.toString();
};

/*--The search page: a search box, keyword or meaning, filters, and the results--*/
export default function SearchPanel() {
  const router = useRouter();
  const address = useSearchParams().toString(); // e.g. "q=chairs&mode=meaning"
  const [form, setForm] = useState<FormValues>(() => formFromAddress(new URLSearchParams(address)));
  const [answer, setAnswer] = useState<SearchAnswer | null>(null);
  const [error, setError] = useState<{ message: string; meaningNotAvailable: boolean } | null>(null);
  const [searching, setSearching] = useState(false);

  const params = new URLSearchParams(address);
  const mode: SearchMode = params.get("mode") === "meaning" ? "meaning" : "keyword"; // the mode of the results shown

  /*--Search again whenever the address changes (a new search, another page, or Back)--*/
  useEffect(() => {
    const current = new URLSearchParams(address);
    setForm(formFromAddress(current)); // e.g. after Back, the form shows the search again
    if (!address) {
      setAnswer(null);
      setError(null);
      return;
    }

    let stopped = false; // an older search that answers late is ignored
    setSearching(true);
    const options = Object.fromEntries(current.entries());
    searchInvoices({ ...options, page: Number(options.page) || 1 })
      .then((data) => {
        if (stopped) return;
        setAnswer(data);
        setError(null);
      })
      .catch((problem) => {
        if (stopped) return;
        setAnswer(null);
        setError({
          message: problem instanceof ApiError ? problem.message : "The search failed. Please try again.",
          // 503 from a meaning search: Gemini can't be used right now, but keyword search still works
          meaningNotAvailable: problem instanceof ApiError && problem.statusCode === 503 && current.get("mode") === "meaning",
        });
      })
      .finally(() => !stopped && setSearching(false));
    return () => {
      stopped = true;
    };
  }, [address]);

  const change = (name: keyof FormValues, value: string) => setForm({ ...form, [name]: value });
  const goTo = (newAddress: string) => router.push(newAddress ? `/search?${newAddress}` : "/search");

  return (
    <div className="space-y-6">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          goTo(addressFromForm(form)); // a new search always starts on page 1
        }}
        className="space-y-4"
      >
        {/* The search words, and how to search */}
        <div className="flex flex-wrap gap-2">
          <Input
            value={form.q}
            onChange={(event) => change("q", event.target.value)}
            placeholder={form.mode === "meaning" ? 'Describe what you look for, e.g. "office furniture"' : "Invoice number, supplier, customer, item, any word..."}
            aria-label="Search words"
            maxLength={200}
            className="min-w-60 flex-1"
          />
          <div role="radiogroup" aria-label="How to search" className="flex rounded-md border p-0.5">
            {(["keyword", "meaning"] as const).map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={(form.mode || "keyword") === option}
                onClick={() => change("mode", option)}
                className={cn(
                  "rounded px-3 text-sm",
                  (form.mode || "keyword") === option ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {option === "keyword" ? "Keyword" : "Meaning"}
              </button>
            ))}
          </div>
          <Button type="submit" disabled={searching}>
            {searching ? <Loader2 className="animate-spin" /> : <Search />} Search
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {(form.mode || "keyword") === "keyword"
            ? "Keyword: finds the exact words (small or capital letters don't matter)."
            : 'Meaning: also finds invoices that mean the same without the same words, e.g. "office furniture" finds "Office chairs".'}
        </p>

        {/* Filters (all optional). With a filter, keyword search also works without search words. */}
        <fieldset className="grid gap-3 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-4">
          <legend className="px-1 text-sm font-medium">Filters</legend>
          <FilterField label="Date from"><Input type="date" value={form.date_from} onChange={(event) => change("date_from", event.target.value)} /></FilterField>
          <FilterField label="Date to"><Input type="date" value={form.date_to} onChange={(event) => change("date_to", event.target.value)} /></FilterField>
          <FilterField label="Total from"><Input inputMode="decimal" placeholder="e.g. 500" value={form.total_min} onChange={(event) => change("total_min", event.target.value)} /></FilterField>
          <FilterField label="Total to"><Input inputMode="decimal" placeholder="e.g. 999.99" value={form.total_max} onChange={(event) => change("total_max", event.target.value)} /></FilterField>
          <FilterField label="Currency"><Input placeholder="e.g. USD" maxLength={3} value={form.currency} onChange={(event) => change("currency", event.target.value)} /></FilterField>
          <FilterField label="Supplier"><Input placeholder="Part of the name" maxLength={200} value={form.supplier} onChange={(event) => change("supplier", event.target.value)} /></FilterField>
          <FilterField label="Needs review">
            <select value={form.needs_review} onChange={(event) => change("needs_review", event.target.value)} className="h-9 w-full rounded-md border bg-background px-2 text-sm">
              <option value="">Any</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </FilterField>
          <div className="flex items-end">
            <Button type="button" variant="ghost" onClick={() => goTo("")}>Clear all</Button>
          </div>
        </fieldset>
      </form>

      {/* Problems */}
      {error && (
        <div className="flex flex-wrap items-center gap-4 rounded-md border border-destructive/50 p-3 text-sm" role="alert">
          <span className="text-destructive">{error.message}</span>
          {error.meaningNotAvailable && (
            <Button variant="outline" size="sm" onClick={() => goTo(addressFromForm({ ...formFromAddress(params), mode: "keyword" }))}>
              Search by keyword instead
            </Button>
          )}
        </div>
      )}

      {!address && <p className="text-muted-foreground">Type something to search for, or use a filter.</p>}

      {/* The results */}
      {answer && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {answer.total} {answer.total === 1 ? "invoice" : "invoices"} found
            {mode === "meaning" && " by meaning, closest first. Closeness goes from 0 (unrelated) to 1 (the same meaning)."}
          </p>
          {mode === "meaning" && (answer.not_in_meaning_search ?? 0) > 0 && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden />
              {answer.not_in_meaning_search} {answer.not_in_meaning_search === 1 ? "invoice is" : "invoices are"} not in meaning
              search yet; keyword search still finds them.
            </p>
          )}

          {answer.invoices.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>{mode === "meaning" ? "Closeness" : "Found in"}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {answer.invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell className="whitespace-normal">
                      <Link href={`/documents/${invoice.document_id}`} className="font-medium underline-offset-4 hover:underline">
                        {invoice.invoice_number ?? "(no number)"}
                      </Link>
                      <div className="text-xs text-muted-foreground">{invoice.filename} · {invoice.source}</div>
                      {invoice.needs_review && (
                        <Badge className="mt-1 bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300">Needs review</Badge>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-normal">{invoice.supplier_name ?? "—"}</TableCell>
                    <TableCell className="whitespace-normal">{invoice.customer_name ?? "—"}</TableCell>
                    <TableCell>{invoice.invoice_date ?? "—"}</TableCell>
                    <TableCell className="text-right">{invoice.total ? `${invoice.total} ${invoice.currency ?? ""}` : "—"}</TableCell>
                    <TableCell className="max-w-xs whitespace-normal text-sm">
                      {mode === "meaning" ? (
                        <Closeness value={invoice.similarity ?? 0} />
                      ) : (
                        <>
                          {invoice.found_in ?? <span className="text-muted-foreground">filters only</span>}
                          {invoice.matched_text && <q className="block font-mono text-xs text-muted-foreground">{invoice.matched_text}</q>}
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pages */}
          {answer.total_pages > 1 && (
            <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
              <Button variant="outline" size="sm" disabled={answer.page <= 1} onClick={() => goTo(addressFromForm(formFromAddress(params), answer.page - 1))}>Previous</Button>
              Page {answer.page} of {answer.total_pages}
              <Button variant="outline" size="sm" disabled={answer.page >= answer.total_pages} onClick={() => goTo(addressFromForm(formFromAddress(params), answer.page + 1))}>Next</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

/*--The closeness of a meaning-search result, as a number and a small bar--*/
function Closeness({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-16 overflow-hidden rounded bg-muted" aria-hidden>
        <span className="block h-full bg-primary" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="font-mono">{value.toFixed(3)}</span>
    </span>
  );
}
