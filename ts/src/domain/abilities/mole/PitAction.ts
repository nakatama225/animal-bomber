import { cellOf, sameCell, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { PlayerId } from '../../state/PlayerState.js';
import type { PlayerState } from '../../state/PlayerState.js';
import { isAlive } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { ActiveAction } from '../ActiveAction.js';
import { ACTOR_TURNS, type WorldActor } from '../WorldActor.js';

/** 掘り終わるまでの長さ。 */
const DIG_TIME: Tick = tick(90);

/** 落ちた相手が動けない長さ。 */
const HOLD_TIME: Tick = tick(180);

/** 穴を掘れる動物。掘れる側は、誰の穴にも落ちない。 */
const DIGGER = 'mole';

/** そのマスに掘られている落とし穴。無ければ undefined。 */
export function pitAt(world: Readonly<WorldState>, cell: Cell): PitActor | undefined {
  // ⚠️ 型で探す。actor の encode の文字列の頭で探すと、同じ形の encode を持つ
  // 別の actor（撒く本体・跳ねる爆弾）まで穴と見なす。
  return world.actors.find(
    (actor): actor is PitActor => actor instanceof PitActor && sameCell(actor.cell, cell),
  );
}

/**
 * 掘られた落とし穴。
 *
 * ⚠️ 盤面には見えない。踏むまで存在が分からないのがこの技の要点で、
 * 見えていると誰も踏まない。
 *
 * もぐら（掘れる側）は、自分の穴にもほかのもぐらの穴にも落ちない（原型の pitfallCheck）。
 * 自分の穴で自分が止まると、掘る判断がそもそも成り立たなくなる。
 *
 * 落ちたプレイヤーには 'pitfall' をかける。たまねぎの 'stun' と同じく動けないが、
 * はまっている間は爆弾を置けない（`canPlaceBomb`）。泣いている間は置ける。
 * はまっている間は、別の穴の上を通っても落ちない。その穴は残る。
 *
 * 穴に寿命は無い。消えるのは誰かが落ちたときと、ラウンドが始まり直すとき（延長戦も含む）だけ
 * （原型も同じ）。
 */
export class PitActor implements WorldActor {
  readonly kind = 'pit';
  readonly turn = ACTOR_TURNS.pit;

  constructor(
    readonly cell: Cell,
    readonly owner: PlayerId,
  ) {}

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    for (const player of world.players) {
      if (player.animal === DIGGER || !isAlive(player)) continue;
      // ⚠️ 落とし穴の印だけを見る。泣いている（'stun'）かは見ない。泣いている相手は原型でも落ちる。
      if (player.effects.has('pitfall')) continue;
      if (!sameCell(cellOf(player.position), this.cell)) continue;
      return { events: this.#trap(world, player), done: true };
    }
    return { events: [], done: false };
  }

  /** 落ちたプレイヤーを止める。穴は埋まる（この actor は終わる）。 */
  #trap(world: WorldState, player: PlayerState): SimEvent[] {
    // 上限を同じ長さにする。はまっている間は別の穴に落ちないので、足し算になる場面は無い。
    player.effects.add('pitfall', HOLD_TIME, HOLD_TIME);
    // 滑っている最中でも止まる。滑りを残すと、穴が切れたとたんに滑り出す。
    player.effects.clear('slide');
    const events: SimEvent[] = [{ type: 'effectApplied', target: player.id, effect: 'pitfall' }];
    // 位置を決める振る舞い（掘る・舌・突進）は打ち切る。穴は無敵でも避けられない。
    // 打ち切るときも後始末は呼ぶ（抱えていたものを撒く、など。`ActiveAction.finish`）。
    // 動きを乗っ取らない振る舞いは続く（いまの動物には無い。撒くのは盤面の側の物なので、穴に落ちても続く）。
    // 原型も、穴に落ちて止めるのは掘る・舌・突進だけだった。
    const aborted = player.action;
    if (aborted?.drivesMovement === true) {
      player.action = null;
      if (aborted.finish !== undefined) events.push(...aborted.finish(world, player));
    }
    return events;
  }

  encode(): string {
    return `${this.cell.col},${this.cell.row},${this.owner}`;
  }
}

/**
 * そのマスに穴を掘り始められるか（原型の startDigPit）。
 *
 * 掘れないのは3つ。マスが空いていない（壊せるブロックの中）、すでに穴がある、爆弾がある。
 * ⚠️ アイテム（とくぎで撒かれたうんこも）の上には掘れる。原型が見るのもこの3つだけ。
 * ⚠️ 掘り始めの確認で、掘り終わりには使わない。掘り終わりは爆弾を見ない（`PitAction.finish`）。
 */
export function canDigAt(world: Readonly<WorldState>, cell: Cell): boolean {
  if (world.board.at(cell) !== 'empty') return false;
  if (pitAt(world, cell) !== undefined) return false;
  return bombAt(world, cell) === undefined;
}

/**
 * もぐらのとくぎ。足元に見えない穴を掘る。
 *
 * 掘っている間は動けない。仕掛ける側にも隙を持たせないと、
 * 逃げながら通り道に穴を並べられてしまう。
 *
 * 掘り始めたマスを覚えておき、押し出されてそこを離れたらやめる。穴はできない
 * （原型の updateDigging）。覚えておかないと、押された先のマスに穴ができる。
 */
export class PitAction implements ActiveAction {
  readonly kind = 'dig';
  readonly drivesMovement = true;
  readonly damageCap = null;
  readonly untouchable = false;
  readonly canPlaceBomb = false;
  /** 最中も技のボタンは有効だが、掘り直しはしない（`MOLE.onHold`。押すとチキンだけ減る）。 */
  readonly blocksButtons = false;
  readonly sweepsItems = false;

  #remaining: Tick = DIG_TIME;

  /** @param cell 掘り始めたマス。穴はここにできる */
  constructor(readonly cell: Cell) {}

  /** 掘り進んだ割合（0〜1）。描画のためだけに読む。状態も要約（ハッシュ）も変えない。 */
  get progress(): number {
    return Math.min(1, Math.max(0, 1 - this.#remaining / DIG_TIME));
  }

  tick(_world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    // 押し出されたらやめる。残りが 0 でないまま終わるので、finish は穴を作らない。
    if (!sameCell(cellOf(player.position), this.cell)) return { events: [], done: true };
    this.#remaining = tick(this.#remaining - 1);
    return { events: [], done: this.#remaining <= 0 };
  }

  /** 掘り終わった時点で穴が生まれる。途中で打ち切られたときは何も残らない。 */
  finish(world: WorldState, player: PlayerState): SimEvent[] {
    if (this.#remaining > 0) return [];
    // 掘り終わりにも確認し直す。2匹が同じマスを同時に掘ると、先に掘り終えた側の穴がもうある。
    // ⚠️ 確認し直すのはマスと穴の2つだけで、爆弾は見ない（原型の updateDigging）。掘っている間に
    // 同じマスへ爆弾を置かれても、その下に穴ができる。爆弾を見るのは掘り始め（`canDigAt`）だけ。
    if (world.board.at(this.cell) !== 'empty' || pitAt(world, this.cell) !== undefined) return [];
    world.actors.push(new PitActor(this.cell, player.id));
    // 掘り終えた音のため。どのマスかは知らせない（見えないはずの穴がばれる）。
    return [{ type: 'techniqueMoment', player: player.id, moment: 'pitDug' }];
  }
}
