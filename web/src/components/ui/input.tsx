import * as React from 'react';
import { cn } from '@/lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-9 w-full rounded-[2px] border border-hairline-bold bg-paper-sink px-3 py-2 text-[14px] text-ink ' +
          'placeholder:text-ink-3 focus:outline-none focus:border-vermilion focus:bg-paper ' +
          'disabled:cursor-not-allowed disabled:opacity-50 transition-colors',
        className
      )}
      {...props}
    />
  )
);
Input.displayName = 'Input';
