"use client";

import { useState } from "react";
import { Button } from "@dijione/design-system";
import { FileSpreadsheet } from "lucide-react";
import { downloadExport, type ExportPath } from "@/lib/dashboard";

type Params = Record<string, string | number | boolean | undefined | null>;

/** "Export to Excel": the server builds the .xlsx from the same filters the
 *  page is showing (page/sort excluded), re-applying site scope itself. */
export function ExportButton({ path, params, label = "Export to Excel" }: { path: ExportPath; params: Params; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" disabled={busy} onClick={async () => {
        setBusy(true);
        setError(null);
        try {
          await downloadExport(path, params);
        } catch (e) {
          setError(e instanceof Error ? e.message : "Export failed. Please try again.");
        } finally {
          setBusy(false);
        }
      }}>
        <FileSpreadsheet className="size-4" aria-hidden /> {busy ? "Preparing…" : label}
      </Button>
      {error && <p role="alert" className="max-w-sm text-right text-sm text-dt-danger">{error}</p>}
    </div>
  );
}
