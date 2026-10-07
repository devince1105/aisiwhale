import { Suspense } from "react";

import { AgentsPage } from "@/features/agents/AgentsPage";
import { TokenGate } from "@/features/auth/TokenGate";

export const metadata = { title: "代理 · 艾矽鯨" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <AgentsPage />
      </Suspense>
    </TokenGate>
  );
}
