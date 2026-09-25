import { lookOf } from '../../../content/animals.js';
import { PitAction } from '../../../domain/abilities/mole/PitAction.js';
import type { Frame } from '../Frame.js';
import type { PlayerView } from '../PlayerView.js';
import { outline, roundRect } from '../primitives.js';
import type { ActionLook, HeadPainter } from './painters.js';
import { drawEye, fillCircle, fillEllipse } from './parts.js';

const NOSE = '#ff9ec0';
const HOLE = '#22140a';
const SOIL = '#8a5a2a';
const CLOD = '#a06a30';

/** もぐらの頭。ほぼ閉じた目・大きなピンクの鼻・前歯。 */
export const drawMoleHead: HeadPainter = (g, x, y, r, mode, colors) => {
  const side = mode === 'side';

  // 小さな丸い耳
  g.fillStyle = colors.shade;
  for (const sign of side ? [-1] : [-1, 1]) {
    fillCircle(g, x + sign * r * 0.72, y - r * 0.56, r * 0.19);
    outline(g, 1.5);
  }

  // 頭（前が細くなる砲弾型）
  g.fillStyle = colors.color;
  if (side) fillEllipse(g, x + r * 0.06, y, r * 1.06, r * 0.86);
  else fillEllipse(g, x, y, r * 0.98, r * 0.92);
  outline(g, 2.2);
  if (mode === 'back') return;

  g.fillStyle = colors.fur;
  if (side) fillEllipse(g, x + r * 0.58, y + r * 0.18, r * 0.5, r * 0.4);
  else fillEllipse(g, x, y + r * 0.3, r * 0.62, r * 0.4);

  // 目はほぼ閉じている（土の中で暮らしているので）。
  if (side) drawEye(g, x + r * 0.26, y - r * 0.16, r * 0.16, { closed: true });
  else for (const sign of [-1, 1]) drawEye(g, x + sign * r * 0.34, y - r * 0.14, r * 0.17, { closed: true });

  // 大きな鼻
  const nx = side ? x + r * 0.92 : x;
  g.fillStyle = NOSE;
  fillEllipse(g, nx, y + r * 0.26, r * 0.26, r * 0.2);
  outline(g, 1.5);
  g.fillStyle = 'rgba(90,20,45,.8)';
  for (const sign of side ? [1] : [-1, 1]) fillEllipse(g, nx + sign * r * 0.11, y + r * 0.26, r * 0.05, r * 0.07);

  // 前歯
  g.fillStyle = '#fffaf0';
  g.beginPath();
  g.rect(nx - r * 0.09, y + r * 0.44, r * 0.18, r * 0.14);
  g.fill();
  outline(g, 1.1);
};

/** 掘り進んだ割合（0〜1）。 */
function progressOf(view: PlayerView): number {
  const action = view.player.action;
  return action instanceof PitAction ? action.progress : 0;
}

/** 土を掻く腕の振れ（-1〜1）。時刻だけで決まる。 */
function digSwing(frame: Frame): number {
  return Math.sin(frame.time * 17);
}

/**
 * 穴を掘っている最中の見た目。土を掻き出す様子と、進みのゲージ。
 *
 * 掘り終わった穴は盤面に描かない。踏むまで見えないのがこの技の要点なので、
 * 描くのは掘っている間だけ。
 *
 * ゲージは原型では体より先に描いていたため、ほとんど頭に隠れていた。
 * ここでは体の後に、頭より上の位置へ描く。
 */
export const DIG_LOOK: ActionLook = {
  icon: '⛏️',
  drawUnder(frame, view, x, y) {
    const { g, layout } = frame;
    const tile = layout.tile;
    const k = progressOf(view);
    const swing = digSwing(frame);
    g.save();
    // 掘りかけの穴。進むほど大きくなる。
    g.fillStyle = HOLE;
    fillEllipse(g, x, y + tile * 0.16, tile * (0.1 + 0.22 * k), tile * (0.05 + 0.13 * k));
    // 掻き出した土。左右に振れる。
    g.fillStyle = SOIL;
    g.strokeStyle = 'rgba(0,0,0,.45)';
    g.lineWidth = 1.4;
    for (const sign of [-1, 1]) {
      const ox = sign * (0.26 + 0.06 * k) * tile + swing * sign * tile * 0.03;
      fillEllipse(g, x + ox, y + tile * 0.22, tile * (0.08 + 0.05 * k), tile * (0.05 + 0.03 * k));
      g.stroke();
    }
    // 振りきったときだけ土くれが飛ぶ。
    if (Math.abs(swing) > 0.85) {
      g.fillStyle = CLOD;
      for (let i = 0; i < 3; i += 1) {
        const angle = -0.6 - i * 0.5 + swing * 0.4;
        fillCircle(g, x + Math.cos(angle) * tile * 0.34, y + tile * 0.05 + Math.sin(angle) * tile * 0.3, tile * 0.045);
      }
    }
    g.font = `${Math.floor(tile * 0.3)}px system-ui`;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText('⛏️', x + swing * tile * 0.1, y - tile * 0.02);
    g.restore();
  },
  drawOver(frame, view, x, y) {
    const { g, layout } = frame;
    const tile = layout.tile;
    const k = progressOf(view);
    const gx = x - tile * 0.3;
    const gy = y - tile * 1.0;
    g.fillStyle = 'rgba(0,0,0,.6)';
    roundRect(g, gx, gy, tile * 0.6, tile * 0.11, 4);
    g.fill();
    g.fillStyle = lookOf(view.player.animal).color;
    roundRect(g, gx, gy, tile * 0.6 * k, tile * 0.11, 4);
    g.fill();
  },
};
