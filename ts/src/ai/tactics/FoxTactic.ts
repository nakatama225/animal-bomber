import { SCAN_ORDER, step, type Cell, type Direction } from '../../domain/core/Coord.js';
import { FOXFIRE_REACH } from '../../domain/abilities/fox/FoxfireActor.js';
import { bombAt } from '../../domain/query/BoardQuery.js';
import { BOMB_FUSE } from '../../domain/rules/tuning.js';
import { powerOf } from '../../domain/state/PlayerState.js';
import type { CpuContext } from '../CpuContext.js';
import type { AnimalTactic } from './AnimalTactic.js';

/**
 * きつねの戦い方。
 *
 * ## 一列に並べる（原型 cpuUpdate の「爆弾を置く」）
 *
 * 通常技で、手持ちの爆弾を正面へ一列に並べられる。爆弾を置くと決めたら、いま向いている方向
 * （この tick に歩くなら、歩いた向き）に並べる。前が塞がっていて1本も並べられなければ、
 * ほかの動物と同じく足元に1個置く。
 *
 * ⚠️ 原型の CPU は、手持ち全部では逃げ切れないとき、本数を減らして逃げ切れる本数だけ並べる
 * （cpuUpdate の `canEscapeAfterBomb(p,tx,ty,n)` を n を減らしながら試し、通った本数を `p.lineCap` に書く）。
 * この版は本数を絞らない。本数はボタンの組（入力）に載らず、原型の CPU はプレイヤーの状態に直に書いていた。
 * 手持ち全部で逃げ切れなければ、置かない。
 *
 * ## ブロックの2マス手前に立つ（原型 planCPU の digHere）
 *
 * 一列は足元ではなく1マス前から並ぶ。ブロックの隣に立つと前が塞がっていて
 * 1本も並べられない。壊しに行くときは、1マス空けた手前に立つ。
 *
 * そこで置くと決めても、並べる向きのどれにも、一列と爆風の届く先に壊せるブロックが無ければ置かない
 * （原型の実測で、壊せるブロックの無い向きに一列を置き、自分の爆風から逃げて離れ、爆発が終わると
 * 戻ってまた置く、を 40 秒くり返したことがあった）。
 *
 * ⚠️ 原型 planCPU は、このとき壊せる向きへ向きを変える（`p.dir=`）。ただし同じフレームのうちに
 * 経路を1歩進め（movePlayer が向きを書き換える）、そのあとで並べるので、一列は歩いた向きに並ぶ。
 * 向きを変える処理は持たない。
 *
 * ## 狐火（原型 cpuUpdate の最後の分岐）
 *
 * 相手が歩ける道で、寿命のうちに届く距離の 8 割まで来ていれば放つ。原型の CPU は useSpecial を
 * 直に呼ぶので、とくぎを直に出すボタンで出す（一列は並ばない）。
 */
export const FOX_TACTIC: AnimalTactic = {
  animal: 'fox',

  bombOption(ctx, facing) {
    const cells = lineCells(ctx, facing);
    if (cells.length === 0) return null;
    // ⚠️ この版は一列のあとに間隔を置く（原型には無い。直すのは Python 版を一通り作り終えてから）。
    // 間隔の最中は並べられないので、足元に置く。
    if (ctx.me.abilityCooldown > 0) return null;
    return {
      bombs: cells.map((cell) => ({ cell, power: powerOf(ctx.me), fuse: BOMB_FUSE })),
      button: 'action',
    };
  },

  isBreakSpot(ctx, cell) {
    return SCAN_ORDER.some(
      (direction) =>
        ctx.world.board.at(step(cell, direction)) === 'empty' &&
        ctx.world.board.at(step(cell, direction, 2)) === 'soft',
    );
  },

  confirmsBreakBomb(ctx) {
    const reach = powerOf(ctx.me) + (ctx.me.maxBombs - ctx.me.activeBombs);
    return SCAN_ORDER.some((direction) => {
      const first = step(ctx.here, direction);
      if (ctx.world.board.at(first) !== 'empty' || bombAt(ctx.world, first) !== undefined) return false;
      for (let i = 1; i <= reach; i += 1) {
        const tile = ctx.world.board.at(step(ctx.here, direction, i));
        if (tile === 'hard') return false;
        if (tile === 'soft') return true;
      }
      return false;
    });
  },

  afterMove(ctx) {
    if (ctx.me.specialCharges <= 0 || ctx.inDanger) return false;
    // 寿命のうちに届く距離の 8 割まで。遠いと届く前に消える。
    return ctx.foePathDistance(FOXFIRE_REACH) <= Math.floor(FOXFIRE_REACH * 0.8) && ctx.skillReady();
  },
};

/**
 * その向きに並べたとき、爆弾が置かれるマス（原型 plannedLineBombs）。
 *
 * 能力の側の並べ方（空いたマスが続く限り、手持ちのぶんだけ）と揃えてある。
 */
function lineCells(ctx: CpuContext, direction: Direction): Cell[] {
  const cells: Cell[] = [];
  const budget = ctx.me.maxBombs - ctx.me.activeBombs;
  for (let i = 1; cells.length < budget; i += 1) {
    const cell = step(ctx.here, direction, i);
    if (ctx.world.board.at(cell) !== 'empty' || bombAt(ctx.world, cell) !== undefined) break;
    cells.push(cell);
  }
  return cells;
}
