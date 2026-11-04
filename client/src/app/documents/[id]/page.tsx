import type { Metadata } from "next";
import DocumentDetails from "@/components/documentDetails";

export const metadata: Metadata = { title: "Document · DocIntel" };

// The address is /documents/5: Next.js gives us "5" as params.id
export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DocumentDetails id={id} />;
}
