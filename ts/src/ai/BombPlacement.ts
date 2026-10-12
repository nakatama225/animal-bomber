import { sameCell, type Direction } from '../domain/core/Coord.js';
import { bombAt } from '../domain/query/BoardQuery.js';
import { DangerMap } from '../domain/query/DangerMap.js';
import { BOMB_FUSE } from '../domain/rules/tuning.js';
import { canPlaceBomb, powerOf, speedOf } from '../domain/state/PlayerState.js';
import type { CpuContext } from './CpuContext.js';
import type { BombOption } from './CpuPlan.js';
import {
  ESCAPE_MARGIN,
  ESCAPE_SPEED_RATIO,
  OUT_OF_BOMBS_BAN,
  SAME_SPOT_BAN,
  UNSAFE_SPOT_BAN,
} from './margins.js';
import { tacticOf } from './tactics/registry.js';

/** 足元に1個置く。 */
export function footBomb(ctx: CpuContext): BombOption {
  return {
    bombs: [{ cell: ctx.here, power: powerOf(ctx.me), fuse: BOMB_FUSE }],
    button: 'bomb',
  };
}

/**
 * その置き方で置いたあと、爆風の届かないマスまで逃げ切れるか（原型 canEscapeAfterBomb）。
 *
 * 置いた爆弾は自分の逃げ道も塞ぐので、塞がれたものとして経路を探す。
 */
export function canEscapeAfter(ctx: CpuContext, option: BombOption): boolean {
  if (option.bombs.length === 0) return false;
  const danger = DangerMap.of(ctx.world, option.bombs);
  if (danger.isSafe(ctx.here)) return true;

  const path = ctx.pathTo((cell) => danger.isSafe(cell), {
    maxDistance: 8,
    extraObstacles: option.bombs.map((bomb) => bomb.cell),
  });
  if (path === null) return false;

  const speed =
    speedOf(ctx.me, ctx.ability.speedMultiplier, ctx.world.board.at(ctx.here)) * ESCAPE_SPEED_RATIO;
  const needed = path.length / speed;
  return needed < BOMB_FUSE - ESCAPE_MARGIN;
}

/** いまいるマスに、そもそも爆弾を置ける状態か。 */
export function canPlaceHere(ctx: CpuContext): boolean {
  const { me, world, here } = ctx;
  // ゲームの側と同じ確かめを通す（原型の CPU も canPlaceBomb を見る）。爆弾おけないだけを見ると、
  // 「勝手に設置」が重なって置ける間も、CPU だけが置かなくなる。
  if (!canPlaceBomb(me)) return false;
  if (me.activeBombs >= me.maxBombs) return false;
  if (bombAt(world, here) !== undefined) return false;
  // 壊せるブロックの中に潜っているときは置けない。
  return world.board.at(here) === 'empty';
}

/**
 * 爆弾を置きたいと判断していたら、置いてよいかを確かめて、押すボタンを返す（原型 cpuUpdate の「爆弾を置く」）。
 *
 * 置けなかった場合は、理由に応じて「しばらく爆弾を狙わない」を記憶に残す。
 * 押すボタンを前の tick にも押していたら、この tick は何も決めずに待つ（押した瞬間でしか効かない）。
 *
 * @param facing この tick の移動のあとに向いている方向。一列に並べる置き方は、この向きに並ぶ
 *   （原型も、経路を1歩進めて向きが変わってから並べる）
 * @returns 押すボタン。置かないなら null
 */
export function decideBomb(ctx: CpuContext, facing: Direction): BombOption['button'] | null {
  const memory = ctx.memory;
  if (!memory.wantBomb || ctx.inDanger || !canPlaceHere(ctx)) return null;

  const option = tacticOf(ctx.me.animal).bombOption?.(ctx, facing) ?? footBomb(ctx);
  if (!ctx.canPress(option.button)) return null;
  const now = ctx.world.now;
  const sameSpot =
    memory.lastBomb !== null &&
    sameCell(memory.lastBomb.cell, ctx.here) &&
    now - memory.lastBomb.at < SAME_SPOT_BAN;
  // ⛔ 同じマスに置き直さない。逃げ切れても、置けない場所として扱う。
  const escapes = canEscapeAfter(ctx, option) && !sameSpot;

  // ⛔ 「袋小路では置かない」という規則は入れない。
  // このゲームはブロックを壊して道を作るので、序盤はかならず袋小路になる。
  // 入れると「道が狭いから置かない → 壊せない → ずっと狭い」で永久に置けなくなる。
  // 原型の実測で、つよい CPU が40秒のあいだ爆弾を1個も置かなかった。
  // 置いてよいかは「逃げ切れるか」だけで決める。

  // 自分の爆弾が多すぎるなら、場所が悪いのではなく「今は待つ」。
  const tooMany = ctx.liveOwnBombs >= ctx.level.maxLiveBombs;

  memory.wantBomb = false;
  memory.path = [];
  memory.thinkIn = 0;

  if (escapes && !tooMany) {
    memory.lastBomb = { cell: ctx.here, at: now };
    return option.button;
  }
  memory.bombBan = escapes ? OUT_OF_BOMBS_BAN : UNSAFE_SPOT_BAN;
  return null;
}
