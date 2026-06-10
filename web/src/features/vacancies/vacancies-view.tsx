'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { toast } from 'sonner';
import { ExternalLink, ChevronDown, FileText, Ban } from 'lucide-react';
import { PageMast } from '@/components/ui/page-mast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getJson, api } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { Vacancy, VacanciesResponse } from './types';

const STATUS_PILLS = [
  { key: 'scored',   label: 'Оценённые' },
  { key: 'queued',   label: 'В очереди' },
  { key: 'applied',  label: 'Отправлены' },
  { key: 'skipped',  label: 'Пропущены' },
  { key: 'archived', label: 'Архив' },
  { key: null,       label: 'Все' },
] as const;

const EMPLOYMENT_PILLS = [
  { key: 'part',    label: 'Частичная' },
  { key: 'project', label: 'Проектная' },
  { key: 'full',    label: 'Полная' },
] as const;

function scoreClass(s: number | null) {
  if (s === null) return 'text-ink-3';
  if (s >= 0.7) return 'text-sage';
  if (s >= 0.5) return 'text-gold';
  return 'text-brick';
}

function buildSearch(p: { status: string | null; employment: string | null; q: string; page: number }) {
  const sp = new URLSearchParams();
  if (p.status) sp.set('status', p.status);
  if (p.employment) sp.set('employment', p.employment);
  if (p.q) sp.set('q', p.q);
  if (p.page > 0) sp.set('page', String(p.page));
  return sp.toString();
}

export function VacanciesView() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const qc = useQueryClient();

  const status = sp.get('status');
  const employment = sp.get('employment');
  const q = sp.get('q') ?? '';
  const page = Number(sp.get('page') ?? '0');
  const group = sp.get('group');

  const queryParams = { status, employment, q, page };
  const queryKey = React.useMemo(
    () => ['vacancies', queryParams],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status, employment, q, page],
  );

  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () =>
      getJson<VacanciesResponse>(
        `api/vacancies${buildSearch(queryParams) ? `?${buildSearch(queryParams)}` : ''}`,
      ),
    refetchInterval: 120_000,
  });

  const pushParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp.toString());
    if (value === null || value === '') next.delete(key);
    else next.set(key, value);
    // any filter change resets page
    if (key !== 'page') next.delete('page');
    router.push(`${pathname}${next.toString() ? `?${next.toString()}` : ''}`);
  };

  const blacklistMut = useMutation({
    mutationFn: (id: number) => api.post(`api/vacancies/${id}/blacklist.json`).json(),
    onSuccess: () => {
      toast.success('компания добавлена в ЧС');
      qc.invalidateQueries({ queryKey: ['vacancies'] });
    },
    onError: () => toast.error('не удалось добавить в ЧС'),
  });

  const genLetterMut = useMutation({
    mutationFn: (id: number) => api.post(`api/vacancies/${id}/generate-letter.json`).json(),
    onSuccess: () => {
      toast.success('запрошено создание письма');
      qc.invalidateQueries({ queryKey: ['vacancies'] });
      qc.invalidateQueries({ queryKey: ['letters'] });
      qc.invalidateQueries({ queryKey: ['pending-letters'] });
    },
    onError: () => toast.error('не удалось сгенерировать письмо'),
  });

  const groupedRows = React.useMemo(() => {
    if (!data || group !== 'company') return null;
    const map = new Map<string, Vacancy[]>();
    for (const v of data.vacancies) {
      const k = v.company_name || 'Без компании';
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(v);
    }
    return map;
  }, [data, group]);

  return (
    <>
      <PageMast
        title="Вакансии"
        count={data ? String(data.total) : undefined}
        subtitle="РЕЕСТР ОБЪЯВЛЕНИЙ"
      />

      <SearchInput value={q} onChange={(v) => pushParam('q', v || null)} />

      <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-3">
        {STATUS_PILLS.map((p) => (
          <Pill key={p.key ?? 'all'} active={status === p.key} onClick={() => pushParam('status', p.key)}>
            {p.label}
          </Pill>
        ))}
      </div>

      {data && Object.keys(data.employment_counts).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-3">
          <FilterLabel>Занятость</FilterLabel>
          {EMPLOYMENT_PILLS.map((p) => {
            const cnt = data.employment_counts[p.key];
            if (!cnt) return null;
            return (
              <Pill
                key={p.key}
                size="sm"
                active={employment === p.key}
                onClick={() => pushParam('employment', employment === p.key ? null : p.key)}
              >
                {p.label} <span className="num text-ink-3 ml-1">·{cnt}</span>
              </Pill>
            );
          })}
          {employment && (
            <Pill size="sm" variant="reset" onClick={() => pushParam('employment', null)}>
              ✕ сбросить
            </Pill>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-4">
        <FilterLabel>Группировка</FilterLabel>
        <Pill
          size="sm"
          active={group === 'company'}
          onClick={() => pushParam('group', group === 'company' ? null : 'company')}
        >
          по компаниям
        </Pill>
      </div>

      {isError && (
        <p className="font-mono text-[12px] text-brick uppercase tracking-[0.08em] py-6">
          ⚠ ошибка загрузки
        </p>
      )}
      {isLoading && !data && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка вакансий  ···
        </p>
      )}

      {data && data.vacancies.length === 0 && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  по фильтру вакансий нет  ···
        </p>
      )}

      {data && data.vacancies.length > 0 && (
        <>
          {groupedRows ? (
            [...groupedRows.entries()].map(([company, rows]) => (
              <React.Fragment key={company}>
                <h4 className="font-display italic font-medium text-[20px] tracking-[-0.01em] text-ink mt-8 mb-2.5 pb-1 border-b border-hairline">
                  {company} · {rows.length}
                </h4>
                <VacanciesTable
                  rows={rows}
                  resumeNames={data.resume_names}
                  onBlacklist={(id, company) => {
                    if (confirm(`Заблокировать ${company || 'компанию'}?`)) blacklistMut.mutate(id);
                  }}
                  onGenerateLetter={(id) => genLetterMut.mutate(id)}
                  busy={blacklistMut.isPending || genLetterMut.isPending}
                />
              </React.Fragment>
            ))
          ) : (
            <VacanciesTable
              rows={data.vacancies}
              resumeNames={data.resume_names}
              onBlacklist={(id, company) => {
                if (confirm(`Заблокировать ${company || 'компанию'}?`)) blacklistMut.mutate(id);
              }}
              onGenerateLetter={(id) => genLetterMut.mutate(id)}
              busy={blacklistMut.isPending || genLetterMut.isPending}
            />
          )}

          {!groupedRows && (data.page > 0 || data.has_more) && (
            <div className="flex justify-center gap-4 py-7 mt-7 border-t border-hairline">
              {data.page > 0 && (
                <Button variant="outline" onClick={() => pushParam('page', String(data.page - 1))}>
                  ← Назад
                </Button>
              )}
              {data.has_more && (
                <Button variant="outline" onClick={() => pushParam('page', String(data.page + 1))}>
                  Далее →
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}

function VacanciesTable({
  rows,
  resumeNames,
  onBlacklist,
  onGenerateLetter,
  busy,
}: {
  rows: Vacancy[];
  resumeNames: Record<string, string>;
  onBlacklist: (id: number, company: string | null) => void;
  onGenerateLetter: (id: number) => void;
  busy: boolean;
}) {
  return (
    <div className="border-y-2 border-hairline-bold overflow-x-auto my-3.5 mb-7">
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          <tr>
            {['Вакансия', 'Компания', 'Зарплата', 'Оценка', 'Резюме', 'Детали', 'Статус', 'Действия'].map((h) => (
              <th
                key={h}
                className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink sticky top-0 z-[2]"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.id} className="group hover:bg-paper-edge transition-colors">
              <td className="p-3 border-b border-hairline align-top group-hover:shadow-[inset_2px_0_0_var(--color-vermilion)]">
                <a
                  href={v.url ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-ink border-b border-dotted border-ink-3 pb-px hover:text-vermilion hover:border-vermilion inline-flex items-center gap-1"
                >
                  {v.title}
                  <ExternalLink className="size-3 opacity-60" />
                </a>
                {v.schedule === 'remote' && (
                  <small className="text-ink-3 ml-1 text-[12px]">удал.</small>
                )}
                {v.description && (
                  <details className="mt-2 group/desc">
                    <summary className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3 cursor-pointer pb-0.5 border-b border-dotted border-ink-4 w-max inline-flex items-center gap-1 hover:text-vermilion list-none">
                      <ChevronDown className="size-3 transition-transform group-open/desc:rotate-180" />
                      описание
                    </summary>
                    <div
                      className="pt-2.5 text-ink-2 leading-[1.6] text-[12.5px] mt-1 border-t border-hairline max-h-[280px] overflow-y-auto"
                      dangerouslySetInnerHTML={{ __html: v.description }}
                    />
                  </details>
                )}
              </td>
              <td className="p-3 border-b border-hairline align-top text-ink-2">
                {v.company_name || '—'}
              </td>
              <td className="p-3 border-b border-hairline align-top num">
                {v.salary_from || v.salary_to ? (
                  <>
                    {v.salary_from ?? '?'}–{v.salary_to ?? '?'}
                    <small className="text-ink-3 ml-1">{v.salary_currency ?? ''}</small>
                  </>
                ) : (
                  '—'
                )}
              </td>
              <td className="p-3 border-b border-hairline align-top num">
                {v.relevance_score !== null ? (
                  <span className={cn('font-semibold', scoreClass(v.relevance_score))}>
                    {(v.relevance_score * 100).toFixed(0)}%
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="p-3 border-b border-hairline align-top">
                {v.recommended_resume_id && resumeNames[v.recommended_resume_id] ? (
                  <Badge variant="resume">{resumeNames[v.recommended_resume_id]}</Badge>
                ) : (
                  '—'
                )}
              </td>
              <td className="p-3 border-b border-hairline align-top space-y-1">
                {v.employment === 'part' && <Badge variant="parttime">Частичная</Badge>}
                {v.employment === 'project' && <Badge variant="project">Проект</Badge>}
                {v.matched_skills.length > 0 && (
                  <div className="font-mono text-[10.5px] text-sage">+ {v.matched_skills.join(' · ')}</div>
                )}
                {v.missing_skills.length > 0 && (
                  <div className="font-mono text-[10.5px] text-brick opacity-90">− {v.missing_skills.join(' · ')}</div>
                )}
              </td>
              <td className="p-3 border-b border-hairline align-top">
                <Badge variant={v.status as never}>{v.status}</Badge>
              </td>
              <td className="p-3 border-b border-hairline align-top">
                <div className="flex flex-wrap gap-1.5">
                  {v.status === 'scored' && (
                    <Button
                      size="sm"
                      onClick={() => onGenerateLetter(v.id)}
                      disabled={busy}
                    >
                      <FileText className="size-3.5" /> письмо
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => onBlacklist(v.id, v.company_name)}
                    disabled={busy}
                  >
                    <Ban className="size-3.5" /> ЧС
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-ink-3 mr-2">
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
        className="w-full bg-paper border-0 border-b-2 border-hairline-bold py-3 px-1 font-display italic text-[18px] text-ink placeholder:text-ink-3 placeholder:italic focus:outline-none focus:border-vermilion transition-colors"
      />
    </form>
  );
}
