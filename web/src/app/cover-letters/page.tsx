import { Suspense } from 'react';
import { Shell } from '@/components/layout/shell';
import { LettersView } from '@/features/letters/letters-view';

export default function CoverLettersPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">···  загрузка  ···</p>}>
        <LettersView />
      </Suspense>
    </Shell>
  );
}
