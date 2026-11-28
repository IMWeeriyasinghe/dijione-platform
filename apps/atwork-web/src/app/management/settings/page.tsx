"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, FormField, Input, LoadingState, PageHeader, Select } from "@dijione/design-system";
import { Notice, Page, QueryError, RequirePermission } from "@/components/ui";
import { errorMessage, management, type Settings, type WorkMode } from "@/lib/api";
import { ALL_WORK_MODES, WORK_MODE_LABEL } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { BPAccessContent } from "@/app/management/bp/page";

// ─── General Settings ─────────────────────────────────────────────────────────

function SettingsForm({ initial }: { initial: Settings }) {
  const client = useQueryClient();
  const [v, setV] = useState(initial);
  const save = useMutation({ mutationFn: () => management.saveSettings(v), onSuccess: (saved) => { setV(saved); client.invalidateQueries({ queryKey: ["atwork"] }); } });
  const toggle = (m: WorkMode) => setV({ ...v, enabled_work_modes: v.enabled_work_modes.includes(m) ? v.enabled_work_modes.filter((x) => x !== m) : [...v.enabled_work_modes, m] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (!save.isPending) save.mutate(); }}>
      {save.isError && <Notice tone="error">{errorMessage(save.error)}</Notice>}
      {save.isSuccess && <Notice tone="success">Settings saved.</Notice>}
      <Card className="max-w-xl space-y-4 p-5">
        <fieldset><legend className="text-sm font-medium">Enabled work modes</legend><div className="mt-2 space-y-1">{ALL_WORK_MODES.map((m) => <label key={m} className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-dt-orange" checked={v.enabled_work_modes.includes(m)} onChange={() => toggle(m)} />{WORK_MODE_LABEL[m]}</label>)}</div></fieldset>
        <FormField label="Business time zone" htmlFor="tz" hint="An IANA name, such as Asia/Colombo. Daily totals and reports use this zone." required><Input id="tz" value={v.business_time_zone} onChange={(e) => setV({ ...v, business_time_zone: e.target.value })} /></FormField>
        <FormField label="Missed check-out threshold (hours)" htmlFor="threshold" hint="Sessions open longer are flagged. Nobody is checked out automatically." required><Input id="threshold" type="number" min={1} max={72} value={v.missed_checkout_hours} onChange={(e) => setV({ ...v, missed_checkout_hours: Number(e.target.value) })} /></FormField>
        <FormField label="Time format" htmlFor="format"><Select id="format" value={v.time_format} onChange={(e) => setV({ ...v, time_format: e.target.value as Settings["time_format"] })}><option value="24h">24-hour</option><option value="12h">12-hour</option></Select></FormField>
        <FormField label="Default history range (days)" htmlFor="days" required><Input id="days" type="number" min={7} max={90} value={v.default_history_days} onChange={(e) => setV({ ...v, default_history_days: Number(e.target.value) })} /></FormField>
        <Button type="submit" loading={save.isPending} disabled={v.enabled_work_modes.length === 0}>Save settings</Button>
      </Card>
    </form>
  );
}

function GeneralSettingsTab() {
  const query = useQuery({ queryKey: ["atwork", "settings"], queryFn: management.settings });
  if (query.isLoading) return <LoadingState />;
  if (!query.data) return <QueryError error={query.error} retry={() => query.refetch()} />;
  return <SettingsForm key={query.data.version} initial={query.data} />;
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

type Tab = "general" | "access";

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const base = "px-4 py-2 text-sm font-medium border-b-2 transition-colors";
  const active_ = "border-dt-orange text-dt-orange";
  const inactive = "border-transparent text-dt-text-secondary hover:text-dt-text-primary";
  return (
    <div className="mb-6 flex gap-0 border-b border-dt-border">
      <button className={`${base} ${active === "general" ? active_ : inactive}`} onClick={() => onChange("general")}>
        General Settings
      </button>
      <button className={`${base} ${active === "access" ? active_ : inactive}`} onClick={() => onChange("access")}>
        Access Management
      </button>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

function SettingsScreen() {
  const [tab, setTab] = useState<Tab>("general");
  return (
    <>
      <PageHeader title="Settings" description="DijiAtWork operational policy and access management." />
      <TabBar active={tab} onChange={setTab} />
      {tab === "general" && <GeneralSettingsTab />}
      {tab === "access" && (
        <RequirePermission permission={PERM.ACCESS_MANAGE} title="Access administration required">
          <BPAccessContent />
        </RequirePermission>
      )}
    </>
  );
}

export default function SettingsPage() {
  return (
    <Page>
      <RequirePermission permission={[PERM.MANAGEMENT, PERM.SETTINGS]} title="Settings access required">
        <SettingsScreen />
      </RequirePermission>
    </Page>
  );
}

