import { Suspense } from "react";

import { TokenGate } from "@/features/auth/TokenGate";
import { CompsPage } from "@/features/memberships/CompsPage";

export const metadata = { title: "VIP 授予 · 艾矽鯨" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <CompsPage />
      </Suspense>
    </TokenGate>
  );
}
