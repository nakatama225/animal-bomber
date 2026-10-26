import type { Cell } from '../core/Coord.js';
import type { EntityId } from '../core/EntityId.js';
import type { Tick } from '../core/Tick.js';
import type { ItemKind } from '../rules/items.js';
import type { PlayerId } from './PlayerState.js';

/** 盤面に落ちているアイテム。 */
export interface Item {
  readonly id: EntityId;
  readonly cell: Cell;
  readonly kind: ItemKind;
  /**
   * とくぎで撒かれたアイテムなら、撒いたプレイヤー（原型の poro と owner）。ふつうのアイテムは書かない。
   *
   * 撒かれたアイテムは、ふつうのアイテムと3つ違う：撒いたプレイヤー自身は踏んでも拾わない（効果が無く、残る）・
   * 爆風で焼けない・`expiresAt` を過ぎると消える。ほかのプレイヤーが踏めば、ふつうのアイテムと同じく適用されて消える。
   */
  readonly scatteredBy?: PlayerId;
  /**
   * この tick を過ぎたら盤面から消える。うんこ（`rules/items.ts` の `POOP_LIFETIME`。原型の POOP_LIFE）と、
   * とくぎで撒かれたものだけが持つ。ほかのアイテムは消えない。
   */
  readonly expiresAt?: Tick;
  /**
   * 鼻水で流されて溶けている最中なら、消える tick（原型の melt）。溶けている間は盤面に残るが、
   * 踏んでも拾わない（効果が無い）。舌で掴む・体当たりで抱えるのは、原型と同じく溶けていても止めない。
   */
  readonly meltingUntil?: Tick;
}
