import { describe, expect, it } from 'vitest';

import { Toast, TOAST_FADE_MS, TOAST_SHOW_MS } from '../../src/presentation/hud/toast.js';

/** 通知の状態（原型の `toast` L6088-6096：1枚・置き換え・1400 ms で消え始め、0.2 秒で薄れる）。 */
describe('通知の状態', () => {
  it('一度も出していなければ、写すものは無い', () => {
    expect(new Toast().view(0)).toBeNull();
  });

  it('出してから 1400 ms の間は出し、そのあとは薄れて消える（文は残す。原型も on を外すだけ）', () => {
    const toast = new Toast();
    toast.show('🍌 うさぎ すべる！', 1000);
    expect(toast.view(1000)).toEqual({ text: '🍌 うさぎ すべる！', on: true });
    expect(toast.view(1000 + TOAST_SHOW_MS - 1)).toEqual({ text: '🍌 うさぎ すべる！', on: true });
    expect(toast.view(1000 + TOAST_SHOW_MS)).toEqual({ text: '🍌 うさぎ すべる！', on: false });
    expect(toast.view(1000 + TOAST_SHOW_MS + TOAST_FADE_MS + 5000)?.on).toBe(false);
    expect([TOAST_SHOW_MS, TOAST_FADE_MS]).toEqual([1400, 200]);
  });

  it('新しい文が来たら積まずに置き換え、消え始めるまでを数え直す（原型の clearTimeout）', () => {
    const toast = new Toast();
    toast.show('前の通知', 0);
    toast.show('新しい通知', 1000);
    expect(toast.view(1500)).toEqual({ text: '新しい通知', on: true });
    // 前の通知から数えると消えている時刻でも、新しい通知から 1400 ms たつまでは出す。
    expect(toast.view(2399)?.on).toBe(true);
    expect(toast.view(2400)?.on).toBe(false);
  });

  it('消えたあとに出し直せば、また出す', () => {
    const toast = new Toast();
    toast.show('一つ目', 0);
    expect(toast.view(5000)?.on).toBe(false);
    toast.show('二つ目', 5000);
    expect(toast.view(5000)).toEqual({ text: '二つ目', on: true });
  });
});
