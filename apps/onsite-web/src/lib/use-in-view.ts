"use client";

import { useEffect, useRef, useState } from "react";

/** True once the element has come within `rootMargin` of the viewport (and
 *  stays true). Defers per-row work such as photo requests until the row is
 *  actually about to be seen. Without IntersectionObserver it reports true. */
export function useInView<T extends Element>(rootMargin = "200px"): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (inView || !ref.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setInView(true);
        observer.disconnect();
      }
    }, { rootMargin });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [inView, rootMargin]);
  return [ref, inView];
}
