// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { speedControl } from '../../src/platform/ui/SpeedControl.js';

afterEach(() => document.body.replaceChildren());

function rangeOf(box: HTMLElement): HTMLInputElement {
  const input = box.querySelector('input');
  if (!(input instanceof HTMLInputElement)) throw new Error('つまみが無い');
  return input;
}

describe('ゲームの速さのつまみ', () => {
  it('動かすと、倍率を渡し、表示と枠の目立たせ方を変える', () => {
    const chosen: number[] = [];
    const box = speedControl(1, (rate) => chosen.push(rate));
    expect(box.querySelector('.sv')?.textContent).toBe('1×');
    expect(box.classList.contains('fast')).toBe(false);

    const input = rangeOf(box);
    input.value = '2.5';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(chosen).toEqual([2.5]);
    expect(box.querySelector('.sv')?.textContent).toBe('2.5×');
    expect(box.classList.contains('fast')).toBe(true);

    input.value = '0.75';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(box.classList.contains('fast')).toBe(false);
  });

  it('範囲と刻みは原型と同じ（0.5〜3 倍を 0.25 刻み）で、いまの倍率から始まる', () => {
    const input = rangeOf(speedControl(1.5, () => undefined));
    expect([input.min, input.max, input.step, input.value]).toEqual(['0.5', '3', '0.25', '1.5']);
  });

  it('目盛りは等間隔に置かず、つまみの中心が来る位置に置く', () => {
    // 等間隔だと「1×」の目盛りに合わせたつまみが 1.33 倍を指す（原型で実際に起きた）。
    // 値は原型の CSS に手で計算して書いてあったものと同じ。
    const marks = [...speedControl(1, () => undefined).querySelectorAll<HTMLElement>('.ticks span')];
    expect(marks.map((mark) => mark.textContent)).toEqual(['0.5×', '1×', '2×', '3×']);
    expect(marks[0]?.style.left).toBe('0px');
    expect(marks[1]?.style.left).toBe('calc(20% + 5.1px)');
    expect(marks[2]?.style.left).toBe('calc(60% - 1.7px)');
    expect(marks[3]?.style.right).toBe('0px');
  });

  it('Tab でフォーカスさせず、動かし終えたらフォーカスを外す', () => {
    // 矢印は移動のキー。つまみにフォーカスが残ると、試合中の矢印で速さが変わる。
    const box = speedControl(1, () => undefined);
    document.body.append(box);
    const input = rangeOf(box);
    expect(input.tabIndex).toBe(-1);
    input.focus();
    expect(document.activeElement).toBe(input);
    input.dispatchEvent(new Event('change', { bubbles: true }));
    expect(document.activeElement).not.toBe(input);
  });
});
