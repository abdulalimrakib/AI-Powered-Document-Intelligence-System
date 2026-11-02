import Link from "next/link";
import { FileSearch } from "lucide-react";
import { ThemeToggle } from "@/_providers/themeToggle";

const links = [
  { href: "/upload", label: "Upload" },
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
];

export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-sm">
      <nav className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <FileSearch className="h-5 w-5" aria-hidden />
          <span>DocIntel</span>
        </Link>
        <div className="flex items-center gap-1 sm:gap-4">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {label}
            </Link>
          ))}
          <ThemeToggle />
        </div>
      </nav>
    </header>
  );
}
