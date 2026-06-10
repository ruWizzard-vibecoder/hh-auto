import * as React from 'react';
import { cn } from '@/lib/utils';

/* "Стат-фигура" — большая italic-цифра в editorial-стиле. */

const accentClass: Record<string, string> = {
  default: 'text-ink',
  hot:     'text-vermilion',
  gold:    'text-gold',
  sage:    'text-sage',
  indigo:  'text-indigo',
};

interface FigureProps {
  num: string;       // small "01" prefix in top-right
  value: React.ReactNode;
  label: string;
  trend?: React.ReactNode;
  accent?: keyof typeof accentClass;
  className?: string;
}

export function Figure({ num, value, label, trend, accent = 'default', className }: FigureProps) {
  return (
    <div
      className={cn(
        'relative flex flex-col gap-1.5 px-6 py-5 border-r border-hairline last:border-r-0 ' +
          'transition-colors hover:bg-gradient-to-b hover:from-transparent hover:to-vermilion-soft',
        className
      )}
    >
      <span className="absolute top-3 right-4 font-mono text-[10px] tracking-[0.16em] text-ink-4">
        {num}
      </span>
      <span
        className={cn(
          'font-display italic font-medium text-[52px] leading-none tracking-[-0.03em] num',
          accentClass[accent]
        )}
      >
        {value}
      </span>
      <span className="font-sans text-[11.5px] font-medium uppercase tracking-[0.16em] text-ink-3">
        {label}
      </span>
      {trend && (
        <span className="font-mono text-[11px] text-ink-2 tracking-[0.02em]">
          {trend}
        </span>
      )}
    </div>
  );
}

export function FigureGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <section
      className={cn(
        'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 border-t border-b border-hairline mb-9',
        className
      )}
    >
      {children}
    </section>
  );
}
