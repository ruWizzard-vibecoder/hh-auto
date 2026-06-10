'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronDown, Sparkles, ExternalLink } from 'lucide-react';
import { PageMast } from '@/components/ui/page-mast';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api, getJson } from '@/lib/api';
import { cn } from '@/lib/utils';

interface TopVacancy { title: string; company: string | null; score: number | null; url?: string | null; why_promising?: string | null }
interface InterviewPrep {
  vacancy_title: string;
  company: string | null;
  questions_to_prepare?: string[];
  projects_to_highlight?: string[];
  tech_topics_to_review?: string[];
  company_research?: string | null;
}
interface SummaryRow {
  id: number;
  summary_date: string | null;
  vacancies_discovered: number;
  applications_sent: number;
  responses_received: number;
  avg_relevance_score: number | null;
  summary_text: string | null;
  top_vacancies: TopVacancy[] | null;
  interview_prep: InterviewPrep[] | null;
  insights: string | null;
}

const MONTHS_FULL = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS_FULL[d.getMonth()]} ${d.getFullYear()}`;
}
function scoreClass(s: number | null): string {
  if (s === null) return 'text-ink-3';
  if (s >= 0.7) return 'text-sage';
  if (s >= 0.5) return 'text-gold';
  return 'text-brick';
}

export function SummariesView() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['summaries'],
    queryFn: () => getJson<{ summaries: SummaryRow[] }>('api/summaries.json'),
  });

  const genMut = useMutation({
    mutationFn: () => api.post('api/summaries/generate').json(),
    onSuccess: () => {
      toast.success('сводка формируется');
      setTimeout(() => qc.invalidateQueries({ queryKey: ['summaries'] }), 2000);
    },
    onError: () => toast.error('не удалось запустить генерацию'),
  });

  return (
    <>
      <PageMast
        title="Сводки"
        count={data ? String(data.summaries.length) : undefined}
        subtitle="ЕЖЕДНЕВНЫЕ ОТЧЁТЫ"
      />

      <div className="flex flex-wrap items-center gap-2 mb-7">
        <Button variant="primary" onClick={() => genMut.mutate()} disabled={genMut.isPending}>
          <Sparkles className="size-4" />
          {genMut.isPending ? 'формируется…' : 'Сформировать сводку за сегодня'}
        </Button>
      </div>

      {isLoading && !data && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка сводок  ···
        </p>
      )}

      {data && data.summaries.length === 0 && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  сводок ещё нет — нажмите «сформировать» после первого цикла поиска  ···
        </p>
      )}

      {data?.summaries.map((s) => (
        <SummaryCard key={s.id} summary={s} />
      ))}
    </>
  );
}

function SummaryCard({ summary: s }: { summary: SummaryRow }) {
  const [open, setOpen] = React.useState(false);
  return (
    <article className="border-t-2 border-t-hairline-bold border-b border-b-hairline py-5 mt-1">
      <div className="flex items-end justify-between gap-6 flex-wrap">
        <strong className="font-display italic font-semibold text-[26px] text-ink leading-tight tracking-[-0.01em]">
          {formatDate(s.summary_date)}
        </strong>
        <div className="font-mono text-[11.5px] text-ink-2 tracking-[0.04em] flex flex-wrap gap-x-5 gap-y-1">
          <span>вакансий <strong className="text-ink num font-sans">{s.vacancies_discovered}</strong></span>
          <span>откликов <strong className="text-ink num font-sans">{s.applications_sent}</strong></span>
          <span>ответов <strong className="text-ink num font-sans">{s.responses_received}</strong></span>
          <span>
            ср.оценка{' '}
            <strong className={cn('num font-sans', scoreClass(s.avg_relevance_score))}>
              {s.avg_relevance_score !== null ? `${(s.avg_relevance_score * 100).toFixed(0)}%` : '—'}
            </strong>
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3 hover:text-vermilion border-b border-dotted border-ink-4 pb-0.5"
      >
        <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} />
        {open ? 'скрыть отчёт' : 'показать полный отчёт'}
      </button>

      {open && (
        <div className="mt-5">
          {s.summary_text && (
            <div
              className="py-4 text-[14px] leading-[1.7] text-ink-2 border-t border-hairline mt-1 [&_strong]:text-ink"
              dangerouslySetInnerHTML={{ __html: s.summary_text.replace(/\n/g, '<br>') }}
            />
          )}

          {s.top_vacancies && s.top_vacancies.length > 0 && (
            <>
              <h4 className="font-sans text-[13px] font-semibold uppercase tracking-[0.14em] text-ink-2 border-b border-hairline pb-1.5 mt-7 mb-3.5">
                Лучшие вакансии
              </h4>
              <div className="border-y-2 border-hairline-bold overflow-x-auto">
                <table className="w-full border-collapse text-[13.5px]">
                  <thead>
                    <tr>
                      {['Вакансия', 'Компания', 'Оценка', 'Почему интересна'].map((h) => (
                        <th key={h} className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {s.top_vacancies.map((v, i) => (
                      <tr key={i} className="hover:bg-paper-edge">
                        <td className="p-2.5 px-3 border-b border-hairline">
                          {v.url ? (
                            <a href={v.url} target="_blank" rel="noreferrer" className="text-ink border-b border-dotted border-ink-3 hover:text-vermilion hover:border-vermilion inline-flex items-center gap-1">
                              {v.title}
                              <ExternalLink className="size-3 opacity-60" />
                            </a>
                          ) : (
                            v.title
                          )}
                        </td>
                        <td className="p-2.5 px-3 border-b border-hairline text-ink-2">{v.company || '—'}</td>
                        <td className="p-2.5 px-3 border-b border-hairline num">
                          {v.score !== null && v.score !== undefined ? (
                            <span className={cn('font-semibold', scoreClass(v.score))}>{(v.score * 100).toFixed(0)}%</span>
                          ) : '—'}
                        </td>
                        <td className="p-2.5 px-3 border-b border-hairline text-ink-2 text-[13px]">{v.why_promising || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {s.interview_prep && s.interview_prep.length > 0 && (
            <>
              <h4 className="font-sans text-[13px] font-semibold uppercase tracking-[0.14em] text-ink-2 border-b border-hairline pb-1.5 mt-7 mb-3.5">
                Подготовка к собеседованиям
              </h4>
              {s.interview_prep.map((p, i) => (
                <div key={i} className="relative bg-paper border-t-2 border-t-hairline-bold border-b border-b-hairline pl-[30px] pr-6 py-4 mt-3">
                  <span className="absolute left-0 top-0 w-[3px] h-full bg-vermilion" />
                  <div className="font-display italic font-semibold text-[20px] text-ink mb-2">
                    {p.vacancy_title}
                    {p.company && <span className="not-italic font-normal text-ink-2 font-sans text-[14px] ml-2">@ {p.company}</span>}
                  </div>
                  {p.questions_to_prepare?.length ? (
                    <PrepSection title="Вопросы для подготовки" items={p.questions_to_prepare} />
                  ) : null}
                  {p.projects_to_highlight?.length ? (
                    <PrepSection title="Проекты для упоминания" items={p.projects_to_highlight} />
                  ) : null}
                  {p.tech_topics_to_review?.length ? (
                    <PrepSection title="Темы для повторения" items={p.tech_topics_to_review} />
                  ) : null}
                  {p.company_research && (
                    <p className="mt-3 text-ink-2 text-[14px]">
                      <strong className="text-ink">О компании.</strong> {p.company_research}
                    </p>
                  )}
                </div>
              ))}
            </>
          )}

          {s.insights && (
            <>
              <h4 className="font-sans text-[13px] font-semibold uppercase tracking-[0.14em] text-ink-2 border-b border-hairline pb-1.5 mt-7 mb-3.5">
                Выводы и рекомендации
              </h4>
              <div className="font-mono text-[13px] leading-[1.75] text-ink whitespace-pre-wrap bg-paper-sink border border-hairline border-l-[3px] border-l-gold p-5">
                {s.insights}
              </div>
            </>
          )}
        </div>
      )}
    </article>
  );
}

function PrepSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-3">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-3 mb-1.5">{title}</div>
      <ul className="list-none pl-0 space-y-1">
        {items.map((x, i) => (
          <li key={i} className="text-ink-2 text-[13.5px] pl-4 relative leading-[1.55]">
            <span className="absolute left-0 top-[0.4em] w-1.5 h-1.5 bg-vermilion rotate-45" />
            {x}
          </li>
        ))}
      </ul>
    </div>
  );
}
