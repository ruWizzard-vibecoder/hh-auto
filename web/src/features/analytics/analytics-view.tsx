'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { PageMast } from '@/components/ui/page-mast';
import { Figure, FigureGrid } from '@/components/ui/figure';
import { SectionRule } from '@/components/ui/section-rule';
import { getJson } from '@/lib/api';
import { cn } from '@/lib/utils';

interface AnalyticsData {
  stats: {
    total_vacancies: number;
    applications_sent: number;
    response_rate: number;
    avg_score: number;
    invited: number;
    letters_approved: number;
  };
  daily_stats: Array<{ date: string; iso_date: string; sent: number; viewed: number; invited: number; declined: number }>;
  top_companies: Array<{ name: string; count: number; responses: number }>;
  score_distribution: Array<{ range: string; count: number; applied: number }>;
}

const SERIES_COLORS = {
  sent: 'var(--color-indigo)',
  viewed: 'var(--color-gold)',
  invited: 'var(--color-sage)',
  declined: 'var(--color-brick)',
};

export function AnalyticsView() {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => getJson<AnalyticsData>('api/analytics.json'),
    refetchInterval: 120_000,
  });

  if (isLoading || !data) {
    return (
      <>
        <PageMast title="Аналитика" count="06" subtitle="ЦИФРЫ · ТЕНДЕНЦИИ" />
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка аналитики  ···
        </p>
      </>
    );
  }

  const s = data.stats;
  const maxDistCount = Math.max(...data.score_distribution.map((b) => b.count), 1);

  return (
    <>
      <PageMast title="Аналитика" count="06" subtitle="ЦИФРЫ · ТЕНДЕНЦИИ" />

      <FigureGrid>
        <Figure num="01" value={s.total_vacancies.toLocaleString('ru-RU')} label="Всего вакансий" />
        <Figure num="02" value={s.applications_sent.toLocaleString('ru-RU')} label="Откликов отправлено" accent="indigo" />
        <Figure num="03" value={`${s.response_rate.toFixed(0)}%`} label="Процент ответов" accent="sage" />
        <Figure num="04" value={`${(s.avg_score * 100).toFixed(0)}%`} label="Средняя оценка" accent="gold" />
        <Figure num="05" value={s.invited.toLocaleString('ru-RU')} label="Приглашений" accent="hot" />
        <Figure num="06" value={s.letters_approved.toLocaleString('ru-RU')} label="Писем одобрено" />
      </FigureGrid>

      {/* Daily bar chart */}
      <Panel title="Отклики по дням">
        {data.daily_stats.length === 0 ? (
          <p className="text-ink-3 font-mono text-[11px] py-3 uppercase tracking-[0.1em]">
            нет данных за последние 14 дней
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-4 py-2 font-mono text-[10.5px] uppercase tracking-[0.08em] mb-3">
              {(['sent', 'viewed', 'invited', 'declined'] as const).map((k) => (
                <span key={k} className="inline-flex items-center gap-1.5 text-ink-2">
                  <span className="inline-block w-2.5 h-2.5" style={{ background: SERIES_COLORS[k] }} />
                  {labelFor(k)}
                </span>
              ))}
            </div>
            <div className="border-y-2 border-hairline-bold py-3" style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.daily_stats} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke="var(--color-hairline)" strokeDasharray="2 4" vertical={false} />
                  <XAxis
                    dataKey="date"
                    stroke="var(--color-ink-3)"
                    tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--color-ink-3)' }}
                    axisLine={{ stroke: 'var(--color-hairline-bold)' }}
                  />
                  <YAxis
                    stroke="var(--color-ink-3)"
                    tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--color-ink-3)' }}
                    axisLine={{ stroke: 'var(--color-hairline-bold)' }}
                    width={32}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--color-paper-rise)',
                      border: '1px solid var(--color-hairline-bold)',
                      borderLeft: '3px solid var(--color-vermilion)',
                      borderRadius: 2,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--color-ink)',
                    }}
                    labelStyle={{ color: 'var(--color-ink-2)', letterSpacing: '0.04em' }}
                    cursor={{ fill: 'rgba(230,62,17,0.06)' }}
                  />
                  <Bar dataKey="sent"     fill={SERIES_COLORS.sent} />
                  <Bar dataKey="viewed"   fill={SERIES_COLORS.viewed} />
                  <Bar dataKey="invited"  fill={SERIES_COLORS.invited} />
                  <Bar dataKey="declined" fill={SERIES_COLORS.declined} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </Panel>

      <Panel title="Топ компаний по откликам">
        {data.top_companies.length === 0 ? (
          <p className="text-ink-3 font-mono text-[11px] py-3 uppercase tracking-[0.1em]">
            нет данных
          </p>
        ) : (
          <div className="border-y-2 border-hairline-bold overflow-x-auto">
            <table className="w-full border-collapse text-[13.5px]">
              <thead>
                <tr>
                  {['Компания', 'Откликов', 'Ответов'].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.top_companies.map((c) => (
                  <tr key={c.name} className="group hover:bg-paper-edge">
                    <td className="p-2.5 px-3 border-b border-hairline group-hover:shadow-[inset_2px_0_0_var(--color-vermilion)] text-ink">{c.name}</td>
                    <td className="p-2.5 px-3 border-b border-hairline num text-ink">{c.count}</td>
                    <td className="p-2.5 px-3 border-b border-hairline num">
                      <span className={cn(c.responses > 0 ? 'text-sage font-semibold' : 'text-ink-3')}>
                        {c.responses}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Распределение оценок">
        <div className="flex flex-col">
          {data.score_distribution.map((b) => {
            const pct = (b.count / maxDistCount) * 100;
            return (
              <div key={b.range} className="grid grid-cols-[96px_1fr_96px] items-center gap-3.5 py-2 border-b border-hairline">
                <span className="font-mono text-[11.5px] tracking-[0.06em] text-ink-2">{b.range}</span>
                <div className="h-[22px] bg-paper-sink border border-hairline relative overflow-hidden">
                  <div
                    className="h-full transition-[width] duration-700 ease-[cubic-bezier(0.2,0.7,0.2,1)] flex items-center justify-end pr-2"
                    style={{
                      width: `${pct}%`,
                      background: 'linear-gradient(90deg, var(--color-vermilion-dim), var(--color-vermilion))',
                    }}
                  >
                    {pct > 10 && (
                      <span className="font-mono text-[11px] text-paper font-semibold">{b.count}</span>
                    )}
                  </div>
                </div>
                <span className="font-mono text-[11px] tracking-[0.04em] text-ink-3 text-right">
                  {b.applied} отпр.
                </span>
              </div>
            );
          })}
        </div>
      </Panel>
    </>
  );
}

function labelFor(k: 'sent' | 'viewed' | 'invited' | 'declined'): string {
  switch (k) {
    case 'sent': return 'отправлено';
    case 'viewed': return 'просмотрено';
    case 'invited': return 'приглашения';
    case 'declined': return 'отказы';
  }
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="border-t-2 border-t-hairline-bold border-b border-b-hairline py-6 mt-1">
      <header className="pb-3 mb-4 border-b border-hairline">
        <strong className="block font-display italic font-medium text-[22px] tracking-[-0.005em] text-ink">
          {title}
        </strong>
      </header>
      {children}
    </article>
  );
}
