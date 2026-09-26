import { lookOf } from '../../content/animals.js';
import { step, type Direction, type Point } from '../../domain/core/Coord.js';
import type { Tick } from '../../domain/core/Tick.js';
import { laneSpot } from '../../domain/negibon/lane.js';
import { LEEK_COOLDOWN } from '../../domain/rules/negibon.js';
import type { Negibon } from '../../domain/state/Life.js';
import type { Frame } from './Frame.js';
import { FULL_TURN } from './Frame.js';
import { screenX, screenY } from './Layout.js';
import { roundRect } from './primitives.js';

/**
 * 外周の葱ボンと、飛んでいる葱の絵。形と色は原型のまま。
 *
 * 外周の帯そのものは描かない。原型も帯を塗り分けず、盤面の外の余白を帯に見立てていた。
 */

/** 撃つ向きの点線を、葱ボンの中心からどれだけ離して引き始め、どこまで引くか（マス）。 */
const AIM_FROM = 0.4;
const AIM_TO = 1.1;

/**
 * 次の葱までの残りを示す棒の、満タンのときの幅（マス）。鍋の幅より少し短くして、
 * 鍋の真下から左右にはみ出さないようにする。
 */
const COOLDOWN_BAR = 0.56;

/**
 * 飛ぶ向きごとの、葱を回す角度。原型は速度から `Math.atan2` で求めていたが、
 * 葱の向きは4つのどれかなので表で引く。
 */
const HEADING: Readonly<Record<Direction, number>> = {
  right: 0,
  down: Math.PI / 2,
  left: Math.PI,
  up: -Math.PI / 2,
};

/**
 * 外周にいる葱ボンを1人描く。
 *
 * 描く順は、影 → 鍋（外周の乗り物）→ 動物の絵文字 → 次の葱までの残り（撃てるなら葉の印）
 * → 撃つ向きの点線。動物は、原型と同じく絵文字で描く。
 *
 * @param now 試合のいまの tick。撃てるかどうかをルールの層と同じ比べ方で決めるために、
 *   見た目の時刻（`frame.time`）ではなくこちらを使う
 */
export function drawNegibon(frame: Frame, animal: string, life: Negibon, now: Tick): void {
  const { g, layout } = frame;
  const tile = layout.tile;
  const spot = laneSpot(life.along);
  const x = screenX(layout, spot.position.x);
  const y = screenY(layout, spot.position.y);

  g.save();
  g.globalAlpha = 0.95;
  g.fillStyle = 'rgba(0,0,0,.4)';
  g.beginPath();
  g.ellipse(x, y + tile * 0.26, tile * 0.24, tile * 0.09, 0, 0, FULL_TURN);
  g.fill();

  g.fillStyle = '#4d7a1f';
  g.strokeStyle = '#a6e06a';
  g.lineWidth = 2;
  roundRect(g, x - tile * 0.3, y - tile * 0.04, tile * 0.6, tile * 0.3, 5);
  g.fill();
  g.stroke();

  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.font = `${Math.floor(tile * 0.5)}px system-ui`;
  g.fillText(lookOf(animal).emoji, x, y - tile * 0.14);

  const left = cooldownLeft(life, now);
  if (left > 0) {
    g.fillStyle = 'rgba(255,255,255,.3)';
    g.fillRect(x - (tile * COOLDOWN_BAR) / 2, y + tile * 0.28, tile * COOLDOWN_BAR * left, 3);
  } else {
    g.font = `${Math.floor(tile * 0.26)}px system-ui`;
    g.fillText('🌿', x, y + tile * 0.33);
  }

  const unit = step({ col: 0, row: 0 }, spot.facing);
  g.strokeStyle = 'rgba(166,224,106,.55)';
  g.lineWidth = 2;
  g.setLineDash([4, 4]);
  g.beginPath();
  g.moveTo(x + unit.col * tile * AIM_FROM, y + unit.row * tile * AIM_FROM);
  g.lineTo(x + unit.col * tile * AIM_TO, y + unit.row * tile * AIM_TO);
  g.stroke();
  g.restore();
}

/**
 * 次の葱を撃てるまでの残りを、撃つ間隔に対する割合（0〜1）で返す。0 なら撃てる。
 *
 * ⚠️ 1 を上限に切る。外周へ回った直後の待ち（`LEEK_FIRST_COOLDOWN`）は撃つ間隔より長いので、
 * 切らないと棒が鍋の幅を越えてはみ出す（原型はそのまま描いていた）。
 */
function cooldownLeft(life: Negibon, now: Tick): number {
  return Math.max(0, Math.min(1, (life.readyAt - now) / LEEK_COOLDOWN));
}

/**
 * 飛んでいる葱を描く。白い茎と緑の葉を、葉を先にして飛ぶ向きへ回す（原型と同じ向き）。
 *
 * @param position 葱の位置（マス単位の連続座標）
 */
export function drawLeek(frame: Frame, position: Point, facing: Direction): void {
  const { g, layout } = frame;
  const tile = layout.tile;

  g.save();
  g.translate(screenX(layout, position.x), screenY(layout, position.y));
  g.rotate(HEADING[facing]);
  g.fillStyle = '#f2f7e4';
  roundRect(g, -tile * 0.34, -tile * 0.07, tile * 0.42, tile * 0.14, 4);
  g.fill();
  g.fillStyle = '#79c142';
  roundRect(g, tile * 0.06, -tile * 0.09, tile * 0.3, tile * 0.18, 4);
  g.fill();
  g.strokeStyle = '#3f6b1f';
  g.lineWidth = 1.2;
  roundRect(g, -tile * 0.34, -tile * 0.08, tile * 0.7, tile * 0.16, 4);
  g.stroke();
  g.restore();
}
