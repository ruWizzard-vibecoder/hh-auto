'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { getJson } from '@/lib/api';

interface NavItem {
  num: string;
  href: string;
  label: string;
  pendingBadge?: boolean;
}

const NAV: NavItem[] = [
  { num: '01', href: '/',              label: 'Главная' },
  { num: '02', href: '/cover-letters', label: 'Письма', pendingBadge: true },
  { num: '03', href: '/vacancies',     label: 'Вакансии' },
  { num: '04', href: '/applications',  label: 'Отклики' },
  { num: '05', href: '/summaries',     label: 'Сводки' },
  { num: '06', href: '/analytics',     label: 'Аналитика' },
  { num: '07', href: '/settings',      label: 'Настройки' },
];

interface StatusFragment {
  authenticated: boolean;
  applications_today: number;
}

export function Sidebar() {
  const pathname = usePathname();

  const { data: pendingCount } = useQuery({
    queryKey: ['pending-letters'],
    queryFn: () => getJson<{ count: number }>('api/cover-letters/pending-count'),
    refetchInterval: 60_000,
  });

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => getJson<StatusFragment>('api/status.json'),
    refetchInterval: 60_000,
  });

  return (
    <aside className="sticky top-0 h-screen w-[220px] flex-shrink-0 bg-paper-sink border-r border-hairline flex flex-col py-6 z-50">
      <div className="px-[22px] pb-[22px] border-b border-hairline mb-4 flex flex-col gap-1.5">
        <span className="font-display italic font-bold text-[26px] leading-none tracking-[-0.01em] text-ink">
          hh<em className="text-vermilion italic">·</em>auto
        </span>
        <EditionStamp />
      </div>

      <nav className="flex-1 flex flex-col overflow-y-auto">
        {NAV.map((item) => {
          const active =
            item.href === '/'
              ? pathname === '/'
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'relative px-[22px] py-[11px] pl-[30px] flex items-baseline gap-3 ' +
                  'font-sans text-[14px] font-medium tracking-[0.01em] transition-colors',
                active
                  ? 'text-ink bg-gradient-to-r from-vermilion-soft to-transparent'
                  : 'text-ink-2 hover:text-ink hover:bg-paper-edge'
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-[22px] bg-vermilion" />
              )}
              <span className="font-mono text-[10px] tracking-[0.1em] text-ink-4 w-[22px] flex-shrink-0">
                {item.num}
              </span>
              <span className="flex-1">{item.label}</span>
              {item.pendingBadge && pendingCount && pendingCount.count > 0 && (
                <span className="font-mono text-[10px] font-semibold tracking-[0.04em] bg-vermilion text-paper px-1.5 py-px rounded-[2px]">
                  {pendingCount.count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto px-[22px] pt-3.5 border-t border-hairline font-mono text-[10.5px] text-ink-3 tracking-[0.04em] leading-[1.5]">
        {status ? (
          <>
            hh.ru: {status.authenticated ? 'подключено' : 'не подключено'}<br />
            сегодня: {status.applications_today} откликов
          </>
        ) : (
          '···'
        )}
      </div>
    </aside>
  );
}

function EditionStamp() {
  const [text, setText] = React.useState('—');
  React.useEffect(() => {
    const genesis = new Date(2025, 11, 1);
    const num = Math.floor((Date.now() - genesis.getTime()) / 86_400_000) + 1;
    setText(`ИЗДАНИЕ №${num}`);
  }, []);
  return (
    <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">{text}</span>
  );
}
