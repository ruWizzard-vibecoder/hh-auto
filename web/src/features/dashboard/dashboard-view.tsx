'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { getJson } from '@/lib/api';
import { PageMast } from '@/components/ui/page-mast';
import { Figure, FigureGrid } from '@/components/ui/figure';
import { SectionRule } from '@/components/ui/section-rule';
import { buttonVariants } from '@/components/ui/button';
import { FunnelChart } from './funnel-chart';
import { EventsTimeline } from './events-timeline';
import type { DashboardStats } from './types';

export function DashboardView() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: () => getJson<DashboardStats>('api/dashboard/stats'),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageMast title="Главная" count="01" subtitle="ОПЕРАЦИОННАЯ СВОДКА" />

      {isError && (
        <p className="font-mono text-[12px] text-brick uppercase tracking-[0.08em] mb-8">
          ⚠ ошибка загрузки статистики — проверьте, что бэкенд на :8100 запущен
        </p>
      )}

      <FigureGrid>
        <Figure
          num="01"
          value={fmt(data?.total_vacancies, isLoading)}
          label="Вакансий найдено"
        />
        <Figure
          num="02"
          value={fmt(data?.pending_letters, isLoading)}
          label="Ждут проверки"
          accent={data && data.pending_letters > 0 ? 'hot' : 'default'}
        />
        <Figure
          num="03"
          value={fmt(data?.applications_sent, isLoading)}
          label="Откликов отправлено"
          accent="indigo"
        />
        <Figure num="04" value={fmt(data?.applications_today, isLoading)} label="Сегодня" />
        <Figure
          num="05"
          value={fmt(data?.viewed, isLoading)}
          label="Просмотрено"
          accent="gold"
        />
        <Figure
          num="06"
          value={fmt(data?.invited, isLoading)}
          label="Приглашений"
          accent="sage"
        />
      </FigureGrid>

      {data && data.pending_letters > 0 && (
        <div className="flex items-center justify-between gap-6 py-5 px-6 mb-8 border-y border-hairline border-l-[3px] border-l-vermilion bg-gradient-to-r from-vermilion-soft to-transparent">
          <div>
            <strong className="block font-display italic font-semibold text-[20px] text-ink mb-1">
              {data.pending_letters} писем ждут вашего слова
            </strong>
            <small className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-2">
              проверка очереди — основная задача дня
            </small>
          </div>
          <Link
            href="/cover-letters?status=pending"
            className={buttonVariants({ variant: 'primary' })}
          >
            Открыть очередь <ArrowRight className="size-4" />
          </Link>
        </div>
      )}

      <SectionRule>Воронка</SectionRule>
      {data ? (
        <FunnelChart stats={data} />
      ) : (
        <Placeholder>···  данные воронки загружаются  ···</Placeholder>
      )}

      <SectionRule>Хроника</SectionRule>
      <EventsTimeline />
    </>
  );
}

function fmt(n: number | undefined, loading: boolean): string {
  if (loading || n === undefined) return '—';
  return n.toLocaleString('ru-RU');
}

function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-6">{children}</p>
  );
}
