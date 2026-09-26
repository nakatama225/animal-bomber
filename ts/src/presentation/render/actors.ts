import type { WorldActor } from '../../domain/abilities/WorldActor.js';
import { FoxfireActor } from '../../domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../domain/abilities/frog/SlimeBombActor.js';
import { ScatteredActor } from '../../domain/abilities/rabbit/ScatterAction.js';
import { secondsToTicks } from '../../domain/core/Tick.js';
import { LeekActor } from '../../domain/negibon/LeekActor.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { Frame } from './Frame.js';
import { FULL_TURN } from './Frame.js';
import { drawBadge } from './items.js';
import { screenX, screenY } from './Layout.js';
import { drawLeek } from './negibon.js';
import { drawSlime } from './slime.js';

/** 撒かれた障害物が、消える前に点滅を始める残り時間。原型と同じ値。 */
const SCATTERED_BLINK = secondsToTicks(3.5);

/**
 * 床に置かれる自律物を、爆弾より下に描く。
 *
 * Renderer はすべての自律物についてこれを呼ぶ。床に置かれないものは何も描かずに返す。
 * 落とし穴もここでは描かない。見えていると誰も踏まないので、仕掛けた本人にも見せない。
 */
export function drawGroundActor(frame: Frame, actor: WorldActor): void {
  if (!(actor instanceof ScatteredActor)) return;
  let alpha = 1;
  if (actor.remaining < SCATTERED_BLINK) alpha = 0.35 + 0.65 * Math.abs(Math.sin(frame.time * 9));
  drawBadge(frame, actor.cell, itemDefinition('poop').emoji, 'scattered', alpha);
}

/**
 * 宙を飛ぶ自律物を、プレイヤーより上に描く。
 *
 * Renderer はすべての自律物についてこれを呼ぶ。宙を飛ばないものは何も描かずに返す。
 */
export function drawAirActor(frame: Frame, actor: WorldActor): void {
  if (actor instanceof FoxfireActor) drawFoxfire(frame, actor);
  else if (actor instanceof SlimeBombActor) drawSlime(frame, actor.cell, actor.sinceLanding, actor.hopsLeft);
  else if (actor instanceof LeekActor) drawLeek(frame, actor.position, actor.facing);
}

/**
 * 追いかける炎の先端を描く。
 *
 * 位置はマスの中央を含む連続座標なので、マスの半分を足さずにそのまま画面へ移す。
 * 通った跡は粒子の側（`ParticleField`）で出している。
 */
function drawFoxfire(frame: Frame, actor: FoxfireActor): void {
  const { g, layout, time } = frame;
  const size = layout.tile;
  const x = screenX(layout, actor.position.x);
  const y = screenY(layout, actor.position.y);
  const flare = 0.85 + 0.15 * Math.sin(time * 22);

  g.save();
  const flame = g.createRadialGradient(x, y, 1, x, y, size * 0.6 * flare);
  flame.addColorStop(0, '#ffffff');
  flame.addColorStop(0.24, '#e4faff');
  flame.addColorStop(0.5, '#5cc4ff');
  flame.addColorStop(0.78, '#1f5fe0');
  flame.addColorStop(1, 'rgba(12,30,120,0)');
  g.fillStyle = flame;
  g.beginPath();
  g.arc(x, y, size * 0.6 * flare, 0, FULL_TURN);
  g.fill();

  // 揺らぐ白い芯。
  g.globalAlpha = 0.9;
  g.fillStyle = '#fff';
  const core = size * (0.1 + 0.05 * Math.sin(time * 30));
  g.beginPath();
  g.ellipse(x, y - size * 0.04, core * 0.7, core * 1.15, 0, 0, FULL_TURN);
  g.fill();
  g.restore();
}
