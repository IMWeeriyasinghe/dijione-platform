"use client";

function FlowBox({ x, y, w, h, label, sub, fill }: { x: number; y: number; w: number; h: number; label: string; sub?: string; fill: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={fill} stroke="var(--dt-border)" />
      <text x={x + w / 2} y={y + h / 2 + (sub ? -4 : 5)} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--dt-text-primary)">
        {label}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 12} textAnchor="middle" fontSize={10.5} fill="var(--dt-text-secondary)">
          {sub}
        </text>
      )}
    </g>
  );
}

function VArrow({ x, y1, y2 }: { x: number; y1: number; y2: number }) {
  return (
    <g stroke="var(--dt-burnt-orange)" strokeWidth={1.6} fill="none">
      <line x1={x} y1={y1} x2={x} y2={y2 - 6} />
      <polygon points={`${x - 4},${y2 - 6} ${x + 4},${y2 - 6} ${x},${y2}`} fill="var(--dt-burnt-orange)" stroke="none" />
    </g>
  );
}

/** The primary top-to-bottom authorization chain: Entra → User → … → Business Application. */
function MainChain() {
  // Canvas: 560 wide. Main chain is centered on cx=280, with a symmetric
  // 40px margin on each side of the two branch boxes (70px left, 70px right)
  // so neither branch can be clipped by the viewBox.
  const canvasWidth = 560;
  const cx = 280;
  const w = 260;
  const h = 42;
  const gap = 58;
  let y = 10;

  const rows: { label: string; sub?: string; fill: string }[] = [
    { label: "Microsoft Entra ID", sub: "Authentication / SSO", fill: "var(--dt-cream)" },
    { label: "DijiOne User", fill: "var(--dt-surface-warm)" },
    { label: "Application Access", fill: "var(--dt-surface-warm)" },
  ];

  const boxes = rows.map((r) => {
    const box = { ...r, x: cx - w / 2, y, w, h };
    y += gap;
    return box;
  });

  // Branch: Direct Assignment | Group Membership — two boxes of equal width,
  // centered as a pair under cx with a fixed gap between them.
  const branchY = y;
  const branchW = 170;
  const branchGap = 40;
  const leftX = cx - branchGap / 2 - branchW;
  const rightX = cx + branchGap / 2;
  const leftCenter = leftX + branchW / 2;
  const rightCenter = rightX + branchW / 2;
  y += gap;

  const afterBranchRows: { label: string; sub?: string; fill: string }[] = [
    { label: "Access Group", fill: "var(--dt-surface-warm)" },
    { label: "Application Role", fill: "var(--dt-surface-warm)" },
    { label: "Permissions", fill: "var(--dt-surface-warm)" },
    { label: "Client / Portfolio Scope", fill: "var(--dt-cream)" },
    { label: "Effective Access", fill: "var(--dt-amber)" },
    { label: "Business Application", sub: "DijiTalentFlow · DijiBirthday · DijiSpark", fill: "var(--dt-cream)" },
  ];
  const bottomBoxes = afterBranchRows.map((r) => {
    const box = { ...r, x: cx - w / 2, y, w, h };
    y += gap;
    return box;
  });

  const totalHeight = y - gap + h + 10;

  return (
    <svg
      viewBox={`0 0 ${canvasWidth} ${totalHeight}`}
      className="mx-auto w-full max-w-lg"
      role="img"
      aria-label="DijiOne access and authorization model diagram"
    >
      {boxes.map((b, i) => (
        <g key={b.label}>
          <FlowBox {...b} />
          {i > 0 && <VArrow x={cx} y1={boxes[i - 1].y + h} y2={b.y} />}
        </g>
      ))}
      <VArrow x={cx} y1={boxes[boxes.length - 1].y + h} y2={branchY} />

      {/* Branch boxes — fully inside the canvas, symmetric around cx */}
      <FlowBox x={leftX} y={branchY} w={branchW} h={h} label="Direct Assignment" fill="var(--dt-surface-warm)" />
      <FlowBox x={rightX} y={branchY} w={branchW} h={h} label="Group Membership" fill="var(--dt-surface-warm)" />
      <g stroke="var(--dt-burnt-orange)" strokeWidth={1.6} fill="none">
        <line x1={cx} y1={boxes[boxes.length - 1].y + h + 6} x2={leftCenter} y2={branchY - 6} />
        <line x1={cx} y1={boxes[boxes.length - 1].y + h + 6} x2={rightCenter} y2={branchY - 6} />
      </g>

      {/* Both branches rejoin the main chain below: Group Membership continues
          straight down into Access Group; Direct Assignment rejoins the chain
          at Application Role's row (it does not pass through Access Group). */}
      <VArrow x={rightCenter} y1={branchY + h} y2={bottomBoxes[0].y} />
      <g stroke="var(--dt-burnt-orange)" strokeWidth={1.6} strokeDasharray="3,3" fill="none">
        <line x1={leftCenter} y1={branchY + h} x2={leftCenter} y2={bottomBoxes[1].y + h / 2} />
        <line x1={leftCenter} y1={bottomBoxes[1].y + h / 2} x2={cx - w / 2} y2={bottomBoxes[1].y + h / 2} />
      </g>

      {bottomBoxes.map((b, i) => (
        <g key={b.label}>
          <FlowBox {...b} />
          {i > 0 && <VArrow x={cx} y1={bottomBoxes[i - 1].y + h} y2={b.y} />}
        </g>
      ))}
    </svg>
  );
}

function PerspectiveCard({ title, steps }: { title: string; steps: string[] }) {
  return (
    <div className="rounded-xl border border-dt-border bg-dt-surface-warm p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-dt-burnt-orange">{title}</p>
      <div className="flex flex-col gap-1">
        {steps.map((s, i) => (
          <div key={s} className="flex items-center gap-2 text-sm text-dt-text-primary">
            {i > 0 && <span className="text-dt-text-secondary">→</span>}
            <span className={i === 0 ? "font-semibold" : ""}>{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AccessModelDiagram() {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-dt-border bg-dt-surface p-4 sm:p-6">
        <MainChain />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <PerspectiveCard title="User-centric" steps={["User", "Applications", "Role", "Client Scope"]} />
        <PerspectiveCard title="Application-centric" steps={["Application", "Users / Groups", "Role", "Client Scope"]} />
        <PerspectiveCard title="Group-centric" steps={["User", "Group", "Application", "Role", "Permissions", "Client Scope"]} />
      </div>
    </div>
  );
}
