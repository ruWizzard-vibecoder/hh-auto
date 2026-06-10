'use client';

import { useQuery } from '@tanstack/react-query';
import { getJson } from '@/lib/api';
import type { EventLogEntry } from './types';

const EVENT_ICONS: Record<string, string> = {
  search_cycle_complete:  '🔍',
  apply_cycle_complete:   '✉',
  archive_check_complete: '⌀',
  status_check_complete:  '↻',
  resume_touch_complete:  '✦',
  similar_expansion_complete: '⌥',
  scoring_complete:       '◆',
  letter_generation_complete: '✎',
};

function formatTime(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const HH = String(d.getHours()).padStart(2, '0');
  const MM = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm} ${HH}:${MM}`;
}

function summarize(details: Record<string, unknown> | null): string | null {
  if (!details) return null;
  const entries = Object.entries(details).slice(0, 4);
  if (!entries.length) return null;
  return entries.map(([k, v]) => `${k} ${formatValue(v)}`).join(' · ');
}

function formatValue(v: unknown): string {
  if (Array.isArray(v)) return `[${v.length}]`;
  if (typeof v === 'object' && v !== null) return JSON.stringify(v).slice(0, 30);
  return String(v);
}

export function EventsTimeline() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['events-recent'],
    queryFn: () => getJson<{ events: EventLogEntry[] }>('api/events/recent.json'),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return <Placeholder>···  загрузка ленты  ···</Placeholder>;
  }
  if (isError) {
    return <Placeholder error>···  не удалось загрузить события  ···</Placeholder>;
  }
  if (!data || data.events.length === 0) {
    return <Placeholder>···  событий пока нет — запустите поиск  ···</Placeholder>;
  }

  return (
    <div className="relative border-t border-hairline pt-2 pl-[22px]">
      <div className="absolute left-[6px] top-2 bottom-2 w-px bg-hairline" aria-hidden />
      {data.events.map((e) => {
        const icon = EVENT_ICONS[e.event_type] || '●';
        const summary = summarize(e.details);
        return (
          <div
            key={e.id}
            className="relative py-2.5 pl-4 border-b border-hairline last:border-b-0 flex items-start gap-2.5"
          >
            <span
              className="absolute -left-[22px] top-[14px] w-[7px] h-[7px] rotate-45 bg-vermilion"
              aria-hidden
            />
            <span className="font-mono text-[10.5px] tracking-[0.06em] uppercase text-ink-3 flex-shrink-0 mr-1">
              {formatTime(e.created_at)}
            </span>
            <span className="text-[14px] mr-1 select-none" aria-hidden>
              {icon}
            </span>
            <div className="flex-1 min-w-0">
              <span className="font-sans font-semibold text-[13.5px] text-ink tracking-[0.01em]">
                {e.event_type}
              </span>
              {summary && (
                <span className="text-ink-2 text-[13px]">
                  {' '}— {summary}
                </span>
              )}
              {e.error_message && (
                <div className="font-mono text-[11px] text-brick mt-1 break-all">
                  ⚠ {e.error_message.slice(0, 120)}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Placeholder({ children, error }: { children: React.ReactNode; error?: boolean }) {
  return (
    <p
      className={`font-mono text-[11px] tracking-[0.1em] uppercase py-6 ${
        error ? 'text-brick' : 'text-ink-3'
      }`}
    >
      {children}
    </p>
  );
}
