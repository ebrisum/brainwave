/**
 * Translations: English is the source text and the key; nl.ts maps it to
 * Dutch. Missing entries fall back to English. Placeholders: {name}.
 * Pure TypeScript (no React) so the node test runner can load it.
 */
import { NL } from './nl.ts';

export type Lang = 'en' | 'nl';
export type LangPref = 'system' | Lang;

export function systemLang(): Lang {
  try {
    const loc = Intl.DateTimeFormat().resolvedOptions().locale ?? '';
    return loc.toLowerCase().startsWith('nl') ? 'nl' : 'en';
  } catch {
    return 'en';
  }
}

let current: Lang = systemLang();

export const getLang = (): Lang => current;
export function setLang(lang: Lang): void {
  current = lang;
}

type Params = Record<string, string | number | null | undefined>;

export function t(text: string, params?: Params): string {
  const base = current === 'nl' ? NL[text] ?? text : text;
  if (!params) return base;
  return base.replace(/\{(\w+)\}/g, (m, k: string) => {
    const v = params[k];
    return v === undefined || v === null ? m : String(v);
  });
}

/** Singular or plural: tn(n, '{n} cat', '{n} cats'). */
export function tn(n: number, one: string, other: string, params?: Params): string {
  return t(n === 1 ? one : other, { n, ...params });
}

/** Locale for dates and times in the chosen language. */
export const locale = (): string => (current === 'nl' ? 'nl-NL' : 'en-GB');

/** Marks a string as a translation key without translating it yet (lists defined outside render). */
export const tk = (text: string): string => text;
