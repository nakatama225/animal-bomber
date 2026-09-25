import type { SoundName } from './SoundBank.js';

/**
 * 技を使ったときに鳴らす音の、動物ごとの対応表。
 *
 * ルールの層は「誰が、通常技かとくぎかを使った」だけを知らせてくる。
 * 何の音を当てるかはこの層の判断なので、動物の名前はここに書いてよい。
 */
const TABLE: Readonly<Record<string, { readonly tap?: SoundName; readonly special: SoundName }>> = {
  rabbit: { tap: 'hop', special: 'scatter' },
  elephant: { special: 'charge' },
  mole: { special: 'dig' },
  fox: { tap: 'lineBombs', special: 'foxfire' },
  frog: { tap: 'tongue', special: 'slime' },
};

/**
 * その動物がその技を使ったときの音。鳴らさないなら null。
 *
 * 表に無い動物は、とくぎだけ共通の音を鳴らす。
 */
export function techniqueSound(animal: string, special: boolean): SoundName | null {
  const entry = TABLE[animal];
  if (special) return entry?.special ?? 'special';
  return entry?.tap ?? null;
}
