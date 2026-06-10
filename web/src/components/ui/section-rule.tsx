import { cn } from '@/lib/utils';

/* Section heading с § маркером в стиле broadsheet. */
export function SectionRule({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h2
      className={cn(
        'relative font-display italic font-medium text-[28px] leading-tight tracking-[-0.01em] ' +
          'mt-12 mb-4 pb-2 border-b border-hairline text-ink',
        className
      )}
    >
      <span className="absolute -left-[22px] text-vermilion not-italic font-normal">§</span>
      {children}
    </h2>
  );
}
