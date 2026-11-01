import { useQuery } from "@tanstack/react-query";
import { endpointsApi, type DeliveryStats } from "@/api/client";
import { Spinner } from "@/components/Spinner";

function StatBox({ label, value, unit = "" }: { label: string; value: string | number | null; unit?: string }) {
  return (
    <div style={{
      background: "var(--bg)", border: "1px solid var(--border)",
      borderRadius: "var(--radius)", padding: "0.75rem 1rem", minWidth: 100,
    }}>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>
        {label}
      </div>
      <div style={{ fontSize: "1.1rem", fontWeight: 600 }}>
        {value == null ? <span style={{ color: "var(--text-muted)" }}>—</span> : `${value}${unit}`}
      </div>
    </div>
  );
}

export function StatsPanel({ endpointId }: { endpointId: string }) {
  const { data, isLoading } = useQuery<DeliveryStats>({
    queryKey: ["stats", endpointId],
    queryFn: () => endpointsApi.stats(endpointId),
  });

  if (isLoading) return <Spinner size={14} />;
  if (!data) return null;

  const successPct = data.total_attempts > 0
    ? `${(data.success_rate * 100).toFixed(1)}%`
    : "—";

  return (
    <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
      <StatBox label="Total (24h)" value={data.total_attempts} />
      <StatBox label="Success rate" value={successPct} />
      <StatBox label="p50" value={data.p50_ms} unit=" ms" />
      <StatBox label="p95" value={data.p95_ms} unit=" ms" />
      <StatBox label="p99" value={data.p99_ms} unit=" ms" />
    </div>
  );
}
