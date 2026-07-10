import { readableStatus, statusTone } from "../constants";

type StatusBadgeProps = {
  value: string | null | undefined;
};

export function StatusBadge({ value }: StatusBadgeProps) {
  return <span className={`status-badge status-${statusTone(value)}`}>{readableStatus(value)}</span>;
}
