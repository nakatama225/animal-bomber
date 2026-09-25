import type { AnimalLook } from '../../../content/animals.js';
import type { Direction } from '../../../domain/core/Coord.js';
import { outline, roundRect } from '../primitives.js';
import type { BodyPose, HeadMode } from './painters.js';
import { fillCircle, fillEllipse } from './parts.js';
import { headPainterOf } from './registry.js';

/** 歩いた距離（マス）あたりの、脚の振りの位相の進み。 */
const WALK_FREQUENCY = 5.6;

/** 体を描くのに要るもの。 */
export interface BodyState {
  readonly look: AnimalLook;
  readonly facing: Direction;
  /** 歩いた距離の合計（マス）。脚の振りの位相に使う。 */
  readonly walked: number;
  /** 歩いている最中か。止まっている間は脚を動かさない。 */
  readonly moving: boolean;
  readonly pose: BodyPose;
}

/** 胴の寸法と、脚・腕の振り。部位ごとの描く関数に渡す。 */
interface BodyShape {
  readonly side: boolean;
  readonly back: boolean;
  readonly width: number;
  readonly height: number;
  /** 胴の中心の高さ。 */
  readonly centerY: number;
  /** 脚と腕の振り（-1〜1）。止まっていれば 0。 */
  readonly swing: number;
}

/**
 * 2頭身の体を描く。原点は足元の中央で、呼ぶ側で平行移動しておく。
 *
 * 下向きは顔が見え、上向きは後頭部、左右は横向きになる。歩くと脚が交互に出て体が弾む。
 * 横向きは右向きだけを描き、左向きは左右を反転する。
 */
export function drawAnimalBody(g: CanvasRenderingContext2D, tile: number, body: BodyState): void {
  const { look, facing, pose } = body;
  const build = look.build;
  const side = facing === 'left' || facing === 'right';
  const back = facing === 'up';

  const phase = Math.sin(body.walked * WALK_FREQUENCY);
  const swing = body.moving ? phase : 0;
  const bounce = body.moving ? Math.abs(phase) * tile * 0.045 : 0;

  const headR = tile * 0.29 * build.head;
  const width = (side ? tile * 0.21 : tile * 0.28) * build.bodyWidth;
  const height = tile * 0.22 * build.bodyHeight;
  const centerY = -tile * 0.1 - bounce + pose.drop * tile;
  const shape: BodyShape = { side, back, width, height, centerY, swing };

  g.save();
  // 足元を軸に傾け、縦に伸び縮みさせる。
  if (pose.tilt !== 0 || pose.squash !== 1) {
    g.rotate(pose.tilt);
    g.scale(1 / pose.squash, pose.squash);
  }
  if (facing === 'left') g.scale(-1, 1);

  // 尻尾は体より奥にあるので先に描く。
  drawTail(g, look, shape);
  drawLegs(g, tile, look, shape);
  drawTorso(g, look, shape);
  drawArms(g, tile, look, shape);

  const mode: HeadMode = back ? 'back' : side ? 'side' : 'front';
  const headY = centerY - height * 0.5 - headR * 0.82;
  headPainterOf(look.key)(g, 0, headY, headR, mode, { color: look.color, shade: look.shade, fur: build.fur });
  g.restore();
}

/** 脚を2本。横向きは前後に、正面と背面は上下に動かす。 */
function drawLegs(g: CanvasRenderingContext2D, tile: number, look: AnimalLook, shape: BodyShape): void {
  const build = look.build;
  const legW = tile * 0.095 * build.bodyWidth;
  const legH = tile * 0.13 * build.legHeight;
  const legX = (shape.side ? tile * 0.045 : tile * 0.1) * build.bodyWidth;
  const top = shape.centerY + shape.height * 0.42;
  g.fillStyle = look.shade;
  for (const sign of [-1, 1]) {
    const forward = shape.side ? sign * shape.swing * tile * 0.11 : 0;
    const lift = shape.side ? 0 : Math.max(0, sign * shape.swing) * tile * 0.05;
    roundRect(g, sign * legX - legW / 2 + forward, top - lift, legW, legH, legW * 0.45);
    g.fill();
    outline(g, 1.6);
    if (build.bigFeet) {
      fillEllipse(g, sign * legX + forward, top - lift + legH, legW * 0.85, legW * 0.42);
      outline(g, 1.4);
    }
  }
}

/** 胴。上から下へ体の色から影の色へ塗り、正面と横向きはお腹を明るくする。 */
function drawTorso(g: CanvasRenderingContext2D, look: AnimalLook, shape: BodyShape): void {
  const { width, height, centerY } = shape;
  const gradient = g.createLinearGradient(0, centerY - height, 0, centerY + height);
  gradient.addColorStop(0, look.color);
  gradient.addColorStop(1, look.shade);
  g.fillStyle = gradient;
  fillEllipse(g, 0, centerY, width * 0.56, height * 0.68);
  outline(g, 2);
  if (shape.back) return;

  // ⚠️ 透明度は今の値に掛け、終わったら元の値に戻す。1 に戻すと、無敵の点滅で
  // 下げた透明度がこの後に描く腕と頭で消える（原型の書き方ではそうなっていた）。
  const alpha = g.globalAlpha;
  g.globalAlpha = alpha * 0.85;
  g.fillStyle = look.build.fur;
  fillEllipse(g, shape.side ? width * 0.12 : 0, centerY + height * 0.14, width * 0.3, height * 0.4);
  g.globalAlpha = alpha;
}

/** 腕。横向きは手前の1本だけ描く。 */
function drawArms(g: CanvasRenderingContext2D, tile: number, look: AnimalLook, shape: BodyShape): void {
  const armW = tile * 0.075 * look.build.bodyWidth;
  const armH = tile * 0.11;
  const armX = shape.width * 0.56 + armW * 0.15;
  g.fillStyle = look.shade;
  for (const sign of shape.side ? [1] : [-1, 1]) {
    const sway = shape.side ? -shape.swing * tile * 0.09 : Math.max(0, -sign * shape.swing) * tile * 0.045;
    roundRect(g, sign * armX - armW / 2, shape.centerY - armH * 0.35 + sway, armW, armH, armW * 0.5);
    g.fill();
    outline(g, 1.5);
  }
}

/** 尻尾。正面からは体に隠れて見えないので、横向きと背面だけ描く。 */
function drawTail(g: CanvasRenderingContext2D, look: AnimalLook, shape: BodyShape): void {
  const kind = look.build.tail;
  if (kind === 'none' || (!shape.side && !shape.back)) return;
  const { width, height } = shape;
  const tx = shape.side ? -width * 0.6 : 0;
  const ty = shape.centerY + height * 0.16;

  switch (kind) {
    case 'bushy':
      // 太くて先が明るい。
      g.save();
      g.translate(tx, ty);
      g.rotate((shape.side ? 0.5 : 0) + shape.swing * 0.12);
      g.fillStyle = look.color;
      fillEllipse(g, -width * 0.3, 0, width * 0.46, height * 0.42, 0.3);
      outline(g, 1.8);
      g.fillStyle = look.build.fur;
      fillEllipse(g, -width * 0.62, height * 0.1, width * 0.2, height * 0.22, 0.3);
      g.restore();
      return;
    case 'ball':
      // 丸い綿毛。
      g.fillStyle = look.build.fur;
      fillCircle(g, tx - (shape.side ? width * 0.1 : 0), ty, height * 0.34);
      outline(g, 1.6);
      return;
    case 'thin':
      g.save();
      g.strokeStyle = look.shade;
      g.lineWidth = Math.max(1.6, height * 0.16);
      g.lineCap = 'round';
      g.beginPath();
      g.moveTo(tx, ty);
      g.quadraticCurveTo(tx - width * 0.3, ty - height * 0.3, tx - width * 0.4, ty + height * 0.1);
      g.stroke();
      g.restore();
      return;
  }
}
