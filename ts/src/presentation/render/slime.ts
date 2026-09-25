import type { Cell } from '../../domain/core/Coord.js';
import { TICKS_PER_SECOND, type Tick } from '../../domain/core/Tick.js';
import type { Frame } from './Frame.js';
import { FULL_TURN } from './Frame.js';
import { cellCenter } from './Layout.js';

/**
 * 跳ね回る爆弾の絵。
 *
 * 太ったしずく型の粘液が、着地するたびに縦に潰れて跳ね返り、
 * 小さく揺れながら落ち着く。跳ぶ動きそのものはルールの層で一瞬で
 * 2マス移るので、動いたことは着地の潰れで見せる。
 */

/** 残りの跳ねる回数がこれ以下になったら、赤く点滅して爆発が近いことを知らせる。 */
const WARN_HOPS = 1;

/**
 * 跳ね回る爆弾を描く。
 *
 * @param sinceLanding 最後に着地してからの tick 数。潰れと揺れの位相を決める
 * @param hopsLeft 爆発するまでに残っている跳ねる回数
 */
export function drawSlime(frame: Frame, cell: Cell, sinceLanding: Tick, hopsLeft: number): void {
  const { g, layout, time } = frame;
  const size = layout.tile;
  const seconds = sinceLanding / TICKS_PER_SECOND;

  // 着地の瞬間が 1 で、0.25 秒で 0 に戻る。その間に山なりに小さく跳ね返る。
  const air = Math.max(0, 1 - seconds * 4);
  const lift = Math.sin(air * Math.PI) * size * 0.42;
  // 着地のあとに残る、だんだん弱まる揺れ。
  const wobble = Math.sin(seconds * 26) * Math.exp(-seconds * 7);
  // 1 より小さいと平たく、大きいと縦長になる。
  const squash = Math.max(0.62, Math.min(1.4, 1 - 0.3 * air + 0.22 * wobble));

  const ground = cellCenter(layout, cell);
  const x = ground.x;
  const y = ground.y - lift;
  // 潰れるほど横に広がる。体積が変わらないように見せるため、横は縦の逆数で伸ばす。
  const w = (size * 0.42) / squash;
  const h = size * 0.36 * squash;

  g.save();

  // 影。高く上がるほど小さくする。
  g.globalAlpha = 0.32;
  g.fillStyle = '#000';
  g.beginPath();
  g.ellipse(ground.x, ground.y + size * 0.2, (w * 0.85) / (1 + lift / size), h * 0.3, 0, 0, FULL_TURN);
  g.fill();
  g.globalAlpha = 1;

  drawBody(g, x, y, w, h);

  if (hopsLeft <= WARN_HOPS) {
    g.globalAlpha = 0.45 + 0.45 * Math.abs(Math.sin(time * 14));
    g.strokeStyle = '#ff5f5f';
    g.lineWidth = 2.8;
    g.beginPath();
    g.ellipse(x, y + h * 0.2, w * 1.25, h * 1.45, 0, 0, FULL_TURN);
    g.stroke();
  }
  g.restore();
}

/** 下がぷっくり丸く、上に短いとんがりのある体と、照りと目。 */
function drawBody(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): void {
  const fill = g.createRadialGradient(x - w * 0.28, y - h * 0.45, 1, x, y + h * 0.2, h * 2.1);
  fill.addColorStop(0, '#eaffd6');
  fill.addColorStop(0.35, '#7ce23a');
  fill.addColorStop(0.72, '#3fb814');
  fill.addColorStop(1, '#12490a');
  g.fillStyle = fill;

  const top = y - h * 1.18;
  g.beginPath();
  g.moveTo(x, top);
  // とんがりから右の胴へ下り、底の丸みを回って左へ戻る。
  g.bezierCurveTo(x + w * 0.42, top + h * 0.3, x + w, y + h * 0.1, x + w, y + h * 0.52);
  g.bezierCurveTo(x + w, y + h * 1.05, x + w * 0.55, y + h * 1.2, x, y + h * 1.2);
  g.bezierCurveTo(x - w * 0.55, y + h * 1.2, x - w, y + h * 1.05, x - w, y + h * 0.52);
  g.bezierCurveTo(x - w, y + h * 0.1, x - w * 0.42, top + h * 0.3, x, top);
  g.closePath();
  g.fill();
  g.strokeStyle = 'rgba(8,44,0,.7)';
  g.lineWidth = 2.4;
  g.stroke();

  // 左上の照り。
  g.fillStyle = 'rgba(255,255,255,.6)';
  g.beginPath();
  g.ellipse(x - w * 0.36, y - h * 0.28, w * 0.24, h * 0.3, -0.5, 0, FULL_TURN);
  g.fill();

  // 目。
  g.fillStyle = '#0d2a04';
  for (const side of [-1, 1]) {
    g.beginPath();
    g.ellipse(x + side * w * 0.3, y + h * 0.16, w * 0.1, h * 0.17, 0, 0, FULL_TURN);
    g.fill();
  }
}
