import type { Cell } from '../core/Coord.js';
import type { EntityId } from '../core/EntityId.js';
import type { ItemKind } from '../rules/items.js';

/** 盤面に落ちているアイテム。 */
export interface Item {
  readonly id: EntityId;
  readonly cell: Cell;
  readonly kind: ItemKind;
}
