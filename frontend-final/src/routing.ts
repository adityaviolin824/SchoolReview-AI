export type AppRoute = "overview" | "new-inspection" | "human-review" | "reports";

export const ROUTES: { id: AppRoute; label: string; description: string }[] = [
  { id: "overview", label: "Overview", description: "Run status and next action" },
  { id: "new-inspection", label: "New Inspection", description: "Create, upload, and start" },
  { id: "human-review", label: "Human Review", description: "Resolve flagged evidence" },
  { id: "reports", label: "Reports", description: "Finalize and download" },
];

export function routeFromHash(hash: string): AppRoute {
  const normalized = hash.replace(/^#\/?/, "");
  return ROUTES.some((route) => route.id === normalized) ? (normalized as AppRoute) : "overview";
}

export function routeHref(route: AppRoute): string {
  return `#/${route}`;
}

export function routeLabel(route: AppRoute): string {
  return ROUTES.find((item) => item.id === route)?.label ?? "Overview";
}
