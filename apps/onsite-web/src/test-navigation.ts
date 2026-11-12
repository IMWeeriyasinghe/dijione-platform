// In-memory stand-in for next/navigation used by every test (vitest.setup.ts):
// one current URL that router.replace/push update and hooks re-render on.
import { useSyncExternalStore } from "react";

let current = new URL("http://test/");
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function setTestUrl(pathAndQuery: string) {
  current = new URL(pathAndQuery, "http://test");
  emit();
}
export function getTestUrl(): URL {
  return current;
}

const subscribe = (l: () => void) => { listeners.add(l); return () => listeners.delete(l); };
const snapshot = () => current.href;

export const navigationMock = {
  useSearchParams: () => { useSyncExternalStore(subscribe, snapshot, snapshot); return new URLSearchParams(current.search); },
  usePathname: () => { useSyncExternalStore(subscribe, snapshot, snapshot); return current.pathname; },
  useRouter: () => ({
    replace: (href: string) => setTestUrl(href),
    push: (href: string) => setTestUrl(href),
    back: () => {}, forward: () => {}, refresh: () => {}, prefetch: () => {},
  }),
  redirect: () => {},
  notFound: () => {},
};
