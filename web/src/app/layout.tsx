import type { Metadata } from 'next';
import { EB_Garamond, Inter, JetBrains_Mono } from 'next/font/google';
import { Providers } from '@/components/providers';
import { Toaster } from 'sonner';
import './globals.css';

const garamond = EB_Garamond({
  variable: '--font-display',
  subsets: ['latin', 'latin-ext', 'cyrillic', 'cyrillic-ext'],
  weight: ['400', '500', '600', '700', '800'],
  style: ['normal', 'italic'],
  display: 'swap',
});

const inter = Inter({
  variable: '--font-sans',
  subsets: ['latin', 'latin-ext', 'cyrillic', 'cyrillic-ext'],
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
});

const jetbrains = JetBrains_Mono({
  variable: '--font-mono',
  subsets: ['latin', 'latin-ext', 'cyrillic'],
  weight: ['400', '500', '600'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'hh-auto · ИЗДАНИЕ',
  description: 'Operations console for the job hunt',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="ru"
      suppressHydrationWarning
      className={`${garamond.variable} ${inter.variable} ${jetbrains.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
        <Toaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: 'var(--color-paper-sink)',
              color: 'var(--color-ink)',
              border: '1px solid var(--color-hairline-bold)',
              borderLeft: '3px solid var(--color-vermilion)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              letterSpacing: '0.04em',
              borderRadius: '2px',
            },
          }}
        />
      </body>
    </html>
  );
}
