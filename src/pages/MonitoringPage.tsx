import MonitoringDashboard from "../features/monitoring/MonitoringDashboard";

interface Props {
  token: string;
}

export default function MonitoringPage({ token }: Props) {
  return <MonitoringDashboard token={token} />;
}
