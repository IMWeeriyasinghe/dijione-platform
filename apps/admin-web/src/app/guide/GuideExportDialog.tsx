"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Mail, Send } from "lucide-react";
import { Button, Card, Modal, Select } from "@dijione/design-system";
import { listAdminGroups, getAdminGroup } from "@/lib/api";
import type { GuideModule, GuideSection } from "./content";

const MODULE_LABELS: Record<GuideModule, string> = {
  platform: "Platform / Admin Center",
  "talent-flow": "DijiTalentFlow",
  birthday: "DijiBirthday",
  spark: "DijiSpark",
};

export function GuideExportDialog({
  open,
  onClose,
  sections,
  onDownload,
}: {
  open: boolean;
  onClose: () => void;
  sections: GuideSection[];
  onDownload: (selectedIds: string[]) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<string[]>(sections.map((s) => s.id));
  const [selectedModules, setSelectedModules] = useState<GuideModule[]>(["platform", "talent-flow"]);
  const [mode, setMode] = useState<"download" | "share">("download");
  const [groupId, setGroupId] = useState<number | "">("");
  const [shareResult, setShareResult] = useState<{ groupName: string; activeCount: number } | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listAdminGroups, enabled: open });

  const modulesInScope = new Set(selectedModules);
  const visibleSections = sections.filter((s) => modulesInScope.has(s.module));

  const toggleSection = (id: string) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const toggleModule = (m: GuideModule) =>
    setSelectedModules((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const effectiveSelection = selectedIds.filter((id) => visibleSections.some((s) => s.id === id));

  const handleShare = async () => {
    if (!groupId) return;
    setResolving(true);
    setShareError(null);
    setShareResult(null);
    try {
      const group = await getAdminGroup(Number(groupId));
      setShareResult({ groupName: group.display_name, activeCount: group.members.length });
    } catch {
      setShareError("Could not resolve this group's members.");
    } finally {
      setResolving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Export / Share Guide">
      <div className="flex flex-col gap-5">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-semibold text-dt-text-primary">Step 1 — Select content</p>
            <div className="flex gap-2">
              <button
                type="button"
                className="text-xs font-medium text-dt-burnt-orange underline underline-offset-2"
                onClick={() => setSelectedIds(visibleSections.map((s) => s.id))}
              >
                Select All
              </button>
              <button
                type="button"
                className="text-xs font-medium text-dt-text-secondary underline underline-offset-2"
                onClick={() => setSelectedIds([])}
              >
                Clear
              </button>
            </div>
          </div>

          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">Manual scope</p>
          <div className="mb-3 flex flex-wrap gap-3">
            {(Object.keys(MODULE_LABELS) as GuideModule[]).map((m) => (
              <label key={m} className="flex items-center gap-1.5 text-sm text-dt-text-primary">
                <input type="checkbox" checked={selectedModules.includes(m)} onChange={() => toggleModule(m)} />
                {MODULE_LABELS[m]}
              </label>
            ))}
          </div>
          {(selectedModules.includes("birthday") || selectedModules.includes("spark")) && (
            <p className="mb-3 text-xs text-dt-text-secondary">
              DijiBirthday and DijiSpark are Coming Soon — only platform-level registry information is documented for
              them; detailed functional workflows are not yet available.
            </p>
          )}

          <Card className="max-h-48 overflow-y-auto p-3">
            <div className="grid gap-1.5 sm:grid-cols-2">
              {visibleSections.map((s) => (
                <label key={s.id} className="flex items-center gap-1.5 text-sm text-dt-text-primary">
                  <input type="checkbox" checked={selectedIds.includes(s.id)} onChange={() => toggleSection(s.id)} />
                  {s.title}
                </label>
              ))}
            </div>
          </Card>
        </div>

        <div>
          <p className="mb-2 text-sm font-semibold text-dt-text-primary">Step 2 — Choose action</p>
          <div className="flex gap-4">
            <label className="flex items-center gap-1.5 text-sm text-dt-text-primary">
              <input type="radio" checked={mode === "download"} onChange={() => setMode("download")} /> Download
            </label>
            <label className="flex items-center gap-1.5 text-sm text-dt-text-primary">
              <input type="radio" checked={mode === "share"} onChange={() => setMode("share")} /> Share with Group
            </label>
          </div>

          {mode === "share" && (
            <div className="mt-3 flex flex-col gap-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-dt-text-primary">Share with</label>
                  <Select
                    value={groupId}
                    onChange={(e) => {
                      setGroupId(e.target.value ? Number(e.target.value) : "");
                      setShareResult(null);
                      setShareError(null);
                    }}
                    className="min-w-48"
                  >
                    <option value="">Select a group…</option>
                    {(groupsQuery.data ?? []).map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.display_name} ({g.member_count} member{g.member_count === 1 ? "" : "s"})
                      </option>
                    ))}
                  </Select>
                </div>
                <Button size="sm" variant="secondary" onClick={handleShare} disabled={!groupId} loading={resolving}>
                  <Mail className="size-4" /> Resolve Group
                </Button>
              </div>

              {shareError && <p className="text-sm text-dt-danger">{shareError}</p>}

              {shareResult && (
                <div className="rounded-lg border border-dt-warning/40 bg-[color-mix(in_srgb,var(--dt-warning)_8%,white)] p-3 text-sm text-dt-text-primary">
                  <p>
                    Resolved <strong>{shareResult.activeCount}</strong> active member
                    {shareResult.activeCount === 1 ? "" : "s"} of <strong>{shareResult.groupName}</strong>.
                  </p>
                  <p className="mt-1 text-dt-text-secondary">
                    Email delivery is not configured for this environment — no message was sent. This guide has been
                    prepared for email integration; use Download in the meantime to distribute it manually.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <p className="mb-2 text-sm font-semibold text-dt-text-primary">Step 3 — Generate</p>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => onDownload(effectiveSelection)}
              disabled={effectiveSelection.length === 0}
            >
              <Download className="size-4" /> Download
            </Button>
            {mode === "share" && (
              <Button variant="secondary" disabled title="Live email sending requires a configured email provider">
                <Send className="size-4" /> Send Email (not configured)
              </Button>
            )}
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
