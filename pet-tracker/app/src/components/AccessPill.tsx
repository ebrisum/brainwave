import type { Cat } from '../backend/types';
import { shortDate } from '../time';
import { Pill } from './ui';
import { t as tr } from '../i18n';

/**
 * How you see a cat that is not yours: through a household, or as its cat
 * sitter. With `own`, your own cats show their household too.
 */
export function AccessPill({ cat, own = false }: { cat: Cat; own?: boolean }) {
  if (cat.access === 'sitter') {
    return <Pill label={cat.sitterUntil ? tr('Cat sitting · until {sitterUntil}', { sitterUntil: shortDate(cat.sitterUntil) }) : tr('Cat sitting')} tone="accent" icon="heart-outline" />;
  }
  if (cat.access === 'household' || (own && cat.householdName)) return <Pill label={cat.householdName ?? tr('Household')} icon="home-outline" />;
  return null;
}
