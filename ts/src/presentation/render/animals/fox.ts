import { outline } from '../primitives.js';
import type { EyeOptions } from './parts.js';
import { drawEye, drawTriangleEar, fillEllipse } from './parts.js';
import type { HeadPainter } from './painters.js';

const INNER_EAR = '#4a1a00';
const NOSE = '#241209';
const EYE: EyeOptions = { iris: '#3a1400', tall: 0.78 };

/** きつねの頭。とがった三角の耳・細い目・白いマズル。 */
export const drawFoxHead: HeadPainter = (g, x, y, r, mode, colors) => {
  const side = mode === 'side';

  for (const sign of side ? [1, -1] : [-1, 1]) {
    const ex = x + sign * r * (side ? 0.18 : 0.6);
    drawTriangleEar(g, ex, y - r * 0.66, r * 0.52, r * 0.72, sign * (side ? 0.15 : 0.28), colors.color, INNER_EAR);
  }

  // 頭（少し角ばった逆三角）
  g.fillStyle = colors.color;
  g.beginPath();
  if (side) {
    g.moveTo(x - r * 0.86, y - r * 0.3);
    g.quadraticCurveTo(x + r * 0.1, y - r * 1.0, x + r * 0.72, y - r * 0.22);
    g.quadraticCurveTo(x + r * 1.2, y + r * 0.16, x + r * 0.3, y + r * 0.62);
    g.quadraticCurveTo(x - r * 0.6, y + r * 0.72, x - r * 0.86, y - r * 0.3);
  } else {
    g.moveTo(x - r * 0.96, y - r * 0.34);
    g.quadraticCurveTo(x, y - r * 1.04, x + r * 0.96, y - r * 0.34);
    g.quadraticCurveTo(x + r * 0.78, y + r * 0.58, x, y + r * 0.8);
    g.quadraticCurveTo(x - r * 0.78, y + r * 0.58, x - r * 0.96, y - r * 0.34);
  }
  g.closePath();
  g.fill();
  outline(g, 2.2);
  if (mode === 'back') return;

  // 白いマズルと頬
  g.fillStyle = colors.fur;
  if (side) {
    g.beginPath();
    g.moveTo(x + r * 0.1, y + r * 0.1);
    g.quadraticCurveTo(x + r * 1.16, y + r * 0.16, x + r * 0.3, y + r * 0.6);
    g.closePath();
    g.fill();
  } else {
    fillEllipse(g, x, y + r * 0.36, r * 0.44, r * 0.36);
    for (const sign of [-1, 1]) fillEllipse(g, x + sign * r * 0.66, y + r * 0.16, r * 0.24, r * 0.3, sign * 0.4);
  }

  if (side) drawEye(g, x + r * 0.3, y - r * 0.2, r * 0.17, { ...EYE, look: 1 });
  else for (const sign of [-1, 1]) drawEye(g, x + sign * r * 0.4, y - r * 0.16, r * 0.18, EYE);

  // 黒い鼻
  const nx = side ? x + r * 0.72 : x;
  g.fillStyle = NOSE;
  fillEllipse(g, nx, y + r * 0.3, r * 0.16, r * 0.13);
  g.strokeStyle = 'rgba(40,15,0,.8)';
  g.lineWidth = 1.4;
  g.beginPath();
  g.moveTo(nx, y + r * 0.42);
  g.lineTo(nx, y + r * 0.52);
  g.stroke();
};
