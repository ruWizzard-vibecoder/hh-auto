'use client';

import * as React from 'react';
import { Dialog as BaseDialog } from '@base-ui-components/react/dialog';
import { cn } from '@/lib/utils';

const Root = BaseDialog.Root;
const Trigger = BaseDialog.Trigger;
const Close = BaseDialog.Close;
const Portal = BaseDialog.Portal;

const Backdrop = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof BaseDialog.Backdrop>
>(({ className, ...props }, ref) => (
  <BaseDialog.Backdrop
    ref={ref}
    className={cn(
      'fixed inset-0 z-50 bg-black/70 backdrop-blur-sm ' +
        'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 ' +
        'transition-opacity duration-200',
      className
    )}
    {...props}
  />
));
Backdrop.displayName = 'DialogBackdrop';

const Popup = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof BaseDialog.Popup>
>(({ className, children, ...props }, ref) => (
  <BaseDialog.Popup
    ref={ref}
    className={cn(
      'fixed left-1/2 top-1/2 z-50 w-full max-w-[760px] -translate-x-1/2 -translate-y-1/2 ' +
        'bg-paper-rise border border-hairline-bold border-l-[3px] border-l-vermilion ' +
        'shadow-[0_24px_80px_rgba(0,0,0,0.6)] ' +
        'data-[starting-style]:opacity-0 data-[starting-style]:scale-95 ' +
        'data-[ending-style]:opacity-0 data-[ending-style]:scale-95 ' +
        'transition-all duration-200',
      className
    )}
    {...props}
  >
    {children}
  </BaseDialog.Popup>
));
Popup.displayName = 'DialogPopup';

const Title = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentPropsWithoutRef<typeof BaseDialog.Title>
>(({ className, ...props }, ref) => (
  <BaseDialog.Title
    ref={ref}
    className={cn(
      'font-display italic font-semibold text-[26px] leading-tight tracking-[-0.005em] text-ink',
      className
    )}
    {...props}
  />
));
Title.displayName = 'DialogTitle';

const Description = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentPropsWithoutRef<typeof BaseDialog.Description>
>(({ className, ...props }, ref) => (
  <BaseDialog.Description
    ref={ref}
    className={cn(
      'font-mono text-[11.5px] tracking-[0.04em] text-ink-2 mt-1',
      className
    )}
    {...props}
  />
));
Description.displayName = 'DialogDescription';

export const Dialog = {
  Root,
  Trigger,
  Portal,
  Backdrop,
  Popup,
  Title,
  Description,
  Close,
};
