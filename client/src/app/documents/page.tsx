import type { Metadata } from "next";
import Link from "next/link";
import DocumentList from "@/components/documentList";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Documents · DocIntel" };

export default function DocumentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-muted-foreground">Every uploaded file, newest first. Open one to see what was found.</p>
        </div>
        <Button asChild>
          <Link href="/upload">Upload documents</Link>
        </Button>
      </div>
      <DocumentList />
    </div>
  );
}
