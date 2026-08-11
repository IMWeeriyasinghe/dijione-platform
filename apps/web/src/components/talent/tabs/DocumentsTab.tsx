"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Upload } from "lucide-react";
import { useState } from "react";
import { listDocuments, uploadDocument } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { FormField, Input, Select } from "@/components/ui/FormField";

const CATEGORIES = ["CV", "CONTRACT", "REQUIREMENT", "OFFER_LETTER", "OTHER"] as const;

export function DocumentsTab({ requestId }: { requestId: number }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [fileName, setFileName] = useState("");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("OTHER");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", requestId],
    queryFn: () => listDocuments(requestId),
  });

  const mutation = useMutation({
    mutationFn: () => uploadDocument(requestId, fileName, category),
    onSuccess: () => {
      setFileName("");
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["documents", requestId] });
    },
  });

  if (isLoading) return <LoadingState label="Loading documents…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          Add Document
        </Button>
      </div>

      {!data || data.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Add CVs, requirement briefs, contracts, or offer letters relevant to this request."
          action={
            <Button size="sm" onClick={() => setOpen(true)}>
              Add Document
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.map((doc) => (
            <Card key={doc.id} className="flex items-center gap-3 p-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-dt-surface-warm text-dt-burnt-orange">
                <FileText className="size-4.5" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-dt-text-primary">{doc.file_name}</p>
                <p className="text-xs text-dt-text-secondary">
                  {doc.category.replace("_", " ")} · {doc.uploaded_by_name} · {formatDate(doc.created_at)}
                </p>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="Add Document">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (fileName.trim()) mutation.mutate();
          }}
          className="flex flex-col gap-4"
        >
          <FormField label="File Name" htmlFor="file-name" required hint="Local MVP — metadata only, no real upload storage yet.">
            <Input
              id="file-name"
              required
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              placeholder="e.g. Candidate_CV.pdf"
            />
          </FormField>
          <FormField label="Category" htmlFor="category">
            <Select id="category" value={category} onChange={(e) => setCategory(e.target.value as (typeof CATEGORIES)[number])}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace("_", " ")}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="flex justify-end gap-3 pt-1">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              <Upload className="size-4" />
              Add
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
