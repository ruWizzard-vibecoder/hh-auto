'use client';

import * as React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { bulkApprove, bulkNoLetter, bulkReject } from './api';

export function BulkBar() {
  const qc = useQueryClient();
  const [approveT, setApproveT] = React.useState(70);
  const [noLetterT, setNoLetterT] = React.useState(60);
  const [rejectT, setRejectT] = React.useState(40);

  function makeMutation(
    fn: (threshold: number) => Promise<{ updated: number }>,
    confirmMsg: (n: number) => string,
    successMsg: (n: number) => string,
    errorMsg: string,
  ) {
    return useMutation({ // eslint-disable-line react-hooks/rules-of-hooks
      mutationFn: ({ threshold }: { threshold: number }) => fn(threshold),
      onSuccess: ({ updated }) => {
        toast.success(successMsg(updated));
        qc.invalidateQueries({ queryKey: ['letters'] });
        qc.invalidateQueries({ queryKey: ['pending-letters'] });
      },
      onError: () => toast.error(errorMsg),
    });
  }
  // (We accept the lint disable above — bulk handlers are stable and unconditional.)

  const approveMut = makeMutation(
    bulkApprove,
    (n) => `Одобрить ${n} писем с оценкой ≥ порога?`,
    (n) => `одобрено ${n} писем`,
    'не удалось одобрить пачкой',
  );
  const noLetterMut = makeMutation(
    bulkNoLetter,
    (n) => `Откликнуться без письма на ${n} вакансий с оценкой ниже порога?`,
    (n) => `${n} помечено «без письма»`,
    'не удалось пометить «без письма»',
  );
  const rejectMut = makeMutation(
    bulkReject,
    (n) => `Отклонить ${n} писем с оценкой ниже порога?`,
    (n) => `отклонено ${n} писем`,
    'не удалось отклонить пачкой',
  );

  const busy = approveMut.isPending || noLetterMut.isPending || rejectMut.isPending;

  return (
    <div className="flex flex-wrap items-center gap-5 px-5 py-3.5 mb-6 bg-paper-sink border-y border-hairline">
      <ThresholdForm
        label="Одобрить ≥"
        value={approveT}
        onChange={setApproveT}
        variant="primary"
        disabled={busy}
        onSubmit={(t) => {
          if (confirm(`Одобрить все письма с оценкой ≥ ${t}%?`)) {
            approveMut.mutate({ threshold: t });
          }
        }}
      />
      <ThresholdForm
        label="Без письма <"
        value={noLetterT}
        onChange={setNoLetterT}
        variant="outline"
        disabled={busy}
        onSubmit={(t) => {
          if (confirm(`Отклик без письма на все с оценкой < ${t}%?`)) {
            noLetterMut.mutate({ threshold: t });
          }
        }}
      />
      <ThresholdForm
        label="Отклонить <"
        value={rejectT}
        onChange={setRejectT}
        variant="destructive"
        disabled={busy}
        onSubmit={(t) => {
          if (confirm(`Отклонить все с оценкой < ${t}%?`)) {
            rejectMut.mutate({ threshold: t });
          }
        }}
      />
    </div>
  );
}

function ThresholdForm({
  label,
  value,
  onChange,
  onSubmit,
  variant,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  onSubmit: (n: number) => void;
  variant: 'primary' | 'outline' | 'destructive';
  disabled: boolean;
}) {
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
      }}
    >
      <label className="font-mono text-[10.5px] tracking-[0.14em] uppercase text-ink-3 m-0 normal-case-keep">
        {label}
      </label>
      <Input
        type="number"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-7 w-[68px] px-2 py-1 text-[12px]"
      />
      <Button type="submit" variant={variant} size="sm" disabled={disabled}>
        %
      </Button>
    </form>
  );
}
