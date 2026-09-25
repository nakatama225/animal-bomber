import { step } from '../../../domain/core/Coord.js';
import { TongueAction } from '../../../domain/abilities/frog/TongueAction.js';
import { outline } from '../primitives.js';
import type { ActionLook, HeadPainter } from './painters.js';
import { drawEye, fillCircle, fillEllipse } from './parts.js';

const EYE_WHITE = '#fff8d8';
const EYE_IRIS = '#141a06';
const TONGUE = '#e8547e';
const TONGUE_LIGHT = '#ff8fae';

/** かえるの頭。頭の上に飛び出た大きな目と、横に広い口。 */
export const drawFrogHead: HeadPainter = (g, x, y, r, mode, colors) => {
  const side = mode === 'side';
  const back = mode === 'back';

  // 頭（横に広い）
  g.fillStyle = colors.color;
  fillEllipse(g, x, y + r * 0.1, r * 1.12, r * 0.82);
  outline(g, 2.2);

  // 飛び出た目。後ろからも盛り上がりは見えるので、目玉だけを省く。
  const eyeR = r * 0.34;
  for (const sign of side ? [1] : [-1, 1]) {
    const ex = side ? x + r * 0.34 : x + sign * r * 0.56;
    const ey = y - r * 0.56;
    g.fillStyle = colors.color;
    fillCircle(g, ex, ey, eyeR);
    outline(g, 1.9);
    if (!back) {
      drawEye(g, ex, ey - eyeR * 0.06, eyeR * 0.68, { iris: EYE_IRIS, white: EYE_WHITE, look: side ? 1 : 0 });
    }
  }
  if (back) return;

  // 口（横に広い一本線と口角）
  g.strokeStyle = 'rgba(20,50,0,.85)';
  g.lineWidth = Math.max(1.6, r * 0.11);
  g.beginPath();
  if (side) {
    g.moveTo(x - r * 0.2, y + r * 0.34);
    g.quadraticCurveTo(x + r * 0.6, y + r * 0.5, x + r * 1.02, y + r * 0.22);
  } else {
    g.moveTo(x - r * 0.82, y + r * 0.3);
    g.quadraticCurveTo(x, y + r * 0.72, x + r * 0.82, y + r * 0.3);
  }
  g.stroke();

  // 喉の明るい部分。透明度は今の値に掛ける（点滅中の透明度を消さないため）。
  const alpha = g.globalAlpha;
  g.globalAlpha = alpha * 0.8;
  g.fillStyle = colors.fur;
  fillEllipse(g, side ? x + r * 0.3 : x, y + r * 0.62, r * 0.44, r * 0.2);
  g.globalAlpha = alpha;
};

/**
 * 舌を伸ばしている最中の見た目。伸びた長さぶんの帯と、先端の吸盤。
 *
 * 体より先に描き、根元を体の後ろに隠す。伸ばし始めは原型と同じく足元の中心で、口の高さではない。
 * 原型は掴んだアイテムを舌先に載せて戻していたが、この版の舌は
 * 掴んだ瞬間に効果が出て振る舞いが終わるので、運ぶ場面が無い。
 */
export const TONGUE_LOOK: ActionLook = {
  icon: '👅',
  drawUnder(frame, view, x, y) {
    const action = view.player.action;
    if (!(action instanceof TongueAction)) return;
    const { g, layout } = frame;
    const tile = layout.tile;
    const length = action.extent * tile;
    // 向きの1マスぶんの差分を、そのまま単位の向きとして使う。
    const unit = step({ col: 0, row: 0 }, view.player.facing);
    const ex = x + unit.col * length;
    const ey = y + unit.row * length;

    g.save();
    g.lineCap = 'round';
    for (const [color, width] of [
      [TONGUE, tile * 0.17],
      [TONGUE_LIGHT, tile * 0.08],
    ] as const) {
      g.strokeStyle = color;
      g.lineWidth = width;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(ex, ey);
      g.stroke();
    }
    g.fillStyle = TONGUE;
    g.strokeStyle = 'rgba(0,0,0,.5)';
    g.lineWidth = 1.6;
    fillCircle(g, ex, ey, tile * 0.14);
    g.stroke();
    g.restore();
  },
};
