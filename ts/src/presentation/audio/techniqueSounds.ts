import type { TechniqueMoment } from '../../domain/events/SimEvent.js';
import type { SoundName } from './SoundBank.js';

/**
 * 技を使ったときに鳴らす音の、動物ごとの対応表。
 *
 * ルールの層は「誰が、通常技かとくぎかを使った」だけを知らせてくる。
 * 何の音を当てるかはこの層の判断なので、動物の名前はここに書いてよい。
 *
 * とくぎは、どの動物でも共通の音（'special'）を先に鳴らし、そのあと動物ごとの音を鳴らす（原型の useSpecial）。
 * うさぎのとくぎは原型ではうんこを踏んだときと同じ音だが、悪い状態にかかったときの音と分けたいので
 * 'scatter' を当てている。
 */
const TABLE: Readonly<Record<string, { readonly tap?: SoundName; readonly special: readonly SoundName[] }>> = {
  rabbit: { tap: 'hop', special: ['scatter'] },
  elephant: { tap: 'snot', special: ['charge'] },
  mole: { special: ['dig'] },
  // 原型は跳び上がる音と炎の音を続けて鳴らす。
  fox: { tap: 'lineBombs', special: ['foxLeap', 'foxfire'] },
  frog: { tap: 'tongue', special: ['slime'] },
};

/**
 * その動物がその技を使ったときに鳴らす音（鳴らす順）。鳴らさないなら空。
 *
 * 表に無い動物は、とくぎだけ共通の音を鳴らす。
 */
export function techniqueSounds(animal: string, special: boolean): readonly SoundName[] {
  const entry = TABLE[animal];
  if (special) return ['special', ...(entry?.special ?? [])];
  return entry?.tap === undefined ? [] : [entry.tap];
}

/** 技の途中で起きたことに当てる音（原型の、それぞれの瞬間の専用の音）。 */
export const MOMENT_SOUNDS: Readonly<Record<TechniqueMoment, SoundName>> = {
  tongueCaught: 'tongueCatch',
  pitDug: 'pitDone',
  slimeHopped: 'slimeHop',
  itemsSpat: 'spit',
  chargeHit: 'charge',
  foxfireHit: 'foxfireHit',
};
