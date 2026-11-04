import type { Metadata } from "next";
import UploadForm from "@/components/uploadForm";

export const metadata: Metadata = { title: "Upload · DocIntel" };

export default function UploadPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Upload documents</h1>
        <p className="text-muted-foreground">
          Invoices are read in the background. You can leave this page and follow the progress on the Documents page.
        </p>
      </div>
      <UploadForm />
    </div>
  );
}
