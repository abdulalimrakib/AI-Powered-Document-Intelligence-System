import Link from "next/link";
import { Upload, FileText, Search } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const sections = [
  { href: "/upload", icon: Upload, title: "Upload", text: "Add PDFs, images, Excel and CSV files for processing." },
  { href: "/documents", icon: FileText, title: "Documents", text: "Track progress, review extracted data and fix errors." },
  { href: "/search", icon: Search, title: "Search", text: "Find documents by keyword, filters or meaning." },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Document intelligence</h1>
        <p className="text-muted-foreground">
          Extract, validate and cross-check invoices and financial documents.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {sections.map(({ href, icon: Icon, title, text }) => (
          <Link key={href} href={href}>
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader>
                <Icon className="h-5 w-5 text-muted-foreground" aria-hidden />
                <CardTitle>{title}</CardTitle>
                <CardDescription>{text}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
