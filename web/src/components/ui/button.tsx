import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] font-sans text-[13px] font-medium tracking-[0.04em] transition-all duration-150 ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-vermilion focus-visible:ring-offset-2 focus-visible:ring-offset-paper ' +
    'disabled:pointer-events-none disabled:opacity-50 active:translate-y-px',
  {
    variants: {
      variant: {
        default:
          'border border-hairline-bold bg-transparent text-ink hover:border-ink-2 hover:bg-paper-edge',
        primary:
          'border border-vermilion bg-vermilion text-paper font-semibold hover:bg-vermilion-dim hover:border-vermilion-dim hover:text-ink',
        secondary:
          'border border-hairline-bold bg-paper-edge text-ink hover:bg-paper-rise',
        outline:
          'border border-hairline-bold bg-transparent text-ink hover:border-ink-2 hover:bg-paper-edge',
        ghost: 'border border-transparent bg-transparent text-ink-2 hover:bg-paper-edge hover:text-ink',
        destructive:
          'border border-brick text-brick bg-transparent hover:bg-brick-soft hover:text-ink',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-7 px-3 text-[11.5px]',
        lg: 'h-11 px-6 text-[14px]',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  )
);
Button.displayName = 'Button';

export { Button, buttonVariants };
