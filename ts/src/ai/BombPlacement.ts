import { sameCell } from '../domain/core/Coord.js';
import { bombAt } from '../domain/query/BoardQuery.js';
import { DangerMap, type HypotheticalBomb } from '../domain/query/DangerMap.js';
import { BOMB_FUSE } from '../domain/rules/tuning.js';
import { canPlaceBomb, powerOf, speedOf } from '../domain/state/PlayerState.js';
import { ButtonMacro } from './ButtonMacro.js';
import type { CpuContext } from './CpuContext.js';
import {
  ESCAPE_MARGIN,
  ESCAPE_SPEED_RATIO,
  OUT_OF_BOMBS_BAN,
  SAME_SPOT_BAN,
  UNSAFE_SPOT_BAN,
} from './margins.js';

/**
 * 爆弾の置き方の候補。
 *
 * 足元に1個置くのが基本だが、動物によっては別の置き方を持つ
 * （正面へ一列に並べる、など）。どの置き方でも、
 * 「置いたあと盤面に増える爆弾」と「そのためのボタンの押し方」の組で表す。
 * 共通の判断は、増える爆弾だけを見て逃げ切れるかを決める。
 */
export interface BombOption {
  readonly bombs: readonly HypotheticalBomb[];
  readonly macro: ButtonMacro;
}

/** 足元に1個置く。 */
export function footBomb(ctx: CpuContext): BombOption {
  return {
    bombs: [{ cell: ctx.here, power: powerOf(ctx.me), fuse: BOMB_FUSE }],
    macro: ButtonMacro.dropBomb(),
  };
}

/**
 * その置き方で置いたあと、爆風の届かないマスまで逃げ切れるか。
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
 * 爆弾を置きたいと判断していたら、置いてよいかを確かめて手順を返す。
 *
 * 置けなかった場合は、理由に応じて「しばらく爆弾を狙わない」を記憶に残す。
 *
 * @param options 試す順に並べた置き方
 * @returns 置くための押し方。置かないなら null
 */
export function decideBomb(ctx: CpuContext, options: readonly BombOption[]): ButtonMacro | null {
  const memory = ctx.memory;
  if (!memory.wantBomb || ctx.inDanger || !canPlaceHere(ctx)) return null;

  const chosen = options.find((option) => canEscapeAfter(ctx, option));
  const now = ctx.world.now;
  const sameSpot =
    memory.lastBomb !== null &&
    sameCell(memory.lastBomb.cell, ctx.here) &&
    now - memory.lastBomb.at < SAME_SPOT_BAN;

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

  if (chosen !== undefined && !sameSpot && !tooMany) {
    memory.lastBomb = { cell: ctx.here, at: now };
    return chosen.macro;
  }
  memory.bombBan = chosen === undefined || sameSpot ? UNSAFE_SPOT_BAN : OUT_OF_BOMBS_BAN;
  return null;
}

/** とくぎの長押しを始める手順。 */
export function holdSpecial(ctx: CpuContext, still: boolean): ButtonMacro {
  return ButtonMacro.hold(ctx.ability.holdTicks, still);
}
