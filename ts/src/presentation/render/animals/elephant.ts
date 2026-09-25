import { outline } from '../primitives.js';
import type { HeadPainter } from './painters.js';
import { fillCircle, fillEllipse } from './parts.js';

/**
 * ぞうの頭の色。
 *
 * 頭だけは体の色ではなく、灰色がかった肌の色で描く（原型のまま）。
 * そのため他の動物と違い、渡された色を使わない。
 */
const SKIN = '#a8bdd2';
const SKIN_SHADE = '#7590ab';
const SKIN_BRIGHT = '#cfdeed';
const TUSK = '#f6f2e4';

/** ぞうの頭。大きく丸い耳・長い鼻・牙。 */
export const drawElephantHead: HeadPainter = (g, x, y, r, mode) => {
  const side = mode === 'side';
  // 横向きは手前の片側（右）だけを描く。
  const signs = side ? [1] : [-1, 1];

  for (const sign of signs) {
    const ex = side ? -r * 0.25 : sign * r * 0.92;
    g.fillStyle = SKIN_SHADE;
    fillEllipse(g, x + ex, y + r * 0.02, r * (side ? 0.4 : 0.5), r * 0.66, sign * 0.22);
    outline(g, 2);
    g.fillStyle = 'rgba(255,255,255,.2)';
    fillEllipse(g, x + ex, y + r * 0.06, r * (side ? 0.22 : 0.3), r * 0.42, sign * 0.22);
  }

  const skin = g.createRadialGradient(x - r * 0.28, y - r * 0.34, r * 0.08, x, y, r * 1.1);
  skin.addColorStop(0, SKIN_BRIGHT);
  skin.addColorStop(1, SKIN);
  g.fillStyle = skin;
  fillCircle(g, x, y, r);
  outline(g, 2.2);

  if (mode === 'back') {
    // 後頭部はしわだけ。
    g.strokeStyle = 'rgba(0,0,0,.22)';
    g.lineWidth = 1.6;
    for (const dy of [-0.3, 0, 0.3]) {
      g.beginPath();
      g.arc(x, y + r * dy, r * 0.55, Math.PI * 0.15, Math.PI * 0.85);
      g.stroke();
    }
    return;
  }

  drawTrunk(g, x, y, r, side);

  g.fillStyle = TUSK;
  for (const sign of signs) {
    const bx = side ? x + r * 0.5 : x + sign * r * 0.34;
    g.beginPath();
    g.moveTo(bx, y + r * 0.46);
    g.quadraticCurveTo(bx + sign * r * 0.2, y + r * 0.86, bx + sign * r * 0.05, y + r * 0.95);
    g.quadraticCurveTo(bx + sign * r * 0.02, y + r * 0.7, bx - sign * r * 0.09, y + r * 0.5);
    g.closePath();
    g.fill();
    outline(g, 1.3);
  }

  for (const sign of signs) {
    const ex = side ? x + r * 0.3 : x + sign * r * 0.36;
    g.fillStyle = '#fff';
    fillCircle(g, ex, y - r * 0.16, r * 0.2);
    outline(g, 1.4);
    g.fillStyle = '#171720';
    fillCircle(g, ex + (side ? r * 0.06 : sign * r * 0.03), y - r * 0.14, r * 0.11);
    g.fillStyle = 'rgba(255,255,255,.85)';
    fillCircle(g, ex - r * 0.04, y - r * 0.21, r * 0.04);
  }
};

/**
 * 鼻。太い黒い線を先に引き、その上に細い肌色の線を重ねて縁取りにする。
 *
 * 鼻は曲線1本で表すので、塗りの縁取り（outline）が使えない。線を2回引いて代わりにする。
 */
function drawTrunk(g: CanvasRenderingContext2D, x: number, y: number, r: number, side: boolean): void {
  const path = (): void => {
    g.beginPath();
    if (side) {
      g.moveTo(x + r * 0.42, y + r * 0.12);
      g.quadraticCurveTo(x + r * 1.18, y + r * 0.5, x + r * 0.9, y + r * 1.12);
    } else {
      g.moveTo(x, y + r * 0.34);
      g.quadraticCurveTo(x + r * 0.14, y + r * 1.0, x - r * 0.22, y + r * 1.18);
    }
  };
  g.save();
  g.lineCap = 'round';
  g.strokeStyle = 'rgba(0,0,0,.6)';
  g.lineWidth = r * 0.46;
  path();
  g.stroke();
  g.strokeStyle = SKIN;
  g.lineWidth = r * 0.32;
  path();
  g.stroke();
  g.restore();

  // 鼻のしわ
  g.strokeStyle = 'rgba(0,0,0,.18)';
  g.lineWidth = 1.4;
  for (let i = 1; i <= 3; i += 1) {
    const t = i / 4;
    const bx = side ? x + r * (0.42 + 0.62 * t) : x + r * (0.06 * t);
    const by = side ? y + r * (0.12 + 0.62 * t) : y + r * (0.34 + 0.62 * t);
    g.beginPath();
    g.moveTo(bx - r * 0.13, by - r * 0.05);
    g.lineTo(bx + r * 0.13, by + r * 0.05);
    g.stroke();
  }
}
