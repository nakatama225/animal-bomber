import { sameCell } from '../../domain/core/Coord.js';
import { PitActor } from '../../domain/abilities/mole/PitAction.js';
import { holdSpecial } from '../BombPlacement.js';
import type { AnimalTactic } from './AnimalTactic.js';

/** 相手が歩いてこの距離まで来られる場所に穴を掘る。 */
const PIT_RANGE = 12;

/**
 * もぐらの戦い方。
 *
 * とくぎは見えない落とし穴。掘り終わるまで動けないので、どの爆弾も
 * 届かないマスでだけ掘る。誰も来ない所に掘っても無駄なので、
 * 相手が歩いて来られる範囲で仕掛ける。
 *
 * 押している間は立ち止まる（長押しが決まった瞬間の足元を掘り始める）。
 * 途中で危なくなったら離す。もぐらには押して離す技が無いので、
 * 離しても別の技には化けない。
 *
 * 壊せるブロックを通り抜けられる点は、経路の探索が能力に従うので
 * ここで扱う必要がない。
 */
export const MOLE_TACTIC: AnimalTactic = {
  animal: 'mole',

  reflex(ctx) {
    if (ctx.inDanger || ctx.me.specialCharges <= 0) return null;
    if (ctx.world.board.at(ctx.here) !== 'empty' || !ctx.danger.isSafe(ctx.here)) return null;
    const alreadyDug = ctx.world.actors.some(
      (actor) => actor instanceof PitActor && sameCell(actor.cell, ctx.here),
    );
    if (alreadyDug) return null;
    if (ctx.foePathDistance(PIT_RANGE + 2) > PIT_RANGE) return null;
    if (!ctx.skillReady()) return null;
    return holdSpecial(ctx, true);
  },
};
