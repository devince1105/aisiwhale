import { TokenGate } from "@/features/auth/TokenGate";
import { TracePage } from "@/features/trace-viewer/TracePage";

export const metadata = { title: "Trace · 艾矽鯨" };

export default async function Page({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <TokenGate>
      <TracePage runId={runId} />
    </TokenGate>
  );
}
