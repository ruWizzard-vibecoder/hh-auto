import { Suspense } from 'react';
import { Shell } from '@/components/layout/shell';
import { VacanciesView } from '@/features/vacancies/vacancies-view';

export default function VacanciesPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">···  загрузка  ···</p>}>
        <VacanciesView />
      </Suspense>
    </Shell>
  );
}
