"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  LoadingState,
  MetricCard,
  PageHeader,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import { Activity, AlertTriangle, Fingerprint, Radio, Users, UserX } from "lucide-react";
import { BreakdownBars, ColumnChart } from "@/components/charts";
import { DateInput, FilterRow, SiteSelect } from "@/components/FilterBar";
import { EmployeeCell, IdentityBadge } from "@/components/FlagChips";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { ExportButton } from "@/components/ExportButton";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { SyncNowButton } from "@/components/SyncNowButton";
import { getHourly, getOverview, getRecent, getTrend } from "@/lib/dashboard";
import { localTime } from "@/lib/flags";
import { FEED_LABEL, formatDateTime } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";

function OverviewView() {
  const { site } = useSite();
  const { scope } = useOnsiteScope();
  const queryClient = useQueryClient();
  const [day, setDay] = useState<string | null>(null);
  const [trendDays, setTrendDays] = useState(30);
  const date = day ?? site.today;
  const params = { site_id: site.site_id, date };

  const overview = useQuery({ queryKey: ["onsite-overview", params], queryFn: () => getOverview(params), ...liveQuery });
  const hourly = useQuery({ queryKey: ["onsite-hourly", params], queryFn: () => getHourly(params), ...liveQuery });
  const trend = useQuery({
    queryKey: ["onsite-trend", site.site_id, trendDays, date],
    queryFn: () => getTrend({ site_id: site.site_id, days: trendDays, date_to: date }),
    ...liveQuery,
  });
  const recent = useQuery({
    queryKey: ["onsite-recent", site.site_id],
    queryFn: () => getRecent({ site_id: site.site_id, limit: 12 }),
    ...liveQuery,
  });

  if (overview.isLoading) return <LoadingState label="Loading attendance overview…" />;
  if (!overview.data) return <ErrorState onRetry={() => overview.refetch()} />;
  const o = overview.data;
  const k = o.kpis;
  const feed = k.feed_state ?? "NOT_SYNCED";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Attendance overview"
        description={`Activity recorded at ${site.name}, in site-local time${site.time_zone ? ` (${site.time_zone})` : ""}.`}
        action={
          <div className="flex flex-wrap items-start gap-2">
            <ExportButton path="dashboard/overview" params={params} label="Export summary" />
            {hasPermission(scope, PERM.SYNC) && <SyncNowButton onDone={() => queryClient.invalidateQueries()} />}
          </div>
        }
      />
      <FilterRow>
        <SiteSelect />
        <DateInput label="Date" value={date} onChange={setDay} />
        {site.last_activity_date && site.last_activity_date !== date && (
          <button
            type="button"
            className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
            onClick={() => setDay(site.last_activity_date)}
          >
            Latest activity day ({site.last_activity_date})
          </button>
        )}
      </FilterRow>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dt-border bg-dt-surface px-4 py-3 text-sm text-dt-text-secondary">
        <FreshnessIndicator siteId={site.site_id} queries={[overview, hourly, trend, recent]} />
        <span>Latest activity received: <span className="text-dt-text-primary">{formatDateTime(o.latest_received_utc)}</span></span>
        {feed !== "FRESH" && (
          <span className="text-dt-burnt-orange">The feed may be incomplete — treat “No activity recorded” with care.</span>
        )}
        {!o.directory_available && <span className="text-dt-burnt-orange">Employee details unavailable — showing codes only.</span>}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Employees with activity" value={k.employees_with_activity} icon={Users} tone="brand" />
        <MetricCard label="Activity events" value={k.total_events} icon={Activity} />
        <MetricCard label="Employees needing review" value={k.employees_needing_review} icon={AlertTriangle} />
        <MetricCard label="Single-activity employees" value={k.single_punch_employees} icon={UserX} />
        <MetricCard label="Unmatched codes" value={k.unmatched_codes} icon={Fingerprint} />
        <MetricCard label="Feed freshness" value={FEED_LABEL[feed]} icon={Radio} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Activity by hour</CardTitle></CardHeader>
          <CardContent>
            {hourly.data ? (
              <ColumnChart
                label={`Activity by hour on ${date}`}
                valueLabel="events"
                xLabel={(h) => `${h.padStart(2, "0")}:00`}
                data={hourly.data.hours.map((h) => ({ key: String(h.hour), value: h.events, tick: h.hour % 3 === 0 ? `${String(h.hour).padStart(2, "0")}` : "" }))}
              />
            ) : (
              <LoadingState label="Loading…" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle>Activity trend</CardTitle>
            <div className="flex gap-1" role="group" aria-label="Trend range">
              {[7, 30].map((d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={trendDays === d}
                  onClick={() => setTrendDays(d)}
                  className={`rounded-md px-2 py-1 text-xs font-medium ${trendDays === d ? "bg-dt-cream text-dt-burnt-orange" : "text-dt-text-secondary hover:bg-dt-surface-warm"}`}
                >
                  {d} days
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {trend.data ? (
              <ColumnChart
                label={`Daily activity, ${trendDays} days to ${date}`}
                valueLabel="events"
                highlightLast
                data={trend.data.days.map((d) => ({ key: d.date, value: d.events }))}
                xLabel={(d) => d.slice(5)}
              />
            ) : (
              <LoadingState label="Loading…" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_3fr]">
        <Card>
          <CardHeader><CardTitle>Needs review</CardTitle></CardHeader>
          <CardContent><BreakdownBars counts={o.review_breakdown} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Recent activity</CardTitle></CardHeader>
          <CardContent>
            {recent.data && recent.data.items.length > 0 ? (
              <Table>
                <Thead><Tr><Th>Employee</Th><Th>Local time</Th><Th>Terminal</Th><Th>Identity</Th></Tr></Thead>
                <tbody>
                  {recent.data.items.map((e, i) => (
                    <Tr key={`${e.emp_code}-${e.local_time}-${i}`}>
                      <Td><EmployeeCell name={e.employee_name} code={e.emp_code} /></Td>
                      <Td>{e.local_date} {localTime(e.local_time)}</Td>
                      <Td>{e.terminal ?? "—"}</Td>
                      <Td><IdentityBadge cls={e.identity_class} /></Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <p className="text-sm text-dt-text-secondary">No activity recorded in the last 92 days.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <SiteProvider>
      <OverviewView />
    </SiteProvider>
  );
}
