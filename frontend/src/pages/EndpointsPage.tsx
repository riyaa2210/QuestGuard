import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2, Eye, ToggleLeft, ToggleRight, Zap, ShieldAlert } from "lucide-react";
import { endpointsApi, type Endpoint } from "@/api/client";
import { Spinner } from "@/components/Spinner";
import { StatsPanel } from "@/components/StatsPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDistanceToNow } from "date-fns";

const CIRCUIT_LABELS: Record<string, string> = {
  closed: "Circuit closed",
  open: "Circuit OPEN",
  half_open: "Circuit probing",
};

function CircuitBadge({ state }: { state: string }) {
  const cls = state === "closed" ? "badge--green" : state === "open" ? "badge--red" : "badge--orange";
  return <span className={`badge ${cls}`}>{CIRCUIT_LABELS[state] ?? state}</span>;
}

function AddEndpointModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [eventTypes, setEventTypes] = useState("");
  const [rateLimit, setRateLimit] = useState("0");
  const [error, setError] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      endpointsApi.create({
        url,
        description: description || undefined,
        event_types: eventTypes ? eventTypes.split(",").map((s) => s.trim()) : undefined,
        rate_limit_per_minute: parseInt(rateLimit, 10) || 0,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["endpoints"] }); onClose(); },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === "string" ? msg : "Failed to create endpoint");
    },
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal__title">Register Endpoint</h2>
        {error && <div className="error-box" style={{ marginBottom: "1rem" }}>{error}</div>}
        <div className="form-group">
          <label>Destination URL *</label>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hooks" style={{ width: "100%" }} />
        </div>
        <div className="form-group">
          <label>Description</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div className="form-group">
          <label>Event Types (comma-separated, blank = all)</label>
          <input value={eventTypes} onChange={(e) => setEventTypes(e.target.value)} placeholder="order.created, payment.failed" style={{ width: "100%" }} />
        </div>
        <div className="form-group">
          <label>Rate Limit (events/min, 0 = unlimited)</label>
          <input type="number" min="0" value={rateLimit} onChange={(e) => setRateLimit(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div className="modal__actions">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!url || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? <Spinner size={14} /> : <Plus size={14} />} Register
          </button>
        </div>
        <style>{`
          .modal-backdrop { position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:100; }
          .modal { background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.75rem;width:500px;max-width:95vw; }
          .modal__title { font-size:1.1rem;font-weight:600;margin-bottom:1.25rem; }
          .modal__actions { display:flex;gap:0.75rem;justify-content:flex-end;margin-top:1.5rem; }
          .form-group { margin-bottom:1rem; }
          .form-group label { display:block;margin-bottom:0.35rem;font-size:0.8rem;color:var(--text-muted); }
        `}</style>
      </div>
    </div>
  );
}

function FanoutModal({ onClose }: { onClose: () => void }) {
  const [eventType, setEventType] = useState("");
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      let p: Record<string, unknown>;
      try { p = JSON.parse(payload); } catch { setError("Invalid JSON payload"); throw new Error("bad json"); }
      return endpointsApi.stats; // placeholder replaced below
    },
  });

  const submit = async () => {
    setError("");
    try {
      const p = JSON.parse(payload);
      const { eventsApi } = await import("@/api/client");
      const res = await eventsApi.fanout({ event_type: eventType, payload: p });
      setResult(JSON.stringify(res, null, 2));
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === "string" ? msg : String(e));
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 560 }}>
        <h2 className="modal__title"><Zap size={16} style={{ marginRight: 6 }} />Fan-out Event</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "1rem" }}>
          Broadcasts to <strong>all active endpoints</strong> matching the event type.
        </p>
        {error && <div className="error-box" style={{ marginBottom: "1rem" }}>{error}</div>}
        <div className="form-group">
          <label>Event Type *</label>
          <input value={eventType} onChange={(e) => setEventType(e.target.value)} placeholder="order.created" style={{ width: "100%" }} />
        </div>
        <div className="form-group">
          <label>Payload (JSON)</label>
          <textarea value={payload} onChange={(e) => setPayload(e.target.value)}
            style={{ width: "100%", height: 100, fontFamily: "monospace", fontSize: "0.85rem", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: "var(--radius)", padding: "0.5rem", resize: "vertical" }} />
        </div>
        {result && (
          <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "0.75rem", fontSize: "0.78rem", overflow: "auto", maxHeight: 200, marginBottom: "1rem" }}>{result}</pre>
        )}
        <div className="modal__actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
          <button className="btn btn-primary" disabled={!eventType} onClick={submit}>
            <Zap size={13} /> Broadcast
          </button>
        </div>
      </div>
    </div>
  );
}

export function EndpointsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [showFanout, setShowFanout] = useState(false);
  const [expandedStats, setExpandedStats] = useState<string | null>(null);

  const { data: endpoints, isLoading, error } = useQuery({
    queryKey: ["endpoints"],
    queryFn: endpointsApi.list,
  });

  const toggleMut = useMutation({
    mutationFn: (ep: Endpoint) => endpointsApi.update(ep.id, { is_active: !ep.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["endpoints"] }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => endpointsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["endpoints"] }),
  });

  if (isLoading) return <div style={{ padding: "2rem" }}><Spinner /></div>;
  if (error) return <div className="error-box">Failed to load endpoints</div>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Endpoints</h1>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="btn btn-ghost" onClick={() => setShowFanout(true)}>
            <Zap size={13} /> Fan-out
          </button>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            <Plus size={14} /> Register
          </button>
        </div>
      </div>

      {showAdd && <AddEndpointModal onClose={() => setShowAdd(false)} />}
      {showFanout && <FanoutModal onClose={() => setShowFanout(false)} />}

      <div className="card table-wrap">
        {!endpoints?.length ? (
          <div className="empty">No endpoints registered yet. Click "Register" to add one.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>URL</th>
                <th>Status</th>
                <th>Circuit</th>
                <th>Rate Limit</th>
                <th>Failures</th>
                <th>Registered</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((ep) => (
                <>
                  <tr key={ep.id}>
                    <td>
                      <div>
                        <code style={{ fontSize: "0.8rem" }}>{ep.url.replace(/^https?:\/\//, "")}</code>
                        {ep.description && <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>{ep.description}</div>}
                      </div>
                    </td>
                    <td>
                      <span className={ep.is_active ? "badge badge--green" : "badge badge--grey"}>
                        {ep.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td><CircuitBadge state={ep.circuit_state} /></td>
                    <td style={{ color: "var(--text-muted)" }}>
                      {ep.rate_limit_per_minute > 0 ? `${ep.rate_limit_per_minute}/min` : "∞"}
                    </td>
                    <td>
                      {ep.consecutive_failures > 0 ? (
                        <span style={{ color: "var(--error)", fontWeight: 600 }}>{ep.consecutive_failures}</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>0</span>
                      )}
                      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}> / {ep.circuit_threshold}</span>
                    </td>
                    <td style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      {formatDistanceToNow(new Date(ep.created_at), { addSuffix: true })}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button className="btn btn-ghost" title="Stats" onClick={() => setExpandedStats(expandedStats === ep.id ? null : ep.id)}>
                          <ShieldAlert size={13} />
                        </button>
                        <button className="btn btn-ghost" title="View events" onClick={() => navigate(`/endpoints/${ep.id}`)}>
                          <Eye size={13} />
                        </button>
                        <button className="btn btn-ghost" title={ep.is_active ? "Disable" : "Enable"} onClick={() => toggleMut.mutate(ep)}>
                          {ep.is_active ? <ToggleRight size={13} color="var(--success)" /> : <ToggleLeft size={13} />}
                        </button>
                        <button className="btn btn-danger" title="Delete"
                          onClick={() => { if (confirm("Delete this endpoint and all its events?")) deleteMut.mutate(ep.id); }}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedStats === ep.id && (
                    <tr key={`${ep.id}-stats`}>
                      <td colSpan={7} style={{ background: "rgba(99,102,241,0.04)", padding: "0.75rem 1rem" }}>
                        <StatsPanel endpointId={ep.id} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
