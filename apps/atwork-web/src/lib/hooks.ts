"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { attendance, errorMessage, isUncertain, newRequestId, type ActionResult, type WorkMode } from "./api";
import type { TimeFormat } from "./format";

const POLL_MS = 60_000;

const live = { refetchOnWindowFocus: "always", refetchOnReconnect: "always", refetchOnMount: "always", refetchInterval: POLL_MS, refetchIntervalInBackground: false, retry: 1 } as const;

export function usePolicy() {
  return useQuery({ queryKey: ["atwork", "policy"], queryFn: attendance.policy, staleTime: 5 * 60_000 });
}

export function useDisplay(): { zone: string; format: TimeFormat } {
  const { data } = usePolicy();
  return { zone: data?.business_time_zone ?? "Asia/Colombo", format: data?.time_format ?? "24h" };
}

export function useLiveStatus() {
  return useQuery({ queryKey: ["atwork", "status"], queryFn: attendance.status, ...live });
}

export function useLiveToday() {
  return useQuery({ queryKey: ["atwork", "today"], queryFn: attendance.today, ...live });
}

/** A once-a-second clock for presentation only. It sends no requests. */
export function useTick(enabled = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [enabled]);
  return now;
}

/** Device-clock offset, captured when a server response arrives. */
export function useServerOffset(serverTime: string | undefined, updatedAt: number): number {
  return serverTime && updatedAt ? new Date(serverTime).getTime() - updatedAt : 0;
}

function subscribeOnline(listener: () => void) {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

export type ActionKind = "CHECK_IN" | "BREAK_START" | "BREAK_END" | "CHECK_OUT";
type Run = { kind: ActionKind; workMode?: WorkMode };

const SUCCESS: Record<ActionKind, string> = {
  CHECK_IN: "You are checked in.", BREAK_START: "Your break has started.", BREAK_END: "Your break has ended.", CHECK_OUT: "You are checked out.",
};

function call({ kind, workMode }: Run, id: string): Promise<ActionResult> {
  if (kind === "CHECK_IN") return attendance.checkIn(workMode as WorkMode, id);
  if (kind === "BREAK_START") return attendance.startBreak(id);
  if (kind === "BREAK_END") return attendance.endBreak(id);
  return attendance.checkOut(id);
}

/** One ID per user action. It is kept after an uncertain failure, so a retry
 *  of that action replays on the server instead of recording it twice. */
export function useAttendanceAction(currentState?: string) {
  const client = useQueryClient();
  const uncertain = useRef<(Run & { id: string; state?: string }) | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [retryable, setRetryable] = useState<(Run & { state?: string }) | null>(null);

  const mutation = useMutation({
    mutationFn: async (run: Run) => {
      const same = uncertain.current && uncertain.current.kind === run.kind && uncertain.current.workMode === run.workMode && uncertain.current.state === currentState;
      const id = same ? uncertain.current!.id : newRequestId();
      try {
        const result = await call(run, id);
        uncertain.current = null;
        return { run, result };
      } catch (error) {
        uncertain.current = isUncertain(error) ? { ...run, id, state: currentState } : null;
        throw error;
      }
    },
    onSuccess: ({ run }) => {
      setRetryable(null);
      setNotice({ tone: "success", text: SUCCESS[run.kind] });
    },
    onError: (error, run) => {
      const unsure = isUncertain(error);
      setRetryable(unsure ? { ...run, state: currentState } : null);
      setNotice({
        tone: "error",
        text: unsure ? "We could not confirm that action. Retry safely: it will not be recorded twice." : errorMessage(error),
      });
    },
    // Not returned: the action must unlock without waiting for the refresh.
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["atwork"] });
    },
  });

  const run = (next: Run) => {
    if (mutation.isPending) return;
    setNotice(null);
    mutation.mutate(next);
  };
  // A changed status means the uncertain action resolved; its retry no longer applies.
  const stillUncertain = retryable !== null && retryable.state === currentState;
  return {
    run,
    pending: mutation.isPending ? mutation.variables?.kind ?? null : null,
    notice: retryable !== null && !stillUncertain ? null : notice,
    retryable: stillUncertain ? retryable : null,
    retry: () => stillUncertain && run(retryable),
  };
}
