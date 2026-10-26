import type { EffectKind } from '../../domain/state/EffectBag.js';

/**
 * 名札と通知に出す絵文字（落とし穴・つるはし・うんこでかかる状態の印）。
 *
 * 値は原型（`legacy/animal-bomber.html`）の絵文字と、見え方を選ぶ印 U+FE0F まで同じ文字列にする
 * （Python 版の `presentation/emoji.py` と同じ）。
 */

/** 落とし穴の絵文字（原型の 🕳️）。 */
export const HOLE = '\u{1F573}\uFE0F';

/** つるはしの絵文字（原型の ⛏️）。 */
export const PICK = '\u26CF\uFE0F';

/**
 * うんこでかかる状態と、その印（原型の POOP_KEYS の並びと POOPS の emoji）。
 *
 * 並びは原型の POOPS に書いた順（そうさ反転・爆弾おけない・とまれない・爆風1マス・勝手に設置・超スロー）。
 * 名札の状態の行はこの順に並べる。呼び方（「そうさ反転」など）はルールの層の `POOP_EFFECTS` の `label` を使う。
 */
export const POOP_MARKS: readonly (readonly [EffectKind, string])[] = [
  ['reverse', '🔄'],
  ['nobomb', '🚫'],
  ['runaway', '💨'],
  ['weak', '🕯️'],
  ['autobomb', '🎰'],
  ['slow', '🐌'],
];
