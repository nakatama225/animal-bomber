import type { EffectKind } from '../../domain/state/EffectBag.js';

/** 一時的な状態の、画面での呼び方。 */
export interface EffectLabel {
  readonly emoji: string;
  readonly label: string;
}

/**
 * 状態の種類ごとの呼び方。原型の表から持ってきた。
 *
 * `Record` にしてあるので、ルールの層に状態を1つ足すと、ここで呼び方を
 * 書き忘れたときに型検査が失敗する。
 */
export const EFFECT_LABELS: Readonly<Record<EffectKind, EffectLabel>> = {
  slide: { emoji: '🍌', label: 'すべる' },
  stun: { emoji: '😭', label: '涙で動けない' },
  reverse: { emoji: '🔄', label: 'そうさ反転' },
  nobomb: { emoji: '🚫', label: '爆弾おけない' },
  runaway: { emoji: '💨', label: 'とまれない' },
  weak: { emoji: '🕯️', label: '爆風1マス' },
  autobomb: { emoji: '🎰', label: '勝手に設置' },
  slow: { emoji: '🐌', label: '超スロー' },
};

/** 絵文字と呼び方をつないだもの（「🍌すべる」）。 */
export function effectText(kind: EffectKind): string {
  const { emoji, label } = EFFECT_LABELS[kind];
  return `${emoji}${label}`;
}
