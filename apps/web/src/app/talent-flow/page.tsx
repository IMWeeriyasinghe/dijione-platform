"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function TalentFlowIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/talent-flow/dashboard");
  }, [router]);
  return null;
}
