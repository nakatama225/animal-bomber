import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { IDLE_INPUT, type PlayerInput } from '../input/PlayerInput.js';
import { lanesOpen } from '../mutations/negibon.js';
import { laneSpot, laneStep, wrapAlong } from '../negibon/lane.js';
import { LeekActor } from '../negibon/LeekActor.js';
import { LANE_SPEED, LEEK_COOLDOWN } from '../rules/negibon.js';
import { OUT } from '../state/Life.js';
import type { PlayerState } from '../state/PlayerState.js';
import { justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 外周にいる葱ボンを動かし、葱を撃たせる。残り時間が短くなったら外周を閉じる。
 *
 * 葱ボンは、盤面の上の処理（移動・爆弾・技・被弾）に関わらない。
 * それらの System は盤面にいるかどうか（`isAlive`）で最初に外すので、
 * 葱ボンのための分岐を足していない。
 * 例外は、盤面を離れても残す振る舞い（`ActiveAction.staysOffBoard`）だけ。技の System は、それを持つプレイヤーを
 * 外周へ回ったあとも退場したあとも外さない。振る舞いを進める所では進めずに止めておき、焼けたかを見る所では
 * 爆風に触れたかを見続ける（`docs/04-葱ボンと延長戦.md`）。
 *
 * 飛んでいる葱は自律物（`LeekActor`）として `ActorSystem` が進める。
 */
export class NegibonSystem {
  /**
   * 残り時間が短くなっていたら、外周を閉じる。1 tick の最後（被弾と、振る舞いが爆風に触れたかを見たあと）に呼ぶ。
   *
   * 原型の L4405 → L4411 と同じ位置にするため。原型は update の最後の checkEnd の頭で外周を閉じる
   * （negibonCutoff）。そのため閉じる tick の中でも、それより前の入力の輪（L4333-4338）で外周のプレイヤーは動いて撃ち、
   * 飛んでいる葱（L4346）は進んで当たる（当たった相手は外周へ回り、同じ tick の最後に退場する）。
   */
  closeIfDue(world: WorldState): SimEvent[] {
    return lanesOpen(world) ? [] : closeLanes(world);
  }

  /**
   * 1人ぶん。外周にいるプレイヤーを動かし、葱を撃たせる。
   *
   * 盤面のプレイヤーが動く番と同じ番に、番号の順に呼ぶ（原型の update も、入力の処理の中で
   * 外周のプレイヤーを動かす）。
   *
   * 残り時間は見ない。原型の外周の操作（humanUpdate の L4072-4087）も時刻を見ないのと同じ。外周が閉じれば
   * 外周のプレイヤーは退場しているので、外周にいるか（`life`）を見るだけで足りる。
   */
  stepFor(world: WorldState, player: PlayerState, playerInput: PlayerInput = IDLE_INPUT): SimEvent[] {
    const life = player.life;
    if (life.kind !== 'negibon') return [];

    const along = wrapAlong(life.along + laneStep(laneSpot(life.along).side, playerInput) * LANE_SPEED);
    let readyAt = life.readyAt;
    const events: SimEvent[] = [];
    // 動いてから撃つ。撃つ位置は動いたあとの位置になる。
    if (wantsToThrow(player, playerInput) && world.now >= readyAt) {
      const spot = laneSpot(along);
      world.actors.push(new LeekActor(spot.position, spot.facing, player.id));
      readyAt = tick(world.now + LEEK_COOLDOWN);
      events.push({ type: 'leekThrown', player: player.id, from: { ...spot.position }, facing: spot.facing });
    }
    // 値は書き換えず、丸ごと差し替える（`Life` の約束）。
    player.life = { kind: 'negibon', along, readyAt };
    return events;
  }
}

/** 爆弾と技のどちらのボタンでも撃てる。押した瞬間に1回だけ。 */
function wantsToThrow(player: PlayerState, playerInput: PlayerInput): boolean {
  return justPressed(player, playerInput, 'bomb') || justPressed(player, playerInput, 'action');
}

/**
 * 外周を閉じる。外周にいる全員を退場させ、飛んでいる葱を消す。
 *
 * 外周にだれもいなければ何もしない（知らせも出さない）。原型の L2362 と同じ。閉じる tick に倒れたプレイヤーは、
 * 外周へ回らずにその場で退場している（`lanesOpen`）ので、外周にほかにだれもいなければ知らせは出ない。
 * 閉じたあとに倒れたプレイヤーは外周へ回らないので、閉じる処理が2度走ってもイベントは1度しか出ない。
 */
function closeLanes(world: WorldState): SimEvent[] {
  const closing = world.players.filter((player) => player.life.kind === 'negibon');
  if (closing.length === 0) return [];
  for (const player of closing) player.life = OUT;
  world.actors = world.actors.filter((actor) => !(actor instanceof LeekActor));
  return [{ type: 'lanesClosed', players: closing.map((player) => player.id) }];
}
