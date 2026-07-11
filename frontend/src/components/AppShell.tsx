import type { ReactNode } from "react";
import { ROUTES, routeLabel, type AppRoute } from "../routing";

type AppShellProps = {
  route: AppRoute;
  attentionRoute?: AppRoute | null;
  routeBadges?: Partial<Record<AppRoute, number | string>>;
  onNavigate: (route: AppRoute) => void;
  onStartNewInspection: () => void;
  newInspectionDisabled: boolean;
  children: ReactNode;
};

function ShieldMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 48 56" aria-hidden="true">
      <path d="M24 3 43 10v15c0 13-8 23-19 28C13 48 5 38 5 25V10L24 3Z" />
      <path d="M15 25h18M17 22l7-6 7 6M18 25v10m12-10v10M14 36h20" />
    </svg>
  );
}

function RouteIcon({ route }: { route: AppRoute }) {
  const paths: Record<AppRoute, string> = {
    overview: "M4 5h7v7H4zM15 5h5v15h-5zM4 16h7v4H4z",
    "new-inspection": "M6 4h12v16H6zM9 8h6M9 12h6M9 16h4",
    "human-review": "M4 13l4 4L20 5M5 5h9M5 9h7M5 17h6",
    reports: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
  };
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[route]} />
    </svg>
  );
}

export function AppShell({
  route,
  attentionRoute = null,
  routeBadges = {},
  onNavigate,
  onStartNewInspection,
  newInspectionDisabled,
  children,
}: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-lockup">
          <ShieldMark />
          <div>
            <strong>SchoolReview AI</strong>
            <span>VLM automation with human review</span>
          </div>
        </div>

        <nav className="main-nav" aria-label="Main navigation">
          {ROUTES.map((item) => {
            const badge = routeBadges[item.id];
            const classes = [
              "nav-link",
              item.id === route ? "nav-link-active" : "",
              item.id === attentionRoute ? "nav-link-attention" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <button
                key={item.id}
                type="button"
                className={classes}
                onClick={() => (item.id === "new-inspection" ? onStartNewInspection() : onNavigate(item.id))}
                disabled={item.id === "new-inspection" && newInspectionDisabled}
              >
                <RouteIcon route={item.id} />
                <span>{item.label}</span>
                {badge ? <strong className="nav-badge">{badge}</strong> : null}
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="page-shell">
        <header className="topbar">
          <div>
            <h1>{routeLabel(route)}</h1>
            <p>Visual evidence review with model automation and human decisions where they matter.</p>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
