'use client';

import * as React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Dialog } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';

type Mode = 'create' | { mode: 'edit'; id: number };

interface ProfileFields {
  name: string;
  search_text: string;
  area_id: string;
  min_relevance_score: string;
  resume_id: string;
  experience: string;
  employment: string;
  schedule: string;
  salary_from: string;
  salary_to: string;
  only_with_salary: boolean;
  is_active: boolean;
}

const EMPTY: ProfileFields = {
  name: '',
  search_text: '',
  area_id: '',
  min_relevance_score: '0.5',
  resume_id: '',
  experience: '',
  employment: '',
  schedule: '',
  salary_from: '',
  salary_to: '',
  only_with_salary: false,
  is_active: true,
};

export interface ExistingProfile {
  id: number;
  name: string;
  search_text: string | null;
  area_id: number | null;
  min_relevance_score: number;
  resume_id: string | null;
  experience: string | null;
  employment: string | null;
  schedule: string | null;
  salary_from: number | null;
  salary_to: number | null;
  only_with_salary: boolean;
  is_active: boolean;
}

function fromProfile(p: ExistingProfile): ProfileFields {
  return {
    name: p.name,
    search_text: p.search_text ?? '',
    area_id: p.area_id?.toString() ?? '',
    min_relevance_score: p.min_relevance_score?.toString() ?? '0.5',
    resume_id: p.resume_id ?? '',
    experience: p.experience ?? '',
    employment: p.employment ?? '',
    schedule: p.schedule ?? '',
    salary_from: p.salary_from?.toString() ?? '',
    salary_to: p.salary_to?.toString() ?? '',
    only_with_salary: p.only_with_salary,
    is_active: p.is_active,
  };
}

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  mode: Mode;
  existing?: ExistingProfile;
}

export function ProfileDialog({ open, onOpenChange, mode, existing }: Props) {
  const qc = useQueryClient();
  const isEdit = mode !== 'create';
  const [fields, setFields] = React.useState<ProfileFields>(EMPTY);

  React.useEffect(() => {
    if (open) {
      if (existing) setFields(fromProfile(existing));
      else setFields(EMPTY);
    }
  }, [open, existing]);

  const mut = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.set('name', fields.name);
      fd.set('search_text', fields.search_text);
      if (fields.area_id) fd.set('area_id', fields.area_id);
      fd.set('min_relevance_score', fields.min_relevance_score);
      fd.set('resume_id', fields.resume_id);
      fd.set('experience', fields.experience);
      fd.set('employment', fields.employment);
      fd.set('schedule', fields.schedule);
      if (fields.salary_from) fd.set('salary_from', fields.salary_from);
      if (fields.salary_to) fd.set('salary_to', fields.salary_to);
      if (fields.only_with_salary) fd.set('only_with_salary', 'true');
      if (isEdit) {
        fd.set('is_active', fields.is_active ? 'true' : 'false');
        return api.put(`api/settings/profiles/${(mode as { id: number }).id}`, { body: fd }).json();
      }
      return api.post('api/settings/profiles', { body: fd }).json();
    },
    onSuccess: () => {
      toast.success(isEdit ? 'профиль обновлён' : 'профиль создан');
      qc.invalidateQueries({ queryKey: ['settings'] });
      onOpenChange(false);
    },
    onError: () => toast.error('не удалось сохранить'),
  });

  const updateField = <K extends keyof ProfileFields>(k: K, v: ProfileFields[K]) =>
    setFields((p) => ({ ...p, [k]: v }));

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop />
        <Dialog.Popup className="max-w-[800px] max-h-[90vh] flex flex-col">
          <div className="px-7 pt-6 pb-4 border-b border-hairline">
            <Dialog.Title>{isEdit ? 'Редактирование профиля' : 'Новый поисковый профиль'}</Dialog.Title>
            <Dialog.Description>фильтр для пайплайна поиска</Dialog.Description>
          </div>

          <form
            className="px-7 py-5 overflow-y-auto flex-1 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              mut.mutate();
            }}
          >
            <Field label="Название">
              <Input
                value={fields.name}
                onChange={(e) => updateField('name', e.target.value)}
                required
              />
            </Field>
            <Field label="Поисковый запрос">
              <Input
                value={fields.search_text}
                onChange={(e) => updateField('search_text', e.target.value)}
                placeholder="AI инженер Python"
              />
            </Field>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Field label="Регион (ID)" hint="2 = СПб, 1 = МСК">
                <Input
                  type="number"
                  value={fields.area_id}
                  onChange={(e) => updateField('area_id', e.target.value)}
                />
              </Field>
              <Field label="Мин. оценка" hint="0.0–1.0">
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={fields.min_relevance_score}
                  onChange={(e) => updateField('min_relevance_score', e.target.value)}
                />
              </Field>
              <Field label="ID резюме">
                <Input
                  value={fields.resume_id}
                  onChange={(e) => updateField('resume_id', e.target.value)}
                />
              </Field>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Field label="Опыт">
                <Select value={fields.experience} onChange={(v) => updateField('experience', v)}>
                  <option value="">Любой</option>
                  <option value="noExperience">Без опыта</option>
                  <option value="between1And3">1–3 года</option>
                  <option value="between3And6">3–6 лет</option>
                  <option value="moreThan6">6+ лет</option>
                </Select>
              </Field>
              <Field label="Занятость">
                <Select value={fields.employment} onChange={(v) => updateField('employment', v)}>
                  <option value="">Любая</option>
                  <option value="full">Полная</option>
                  <option value="part">Частичная</option>
                  <option value="project">Проектная</option>
                  <option value="probation">Стажировка</option>
                </Select>
              </Field>
              <Field label="График">
                <Select value={fields.schedule} onChange={(v) => updateField('schedule', v)}>
                  <option value="">Любой</option>
                  <option value="remote">Удалённая</option>
                  <option value="fullDay">Полный день</option>
                  <option value="flexible">Гибкий</option>
                </Select>
              </Field>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <Field label="ЗП от">
                <Input
                  type="number"
                  value={fields.salary_from}
                  onChange={(e) => updateField('salary_from', e.target.value)}
                  placeholder="руб."
                />
              </Field>
              <Field label="ЗП до">
                <Input
                  type="number"
                  value={fields.salary_to}
                  onChange={(e) => updateField('salary_to', e.target.value)}
                  placeholder="руб."
                />
              </Field>
              <Checkbox
                checked={fields.only_with_salary}
                onChange={(v) => updateField('only_with_salary', v)}
                label="Только с ЗП"
              />
            </div>

            {isEdit && (
              <Checkbox
                checked={fields.is_active}
                onChange={(v) => updateField('is_active', v)}
                label="Профиль активен"
              />
            )}
          </form>

          <div className="px-7 py-4 border-t border-hairline flex justify-end gap-2.5">
            <Dialog.Close
              render={
                <Button variant="outline" type="button" disabled={mut.isPending}>
                  Отмена
                </Button>
              }
            />
            <Button
              variant="primary"
              type="button"
              disabled={mut.isPending || !fields.name.trim()}
              onClick={() => mut.mutate()}
            >
              {mut.isPending ? 'сохраняется…' : isEdit ? 'Сохранить' : 'Создать'}
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block font-sans text-[11.5px] font-medium text-ink-2 tracking-[0.1em] uppercase">
      {label}
      {hint && <span className="ml-2 text-ink-4 tracking-normal lowercase">({hint})</span>}
      <div className="mt-1.5 normal-case tracking-normal">{children}</div>
    </label>
  );
}

function Select({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full bg-paper-sink text-ink border border-hairline-bold rounded-[2px] px-3 py-2 text-[14px] focus:outline-none focus:border-vermilion focus:bg-paper transition-colors"
    >
      {children}
    </select>
  );
}

function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="inline-flex items-center gap-2 cursor-pointer font-sans text-[13px] text-ink normal-case tracking-normal font-normal">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 accent-vermilion"
      />
      {label}
    </label>
  );
}
