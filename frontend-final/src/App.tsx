import { useEffect, useState } from "react";
import { AppShell } from "./components/AppShell";
import { NoticeStack } from "./components/NoticeStack";
import { useInspectionRun } from "./hooks/useInspectionRun";
import { routeFromHash, type AppRoute } from "./routing";
import { HumanReviewPage } from "./views/HumanReviewPage";
import { NewInspectionPage } from "./views/NewInspectionPage";
import { OverviewPage } from "./views/OverviewPage";
import { ReportsPage } from "./views/ReportsPage";

function currentRoute(): AppRoute {
  return routeFromHash(window.location.hash);
}

export default function App() {
  const controller = useInspectionRun();
  const [route, setRoute] = useState<AppRoute>(currentRoute);

  useEffect(() => {
    const handleHashChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", handleHashChange);
    if (!window.location.hash) {
      window.location.hash = "/overview";
    }
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigate = (nextRoute: AppRoute) => {
    window.location.hash = `/${nextRoute}`;
    setRoute(nextRoute);
  };

  return (
    <AppShell route={route} onNavigate={navigate}>
      <NoticeStack message={controller.message} error={controller.error} />
      {route === "overview" && <OverviewPage controller={controller} onNavigate={navigate} />}
      {route === "new-inspection" && <NewInspectionPage controller={controller} />}
      {route === "human-review" && <HumanReviewPage controller={controller} />}
      {route === "reports" && <ReportsPage controller={controller} />}
    </AppShell>
  );
}
