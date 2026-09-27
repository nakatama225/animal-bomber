import { SPEED_RANGE } from '../FrameLoop.js';
import { el } from './dom.js';

/** つまみの幅（px）。目盛りの位置の計算に使う。`style.css` の `.speed` のつまみの幅と揃える。 */
const THUMB_PX = 17;

/** 目盛りを付ける倍率。 */
const MARKS = [0.5, 1, 2, 3] as const;

/**
 * ゲームの速さのつまみ。1台で遊ぶときだけ出す。
 *
 * ⚠️ 目盛りを等間隔に並べない。値は 0.5〜3 の線形なので、4つを等間隔に置くと「1×」の見た目の
 * 位置が、実際には 1.33 倍の所になる（原型で実際に起きた）。つまみの中心は、左端から
 * `THUMB_PX / 2` の所から右端から `THUMB_PX / 2` の所までを動く。割合 p の値の位置は
 * `THUMB_PX / 2 + p × (幅 − THUMB_PX)` になる。両端の目盛りは、はみ出さないよう端に揃える。
 *
 * ⚠️ つまみはキーボードで動かさない。矢印は移動のキーなので、つまみにフォーカスが残ると、
 * 試合中に矢印を押すたびに速さが変わる。Tab でフォーカスさせず（`tabIndex = -1`）、
 * 動かし終えたらフォーカスを外す。
 *
 * @param current いまの倍率
 * @param change つまみが動いたときに、新しい倍率で呼ぶ
 */
export function speedControl(current: number, change: (rate: number) => void): HTMLElement {
  const value = el('span', { className: 'speed-value', text: rateLabel(current) });
  const input = el('input');
  input.type = 'range';
  input.min = String(SPEED_RANGE.min);
  input.max = String(SPEED_RANGE.max);
  input.step = String(SPEED_RANGE.step);
  input.value = String(current);
  input.tabIndex = -1;
  input.setAttribute('aria-label', 'ゲーム速度');

  const box = el('div', { className: boxClass(current), data: { field: 'speed' } }, [
    el('div', { className: 'speed-head' }, [el('span', { text: 'ゲーム速度' }), value]),
    input,
    el('div', { className: 'speed-marks' }, MARKS.map(markAt)),
  ]);
  input.addEventListener('input', () => {
    const rate = Number(input.value);
    value.textContent = rateLabel(rate);
    box.className = boxClass(rate);
    change(rate);
  });
  input.addEventListener('change', () => input.blur());
  return box;
}

function rateLabel(rate: number): string {
  return `${rate}×`;
}

/** 等倍より速いときは枠を目立たせる。速くしたまま忘れて次の試合を始めないように。 */
function boxClass(rate: number): string {
  return rate > 1 ? 'speed fast' : 'speed';
}

/** 目盛り1つ。位置はつまみの中心と同じ式で出す（上の説明）。 */
function markAt(rate: number): HTMLElement {
  const mark = el('span', { text: rateLabel(rate) });
  const p = (rate - SPEED_RANGE.min) / (SPEED_RANGE.max - SPEED_RANGE.min);
  if (p === 0) {
    mark.style.left = '0';
  } else if (p === 1) {
    mark.style.right = '0';
  } else {
    // 小数の誤差（20.000000000000004% など）をそのまま書かないよう、1桁に丸める。
    const percent = Math.round(p * 1000) / 10;
    const offset = Math.round((THUMB_PX / 2 - p * THUMB_PX) * 10) / 10;
    mark.style.left = `calc(${percent}% ${offset < 0 ? '-' : '+'} ${Math.abs(offset)}px)`;
    mark.style.transform = 'translateX(-50%)';
  }
  return mark;
}
