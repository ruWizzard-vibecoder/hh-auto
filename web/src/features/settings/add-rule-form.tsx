'use client';

import * as React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';

export function AddRuleForm() {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [ruleType, setRuleType] = React.useState<'blacklist' | 'whitelist'>('blacklist');
  const [matchType, setMatchType] = React.useState<'company_name' | 'company_id' | 'keyword_in_title'>('company_name');
  const [matchValue, setMatchValue] = React.useState('');
  const [reason, setReason] = React.useState('');

  const mut = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.set('rule_type', ruleType);
      fd.set('match_type', matchType);
      fd.set('match_value', matchValue);
      fd.set('reason', reason);
      return api.post('api/settings/rules', { body: fd }).json();
    },
    onSuccess: () => {
      toast.success('правило добавлено');
      qc.invalidateQueries({ queryKey: ['settings'] });
      setMatchValue('');
      setReason('');
      setOpen(false);
    },
    onError: () => toast.error('не удалось добавить правило'),
  });

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="mt-4">
        <Plus className="size-4" /> Добавить правило
      </Button>
    );
  }

  return (
    <form
      className="mt-4 p-4 border border-hairline-bold bg-paper-sink"
      onSubmit={(e) => {
        e.preventDefault();
        if (matchValue.trim()) mut.mutate();
      }}
    >
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3.5">
        <Field label="Тип">
          <select
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value as typeof ruleType)}
            className="h-9 w-full bg-paper text-ink border border-hairline-bold px-3 py-2 text-[14px] focus:outline-none focus:border-vermilion"
          >
            <option value="blacklist">Чёрный список</option>
            <option value="whitelist">Белый список</option>
          </select>
        </Field>
        <Field label="Совпадение">
          <select
            value={matchType}
            onChange={(e) => setMatchType(e.target.value as typeof matchType)}
            className="h-9 w-full bg-paper text-ink border border-hairline-bold px-3 py-2 text-[14px] focus:outline-none focus:border-vermilion"
          >
            <option value="company_name">Название компании</option>
            <option value="company_id">ID компании</option>
            <option value="keyword_in_title">Слово в названии</option>
          </select>
        </Field>
        <Field label="Значение">
          <Input
            value={matchValue}
            onChange={(e) => setMatchValue(e.target.value)}
            required
            className="bg-paper"
          />
        </Field>
        <Field label="Причина">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="bg-paper"
          />
        </Field>
      </div>
      <div className="flex gap-2 mt-4">
        <Button type="submit" variant="primary" size="sm" disabled={mut.isPending || !matchValue.trim()}>
          {mut.isPending ? '…' : 'Добавить'}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)} disabled={mut.isPending}>
          Отмена
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block font-sans text-[11px] font-medium text-ink-2 tracking-[0.1em] uppercase">
      {label}
      <div className="mt-1.5 normal-case tracking-normal">{children}</div>
    </label>
  );
}
