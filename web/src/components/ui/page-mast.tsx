'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

/* "Шапка-маст" страницы — гигантский italic-заголовок + дата-stamp справа.
   Эстетика: газетный broadsheet, двойная разделительная линия снизу. */

interface PageMastProps {
  title: string;
  count?: string | number;
  subtitle?: string;
  className?: string;
}

const monthShort = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const dows = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const GENESIS = new Date(2025, 11, 1);

function makeStamp() {
  const now = new Date();
  const d = String(now.getDate()).padStart(2, '0');
  const m = monthShort[now.getMonth()];
  const y = String(now.getFullYear()).slice(2);
  const dow = dows[now.getDay()];
  const edition = Math.floor((now.getTime() - GENESIS.getTime()) / 86_400_000) + 1;
  return { date: `${dow} · ${d} ${m} ${y}`, edition: `№${edition}` };
}

export function PageMast({ title, count, subtitle, className }: PageMastProps) {
  // hydrate-safely: render with empty stamp on server, fill in on mount
  const [stamp, setStamp] = React.useState<{ date: string; edition: string } | null>(null);
  React.useEffect(() => setStamp(makeStamp()), []);

  return (
    <header
      className={cn(
        'grid grid-cols-1 md:grid-cols-[1fr_auto] items-end gap-8 pb-5 mb-9 ' +
          'border-b-[4px] border-double border-hairline-bold',
        className
      )}
    >
      <h1 className="m-0 font-display italic font-semibold text-[clamp(40px,5vw,72px)] leading-[0.95] tracking-[-0.02em] text-ink">
        {title}
        {count !== undefined && (
          <span className="not-italic font-normal text-ink-3 text-[0.55em] tracking-[-0.005em] ml-4 align-[0.18em]">
            №{count}
          </span>
        )}
      </h1>
      <div className="font-mono text-[11px] text-ink-2 leading-[1.55] tracking-[0.06em] uppercase md:text-right">
        {subtitle && <><strong className="text-ink font-medium">{subtitle}</strong><br /></>}
        <span className="text-vermilion">●</span>{' '}
        {stamp ? <>вып. {stamp.edition} · {stamp.date}</> : <>—</>}
      </div>
    </header>
  );
}
