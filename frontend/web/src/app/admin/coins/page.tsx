import { Suspense } from "react";

import { TokenGate } from "@/features/auth/TokenGate";
import { CoinsAdminPage } from "@/features/coins/CoinsAdminPage";

export const metadata = { title: "鯨幣 · 艾矽鯨" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <CoinsAdminPage />
      </Suspense>
    </TokenGate>
  );
}
