import { lookOf } from '../../content/animals.js';
import { SCATTER_TIME } from '../../domain/abilities/rabbit/ScatterActor.js';
import { abilityOf } from '../../domain/abilities/registry.js';
import type { PlayerState } from '../../domain/state/PlayerState.js';
import { drawAnimalBody } from './animals/body.js';
import { NEUTRAL_POSE, type BodyPose } from './animals/painters.js';
import { scatteringPose } from './animals/rabbit.js';
import { actionLookOf } from './animals/registry.js';
import { statusIcons } from './effectIcons.js';
import type { Frame } from './Frame.js';
import { FULL_TURN } from './Frame.js';
import { screenX, screenY } from './Layout.js';
import type { PlayerView } from './PlayerView.js';

/** 無敵中の点滅の速さ（1秒あたりに切り替わる回数）。 */
const BLINK_RATE = 14;
/** 点滅で薄くなっている間の透明度。 */
const BLINK_ALPHA = 0.35;

/** 足元に並べる絵文字の数の上限。多く並べると隣のマスまではみ出す。 */
const MAX_ICONS = 3;

/**
 * プレイヤーを1人描く。
 *
 * 描く順は、技の最中に体の下へ出すもの（舌・掘りかけの穴）→ 影と足元の輪 → 体
 * → 技の最中に体の上へ出すもの → とくぎの溜めのゲージ → 足元の絵文字。
 *
 * 名前のラベルは描かない。体に被って邪魔になる。誰がどれかは足元の輪の色で分かる
 * （原型の判断）。
 */
export function drawPlayer(frame: Frame, view: PlayerView): void {
  const { g, layout } = frame;
  const tile = layout.tile;
  const player = view.player;
  const look = lookOf(player.animal);
  const action = player.action === null ? undefined : actionLookOf(player.action.kind);
  const x = screenX(layout, view.x);
  const y = screenY(layout, view.y);

  action?.drawUnder?.(frame, view, x, y);

  g.save();
  // ⚠️ 点滅していないときも必ず代入する。体の中の半透明の部分は、
  // この値に掛けて描くため。
  const blinkOff = view.invulnerable && Math.floor(frame.time * BLINK_RATE) % 2 === 0;
  g.globalAlpha = blinkOff ? BLINK_ALPHA : 1;
  drawFootprint(g, tile, look.color, look.shade, x, y);

  g.save();
  g.translate(x, y);
  drawAnimalBody(g, tile, {
    look,
    facing: player.facing,
    walked: player.walked,
    moving: view.moving,
    pose: action?.pose?.(frame) ?? effectPose(frame, player) ?? NEUTRAL_POSE,
  });
  g.restore();

  action?.drawOver?.(frame, view, x, y);
  drawHoldGauge(g, tile, player, x, y);
  drawIcons(g, tile, statusIcons(player, action?.icon), x, y);
  g.restore();
}

/** 跳び上がっている（'leap'）長さ。ルールの層の長さ（きつねのとくぎで 1 秒）と揃える。 */
const LEAP_TICKS = 60;

/**
 * 一時的な状態がつくる姿勢。どちらも無ければ null。
 *
 * - 跳び上がっている（'leap'）… 山なりに跳んで1回転する（原型のキツネ跳びの絵）
 * - 撒いている（'scattering'）… 腰を落として細かく震える（原型のブリブリ）
 */
function effectPose(frame: Frame, player: PlayerState): BodyPose | null {
  const leap = player.effects.remaining('leap');
  if (leap > 0) {
    const k = Math.min(1, Math.max(0, 1 - leap / LEAP_TICKS));
    return { drop: -Math.sin(k * Math.PI) * 0.62, tilt: k * FULL_TURN, squash: 1 };
  }
  const scattering = player.effects.remaining('scattering');
  if (scattering > 0) return scatteringPose(frame, Math.min(1, Math.max(0, 1 - scattering / SCATTER_TIME)));
  return null;
}

/**
 * 接地の影と、足元の色の輪。
 *
 * 輪は地面に貼り付いた楕円にする。背後に丸い板を敷くと、動物がカプセルに
 * 入っているように見えるので使わない（原型の判断）。
 */
function drawFootprint(
  g: CanvasRenderingContext2D,
  tile: number,
  color: string,
  shade: string,
  x: number,
  y: number,
): void {
  g.fillStyle = 'rgba(0,0,0,.38)';
  g.beginPath();
  g.ellipse(x, y + tile * 0.32, tile * 0.29, tile * 0.1, 0, 0, FULL_TURN);
  g.fill();
  for (const [style, width] of [
    [shade, 4.5],
    [color, 2.4],
  ] as const) {
    g.strokeStyle = style;
    g.lineWidth = width;
    g.beginPath();
    g.ellipse(x, y + tile * 0.3, tile * 0.28, tile * 0.105, 0, 0, FULL_TURN);
    g.stroke();
  }
}

/**
 * とくぎの長押しのゲージ。溜まり切ると出るので、押している手応えを見せる。
 *
 * 出た後も押し続けると、押している長さは伸び続ける。そのままでは満タンの
 * ゲージが残るので、しきい値を越えたら消す（原型も出た後は消していた）。
 */
function drawHoldGauge(g: CanvasRenderingContext2D, tile: number, player: PlayerState, x: number, y: number): void {
  if (player.specialCharges <= 0 || player.actionHeld <= 0) return;
  // ⚠️ 技の最中はゲームの側がボタンを見ないので、押した長さが満タンのまま残る。
  // そのまま描くと、次のとくぎが出せるように見える。
  if (player.action !== null) return;
  const hold = abilityOf(player.animal).holdTicks;
  if (player.actionHeld > hold) return;
  const k = Math.min(1, player.actionHeld / hold);
  const width = tile * 0.62;
  const height = 3.4;
  const gx = x - width / 2;
  const gy = y - tile * 1.18;
  g.fillStyle = 'rgba(0,0,0,.55)';
  g.fillRect(gx - 1, gy - 1, width + 2, height + 2);
  g.fillStyle = k >= 1 ? '#ffe27a' : '#ff9a3c';
  g.fillRect(gx, gy, width * k, height);
}

/** 足元の絵文字を、先頭から上限の数まで並べる。 */
function drawIcons(g: CanvasRenderingContext2D, tile: number, icons: readonly string[], x: number, y: number): void {
  if (icons.length === 0) return;
  g.font = `${Math.floor(tile * 0.34)}px system-ui`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(icons.slice(0, MAX_ICONS).join(''), x, y + tile * 0.42);
}
