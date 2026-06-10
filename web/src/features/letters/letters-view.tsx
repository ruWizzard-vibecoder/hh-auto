'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { PageMast } from '@/components/ui/page-mast';
import { fetchLetters } from './api';
import type { Letter, LetterStatus, LettersListQuery, LettersListResponse } from './types';
import { LetterCard } from './letter-card';
import { BulkBar } from './bulk-bar';
import { cn } from '@/lib/utils';

const STATUS_PILLS: Array<{ key: LetterStatus | null; label: string }> = [
  { key: 'pending',   label: 'Ожидают'   },
  { key: 'approved',  label: 'Одобрены'  },
  { key: 'no_letter', label: 'Без письма'},
  { key: 'sent',      label: 'Отправлены'},
  { key: 'rejected',  label: 'Отклонены' },
  { key: null,        label: 'Все'       },
];

const EMPLOYMENT_PILLS: Array<{ key: 'part' | 'project' | 'full'; label: string }> = [
  { key: 'part',    label: 'Частичная' },
  { key: 'project', label: 'Проектная' },
  { key: 'full',    label: 'Полная'    },
];

export function LettersView() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  const currentStatus = (sp.get('status') as LetterStatus | null) ?? null;
  const currentEmployment = (sp.get('employment') as 'part' | 'project' | 'full' | null) ?? null;
  const currentSort = (sp.get('sort') as 'date' | 'score') ?? 'date';
  const currentSearch = sp.get('q') ?? '';
  const currentGroup = (sp.get('group') as 'company' | null) ?? null;

  const queryParams: LettersListQuery = {
    status: currentStatus,
    employment: currentEmployment,
    sort: currentSort,
    q: currentSearch,
  };
  // Stable query key for the current filter combination.
  const listQueryKey = React.useMemo(
    () => ['letters', queryParams],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentStatus, currentEmployment, currentSort, currentSearch],
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: listQueryKey,
    queryFn: () => fetchLetters(queryParams),
    refetchInterval: 90_000,
  });

  // Navigate preserving other params
  const pushParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp.toString());
    if (value === null || value === '') next.delete(key);
    else next.set(key, value);
    router.push(`${pathname}${next.toString() ? `?${next.toString()}` : ''}`);
  };

  // Group by company on the client (matches the original UI behaviour).
  const groupedLetters = React.useMemo(() => {
    if (!data || currentGroup !== 'company') return null;
    const map = new Map<string, Letter[]>();
    for (const letter of data.letters) {
      const company = letter.vacancy.company_name || 'Без компании';
      if (!map.has(company)) map.set(company, []);
      map.get(company)!.push(letter);
    }
    return map;
  }, [data, currentGroup]);

  const showBulkBar =
    data &&
    data.counts.pending > 0 &&
    (currentStatus === 'pending' || currentStatus === null);

  return (
    <>
      <PageMast
        title="Письма"
        count="02"
        subtitle={
          data ? `НА СТОЛЕ: ${data.counts.pending} · ОДОБРЕНО: ${data.counts.approved}` : 'РЕДАКЦИОННАЯ ПРОВЕРКА'
        }
      />

      <SearchInput value={currentSearch} onChange={(v) => pushParam('q', v || null)} />

      {/* Status pills */}
      <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-3">
        {STATUS_PILLS.map((p) => {
          const count = p.key ? data?.counts[p.key] : undefined;
          return (
            <Pill
              key={p.key ?? 'all'}
              active={currentStatus === p.key}
              onClick={() => pushParam('status', p.key)}
            >
              {p.label}
              {count !== undefined && <span className="num text-ink-3 ml-1">·{count}</span>}
            </Pill>
          );
        })}
      </div>

      {/* Employment pills (only if some are present) */}
      {data && Object.keys(data.employment_counts).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-3">
          <FilterLabel>Занятость</FilterLabel>
          {EMPLOYMENT_PILLS.map((p) => {
            const count = data.employment_counts[p.key];
            if (!count) return null;
            return (
              <Pill
                key={p.key}
                size="sm"
                active={currentEmployment === p.key}
                onClick={() => pushParam('employment', currentEmployment === p.key ? null : p.key)}
              >
                {p.label} <span className="num text-ink-3 ml-1">·{count}</span>
              </Pill>
            );
          })}
          {currentEmployment && (
            <Pill
              size="sm"
              variant="reset"
              onClick={() => pushParam('employment', null)}
            >
              ✕ сбросить
            </Pill>
          )}
        </div>
      )}

      {/* Sort + group */}
      <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-3">
        <FilterLabel>Сортировка</FilterLabel>
        <Pill size="sm" active={currentSort === 'score'} onClick={() => pushParam('sort', 'score')}>
          по оценке
        </Pill>
        <Pill size="sm" active={currentSort !== 'score'} onClick={() => pushParam('sort', null)}>
          по дате
        </Pill>
        <FilterLabel className="ml-5">Группировка</FilterLabel>
        <Pill
          size="sm"
          active={currentGroup === 'company'}
          onClick={() => pushParam('group', currentGroup === 'company' ? null : 'company')}
        >
          по компаниям
        </Pill>
      </div>

      {showBulkBar && <BulkBar />}

      {isError && (
        <p className="font-mono text-[12px] text-brick uppercase tracking-[0.08em] py-6">
          ⚠ не удалось загрузить очередь — проверьте бэкенд
        </p>
      )}

      {isLoading && !data && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка очереди писем  ···
        </p>
      )}

      {data && data.letters.length === 0 && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  по выбранному фильтру писем нет  ···
        </p>
      )}

      {data &&
        (groupedLetters ? (
          [...groupedLetters.entries()].map(([company, letters]) => (
            <React.Fragment key={company}>
              <h4 className="font-display italic font-medium text-[20px] tracking-[-0.01em] text-ink mt-8 mb-2.5 pb-1 border-b border-hairline">
                {company} · {letters.length}
                <span className="inline-block w-8 border-b border-hairline align-middle ml-3" />
              </h4>
              {letters.map((letter) => (
                <LetterCard
                  key={letter.id}
                  letter={letter}
                  resumeName={(letter.resume_id && data.resume_names[letter.resume_id]) || null}
                  listQueryKey={listQueryKey}
                />
              ))}
            </React.Fragment>
          ))
        ) : (
          data.letters.map((letter) => (
            <LetterCard
              key={letter.id}
              letter={letter}
              resumeName={(letter.resume_id && data.resume_names[letter.resume_id]) || null}
              listQueryKey={listQueryKey}
            />
          ))
        ))}
    </>
  );
}

/* ─────────────────────────── helpers ─────────────────────────── */

function Pill({
  children,
  active,
  onClick,
  size = 'md',
  variant = 'default',
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  size?: 'sm' | 'md';
  variant?: 'default' | 'reset';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 border rounded-[2px] font-sans font-medium tracking-[0.01em] transition-colors leading-snug',
        size === 'sm' ? 'px-2.5 py-1 text-[11.5px]' : 'px-3.5 py-1.5 text-[12.5px]',
        active
          ? 'bg-ink text-paper border-ink font-semibold'
          : variant === 'reset'
          ? 'text-brick border-brick-dim hover:bg-brick-soft hover:border-brick hover:text-ink'
          : 'text-ink-2 border-hairline-bold hover:text-ink hover:border-ink-3',
      )}
    >
      {children}
    </button>
  );
}

function FilterLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn('font-mono text-[10.5px] tracking-[0.14em] uppercase text-ink-3 mr-2', className)}>
      {children}
    </span>
  );
}

function SearchInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [local, setLocal] = React.useState(value);
  React.useEffect(() => setLocal(value), [value]);

  return (
    <form
      className="mb-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        onChange(local);
      }}
    >
      <input
        type="search"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder="поиск по названию или компании…"
        className={cn(
          'w-full bg-paper border-0 border-b-2 border-hairline-bold py-3 px-1 ' +
            'font-display italic text-[18px] text-ink placeholder:text-ink-3 placeholder:italic ' +
            'focus:outline-none focus:border-vermilion transition-colors',
        )}
      />
    </form>
  );
}
