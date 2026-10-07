import { Suspense } from "react";

import { AccessPage } from "@/features/access/AccessPage";
import { TokenGate } from "@/features/auth/TokenGate";

export const metadata = { title: "角色與權限 · Autora" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <AccessPage />
      </Suspense>
    </TokenGate>
  );
}
