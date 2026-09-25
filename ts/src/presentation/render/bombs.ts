import { TICKS_PER_SECOND } from '../../domain/core/Tick.js';
import { BLAST_DURATION, BOMB_FUSE } from '../../domain/rules/tuning.js';
import type { Blast, Bomb } from '../../domain/state/Bomb.js';
import type { Frame } from './Frame.js';
import { FULL_TURN } from './Frame.js';
import { cellCenter, screenX, screenY } from './Layout.js';

/**
 * 爆弾を描く。
 *
 * 絵文字では色が薄く床に埋もれるので手描きにしてある。爆発が近づくほど
 * 速く大きく脈打ち、赤く熱を持つ。
 */
export function drawBomb(frame: Frame, bomb: Bomb): void {
  const { g, layout, time } = frame;
  const size = layout.tile;
  // 置いた直後が 0、爆発の瞬間が 1。
  const k = Math.max(0, Math.min(1, 1 - bomb.fuse / BOMB_FUSE));
  // ⚠️ 位相は置いてからの時間で作る。原型はラウンドの経過時間に、爆発が近づくほど
  // 上がる周波数を掛けていた。そのため経過時間が長いほど1 tick あたりの位相の飛びが
  // 大きくなり、10 秒を過ぎたあたりから脈打ちが毎フレームばらばらに跳ねた。
  const lit = (BOMB_FUSE - bomb.fuse) / TICKS_PER_SECOND;
  const pulse = 1 + Math.sin(lit * (9 + k * 26)) * 0.13 * (0.5 + k);

  g.save();
  const center = cellCenter(layout, bomb.cell);
  g.translate(center.x, center.y);
  g.scale(pulse, pulse);

  // 床に落ちる影。
  g.fillStyle = 'rgba(0,0,0,.5)';
  g.beginPath();
  g.ellipse(0, size * 0.31, size * 0.33, size * 0.12, 0, 0, FULL_TURN);
  g.fill();

  // 爆発の直前だけ、まわりに赤い光を出す。
  if (k > 0.62) {
    g.globalAlpha = (0.3 + 0.4 * Math.abs(Math.sin(time * 30))) * ((k - 0.62) / 0.38);
    g.fillStyle = '#ff2f00';
    g.beginPath();
    g.arc(0, size * 0.03, size * 0.52, 0, FULL_TURN);
    g.fill();
    g.globalAlpha = 1;
  }

  // 本体の黒い球。
  const body = g.createRadialGradient(-size * 0.11, -size * 0.13, size * 0.03, 0, size * 0.03, size * 0.4);
  body.addColorStop(0, '#7d7d8c');
  body.addColorStop(0.4, '#31313c');
  body.addColorStop(0.85, '#12121a');
  body.addColorStop(1, '#000');
  g.fillStyle = body;
  g.beginPath();
  g.arc(0, size * 0.04, size * 0.34, 0, FULL_TURN);
  g.fill();

  // 後半は赤く熱を持つ。
  if (k > 0.5) {
    g.globalAlpha = (k - 0.5) * 1.5 * Math.abs(Math.sin(time * 22));
    g.fillStyle = '#ff4013';
    g.beginPath();
    g.arc(0, size * 0.04, size * 0.34, 0, FULL_TURN);
    g.fill();
    g.globalAlpha = 1;
  }

  // 照り。
  g.fillStyle = 'rgba(255,255,255,.6)';
  g.beginPath();
  g.ellipse(-size * 0.12, -size * 0.09, size * 0.075, size * 0.05, -0.5, 0, FULL_TURN);
  g.fill();

  drawFuse(g, size, time);
  g.restore();
}

/** 導火線と、その先の火花。原点は爆弾の中心に置いてある前提。 */
function drawFuse(g: CanvasRenderingContext2D, size: number, time: number): void {
  g.strokeStyle = '#d8b189';
  g.lineWidth = 2.6;
  g.lineCap = 'round';
  g.beginPath();
  g.moveTo(size * 0.09, -size * 0.25);
  g.quadraticCurveTo(size * 0.3, -size * 0.36, size * 0.17, -size * 0.47);
  g.stroke();

  const spark = 0.5 + 0.5 * Math.sin(time * 28);
  g.fillStyle = '#ff8a1e';
  g.beginPath();
  g.arc(size * 0.17, -size * 0.49, size * (0.07 + 0.05 * spark), 0, FULL_TURN);
  g.fill();
  g.fillStyle = '#fffbe0';
  g.beginPath();
  g.arc(size * 0.17, -size * 0.49, size * (0.03 + 0.02 * spark), 0, FULL_TURN);
  g.fill();
}

/**
 * 爆風の1マスを描く。
 *
 * 薄いと迫力が出ないので、マスをまるごと赤く塗ってから白熱した芯を重ねる。
 * 出た直後に芯が膨らみ、消える間際に全体が薄れる。
 */
export function drawBlast(frame: Frame, blast: Blast): void {
  const { g, layout } = frame;
  const size = layout.tile;
  // 出た直後が 1、消える瞬間が 0。
  const k = Math.max(0, Math.min(1, blast.remaining / BLAST_DURATION));
  const grow = Math.min(1, (1 - k) * 4.5);
  const x = screenX(layout, blast.cell.col);
  const y = screenY(layout, blast.cell.row);
  const { x: cx, y: cy } = cellCenter(layout, blast.cell);

  g.save();

  // 下地。マスをまるごと燃やす。
  g.globalAlpha = Math.min(1, k * 2.4);
  g.fillStyle = '#e63a05';
  g.fillRect(x, y, size, size);

  // 炎の芯。マスより大きく描いて、隣の爆風マスと継ぎ目なくつなげる。
  g.globalAlpha = Math.min(1, k * 2.8);
  const span = size * (0.6 + 0.62 * grow);
  const core = g.createRadialGradient(cx, cy, 1, cx, cy, span * 0.62);
  core.addColorStop(0, '#ffffff');
  core.addColorStop(0.22, '#fff6a8');
  core.addColorStop(0.48, '#ffc21e');
  core.addColorStop(0.76, '#ff5a08');
  core.addColorStop(1, 'rgba(170,25,0,0)');
  g.fillStyle = core;
  g.fillRect(cx - span / 2, cy - span / 2, span, span);

  // ちらつく白い芯。
  g.globalAlpha = Math.min(1, k * 2) * 0.65;
  g.fillStyle = '#fffdf0';
  const flicker = size * (0.16 + 0.2 * frame.cosmetic.next()) * k;
  g.fillRect(cx - flicker / 2, cy - flicker / 2, flicker, flicker);
  g.restore();
}
