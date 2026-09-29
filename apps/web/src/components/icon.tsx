import type { SVGProps } from 'react';

const paths = {
  home: 'm3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
  brand: 'M12 3 3 7l9 4 9-4-9-4ZM3 12l9 4 9-4M3 17l9 4 9-4',
  document: 'M14 2H5a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V8l-6-6Zm0 0v6h6M8 13h8M8 17h5',
  campaign: 'M4 5h16v14H4V5Zm4-3v6m8-6v6M4 10h16M8 14h2m4 0h2m-8 3h2',
  publish: 'm22 2-7 20-4-9-9-4L22 2ZM11 13 22 2',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
  chart: 'M4 3v18h17M8 16v-5m5 5V7m5 9V4',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 2 5-2 2-1 4-4 3-3-2-4-1-3-4 2-3 1-4 2-4Z',
  'arrow-right': 'M4 12h16m-6-6 6 6-6 6',
  plus: 'M12 5v14M5 12h14',
  check: 'm5 12 4 4L19 6',
  'chevron-right': 'm9 5 7 7-7 7',
  logout: 'M9 4H4v16h5m6-14 6 6-6 6M8 12h13',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  'chevron-down': 'm5 9 7 7 7-7',
  search: 'M20 20l-5-5M17 10A7 7 0 1 1 3 10a7 7 0 0 1 14 0Z',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
  sparkles: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6',
  mail: 'M3 5h18v14H3V5Zm0 1 9 7 9-7',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  'eye-off': 'm3 3 18 18M10 5h2c6 0 10 7 10 7l-3 4M6 6l-4 6s4 7 10 7h2M9 9a4 4 0 0 0 6 6',
} as const;

export type IconName = keyof typeof paths;
export function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>;
}
export function BrandMark({ className = '' }: { className?: string }) {
  return <span className={`brand-mark ${className}`} aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="m7 24 8-17 10 17H7Z" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" /><path d="m12 18 10-6M20 7l5-2" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" /></svg></span>;
}
