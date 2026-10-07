import { Suspense } from "react";

import { AuditPage } from "@/features/audit/AuditPage";
import { TokenGate } from "@/features/auth/TokenGate";

export const metadata = { title: "操作紀錄 · Autora" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <AuditPage />
      </Suspense>
    </TokenGate>
  );
}
