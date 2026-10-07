import { Suspense } from "react";

import { ApprovalReportPage } from "@/features/approvals/ApprovalReportPage";
import { TokenGate } from "@/features/auth/TokenGate";

export const metadata = { title: "審批報表 · 艾矽鯨" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <ApprovalReportPage />
      </Suspense>
    </TokenGate>
  );
}
