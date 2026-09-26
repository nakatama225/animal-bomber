import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { IDLE_INTENT, type PlayerIntent } from '../intent/PlayerIntent.js';
import { lanesOpen } from '../mutations/negibon.js';
import { laneSpot, laneStep, wrapAlong } from '../negibon/lane.js';
import { LeekActor } from '../negibon/LeekActor.js';
import { LANE_SPEED, LEEK_COOLDOWN } from '../rules/negibon.js';
import { OUT } from '../state/Life.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 外周にいる葱ボンを動かし、葱を撃たせる。残り時間が短くなったら外周を閉じる。
 *
 * 葱ボンは、盤面の上の処理（移動・爆弾・技・被弾）のどれにも関わらない。
 * それらの System は盤面にいるかどうか（`isAlive`）で最初に外すので、
 * 葱ボンのための分岐を足していない。
 *
 * 飛んでいる葱は自律物（`LeekActor`）として `ActorSystem` が進める。
 */
export class NegibonSystem {
  step(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): SimEvent[] {
    if (!lanesOpen(world)) return closeLanes(world);

    const events: SimEvent[] = [];
    for (const player of world.players) {
      const life = player.life;
      if (life.kind !== 'negibon') continue;
      const intent = intents.get(player.id) ?? IDLE_INTENT;

      const along = wrapAlong(life.along + laneStep(laneSpot(life.along).side, intent) * LANE_SPEED);
      let readyAt = life.readyAt;
      // 動いてから撃つ。撃つ位置は動いたあとの位置になる。
      if (wantsToThrow(player, intent) && world.now >= readyAt) {
        const spot = laneSpot(along);
        world.actors.push(new LeekActor(spot.position, spot.facing, player.id));
        readyAt = tick(world.now + LEEK_COOLDOWN);
        events.push({ type: 'leekThrown', player: player.id, from: { ...spot.position }, facing: spot.facing });
      }
      // 値は書き換えず、丸ごと差し替える（`Life` の約束）。
      player.life = { kind: 'negibon', along, readyAt };
    }
    return events;
  }
}

/** 爆弾と技のどちらのボタンでも撃てる。押した瞬間に1回だけ。 */
function wantsToThrow(player: PlayerState, intent: PlayerIntent): boolean {
  return justPressed(player, intent, 'bomb') || justPressed(player, intent, 'action');
}

/**
 * 外周を閉じる。外周にいる全員を退場させ、飛んでいる葱を消す。
 *
 * 外周にだれもいなければ何もしない。閉じたあとに倒れた人は外周へ回らないので、
 * 閉じる処理が2度走ってもイベントは1度しか出ない。
 */
function closeLanes(world: WorldState): SimEvent[] {
  const closing = world.players.filter((player) => player.life.kind === 'negibon');
  if (closing.length === 0) return [];
  for (const player of closing) player.life = OUT;
  world.actors = world.actors.filter((actor) => !(actor instanceof LeekActor));
  return [{ type: 'lanesClosed', players: closing.map((player) => player.id) }];
}
