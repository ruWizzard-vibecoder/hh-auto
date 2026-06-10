'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Play, Send, RotateCw, Ban, X, RefreshCw, Pencil, Plus } from 'lucide-react';
import { PageMast } from '@/components/ui/page-mast';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api, getJson } from '@/lib/api';
import { cn } from '@/lib/utils';
import { ProfileDialog, type ExistingProfile } from './profile-dialog';
import { AddRuleForm } from './add-rule-form';

interface Profile {
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
interface Rule {
  id: number;
  rule_type: 'blacklist' | 'whitelist';
  match_type: string;
  match_value: string;
  reason: string | null;
}
interface Resume {
  id: number;
  hh_id: string;
  title: string;
  short_name: string;
  is_primary: boolean;
  visibility_status: 'visible' | 'hidden' | string;
  last_rotated_at: string | null;
  rotation_priority: number;
}
interface SettingsData {
  is_authenticated: boolean;
  profiles: Profile[];
  rules: Rule[];
  resumes: Resume[];
}

export function SettingsView() {
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getJson<SettingsData>('api/settings.json'),
  });

  return (
    <>
      <PageMast title="Настройки" count="07" subtitle="МАШИННОЕ ОТДЕЛЕНИЕ" />

      {isLoading && !data && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка настроек  ···
        </p>
      )}

      {data && (
        <>
          <AuthPanel ok={data.is_authenticated} />
          <PipelinePanel />
          <ProfilesPanel profiles={data.profiles} />
          <RulesPanel rules={data.rules} />
          <ResumesPanel resumes={data.resumes} />
        </>
      )}
    </>
  );
}

/* ─── Panels ─────────────────────────────────────────────────────── */

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="border-t-2 border-t-hairline-bold border-b border-b-hairline py-6 mt-1">
      <header className="pb-3 mb-5 border-b border-hairline">
        <strong className="block font-display italic font-medium text-[22px] tracking-[-0.005em] text-ink">
          {title}
        </strong>
      </header>
      {children}
    </article>
  );
}

function AuthPanel({ ok }: { ok: boolean }) {
  return (
    <Panel title="Авторизация hh.ru">
      <p className="text-ink-2">
        Статус:{' '}
        {ok ? <Badge variant="approved">подключено</Badge> : <Badge variant="declined">не подключено</Badge>}
      </p>
      <p className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3 mt-3">
        управление логином — через REST API или старый UI; здесь только статус
      </p>
    </Panel>
  );
}

function PipelinePanel() {
  const [msg, setMsg] = React.useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const buttons: Array<{ key: string; label: string; variant: 'primary' | 'secondary' | 'outline'; icon: React.ReactNode; path: string }> = [
    { key: 'search',    label: 'Запустить поиск',           variant: 'primary',   icon: <Play className="size-4" />,     path: 'api/pipeline/search' },
    { key: 'apply',     label: 'Отправить отклики',         variant: 'secondary', icon: <Send className="size-4" />,     path: 'api/pipeline/apply' },
    { key: 'status',    label: 'Проверить статусы',         variant: 'outline',   icon: <RotateCw className="size-4" />, path: 'api/pipeline/status-check' },
    { key: 'archive',   label: 'Проверить архивность',      variant: 'outline',   icon: <Ban className="size-4" />,      path: 'api/pipeline/archive-check' },
  ];
  const trigger = async (path: string, label: string) => {
    try {
      await api.post(path);
      setMsg({ kind: 'ok', text: `${label}: запущено` });
      toast.success(`${label}: запущено`);
    } catch {
      setMsg({ kind: 'err', text: `${label}: ошибка` });
      toast.error(`${label}: ошибка`);
    } finally {
      setTimeout(() => setMsg(null), 5000);
    }
  };
  return (
    <Panel title="Управление пайплайном">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {buttons.map((b) => (
          <Button key={b.key} variant={b.variant} onClick={() => trigger(b.path, b.label)}>
            {b.icon} {b.label}
          </Button>
        ))}
      </div>
      {msg && (
        <p
          className={cn(
            'font-mono text-[12px] uppercase tracking-[0.08em] mt-4 py-2.5 px-3.5 border-l-[3px]',
            msg.kind === 'ok'
              ? 'text-sage bg-sage-soft border-l-sage'
              : 'text-brick bg-brick-soft border-l-brick'
          )}
        >
          {msg.kind === 'ok' ? '✓' : '⚠'} {msg.text}
        </p>
      )}
    </Panel>
  );
}

function ProfilesPanel({ profiles }: { profiles: Profile[] }) {
  const [dialogState, setDialogState] = React.useState<
    | { open: true; mode: 'create' }
    | { open: true; mode: { mode: 'edit'; id: number }; existing: ExistingProfile }
    | { open: false }
  >({ open: false });

  return (
    <Panel title={`Поисковые профили · ${profiles.length}`}>
      <ul className="list-none p-0 m-0 divide-y divide-hairline border-t border-hairline">
        {profiles.map((p) => (
          <li key={p.id} className="py-3.5 flex items-center justify-between gap-3 flex-wrap group">
            <div className="min-w-0 flex-1">
              <span className="font-sans font-medium text-[15px] text-ink">{p.name}</span>
              <span className="ml-2.5">
                {p.is_active ? (
                  <Badge variant="approved">активен</Badge>
                ) : (
                  <Badge variant="failed">отключён</Badge>
                )}
              </span>
              {p.search_text && (
                <div className="font-mono text-[11.5px] text-ink-3 mt-1 tracking-[0.02em]">
                  «{p.search_text}»
                  {p.area_id && <span className="ml-2">area={p.area_id}</span>}
                  {p.experience && <span className="ml-2">exp={p.experience}</span>}
                  {p.employment && <span className="ml-2">emp={p.employment}</span>}
                  {p.schedule && <span className="ml-2">sched={p.schedule}</span>}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                мин. оценка {(p.min_relevance_score * 100).toFixed(0)}%
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setDialogState({
                    open: true,
                    mode: { mode: 'edit', id: p.id },
                    existing: p,
                  })
                }
              >
                <Pencil className="size-3.5" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        size="sm"
        className="mt-4"
        onClick={() => setDialogState({ open: true, mode: 'create' })}
      >
        <Plus className="size-4" /> Новый профиль
      </Button>

      <ProfileDialog
        open={dialogState.open}
        onOpenChange={(v) => !v && setDialogState({ open: false })}
        mode={dialogState.open && dialogState.mode !== 'create' ? dialogState.mode : 'create'}
        existing={dialogState.open && 'existing' in dialogState ? dialogState.existing : undefined}
      />
    </Panel>
  );
}

function RulesPanel({ rules }: { rules: Rule[] }) {
  const qc = useQueryClient();
  const delMut = useMutation({
    mutationFn: (id: number) => api.delete(`api/settings/rules/${id}`),
    onSuccess: () => {
      toast.success('правило удалено');
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: () => toast.error('не удалось удалить'),
  });

  return (
    <Panel title={`Правила компаний · ${rules.length}`}>
      {rules.length === 0 ? (
        <p className="text-ink-3 font-mono text-[11px] uppercase tracking-[0.1em]">правил пока нет</p>
      ) : (
        <div className="border-y-2 border-hairline-bold overflow-x-auto">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr>
                {['Тип', 'Совпадение', 'Значение', 'Причина', ''].map((h) => (
                  <th key={h} className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="group hover:bg-paper-edge">
                  <td className="p-2.5 px-3 border-b border-hairline group-hover:shadow-[inset_2px_0_0_var(--color-vermilion)]">
                    <Badge variant={r.rule_type === 'blacklist' ? 'declined' : 'approved'}>
                      {r.rule_type}
                    </Badge>
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline">
                    <small className="text-ink-3">{r.match_type}</small>
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline text-ink">{r.match_value}</td>
                  <td className="p-2.5 px-3 border-b border-hairline text-ink-2 text-[12.5px]">{r.reason || '—'}</td>
                  <td className="p-2.5 px-3 border-b border-hairline">
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => {
                        if (confirm(`Удалить правило для «${r.match_value}»?`)) delMut.mutate(r.id);
                      }}
                      disabled={delMut.isPending}
                    >
                      <X className="size-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AddRuleForm />
    </Panel>
  );
}

function ResumesPanel({ resumes }: { resumes: Resume[] }) {
  const qc = useQueryClient();
  const seedMut = useMutation({
    mutationFn: () => api.post('api/resumes/seed').json(),
    onSuccess: () => {
      toast.success('ключевые слова обновляются');
      setTimeout(() => qc.invalidateQueries({ queryKey: ['settings'] }), 2000);
    },
    onError: () => toast.error('не удалось обновить'),
  });
  const rotateMut = useMutation({
    mutationFn: () => api.post('api/resumes/rotate').json(),
    onSuccess: () => {
      toast.success('ротация запущена');
      setTimeout(() => qc.invalidateQueries({ queryKey: ['settings'] }), 2000);
    },
    onError: () => toast.error('не удалось запустить ротацию'),
  });

  return (
    <Panel title={`Резюме · ${resumes.length}`}>
      {resumes.length === 0 ? (
        <p className="text-ink-3 font-mono text-[11px] uppercase tracking-[0.1em]">резюме не найдены</p>
      ) : (
        <>
          <div className="border-y-2 border-hairline-bold overflow-x-auto mb-4">
            <table className="w-full border-collapse text-[13.5px]">
              <thead>
                <tr>
                  {['Название', 'Метка', 'hh_id', 'Основное', 'Видимость', 'Последняя ротация'].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resumes.map((r) => (
                  <tr key={r.id} className="hover:bg-paper-edge">
                    <td className="p-2.5 px-3 border-b border-hairline text-ink">{r.title}</td>
                    <td className="p-2.5 px-3 border-b border-hairline">
                      <Badge variant="resume">{r.short_name}</Badge>
                    </td>
                    <td className="p-2.5 px-3 border-b border-hairline">
                      <a href={`https://hh.ru/resume/${r.hh_id}`} target="_blank" rel="noreferrer" className="text-ink-3 font-mono text-[11.5px] border-b border-dotted border-ink-4 hover:text-vermilion">
                        {r.hh_id.slice(0, 12)}…
                      </a>
                    </td>
                    <td className="p-2.5 px-3 border-b border-hairline">
                      {r.is_primary ? <Badge variant="invited">★</Badge> : '—'}
                    </td>
                    <td className="p-2.5 px-3 border-b border-hairline">
                      <Badge variant={r.visibility_status === 'visible' ? 'approved' : r.visibility_status === 'hidden' ? 'declined' : 'pending'}>
                        {r.visibility_status}
                      </Badge>
                    </td>
                    <td className="p-2.5 px-3 border-b border-hairline num text-ink-2">
                      {r.last_rotated_at ? formatRotated(r.last_rotated_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <Button variant="outline" onClick={() => seedMut.mutate()} disabled={seedMut.isPending}>
              <RefreshCw className="size-4" /> Обновить ключевые слова
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                if (confirm('Запустить ротацию резюме?')) rotateMut.mutate();
              }}
              disabled={rotateMut.isPending}
            >
              <RotateCw className="size-4" /> Ротация сейчас
            </Button>
          </div>
        </>
      )}
    </Panel>
  );
}

function formatRotated(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
