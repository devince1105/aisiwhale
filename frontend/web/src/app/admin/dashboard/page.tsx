import { Suspense } from "react";

import { TokenGate } from "@/features/auth/TokenGate";
import { DashboardPage } from "@/features/dashboard/DashboardPage";

export const metadata = { title: "Dashboard · 艾矽鯨" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <DashboardPage />
      </Suspense>
    </TokenGate>
  );
}
