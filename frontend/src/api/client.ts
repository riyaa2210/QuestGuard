import axios from "axios";

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export interface Endpoint {
  id: string;
  url: string;
  description: string | null;
  is_active: boolean;
  event_types: string[] | null;
  payload_schema: Record<string, unknown> | null;
  rate_limit_per_minute: number;
  circuit_state: "closed" | "open" | "half_open";
  consecutive_failures: number;
  circuit_threshold: number;
  circuit_cooldown_s: number;
  created_at: string;
  updated_at: string;
}

export interface DeliveryStats {
  endpoint_id: string;
  window_hours: number;
  total_attempts: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export interface AlertRule {
  id: string;
  endpoint_id: string;
  name: string;
  window_minutes: number;
  failure_rate_threshold: number;
  min_sample_size: number;
  is_active: boolean;
  last_fired_at: string | null;
  notification_url: string | null;
  created_at: string;
}

export interface AlertRuleCreate {
  name: string;
  window_minutes: number;
  failure_rate_threshold: number;
  min_sample_size: number;
  notification_url?: string;
}

export interface FanoutResult {
  event_type: string;
  matched_endpoints: number;
  results: Array<{ endpoint_id: string; event_id?: string; status: string; reason?: string }>;
}

export interface DeliveryAttempt {
  id: string;
  attempt_number: number;
  status: "success" | "failure";
  http_status_code: number | null;
  response_body: string | null;
  duration_ms: number | null;
  error_detail: string | null;
  ai_explanation: string | null;
  created_at: string;
}

export interface WebhookEvent {
  id: string;
  endpoint_id: string;
  event_type: string;
  idempotency_key: string | null;
  payload: Record<string, unknown>;
  status: "pending" | "queued" | "delivered" | "failed" | "dead_lettered";
  sqs_message_id: string | null;
  attempt_count: number;
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
  attempts: DeliveryAttempt[];
}

export interface EventListResponse {
  items: WebhookEvent[];
  total: number;
  page: number;
  page_size: number;
}

export const endpointsApi = {
  list: () => api.get<Endpoint[]>("/endpoints").then((r) => r.data),
  get: (id: string) => api.get<Endpoint>(`/endpoints/${id}`).then((r) => r.data),
  create: (data: {
    url: string;
    description?: string;
    event_types?: string[];
    rate_limit_per_minute?: number;
    circuit_threshold?: number;
    circuit_cooldown_s?: number;
  }) => api.post<Endpoint>("/endpoints", data).then((r) => r.data),
  update: (id: string, data: Partial<Endpoint>) =>
    api.patch<Endpoint>(`/endpoints/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/endpoints/${id}`),
  stats: (id: string, windowHours = 24) =>
    api.get<DeliveryStats>(`/endpoints/${id}/stats`, { params: { window_hours: windowHours } }).then((r) => r.data),
  createAlert: (id: string, data: AlertRuleCreate) =>
    api.post<AlertRule>(`/endpoints/${id}/alerts`, data).then((r) => r.data),
  listAlerts: (id: string) =>
    api.get<AlertRule[]>(`/endpoints/${id}/alerts`).then((r) => r.data),
  deleteAlert: (ruleId: string) => api.delete(`/alerts/${ruleId}`),
};

// ── Events API ─────────────────────────────────────────────────────────────────
export const eventsApi = {
  list: (endpointId: string, params?: { status?: string; page?: number; page_size?: number }) =>
    api.get<EventListResponse>(`/events/${endpointId}`, { params }).then((r) => r.data),
  get: (eventId: string) =>
    api.get<WebhookEvent>(`/events/detail/${eventId}`).then((r) => r.data),
  replay: (eventId: string) =>
    api.post<WebhookEvent>(`/events/detail/${eventId}/replay`).then((r) => r.data),
  attempts: (eventId: string) =>
    api.get<DeliveryAttempt[]>(`/events/detail/${eventId}/attempts`).then((r) => r.data),
  fanout: (data: { event_type: string; payload: Record<string, unknown>; idempotency_key?: string }) =>
    api.post<FanoutResult>("/fanout", data).then((r) => r.data),
};
