// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { Splash, SPLASH_AUTO_MS, SPLASH_GONE_MS } from '../../src/platform/ui/Splash.js';

/** あとで呼ぶものを控え、時刻を進めた分だけ呼ぶ（本物の時計を待たない）。 */
function fakeClock(): { schedule: (callback: () => void, ms: number) => void; advance: (ms: number) => void; pending: () => number } {
  let now = 0;
  let queue: { at: number; callback: () => void }[] = [];
  return {
    schedule: (callback, ms) => queue.push({ at: now + ms, callback }),
    advance: (ms) => {
      now += ms;
      const due = queue.filter((entry) => entry.at <= now).sort((a, b) => a.at - b.at);
      queue = queue.filter((entry) => entry.at > now);
      for (const entry of due) entry.callback();
    },
    pending: () => queue.length,
  };
}

function mount(): { root: HTMLElement; keys: EventTarget; clock: ReturnType<typeof fakeClock>; splash: Splash } {
  const root = document.createElement('div');
  root.id = 'splash';
  root.hidden = true;
  document.body.append(root);
  const keys = new EventTarget();
  const clock = fakeClock();
  const splash = new Splash(root, clock.schedule);
  splash.show(keys);
  return { root, keys, clock, splash };
}

const key = (target: EventTarget, code = 'Enter'): void => {
  target.dispatchEvent(new KeyboardEvent('keydown', { code }));
};

afterEach(() => document.body.replaceChildren());

describe('起動の幕', () => {
  it('ロゴ・題・版の行と、点滅する案内を出す（原型の並び）', () => {
    const { root } = mount();
    expect(root.hidden).toBe(false);
    expect(root.querySelector('.titleWrap .logoPlate .logo')?.textContent).toBe('Nakatando');
    expect(root.querySelector('.titleWrap .logoSub')?.textContent).toBe('🐰💣🐘 どうぶつボンバー');
    expect(root.querySelector('.titleWrap .ver')?.textContent).toBe('VERSION v4.3.0');
    expect(root.querySelector('.tap')?.textContent).toBe('クリック か なにかキーを押す');
    expect(root.classList.contains('off')).toBe(false);
  });

  it('クリックで消え始め、0.5 秒後に隠す', () => {
    const { root, clock } = mount();
    root.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
    expect(root.classList.contains('off')).toBe(true);
    expect(root.hidden).toBe(false);
    clock.advance(SPLASH_GONE_MS - 1);
    expect(root.hidden).toBe(false);
    clock.advance(1);
    expect(root.hidden).toBe(true);
  });

  it('どのキーでも消え始める', () => {
    const { root, keys } = mount();
    key(keys, 'KeyQ');
    expect(root.classList.contains('off')).toBe(true);
  });

  it('何もしなくても 3.2 秒で消え始め、その 0.5 秒後に隠す', () => {
    const { root, clock } = mount();
    expect(SPLASH_AUTO_MS).toBe(3200);
    expect(SPLASH_GONE_MS).toBe(500);
    clock.advance(3199);
    expect(root.classList.contains('off')).toBe(false);
    clock.advance(1);
    expect(root.classList.contains('off')).toBe(true);
    clock.advance(499);
    expect(root.hidden).toBe(false);
    clock.advance(1);
    expect(root.hidden).toBe(true);
  });

  it('消し始めるのは1回目だけ（あとから来た合図で、隠す時刻を延ばさない）', () => {
    const { root, keys, clock, splash } = mount();
    key(keys);
    expect(splash.dismissed).toBe(true);
    // 3.2 秒の合図と、隠す合図の2つが残っている。
    expect(clock.pending()).toBe(2);
    clock.advance(300);
    root.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
    expect(clock.pending()).toBe(2);
    clock.advance(SPLASH_GONE_MS - 300);
    expect(root.hidden).toBe(true);
    // 3.2 秒の合図が来ても、隠したまま（出し直さない）。
    clock.advance(SPLASH_AUTO_MS);
    expect(root.hidden).toBe(true);
    expect(clock.pending()).toBe(0);
  });
});
