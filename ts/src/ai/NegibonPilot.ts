import { cellOf, DIRECTIONS, step, type Point } from '../domain/core/Coord.js';
import { secondsToTicks } from '../domain/core/Tick.js';
import { IDLE_INTENT, type PlayerIntent } from '../domain/intent/PlayerIntent.js';
import {
  alongsAiming,
  alongsFacing,
  LANE_LENGTH,
  laneSpot,
  laneStep,
  wrapAlong,
  type LaneSpot,
} from '../domain/negibon/lane.js';
import { bombAt } from '../domain/query/BoardQuery.js';
import { LANE_SPEED, LEEK_HIT, LEEK_RANGE } from '../domain/rules/negibon.js';
import type { Negibon } from '../domain/state/Life.js';
import { isAlive, isInvulnerable, type PlayerState } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';

/**
 * 射線に相手を捉えてから撃つまでの間。
 *
 * 人のように反応を遅らせる（原型と同じ）。捉えた瞬間に撃たないので、
 * 歩いている相手には当たりにくくなる。
 */
const AIM_TICKS = secondsToTicks(0.6);

/** 寄る位置を選び直す間隔。毎 tick 選び直すと、相手の動きに合わせて外周で震える。 */
const REAIM_TICKS = secondsToTicks(0.25);

/**
 * 射線に乗っているとみなす、撃つ向きと直角のずれ（マス）。
 *
 * ⚠️ 葱の当たり判定（`LEEK_HIT`）より狭くとる。広いと、当たらない位置で止まって
 * 撃ち続ける。狭すぎても困る。外壁に寄って立つ相手を撃てる位置は辺の始まりにしか無く、
 * そこでも体の半径ぶん（最大 0.14 マス）ずれる。残りの幅が外周を1 tick に進む距離より
 * 広くなるようにしてある（狭いと、その幅を飛び越えて止まれない）。
 */
const IN_LINE = LEEK_HIT - 0.04;

/** 撃つのは、この距離までの相手だけ。射程の外には撃たない。原型と同じく1マスの余裕を見る。 */
const AIM_RANGE = LEEK_RANGE - 1;

/** 寄る位置までの残りがこれより短ければ着いたとみなす。外周を1 tick に進む距離の半分。 */
const ARRIVED = LANE_SPEED / 2;

/** 撃てる位置を探す細かさ。外周を1 tick に進む距離の4分の1。 */
const SCAN = LANE_SPEED / 4;

/**
 * 外周にいる CPU の操縦。原型の CPU の操縦をもとにした。
 *
 * 1. 射線上に相手がいて、間に柱・ブロック・爆弾が無ければ、動かずに狙いを定めてから撃つ
 * 2. いなければ、相手を撃てる外周の位置へ回って寄る
 *
 * 強さによる違いは無い（原型も同じ）。乱数も使わない。
 *
 * ## 寄る位置は、撃つかどうかの判定と同じ判定で探す
 *
 * 寄る位置を別の見積もりで選ぶと、着いたのに撃つ判定が通らない、が起きる（原型でも、
 * この版の途中でも起きた）。そこで、撃つかどうかを決める判定（`inLine`）をそのまま使い、
 * 相手の真上（真横）の前後を細かく調べて「ここから撃てば当たる」位置のひと続きを探す。
 * 寄るのはひと続きの真ん中。ひと続きの幅が外周を1 tick に進む距離以上あれば、着く前に
 * 必ずその中の位置を踏み、そこで撃つ判定が通る。それより狭いひと続きは使わない。
 *
 * ⚠️ 原型から直したこと。どれも、外周で止まったまま撃たない・当たらない所から撃ち続ける、
 * という不具合だった。
 * - 寄る位置を、外周を回った近さだけで選んでいた（射程の外・柱の陰でも選んだ）
 * - 寄る位置をマスの中央にしていた（相手が中央からずれて立つと、着いても射線に入らない）
 * - 射線に入ったとみなす幅が、葱の当たり判定より広かった
 * - 無敵中の相手も狙っていた（葱は通り抜けるので、撃つ間隔を無駄にする）
 *
 * 外周に回るたびに作り直す。前に外周にいたときの狙いを持ち越さない。
 */
export class NegibonPilot {
  /** 次に寄る位置を選び直すまでの tick。 */
  #reaimIn = 0;
  /** 射線に相手を捉えてからの tick。 */
  #locked = 0;
  /** 寄る位置（外周の上の位置）。 */
  #target: number | null = null;

  next(world: Readonly<WorldState>, lane: Negibon): PlayerIntent {
    const foes = world.players.filter((player) => canBeHit(world, player));
    if (foes.length === 0) {
      this.#locked = 0;
      return IDLE_INTENT;
    }
    this.#reaimIn -= 1;
    const spot = laneSpot(lane.along);

    if (foes.some((foe) => inLine(world, spot, foe))) {
      this.#locked += 1;
      if (this.#locked <= AIM_TICKS) return IDLE_INTENT; // 狙っている間は動かない
      this.#locked = 0;
      // まだ撃てなくても押す。そのときは何も起きず、狙い直しになる（原型と同じ）。
      return { ...IDLE_INTENT, bomb: true };
    }
    this.#locked = 0;

    if (this.#reaimIn <= 0 || this.#target === null) {
      this.#reaimIn = REAIM_TICKS;
      this.#target = chooseTarget(world, lane.along, spot.position, foes);
    }
    return keysFor(spot, directionTo(lane.along, this.#target));
  }
}

/** 葱が当たりうる相手か。無敵中と、乗っ取り中の振る舞いが触れられない間は、葱が通り抜ける。 */
function canBeHit(world: Readonly<WorldState>, player: PlayerState): boolean {
  return isAlive(player) && !isInvulnerable(player, world.now) && player.action?.untouchable !== true;
}

/** 相手が射線の上にいて、射程の内で、間に葱を止めるものが無いか。 */
function inLine(world: Readonly<WorldState>, spot: LaneSpot, foe: PlayerState): boolean {
  const { offset, ahead } = measure(spot, foe.position);
  if (offset >= IN_LINE || ahead <= 0 || ahead > AIM_RANGE) return false;
  return clearPath(world, spot, ahead);
}

/** 撃つ向きと直角のずれ（`offset`）と、撃つ向きに沿った距離（`ahead`）。 */
function measure(spot: LaneSpot, target: Point): { offset: number; ahead: number } {
  const delta = step({ col: 0, row: 0 }, spot.facing);
  const from = spot.position;
  return delta.col !== 0
    ? { offset: Math.abs(target.y - from.y), ahead: (target.x - from.x) * delta.col }
    : { offset: Math.abs(target.x - from.x), ahead: (target.y - from.y) * delta.row };
}

/** 撃つ位置から `ahead` マス先までに、葱を止める柱・ブロック・爆弾が無いか。 */
function clearPath(world: Readonly<WorldState>, spot: LaneSpot, ahead: number): boolean {
  const delta = step({ col: 0, row: 0 }, spot.facing);
  const board = world.board;
  for (let i = 0; i <= Math.ceil(ahead); i += 1) {
    const cell = cellOf({ x: spot.position.x + delta.col * i, y: spot.position.y + delta.row * i });
    if (!board.inBounds(cell)) continue;
    // 外壁は葱がすり抜けるので数えない。
    if (cell.col === 0 || cell.row === 0 || cell.col === board.cols - 1 || cell.row === board.rows - 1) continue;
    // 爆弾は葱を弾くので、あれば撃っても無駄になる。
    if (board.at(cell) !== 'empty' || bombAt(world, cell) !== undefined) return false;
  }
  return true;
}

/**
 * 寄る位置を選ぶ。
 *
 * 相手ごとに4辺を調べ、撃てば当たる位置のひと続きのうち、外周を回っていちばん近いものの
 * 真ん中を選ぶ（1周をまたぐ近道も考える）。どこにも無ければ、いちばん近い相手を撃てる
 * マスへ、近さだけで寄る（原型と同じ）。
 */
function chooseTarget(
  world: Readonly<WorldState>,
  along: number,
  from: Point,
  foes: readonly PlayerState[],
): number {
  let best: number | null = null;
  let bestDistance = Infinity;
  for (const foe of foes) {
    for (const aim of alongsAiming(foe.position)) {
      for (const candidate of firingSpots(world, foe, aim)) {
        const d = Math.abs(shortestWay(along, candidate));
        if (d < bestDistance) {
          bestDistance = d;
          best = candidate;
        }
      }
    }
  }
  if (best !== null) return best;

  let nearest = foes[0]!;
  let nearestDistance = Infinity;
  for (const foe of foes) {
    const d = Math.abs(foe.position.x - from.x) + Math.abs(foe.position.y - from.y);
    if (d < nearestDistance) {
      nearestDistance = d;
      nearest = foe;
    }
  }
  let fallback = along;
  let fallbackDistance = Infinity;
  for (const candidate of alongsFacing(cellOf(nearest.position))) {
    const d = Math.abs(shortestWay(along, candidate));
    if (d < fallbackDistance) {
      fallbackDistance = d;
      fallback = candidate;
    }
  }
  return fallback;
}

/**
 * `aim` の前後で、撃てば当たる位置のひと続きを探し、それぞれの真ん中を返す。
 *
 * 前後は射線の幅ぶんだけ見る。それより離れた位置は射線に入らない。
 * ⚠️ 幅が外周を1 tick に進む距離より狭いひと続きは返さない。1 tick で飛び越えてしまい、
 * その中で止まれないことがある。
 */
function firingSpots(world: Readonly<WorldState>, foe: PlayerState, aim: number): number[] {
  const spots: number[] = [];
  const end = aim + IN_LINE;
  let first: number | null = null;
  let last = 0;
  const close = (): void => {
    if (first !== null && last - first >= LANE_SPEED) spots.push(wrapAlong((first + last) / 2));
    first = null;
  };
  for (let along = aim - IN_LINE; along <= end; along += SCAN) {
    if (inLine(world, laneSpot(along), foe)) {
      if (first === null) first = along;
      last = along;
    } else {
      close();
    }
  }
  close();
  return spots;
}

/** `from` から `to` へ外周を回るときの、符号つきの近いほうの道のり。 */
function shortestWay(from: number, to: number): number {
  let diff = to - from;
  if (diff > LANE_LENGTH / 2) diff -= LANE_LENGTH;
  if (diff < -LANE_LENGTH / 2) diff += LANE_LENGTH;
  return diff;
}

/**
 * 寄る位置へ向かう向き。着いていれば 0。
 *
 * 向きは毎 tick 決め直す。原型は寄る位置を選び直すとき（0.25 秒ごと）にだけ決めたので、
 * 寄る位置を行き過ぎては戻る往復になった。
 */
function directionTo(along: number, target: number): -1 | 0 | 1 {
  const way = shortestWay(along, target);
  if (Math.abs(way) < ARRIVED) return 0;
  return way > 0 ? 1 : -1;
}

/**
 * 外周をその向きへ進むために押す向き。
 *
 * どの辺で何を押すとどちらへ進むかは、人の操作と同じ変換（`laneStep`）から逆に引く。
 * 別に表を持つと、人と CPU で外周の進み方が食い違ったときに気づけない。
 */
function keysFor(spot: LaneSpot, direction: -1 | 0 | 1): PlayerIntent {
  if (direction === 0) return IDLE_INTENT;
  for (const key of DIRECTIONS) {
    const intent = { ...IDLE_INTENT, [key]: true };
    if (laneStep(spot.side, intent) === direction) return intent;
  }
  return IDLE_INTENT;
}
