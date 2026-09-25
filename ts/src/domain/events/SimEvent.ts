import type { Cell } from '../core/Coord.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { EffectKind } from '../state/EffectBag.js';
import type { ItemKind } from '../rules/items.js';

/**
 * 試合の中で起きたイベント。
 *
 * 「爆弾が置かれた」「ブロックが壊れた」「誰かが倒れた」といった、
 * 1 tick の中で実際に起きたことを1件ずつ表す。
 *
 * ## なぜ戻り値なのか
 *
 * 原型では `update()` の中から効果音（53 箇所）・画面の書き換え（17 箇所）・
 * 通知の表示（17 箇所）を直接呼んでいた。そのため、画面を描かずに
 * ルールだけを動かす方法が無かった。CPU の強さを1万試合で測ろうとすると、
 * 音を鳴らしながら実時間で回すことになる。
 *
 * この版では、ルールの層は**起きたイベントを配列で返すだけ**にする。
 * 音を鳴らすか、画面を光らせるか、何もしないかは受け取った側が決める。
 *
 * ```
 * const events = simulation.step(world, intents);
 * presenter.consume(events);   // 画面と音
 * // 検証のときは consume しない。それだけで無音・無描画になる
 * ```
 *
 * 「音を消すフラグ」も「テスト用のモード」も要らない。**呼ばなければ
 * 起きない**、が構造で保証される。
 *
 * ## なぜ判別可能ユニオンなのか
 *
 * `type` の値で分岐すると、型検査が「まだ扱っていない種類」を見つける。
 * イベントを1種類足したとき、対応を書き忘れた場所が
 * `assertNever` で落ちる（`Presenter` を参照）。
 */
export type SimEvent =
  | { readonly type: 'bombPlaced'; readonly cell: Cell; readonly owner: PlayerId }
  | {
      readonly type: 'exploded';
      readonly cell: Cell;
      readonly owner: PlayerId;
      /** 連鎖した爆弾の数。多いほど大きな音を鳴らす。 */
      readonly chained: number;
    }
  | { readonly type: 'blockDestroyed'; readonly cell: Cell }
  | { readonly type: 'itemDropped'; readonly cell: Cell; readonly kind: ItemKind }
  | {
      readonly type: 'itemTaken';
      readonly cell: Cell;
      readonly kind: ItemKind;
      readonly taker: PlayerId;
    }
  | { readonly type: 'itemBurned'; readonly cell: Cell; readonly kind: ItemKind }
  | {
      readonly type: 'effectApplied';
      readonly target: PlayerId;
      readonly effect: EffectKind;
    }
  | {
      readonly type: 'playerHurt';
      readonly target: PlayerId;
      /** 倒した相手。自爆なら自分自身の席番号が入る。 */
      readonly by: PlayerId | null;
      /** 減った体力（半分の単位）。 */
      readonly amount: number;
    }
  | { readonly type: 'playerDown'; readonly target: PlayerId; readonly by: PlayerId | null };

/**
 * 扱い漏れを型検査で見つけるための仕掛け。
 *
 * すべての種類を処理したあとに呼ぶ。新しいイベントを `SimEvent` へ足すと、
 * そこへ到達しうるようになるため `never` に代入できず、
 * コンパイルエラーになる。
 */
export function assertNever(value: never): never {
  throw new Error(`扱っていないイベント: ${JSON.stringify(value)}`);
}
