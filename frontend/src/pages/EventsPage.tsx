import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { eventsApi, endpointsApi, type WebhookEvent } from "@/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { Spinner } from "@/components/Spinner";
import { formatDistanceToNow, format } from "date-fns";

const PAGE_SIZE = 20;

export function EventsPage() {
  const { endpointId } = useParams<{ endpointId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<WebhookEvent | null>(null);

  const { data: endpoint } = useQuery({
    queryKey: ["endpoint", endpointId],
    queryFn: () => endpointsApi.get(endpointId!),
    enabled: !!endpointId,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["events", endpointId, page, statusFilter],
    queryFn: () =>
      eventsApi.list(endpointId!, {
        page,
        page_size: PAGE_SIZE,
        status: statusFilter || undefined,
      }),
    enabled: !!endpointId,
  });

  const replayMut = useMutation({
    mutationFn: (eventId: string) => eventsApi.replay(eventId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events", endpointId] });
      setSelectedEvent(null);
    },
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button className="btn btn-ghost" onClick={() => navigate("/")} style={{ padding: "0.4rem" }}>
            <ArrowLeft size={14} />
          </button>
          <h1 className="page-title">
            {endpoint ? (
              <span>
                <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>Events for </span>
                <code style={{ fontSize: "0.9em" }}>{endpoint.url.replace(/^https?:\/\//, "")}</code>
              </span>
            ) : (
              "Events"
            )}
          </h1>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="queued">Queued</option>
            <option value="delivered">Delivered</option>
            <option value="failed">Failed</option>
            <option value="dead_lettered">Dead-lettered</option>
          </select>
          <button className="btn btn-ghost" onClick={() => qc.invalidateQueries({ queryKey: ["events", endpointId] })}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {isLoading && <Spinner />}
      {error && <div className="error-box">Failed to load events</div>}

      {data && (
        <>
          <div className="card table-wrap" style={{ marginBottom: "1rem" }}>
            {!data.items.length ? (
              <div className="empty">No events found.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Idempotency Key</th>
                    <th>Submitted</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((ev) => (
                    <tr key={ev.id} style={{ cursor: "pointer" }} onClick={() => setSelectedEvent(ev)}>
                      <td><code>{ev.event_type}</code></td>
                      <td><StatusBadge status={ev.status} /></td>
                      <td>{ev.attempt_count}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                        {ev.idempotency_key ?? "—"}
                      </td>
                      <td style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                        {formatDistanceToNow(new Date(ev.created_at), { addSuffix: true })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "center" }}>
              <button className="btn btn-ghost" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={13} />
              </button>
              <span style={{ alignSelf: "center", color: "var(--text-muted)" }}>
                {page} / {totalPages}
              </span>
              <button className="btn btn-ghost" disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight size={13} />
              </button>
            </div>
          )}
        </>
      )}

      {/* Event detail drawer */}
      {selectedEvent && (
        <EventDrawer
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onReplay={() => replayMut.mutate(selectedEvent.id)}
          replaying={replayMut.isPending}
        />
      )}
    </div>
  );
}

function EventDrawer({
  event,
  onClose,
  onReplay,
  replaying,
}: {
  event: WebhookEvent;
  onClose: () => void;
  onReplay: () => void;
  replaying: boolean;
}) {
  const canReplay = event.status === "failed" || event.status === "dead_lettered";

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer__header">
          <div>
            <code style={{ fontSize: "0.95rem" }}>{event.event_type}</code>
            <div style={{ marginTop: "0.35rem" }}><StatusBadge status={event.status} /></div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {canReplay && (
              <button className="btn btn-primary" disabled={replaying} onClick={onReplay}>
                {replaying ? <Spinner size={13} /> : <RefreshCw size={13} />} Replay
              </button>
            )}
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="drawer__body">
          <section>
            <h3 className="section-label">Details</h3>
            <dl className="detail-grid">
              <dt>Event ID</dt><dd><code>{event.id}</code></dd>
              <dt>Submitted</dt><dd>{format(new Date(event.created_at), "PPpp")}</dd>
              <dt>Attempts</dt><dd>{event.attempt_count}</dd>
              {event.idempotency_key && <><dt>Idempotency Key</dt><dd><code>{event.idempotency_key}</code></dd></>}
              {event.sqs_message_id && <><dt>SQS Message ID</dt><dd><code style={{ fontSize: "0.75rem" }}>{event.sqs_message_id}</code></dd></>}
              {event.next_retry_at && <><dt>Next Retry</dt><dd>{format(new Date(event.next_retry_at), "PPpp")}</dd></>}
            </dl>
          </section>

          <section>
            <h3 className="section-label">Payload</h3>
            <pre className="code-block">{JSON.stringify(event.payload, null, 2)}</pre>
          </section>

          {event.attempts.length > 0 && (
            <section>
              <h3 className="section-label">Delivery Attempts</h3>
              {event.attempts.map((a) => (
                <div key={a.id} className="attempt-card">
                  <div className="attempt-card__header">
                    <span>Attempt #{a.attempt_number}</span>
                    <StatusBadge status={a.status} />
                    {a.http_status_code && (
                      <span className="badge badge--grey">HTTP {a.http_status_code}</span>
                    )}
                    {a.duration_ms && (
                      <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{a.duration_ms}ms</span>
                    )}
                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginLeft: "auto" }}>
                      {format(new Date(a.created_at), "PPpp")}
                    </span>
                  </div>
                  {a.error_detail && (
                    <div className="attempt-card__error">
                      <strong>Error:</strong> {a.error_detail}
                    </div>
                  )}
                  {a.ai_explanation && (
                    <div className="attempt-card__ai">
                      <span className="ai-label">✦ AI Explanation</span>
                      {a.ai_explanation}
                    </div>
                  )}
                  {a.response_body && (
                    <details style={{ marginTop: "0.5rem" }}>
                      <summary style={{ cursor: "pointer", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                        Response body
                      </summary>
                      <pre className="code-block" style={{ marginTop: "0.5rem" }}>{a.response_body}</pre>
                    </details>
                  )}
                </div>
              ))}
            </section>
          )}
        </div>

        <style>{`
          .drawer-backdrop { position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:50;display:flex;justify-content:flex-end; }
          .drawer { width:560px;max-width:95vw;background:var(--surface);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden; }
          .drawer__header { display:flex;align-items:flex-start;justify-content:space-between;padding:1.25rem 1.5rem;border-bottom:1px solid var(--border); }
          .drawer__body { flex:1;overflow-y:auto;padding:1.5rem;display:flex;flex-direction:column;gap:1.5rem; }
          .section-label { font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:0.75rem; }
          .detail-grid { display:grid;grid-template-columns:120px 1fr;gap:0.35rem 0.75rem;font-size:0.85rem; }
          .detail-grid dt { color:var(--text-muted); }
          .code-block { background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:0.75rem;font-size:0.78rem;overflow-x:auto;white-space:pre;font-family:'JetBrains Mono','Fira Code',monospace; }
          .attempt-card { background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:0.85rem;margin-bottom:0.75rem; }
          .attempt-card__header { display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.5rem; }
          .attempt-card__error { background:rgba(239,68,68,0.08);border-left:3px solid #ef4444;padding:0.5rem 0.75rem;border-radius:0 4px 4px 0;font-size:0.83rem;color:#fca5a5;margin-top:0.5rem; }
          .attempt-card__ai { background:rgba(99,102,241,0.08);border-left:3px solid var(--accent);padding:0.5rem 0.75rem;border-radius:0 4px 4px 0;font-size:0.83rem;color:#a5b4fc;margin-top:0.5rem; }
          .ai-label { display:block;font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--accent);margin-bottom:0.35rem; }
        `}</style>
      </div>
    </div>
  );
}
