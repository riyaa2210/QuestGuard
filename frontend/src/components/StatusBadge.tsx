import clsx from "clsx";

type Status = "pending" | "queued" | "delivered" | "failed" | "dead_lettered" | "success" | "failure";

const colours: Record<Status, string> = {
  pending:       "badge--grey",
  queued:        "badge--blue",
  delivered:     "badge--green",
  success:       "badge--green",
  failed:        "badge--red",
  failure:       "badge--red",
  dead_lettered: "badge--orange",
};

const labels: Record<Status, string> = {
  pending:       "Pending",
  queued:        "Queued",
  delivered:     "Delivered",
  success:       "Success",
  failed:        "Failed",
  failure:       "Failed",
  dead_lettered: "Dead-lettered",
};

export function StatusBadge({ status }: { status: string }) {
  const s = status as Status;
  return (
    <span className={clsx("badge", colours[s] ?? "badge--grey")}>
      {labels[s] ?? status}
    </span>
  );
}
