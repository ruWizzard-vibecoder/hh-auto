import { Shell } from '@/components/layout/shell';
import { DashboardView } from '@/features/dashboard/dashboard-view';

export default function HomePage() {
  return (
    <Shell>
      <DashboardView />
    </Shell>
  );
}
