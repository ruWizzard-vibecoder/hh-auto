import { Suspense } from 'react';
import { Shell } from '@/components/layout/shell';
import { ApplicationsView } from '@/features/applications/applications-view';

export default function ApplicationsPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">···  загрузка  ···</p>}>
        <ApplicationsView />
      </Suspense>
    </Shell>
  );
}
