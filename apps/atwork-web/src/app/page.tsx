"use client";

import Link from "next/link";
import { Card, PageHeader } from "@dijione/design-system";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";

const AREAS = [
  { href: "/today", title: "Today", description: "Your current work status." },
  { href: "/history", title: "My History", description: "Your past work sessions." },
];

export default function HomePage() {
  const { scope } = useAtworkScope();
  const areas = hasPermission(scope, PERM.MANAGEMENT)
    ? [...AREAS, { href: "/management", title: "Management", description: "DijiAtWork management tools." }]
    : AREAS;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="DijiAtWork" description="Work check-in and attendance for Dijital Team employees." />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {areas.map((area) => (
          <Link key={area.href} href={area.href} className="block rounded-2xl focus-visible:outline-2 focus-visible:outline-dt-orange">
            <Card className="h-full p-5">
              <h2 className="text-base font-semibold text-dt-text-primary">{area.title}</h2>
              <p className="mt-1 text-sm text-dt-text-secondary">{area.description}</p>
              <p className="mt-3 text-xs font-medium text-dt-text-secondary">Coming soon</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
