'use client';

import type { DashboardStats } from './types';

interface Props {
  stats: DashboardStats;
}

/* "Воронка" — горизонтальные пропорциональные полосы с подписями.
   Не используем FunnelChart из recharts (он рисует трапеции — менее
   информативно для нашего случая); рисуем обычный BarChart с layout="vertical". */

export function FunnelChart({ stats }: Props) {
  const max = stats.total_vacancies || 1;
  const rows = [
    { label: 'Найдено',     value: stats.total_vacancies,    fill: 'var(--color-indigo)' },
    { label: 'Оценено',     value: stats.scored,             fill: 'var(--color-indigo-dim)' },
    { label: 'Письма',      value: stats.letters_total,      fill: 'var(--color-gold)' },
    { label: 'Одобрено',    value: stats.approved,           fill: 'var(--color-gold-dim)' },
    { label: 'Отправлено',  value: stats.applications_sent,  fill: 'var(--color-sage)' },
    { label: 'Ответ',       value: stats.responded,          fill: 'var(--color-vermilion)' },
  ];

  return (
    <div className="border-t border-hairline border-b-2 border-b-hairline-bold py-2">
      {rows.map((row, i) => {
        const pct = max ? (row.value / max) * 100 : 0;
        return (
          <div
            key={row.label}
            className="grid grid-cols-[110px_1fr_76px] items-center gap-4 py-2.5 border-b border-hairline last:border-b-0"
          >
            <span className="font-sans text-[12px] font-medium uppercase tracking-[0.14em] text-ink-2">
              {row.label}
            </span>
            <div className="relative h-7 bg-paper-rise border border-hairline overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 transition-[width] duration-700 ease-[cubic-bezier(0.2,0.7,0.2,1)]"
                style={{
                  width: `${pct}%`,
                  background: row.fill,
                  // tiny highlight on the right edge — like a wet-ink stroke
                  boxShadow: 'inset -2px 0 0 rgba(255,255,255,0.25)',
                }}
              />
              <div
                className="absolute inset-y-0 left-0 flex items-center pl-2 font-mono text-[10px] tracking-[0.06em] text-paper/80"
                style={{ width: `${pct}%`, mixBlendMode: 'difference', opacity: pct > 12 ? 0.85 : 0 }}
              >
                {pct.toFixed(0)}%
              </div>
            </div>
            <span className="font-display italic text-[26px] text-ink leading-none text-right num">
              {row.value.toLocaleString('ru-RU')}
            </span>
          </div>
        );
      })}
    </div>
  );
}
