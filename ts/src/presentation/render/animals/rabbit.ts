import type { Frame } from '../Frame.js';
import { outline } from '../primitives.js';
import type { BodyPose, HeadPainter } from './painters.js';
import { drawEye, fillEllipse } from './parts.js';

const INNER_EAR = '#ffb3cd';
const NOSE = '#ff7fa6';
const IRIS = '#7a0f2a';

/** うさぎの頭。長い耳・丸い頬・小さな鼻と Y 字の口。 */
export const drawRabbitHead: HeadPainter = (g, x, y, r, mode, colors) => {
  const side = mode === 'side';

  // 耳。横向きは2本をほぼ重ねて描く。
  for (const sign of side ? [1, -1] : [-1, 1]) {
    g.save();
    g.translate(x + sign * r * (side ? 0.1 : 0.42), y - r * 0.86);
    g.rotate(sign * (side ? 0.1 : 0.2));
    g.fillStyle = colors.color;
    fillEllipse(g, 0, 0, r * 0.24, r * 0.86);
    outline(g, 1.8);
    g.fillStyle = INNER_EAR;
    fillEllipse(g, 0, r * 0.06, r * 0.12, r * 0.62);
    g.restore();
  }

  // 頭（横長のたまご）
  g.fillStyle = colors.color;
  fillEllipse(g, x, y, r * 1.02, r * 0.94);
  outline(g, 2.2);
  if (mode === 'back') return;

  // 頬とマズル
  g.fillStyle = colors.fur;
  if (side) fillEllipse(g, x + r * 0.42, y + r * 0.22, r * 0.42, r * 0.34);
  else fillEllipse(g, x, y + r * 0.28, r * 0.56, r * 0.4);

  if (side) drawEye(g, x + r * 0.34, y - r * 0.1, r * 0.19, { iris: IRIS, look: 1 });
  else for (const sign of [-1, 1]) drawEye(g, x + sign * r * 0.38, y - r * 0.08, r * 0.2, { iris: IRIS });

  // 鼻と口
  const nx = side ? x + r * 0.72 : x;
  g.fillStyle = NOSE;
  g.beginPath();
  g.moveTo(nx, y + r * 0.14);
  g.lineTo(nx + r * 0.11, y + r * 0.3);
  g.lineTo(nx - r * 0.11, y + r * 0.3);
  g.closePath();
  g.fill();
  g.strokeStyle = 'rgba(60,20,30,.75)';
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(nx, y + r * 0.3);
  g.lineTo(nx, y + r * 0.44);
  for (const sign of [-1, 1]) {
    g.moveTo(nx, y + r * 0.44);
    g.quadraticCurveTo(nx + sign * r * 0.2, y + r * 0.52, nx + sign * r * 0.26, y + r * 0.38);
  }
  g.stroke();

  // ひげ。横向きは手前の3本だけ。
  g.strokeStyle = 'rgba(255,255,255,.7)';
  g.lineWidth = 1.1;
  for (const sign of side ? [1] : [-1, 1]) {
    for (let k = -1; k <= 1; k += 1) {
      g.beginPath();
      g.moveTo(nx + sign * r * 0.16, y + r * 0.3 + k * r * 0.07);
      g.lineTo(nx + sign * r * 0.78, y + r * 0.22 + k * r * 0.16);
      g.stroke();
    }
  }
};

/** 撒いている最中に腰を落とす量のいちばん深いところ（マス）。 */
const SCATTER_DROP = 0.07;
/** 震えの速さ（ラジアン毎秒）。 */
const SHIVER_SPEED = 34;

/**
 * 周りに撒いている最中（'scattering'）の姿勢。腰を落として細かく震える（原型のブリブリ）。
 *
 * 腰は撒き始めからの進みに合わせて落とし、半分を過ぎたら戻す（原型と同じ）。
 *
 * @param progress 撒き始めからの進み（0〜1）
 */
export function scatteringPose(frame: Frame, progress: number): BodyPose {
  const shiver = Math.sin(frame.time * SHIVER_SPEED);
  const drop = SCATTER_DROP * (0.5 + 0.5 * Math.sin(progress * Math.PI));
  return { drop, tilt: shiver * 0.09, squash: 1 + 0.06 * shiver };
}
