'use client';

import * as React from 'react';
import { Dialog } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialText: string;
  title: string;
  company: string | null;
  onSave: (newText: string) => void;
  saving: boolean;
}

export function EditDialog({ open, onOpenChange, initialText, title, company, onSave, saving }: Props) {
  const [text, setText] = React.useState(initialText);

  // Reset text when opening with a new letter
  React.useEffect(() => {
    if (open) setText(initialText);
  }, [open, initialText]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop />
        <Dialog.Popup className="max-h-[90vh] flex flex-col">
          <div className="px-7 pt-6 pb-4 border-b border-hairline">
            <Dialog.Title>Редактирование письма</Dialog.Title>
            <Dialog.Description>
              {title}
              {company && (
                <>
                  <span className="text-ink-4 mx-1.5">·</span>
                  {company}
                </>
              )}
            </Dialog.Description>
          </div>

          <div className="px-7 py-4 overflow-y-auto flex-1">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={14}
              className="w-full bg-paper-sink border border-hairline-bold border-l-[3px] border-l-gold text-ink p-4 font-mono text-[13px] leading-[1.75] resize-y focus:outline-none focus:border-vermilion focus:border-l-vermilion min-h-[260px]"
              autoFocus
            />
            <p className="font-mono text-[10.5px] tracking-[0.08em] uppercase text-ink-3 mt-3">
              сохранить = одобрить и убрать из очереди
            </p>
          </div>

          <div className="px-7 py-4 border-t border-hairline flex justify-end gap-2.5">
            <Dialog.Close
              render={
                <Button variant="outline" type="button" disabled={saving}>
                  Отмена
                </Button>
              }
            />
            <Button
              variant="primary"
              type="button"
              disabled={saving || text.trim().length === 0}
              onClick={() => onSave(text)}
            >
              {saving ? 'сохраняется…' : 'Сохранить и одобрить'}
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
