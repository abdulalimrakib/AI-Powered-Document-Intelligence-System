import { Suspense } from "react";
import type { Metadata } from "next";
import SearchPanel from "@/components/searchPanel";

export const metadata: Metadata = { title: "Search · DocIntel" };

export default function SearchPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Search invoices</h1>
        <p className="text-muted-foreground">Search by keyword or by meaning, and narrow the results with filters.</p>
      </div>
      {/* SearchPanel reads the search from the page address; Next.js needs <Suspense> around that */}
      <Suspense fallback={<p className="text-muted-foreground">Loading...</p>}>
        <SearchPanel />
      </Suspense>
    </div>
  );
}
