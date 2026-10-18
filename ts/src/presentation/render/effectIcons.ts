import { lookOf } from '../../content/animals.js';
import type { EffectKind } from '../../domain/state/EffectBag.js';
import type { PlayerState } from '../../domain/state/PlayerState.js';

/**
 * かかっている状態ごとの、足元に出す絵文字。
 *
 * 状態の種類（`EffectKind`）を鍵にした表なので、種類が増えたのに
 * ここへ足し忘れると型検査が失敗する。
 */
export const EFFECT_ICONS: Readonly<Record<EffectKind, string>> = {
  slide: '🍌',
  stun: '😭',
  reverse: '🔄',
  nobomb: '🚫',
  runaway: '💨',
  weak: '🕯️',
  autobomb: '🎰',
  slow: '🐌',
  pitfall: '🕳️',
  leap: '🦊',
  scattering: '💩',
};

/**
 * プレイヤーの足元に並べる絵文字。
 *
 * 並びは、溜めてあるとくぎ → 技の最中であること → かかっている状態
 * （`EFFECT_KINDS` の順）。表示するのは先頭のいくつかだけなので、
 * 前にあるものほど見える。
 *
 * とくぎは、持っている印（`hasSpecial`）があるときだけ出す。原型の L4813 と同じく回数では見ない。
 * 外周から戻ったプレイヤーは回数だけが残っていることがあるが、そのとくぎは出せない。
 *
 * @param actionIcon 乗っ取り中の振る舞いを表す絵文字。無ければ省く
 */
export function statusIcons(player: PlayerState, actionIcon?: string): string[] {
  const icons: string[] = [];
  if (player.hasSpecial) icons.push(lookOf(player.animal).special.emoji);
  if (actionIcon !== undefined) icons.push(actionIcon);
  for (const kind of player.effects.active()) icons.push(EFFECT_ICONS[kind]);
  return icons;
}
