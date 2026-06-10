import * as React from 'react';
import { Sidebar } from './sidebar';

/* Главная компоновка приложения: sidebar + контент. */
export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative z-[2] grid grid-cols-[220px_1fr] min-h-screen">
      <Sidebar />
      <main className="min-w-0 px-[clamp(20px,3vw,48px)] py-8 pb-20">
        <div className="max-w-[1480px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
