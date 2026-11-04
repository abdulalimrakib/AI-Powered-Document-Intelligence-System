import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

/*--The status of a document as a coloured label: pending, processing, done or failed--*/
const STYLES: Record<DocumentStatus, { label: string; icon: typeof Clock; className: string }> = {
  pending: { label: "Waiting", icon: Clock, className: "bg-muted text-muted-foreground" },
  processing: { label: "Processing", icon: Loader2, className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
  done: { label: "Done", icon: CheckCircle2, className: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300" },
  failed: { label: "Failed", icon: XCircle, className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
};

export default function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, icon: Icon, className } = STYLES[status];
  return (
    <Badge className={className}>
      <Icon className={cn(status === "processing" && "animate-spin")} aria-hidden />
      {label}
    </Badge>
  );
}
