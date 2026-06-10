import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-[2px] border px-2 py-[2px] text-[10.5px] font-mono font-medium uppercase tracking-[0.08em] leading-[1.6] whitespace-nowrap',
  {
    variants: {
      variant: {
        default: 'border-hairline bg-paper-rise text-ink-2',
        // status badges
        pending:  'border-gold-dim bg-gold-soft text-gold',
        scored:   'border-gold-dim bg-gold-soft text-gold',
        queued:   'border-gold-dim bg-gold-soft text-gold',
        approved: 'border-indigo-dim bg-indigo-soft text-indigo',
        sent:     'border-indigo-dim bg-indigo-soft text-indigo',
        viewed:   'border-indigo-dim bg-indigo-soft text-indigo',
        applied:  'border-indigo-dim bg-indigo-soft text-indigo',
        invited:  'border-sage-dim bg-sage-soft text-sage font-semibold',
        rejected: 'border-brick-dim bg-brick-soft text-brick',
        declined: 'border-brick-dim bg-brick-soft text-brick',
        skipped:  'border-brick-dim bg-brick-soft text-brick',
        failed:   'border-brick-dim bg-brick-soft text-brick',
        archived: 'border-brick-dim bg-brick-soft text-brick',
        no_letter: 'border-hairline-bold bg-paper-edge text-ink-2',
        // employment kinds
        parttime: 'border-vermilion-dim bg-vermilion-soft text-vermilion',
        project:  'border-gold-dim bg-gold-soft text-gold',
        // misc
        resume:   'border-ink-4 bg-paper-edge text-ink font-sans normal-case tracking-[0.02em] text-[11px]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
