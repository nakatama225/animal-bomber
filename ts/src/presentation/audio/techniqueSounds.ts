import type { TechniqueMoment } from '../../domain/events/SimEvent.js';
import type { SoundName } from './SoundBank.js';

/**
 * 技を使ったときに鳴らす音の、動物ごとの対応表。
 *
 * ルールの層は、誰が通常技かとくぎかを使ったか（techniqueUsed）と、技の途中で起きたこと（techniqueMoment）を
 * 知らせてくる。何の音を当てるかはこの層の判断なので、動物の名前はここに書いてよい。
 *
 * とくぎは、どの動物でも共通の音（'special'）を先に鳴らし、そのあと動物ごとの音を鳴らす（原型の useSpecial）。
 * ここに書くのは、とくぎを使えば必ず鳴る音だけ。技が出なければ鳴らない音（掘る音・炎の音）は、
 * 技が出たときの techniqueMoment の側で鳴らす（下の MOMENT_SOUNDS）。
 * うさぎのとくぎは、うんこを踏んだときと同じ音（原型の rabbitPoroporo）。撒く輪ごとにも同じ音を鳴らす
 * （ringScattered）。
 */
const TABLE: Readonly<Record<string, { readonly tap?: SoundName; readonly special: readonly SoundName[] }>> = {
  rabbit: { tap: 'hop', special: ['poop'] },
  elephant: { tap: 'snot', special: ['charge'] },
  // 掘る音は、掘り始めたとき（digStarted）だけ。
  mole: { special: [] },
  // 原型は跳び上がる音を鳴らし、炎を出したとき（chaserCast）だけ炎の音を続ける。
  fox: { tap: 'lineBombs', special: ['foxLeap'] },
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
  digStarted: 'dig',
  pitDug: 'pitDone',
  slimeHopped: 'slimeHop',
  itemsSpat: 'spit',
  rammed: 'charge',
  chaserCast: 'foxfire',
  chaserHit: 'foxfireHit',
  ringScattered: 'poop',
};
