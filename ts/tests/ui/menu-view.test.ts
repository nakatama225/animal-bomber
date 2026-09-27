// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { MenuView } from '../../src/platform/ui/MenuView.js';
import type { LocalSetup } from '../../src/presentation/menu/localSetup.js';
import { MenuFlow, type SoundSetting } from '../../src/presentation/menu/MenuFlow.js';

/** マウスで押したのと同じクリック（キーボードで起きたクリックは detail が 0 で、捨てられる）。 */
function press(root: HTMLElement, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

function mount(): {
  root: HTMLElement;
  flow: MenuFlow;
  started: LocalSetup[];
  sounds: SoundSetting[];
  lan: number[];
} {
  const root = document.createElement('div');
  document.body.append(root);
  const flow = new MenuFlow();
  const started: LocalSetup[] = [];
  const sounds: SoundSetting[] = [];
  const lan: number[] = [];
  new MenuView(root, flow, {
    start: (setup) => started.push(setup),
    soundChanged: (sound) => sounds.push(sound),
    openLan: () => lan.push(1),
  }).render();
  return { root, flow, started, sounds, lan };
}

afterEach(() => document.body.replaceChildren());

describe('試合の前の画面', () => {
  it('タイトルから選んで、はじめるまで押していける', () => {
    const { root, started } = mount();
    expect(root.querySelector('.logo-plate')?.textContent).toBe('Nakatando');

    press(root, '[data-choice="duo"]');
    expect(root.querySelector('[data-screen]')?.getAttribute('data-screen')).toBe('pick');
    expect(root.querySelectorAll('[data-human]')).toHaveLength(2);

    press(root, '[data-human="1"] [data-animal="fox"]');
    expect(root.querySelector('[data-human="1"] [data-animal="fox"]')?.classList.contains('on')).toBe(true);

    press(root, '[data-action="next"]');
    press(root, '[data-field="wins"] [data-value="5"]');
    press(root, '[data-field="cpu-1"] [data-value="oni"]');
    press(root, '[data-field="sudden"] [data-value="false"]');
    expect(root.querySelector('[data-field="wins"] .on')?.textContent).toBe('5勝');

    press(root, '[data-action="start"]');
    expect(started).toHaveLength(1);
    expect(started[0]).toMatchObject({
      mode: 'duo',
      picks: ['rabbit', 'fox'],
      winsToTake: 5,
      suddenDeath: false,
      cpuLevels: ['normal', 'oni', 'normal'],
    });
  });

  it('キーボードで起きたクリックでは始まらない', () => {
    const { root, flow, started } = mount();
    flow.chooseMode('solo');
    flow.next();
    new MenuView(root, flow, { start: (s) => started.push(s), soundChanged: () => undefined, openLan: () => undefined }).render();
    const start = root.querySelector('[data-action="start"]');
    if (!(start instanceof HTMLButtonElement)) throw new Error('はじめるが無い');
    start.click();
    expect(started).toHaveLength(0);
  });

  it('遊び方に合わせて、いない人の行を出さない', () => {
    const { root } = mount();
    press(root, '[data-choice="versus"]');
    press(root, '[data-action="next"]');
    expect(root.querySelector('[data-field="hits-p2"]')).not.toBeNull();
    expect(root.querySelector('[data-field="hits-cpu"]')).toBeNull();
    expect(root.querySelector('[data-field="cpu-0"]')).toBeNull();

    press(root, '[data-action="back"]');
    press(root, '[data-action="back"]');
    press(root, '[data-choice="solo"]');
    press(root, '[data-action="next"]');
    expect(root.querySelector('[data-field="hits-p2"]')).toBeNull();
    expect(root.querySelectorAll('[data-field^="cpu-"]')).toHaveLength(3);
  });

  it('設定・遊び方の画面で音を切り替え、説明を出す', () => {
    const { root, sounds } = mount();
    press(root, '[data-choice="manual"]');
    press(root, '[data-field="sound"] [data-value="off"]');
    expect(sounds).toEqual(['off']);
    expect(root.querySelector('[data-field="sound"] .on')?.textContent).toBe('無音');
    expect(root.querySelector('.manual')?.textContent).toContain('葱ボン');
  });

  it('通信対戦を選んだら知らせる', () => {
    const { root, lan } = mount();
    press(root, '[data-choice="lan"]');
    expect(lan).toEqual([1]);
  });
});
