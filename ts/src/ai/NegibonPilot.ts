import { cellOf, DIRECTIONS, step, type Point } from '../domain/core/Coord.js';
import { secondsToTicks } from '../domain/core/Tick.js';
import { IDLE_INPUT, type PlayerInput } from '../domain/input/PlayerInput.js';
import { alongsFacing, LANE_LENGTH, laneSpot, laneStep, type LaneSpot } from '../domain/negibon/lane.js';
import { bombAt } from '../domain/query/BoardQuery.js';
import { LEEK_RANGE } from '../domain/rules/negibon.js';
import type { Negibon } from '../domain/state/Life.js';
import { isAlive, type PlayerState } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';

/**
 * 射線に相手を捉えてから撃つまでの間。
 *
 * 人間のように反応を遅らせる（原型と同じ）。捉えた瞬間に撃たないので、
 * 歩いている相手には当たりにくくなる。
 *
 * ⚠️ 原型は 1/60 秒を小数で足し続けるので 36 フレーム目に撃つ。この版は実数で数えた tick のまま
 * （37 tick 目に押す）にしてある。
 */
const AIM_TICKS = secondsToTicks(0.6);

/**
 * 進む向きを選び直す間隔。
 *
 * ⚠️ 原型は 1/60 秒を小数で引き続けるので 16 フレームごとに選び直す。この版は実数で数えた tick のまま
 * （15 tick ごと）にしてある。
 */
const REAIM_TICKS = secondsToTicks(0.25);

/**
 * 射線に乗っているとみなす、撃つ向きと直角のずれ（マス）。原型の L2380 と同じ 0.3。
 *
 * ⚠️ 葱の当たり判定（`LEEK_HIT`、0.28）より広い。ずれが 0.28〜0.3 の位置では、止まっている相手にも
 * 当たらないのに撃つ（原型も同じ）。
 */
const IN_LINE = 0.3;

/** 撃つのは、この距離までの相手だけ。射程の外には撃たない。原型と同じく1マスの余裕を見る。 */
const AIM_RANGE = LEEK_RANGE - 1;

/**
 * 選び直すとき、寄る位置までの残りがこれより短ければ止まる（原型の L2421 と同じ 0.25）。
 *
 * 外周を1 tick に進む距離（約 0.092）より広い。止まるのは選び直した瞬間の残りで決まり、
 * 選び直しの間はその向きのまま動き続ける。
 */
const SETTLE = 0.25;

/**
 * 外周にいる CPU の操縦。原型の cpuNegiUpdate（L2366-2424）と同じ動きにしてある。
 *
 * 1. 射線上に相手がいて、間に柱・ブロック・爆弾が無ければ、動かずに狙いを定めてから撃つ
 * 2. いなければ、選び直しの間隔ごとに進む向きを決め、次の選び直しまで同じ向きで外周を進む
 *
 * 強さによる違いは無い（原型も同じ）。乱数も使わない。
 *
 * ## 狙う相手と寄る位置（原型の L2369・L2403-2421 と同じ）
 *
 * - 狙う相手は盤面にいる全員。無敵中の相手も、葱が触れられない振る舞いや跳び上がっている最中の相手も含む。葱はそういう相手を
 *   通り抜けるが、原型の L2369 も state==='ALIVE' の全員を見て、射線に乗れば撃つ
 * - 寄る先は、外周の位置からいちばん近い相手（縦と横の距離の和。同じならプレイヤー番号の若いほう）の
 *   マスに向き合う4辺の位置のうち、外周を回っていちばん近いもの（同じなら上・右・下・左の順に先のもの）
 * - 射程も、間の柱・ブロック・爆弾も見ずに選ぶ。原型の L2410-2417 も見ない。いちばん近い辺から撃てない
 *   （射程の外・柱の陰）と、そこへ寄っても撃てず、残り60秒で外周が閉じるまで、その辺で行ったり来たりする
 * - 寄る先は相手のマスの中央に向き合う位置。マスの中央からずれて立つ相手は、着いても射線に乗らないことがある
 *
 * ## 向きは選び直しのときだけ決める（原型の L2418-2423 と同じ）
 *
 * 選び直しの瞬間に、寄る先までの残りが `SETTLE` 未満なら止まり、そうでなければその向きへ、次の選び直しまで
 * 毎 tick 進む。寄る先を行き過ぎては戻る往復になる。往復の間も射線は毎 tick 見るので、射程の内で射線が通る
 * 相手なら、往復の途中で射線に乗ったところで止まって撃つ。
 *
 * ## 同じラウンドのうちは作り直さない
 *
 * 原型は外周の操縦の記憶（選び直しの残り negiAim・向き negiDir）を CPU の記憶 p.ai に持ち、ラウンドの始まり
 * （L4191-4192）にしか作り直さない。外周へ回るとき（toNegibon の L2268）に 0 に戻すのは構えの溜め（negiLock）だけで、
 * 同じラウンドで2度目に外周へ回ると、前の外周の選び直しの残りと向きのまま動き出す。ここも同じにする。
 * 外周へ回ったら `enterLane` を呼ぶ。
 */
export class NegibonPilot {
  /** 次に向きを選び直すまでの tick。0 で始まるので、ラウンドで1度目の外周は最初の tick に選ぶ（原型の L4192）。 */
  #reaimIn = 0;
  /** 射線に相手を捉えてからの tick。 */
  #locked = 0;
  /** 進む向き（外周の上の位置が増える向きが 1）。選び直しのときだけ決める。 */
  #direction: -1 | 0 | 1 = 0;

  /** 外周へ回ったときに呼ぶ。構えの溜めだけを 0 に戻す（原型の toNegibon L2268）。 */
  enterLane(): void {
    this.#locked = 0;
  }

  next(world: Readonly<WorldState>, lane: Negibon): PlayerInput {
    // 盤面に誰もいなければ何もしない。選び直しの残りも構えの溜めも触らない（原型の L2370）。
    const foes = world.players.filter(isAlive);
    if (foes.length === 0) return IDLE_INPUT;
    this.#reaimIn -= 1;
    const spot = laneSpot(lane.along);

    if (foes.some((foe) => inLine(world, spot, foe))) {
      this.#locked += 1;
      if (this.#locked <= AIM_TICKS) return IDLE_INPUT; // 狙っている間は動かない
      this.#locked = 0;
      // まだ撃てなくても押す。そのときは何も起きず、狙い直しになる（原型と同じ）。
      return { ...IDLE_INPUT, bomb: true };
    }
    this.#locked = 0;

    if (this.#reaimIn <= 0) {
      this.#reaimIn = REAIM_TICKS;
      this.#direction = chooseDirection(lane.along, spot.position, foes);
    }
    return keysFor(spot, this.#direction);
  }
}

/** 相手が射線の上にいて、射程の内で、間に葱を止めるものが無いか（原型の L2378-2392）。 */
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
 * 進む向きを選ぶ（原型の L2405-2421）。
 *
 * いちばん近い相手のマスに向き合う4辺の位置から、外周を回っていちばん近いものを寄る先にする
 * （1周をまたぐ近道も考える）。寄る先までの残りが `SETTLE` 未満なら 0（止まる）。
 */
function chooseDirection(along: number, from: Point, foes: readonly PlayerState[]): -1 | 0 | 1 {
  let nearest = foes[0]!;
  let nearestDistance = Infinity;
  for (const foe of foes) {
    const d = Math.abs(foe.position.x - from.x) + Math.abs(foe.position.y - from.y);
    if (d < nearestDistance) {
      nearestDistance = d;
      nearest = foe;
    }
  }
  const candidates = alongsFacing(cellOf(nearest.position));
  let target = candidates[0];
  let targetDistance = Infinity;
  for (const candidate of candidates) {
    const d = Math.abs(shortestWay(along, candidate));
    if (d < targetDistance) {
      targetDistance = d;
      target = candidate;
    }
  }
  const way = shortestWay(along, target);
  if (Math.abs(way) < SETTLE) return 0;
  return way > 0 ? 1 : -1;
}

/** `from` から `to` へ外周を回るときの、符号つきの近いほうの道のり。 */
function shortestWay(from: number, to: number): number {
  let diff = to - from;
  if (diff > LANE_LENGTH / 2) diff -= LANE_LENGTH;
  if (diff < -LANE_LENGTH / 2) diff += LANE_LENGTH;
  return diff;
}

/**
 * 外周をその向きへ進むために押す向き。
 *
 * どの辺で何を押すとどちらへ進むかは、人間の操作と同じ変換（`laneStep`）から逆に引く。
 * 別に表を持つと、人間と CPU で外周の進み方が食い違ったときに気づけない。
 */
function keysFor(spot: LaneSpot, direction: -1 | 0 | 1): PlayerInput {
  if (direction === 0) return IDLE_INPUT;
  for (const key of DIRECTIONS) {
    const playerInput = { ...IDLE_INPUT, [key]: true };
    if (laneStep(spot.side, playerInput) === direction) return playerInput;
  }
  return IDLE_INPUT;
}
