import type { Cell } from '../../domain/core/Coord.js';
import { secondsToTicks, type Tick } from '../../domain/core/Tick.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { Item } from '../../domain/state/Item.js';
import type { Frame } from './Frame.js';
import { cellCenter, screenX, screenY } from './Layout.js';
import { roundRect } from './primitives.js';

/**
 * 札の色分け。
 *
 * - `good` … 拾うと得をするもの。黄色の枠
 * - `harmful` … 拾うと損をするもの。赤い枠にして一目で避けられるようにする
 * - `scattered` … とくぎで撒かれたもの（`Item.scatteredBy`）。桃色の枠にして、ふつうの損をする
 *   アイテムと見分ける
 */
export type BadgeTone = 'good' | 'harmful' | 'scattered';

interface ToneColors {
  /** 床へにじむ光の中心の色。 */
  readonly glow: string;
  /** 不透明な下地。 */
  readonly base: string;
  /** 下地に重ねる色味。 */
  readonly tint: string;
  /** 枠の色。末尾に不透明度を足して使う。 */
  readonly frameRgb: string;
  /** 枠の不透明度の下限と、脈打つ幅。 */
  readonly frameAlpha: number;
  readonly frameSwing: number;
}

const TONES: Readonly<Record<BadgeTone, ToneColors>> = {
  good: {
    glow: 'rgba(255,220,80,.6)',
    base: '#3b2705',
    tint: 'rgba(255,208,70,.38)',
    frameRgb: '255,228,120',
    frameAlpha: 0.7,
    frameSwing: 0.3,
  },
  harmful: {
    glow: 'rgba(255,80,70,.55)',
    base: '#48120f',
    tint: 'rgba(255,105,80,.34)',
    frameRgb: '255,115,90',
    frameAlpha: 0.7,
    frameSwing: 0.3,
  },
  scattered: {
    glow: 'rgba(255,150,200,.6)',
    base: '#4a1230',
    tint: 'rgba(255,150,200,.34)',
    frameRgb: '255,160,205',
    frameAlpha: 0.75,
    frameSwing: 0.25,
  },
};

/** 撒かれたアイテムが、消える前に点滅を始める残り時間。原型と同じ値。 */
const SCATTERED_BLINK = secondsToTicks(3.5);

/**
 * 盤面に落ちているアイテムを描く。
 *
 * とくぎで撒かれたものは桃色の枠にし、消える前の 3.5 秒は点滅させる（原型と同じ）。
 *
 * @param now いまの tick。撒かれたものの残り時間を出すのに使う
 */
export function drawItem(frame: Frame, item: Item, now: Tick): void {
  const definition = itemDefinition(item.kind);
  if (item.scatteredBy === undefined) {
    drawBadge(frame, item.cell, definition.emoji, definition.harmful ? 'harmful' : 'good', 1);
    return;
  }
  const left = item.expiresAt === undefined ? Infinity : item.expiresAt - now;
  const alpha = left < SCATTERED_BLINK ? 0.35 + 0.65 * Math.abs(Math.sin(frame.time * 9)) : 1;
  drawBadge(frame, item.cell, definition.emoji, 'scattered', alpha);
}

/**
 * マスの上に、枠つきの札に載せた絵文字を描く。
 *
 * アイテムは床に埋もれやすいので、濃い下地・脈打つ太い枠・黒い縁取りの絵文字で
 * 床から浮かせる。色分け（`BadgeTone`）だけを替えて、どのアイテムも同じ形で描く。
 *
 * @param alpha 札全体の不透明度。消える前の点滅に使う
 */
export function drawBadge(frame: Frame, cell: Cell, emoji: string, tone: BadgeTone, alpha: number): void {
  const { g, layout, time } = frame;
  const size = layout.tile;
  const x = screenX(layout, cell.col);
  const y = screenY(layout, cell.row);
  const { x: cx, y: cy } = cellCenter(layout, cell);
  const colors = TONES[tone];
  // マスごとに位相をずらし、並んだアイテムが揃って動かないようにする。
  const bob = Math.sin(time * 4 + cell.col + cell.row) * 2;
  const pulse = 0.5 + 0.5 * Math.sin(time * 3.6 + cell.col * 0.7 + cell.row * 0.4);

  g.save();
  g.globalAlpha = alpha;

  // 床へにじむ光。
  const glow = g.createRadialGradient(cx, cy, 1, cx, cy, size * 0.66);
  glow.addColorStop(0, colors.glow);
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = glow;
  g.fillRect(x - size * 0.15, y - size * 0.15, size * 1.3, size * 1.3);

  // 濃い下地。床の色が透けると絵文字が沈むので、先に不透明で塗る。
  g.fillStyle = colors.base;
  roundRect(g, x + 3, y + 3, size - 6, size - 6, 9);
  g.fill();
  g.fillStyle = colors.tint;
  roundRect(g, x + 3, y + 3, size - 6, size - 6, 9);
  g.fill();

  // 脈打つ太い枠と、その外側の黒い細枠。
  g.lineWidth = 3.2;
  g.strokeStyle = `rgba(${colors.frameRgb},${colors.frameAlpha + colors.frameSwing * pulse})`;
  roundRect(g, x + 3, y + 3, size - 6, size - 6, 9);
  g.stroke();
  g.lineWidth = 1.2;
  g.strokeStyle = 'rgba(0,0,0,.5)';
  roundRect(g, x + 2, y + 2, size - 4, size - 4, 10);
  g.stroke();

  // 黒い縁取りつきの絵文字。
  g.font = `${Math.floor(size * 0.62)}px system-ui`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.lineWidth = 3.5;
  g.strokeStyle = 'rgba(0,0,0,.7)';
  g.lineJoin = 'round';
  g.strokeText(emoji, cx, cy + bob);
  g.fillText(emoji, cx, cy + bob);
  g.restore();
}
