"use client";

import { useEffect, useRef } from "react";
import { Button } from "@dijione/design-system";
import { duration } from "@/lib/format";

type Props = { netSeconds: number; grossSeconds: number; onCancel: () => void; onConfirm: () => void };

export function CheckoutDialog({ netSeconds, grossSeconds, onCancel, onConfirm }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    cancel.current?.focus();
    return () => (opener.current as HTMLElement | null)?.focus?.();
  }, []);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") return onCancel();
    if (e.key !== "Tab") return;
    const items = panel.current?.querySelectorAll<HTMLElement>("button:not([disabled])");
    if (!items?.length) return;
    const [first, last] = [items[0], items[items.length - 1]];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onKeyDown={onKeyDown}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="checkout-title" className="w-full max-w-md rounded-2xl bg-dt-surface p-6 shadow-xl">
        <h2 id="checkout-title" className="text-lg font-semibold">End this session?</h2>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-dt-text-secondary">Net working time</dt><dd className="font-mono text-xl font-semibold tabular-nums">{duration(netSeconds)}</dd></div>
          <div><dt className="text-dt-text-secondary">Session elapsed</dt><dd className="font-mono text-xl font-semibold tabular-nums">{duration(grossSeconds)}</dd></div>
        </dl>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-dt-text-secondary">
          <li>Your session ends now and cannot be undone.</li>
          <li>If you still have work to do, you can check in again. That starts a new session, and both count toward today&apos;s total.</li>
          <li>Time between sessions is not counted. To add it or change this check-out, send a correction request for Management to review.</li>
        </ul>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button ref={cancel} variant="secondary" onClick={onCancel}>Keep Working</Button>
          <Button onClick={onConfirm}>Confirm Check Out</Button>
        </div>
      </div>
    </div>
  );
}
