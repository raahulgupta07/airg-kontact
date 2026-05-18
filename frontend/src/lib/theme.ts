import { writable, get } from 'svelte/store';

export type Theme = 'light' | 'dark' | 'auto';

const STORAGE_KEY = 'kontact-theme';

function readStored(): Theme {
  if (typeof localStorage === 'undefined') return 'auto';
  const v = localStorage.getItem(STORAGE_KEY);
  if (v === 'light' || v === 'dark' || v === 'auto') return v;
  return 'auto';
}

export const theme = writable<Theme>('auto');

function resolveTheme(t: Theme): 'light' | 'dark' {
  if (t === 'auto') {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  }
  return t;
}

export function applyTheme(t: Theme): void {
  if (typeof document === 'undefined') return;
  const resolved = resolveTheme(t);
  document.documentElement.setAttribute('data-theme', resolved);
}

let mediaListener: ((e: MediaQueryListEvent) => void) | null = null;

export function initTheme(): void {
  if (typeof window === 'undefined') return;
  const stored = readStored();
  theme.set(stored);
  applyTheme(stored);

  // Watch system preference changes — only matter when theme is 'auto'
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  if (mediaListener) {
    mq.removeEventListener('change', mediaListener);
  }
  mediaListener = () => {
    if (get(theme) === 'auto') applyTheme('auto');
  };
  mq.addEventListener('change', mediaListener);
}

export function setTheme(t: Theme): void {
  theme.set(t);
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, t);
  applyTheme(t);
}

export function toggleTheme(): void {
  const cur = get(theme);
  const next: Theme = cur === 'light' ? 'dark' : cur === 'dark' ? 'auto' : 'light';
  setTheme(next);
}
