/**
 * Language choice (system / English / Nederlands), stored on the phone.
 * Changing it remounts the app below this provider, so every screen redraws
 * in the new language.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, Fragment, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { getLang, setLang, systemLang, type Lang, type LangPref } from './core';

const KEY = 'lang.pref';
const Ctx = createContext<{ pref: LangPref; lang: Lang; setPref: (p: LangPref) => void }>({
  pref: 'system',
  lang: getLang(),
  setPref: () => undefined,
});

const resolve = (p: LangPref): Lang => (p === 'system' ? systemLang() : p);

export function LangProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<LangPref | null>(null);
  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => (v === 'en' || v === 'nl' || v === 'system' ? v : 'system'))
      .catch(() => 'system' as const)
      .then((p) => {
        setLang(resolve(p));
        setPrefState(p);
      });
  }, []);
  const value = useMemo(
    () => ({
      pref: pref ?? 'system',
      lang: resolve(pref ?? 'system'),
      setPref: (p: LangPref) => {
        setLang(resolve(p));
        setPrefState(p);
        void AsyncStorage.setItem(KEY, p).catch(() => undefined);
      },
    }),
    [pref],
  );
  if (pref === null) return null;
  return (
    <Ctx.Provider value={value}>
      <Fragment key={value.lang}>{children}</Fragment>
    </Ctx.Provider>
  );
}

export const useLang = () => useContext(Ctx);
