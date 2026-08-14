"use client";

import { use } from "react";
import { SupplierDetail } from "@/components/birthday/SupplierDetail";

export default function SupplierDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <SupplierDetail supplierId={Number(id)} />;
}
