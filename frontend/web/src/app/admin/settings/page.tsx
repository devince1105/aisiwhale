import { Suspense } from "react";

import { TokenGate } from "@/features/auth/TokenGate";
import { SettingsPage } from "@/features/settings/SettingsPage";

export const metadata = { title: "系統設定 · Autora" };

export default function Page() {
  return (
    <TokenGate>
      <Suspense>
        <SettingsPage />
      </Suspense>
    </TokenGate>
  );
}
