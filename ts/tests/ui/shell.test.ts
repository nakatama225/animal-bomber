// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { Shell, type ShellElements, type ShellTools } from '../../src/app/Shell.js';
import type { WebSocketLinkHandlers } from '../../src/platform/WebSocketLink.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import type { SoundSetting } from '../../src/presentation/menu/MenuFlow.js';
import { fakeCanvas } from '../presentation/fakeCanvas.js';

/**
 * 画面の切り替えの通し。タイトルから試合を始め、決着の幕のボタンでタイトルへ戻るまで。
 *
 * 試合は本物（`GameSession`）を回す。描画は偽の canvas に描く（ブラウザが例外を出す
 * 呼び方では同じく例外を出す）。音は鳴らさず、鳴らした名前だけを控える。
 */

function press(root: ParentNode, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

function mount(sound: SoundSetting = 'both'): {
  shell: Shell;
  elements: ShellElements;
  played: SoundName[];
  music: { started: number; stopped: number };
  captured: boolean[];
  relay: () => WebSocketLinkHandlers;
} {
  const make = (id: string): HTMLElement => {
    const element = document.createElement('div');
    element.id = id;
    document.body.append(element);
    return element;
  };
  const canvas = document.createElement('canvas');
  canvas.width = 920;
  canvas.height = 680;
  const elements: ShellElements = {
    menu: make('menu'),
    play: make('play'),
    canvas,
    side: make('side'),
    banner: make('banner'),
    toasts: make('toasts'),
    pause: make('pause'),
    toolbar: make('toolbar'),
    lanStatus: make('lan-status'),
  };
  const played: SoundName[] = [];
  const music = { started: 0, stopped: 0 };
  const captured: boolean[] = [];
  let relay: WebSocketLinkHandlers | null = null;
  const tools: ShellTools = {
    context: fakeCanvas({ keepLog: false }).context,
    keyboard: { anyOf: () => false },
    gamepads: () => [],
    sounds: { play: (name) => played.push(name) },
    music: { start: () => (music.started += 1), stop: () => (music.stopped += 1) },
    sound,
    setSound: () => undefined,
    captureKeys: (on) => captured.push(on),
    newSeed: () => 7,
    openLan: () => undefined,
    leaveLan: () => undefined,
    connect: (_url, handlers) => {
      relay = handlers;
      return { send: () => undefined, close: () => undefined };
    },
  };
  const connected = (): WebSocketLinkHandlers => {
    if (relay === null) throw new Error('つないでいない');
    return relay;
  };
  return { shell: new Shell(elements, tools), elements, played, music, captured, relay: connected };
}

afterEach(() => document.body.replaceChildren());

describe('画面の切り替え', () => {
  it('タイトルから試合を始め、横の板と幕を出し、もういっかい遊んでからタイトルへ戻る', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    expect(elements.menu.hidden).toBe(false);
    expect(elements.play.hidden).toBe(true);

    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    // 決着を早めるため、1ラウンドを短くする。
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    expect(elements.menu.hidden).toBe(true);
    expect(elements.play.hidden).toBe(false);
    expect(elements.side.querySelectorAll('.card')).toHaveLength(4);

    // 人間は操作しない（キーは何も押されていない）。CPU どうしで決まるまで進める。
    let ticks = 0;
    while (elements.banner.hidden || !elements.banner.textContent?.includes('優勝')) {
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('試合が決まらない');
    }
    // 幕の「もういっかい」で、同じ設定の新しい試合になる（タイトルへは戻らない）。
    press(elements.banner, '[data-action="again"]');
    shell.draw(0);
    expect(elements.menu.hidden).toBe(true);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.time')?.textContent).toBe('1:00');

    press(elements.toolbar, '[data-action="quit"]');
    expect(elements.menu.hidden).toBe(false);
    expect(elements.play.hidden).toBe(true);
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
    // 前の試合のものを残さない。
    expect(elements.banner.hidden).toBe(true);
    expect(elements.toolbar.childElementCount).toBe(0);
    expect(elements.toasts.childElementCount).toBe(0);
  }, 120_000);

  it('試合の画面の間だけ、操作のキーのブラウザの動きを止める', () => {
    const { shell, elements, captured } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    expect(captured.at(-1)).toBe(true);
    press(elements.toolbar, '[data-action="quit"]');
    expect(captured.at(-1)).toBe(false);
  });

  it('通信対戦では、番号を受け取ってから自分のキー配置を出す', () => {
    const { shell, elements, relay } = mount();
    shell.startLan('relay.local:8777');
    shell.draw(0);
    expect(elements.play.hidden).toBe(true);
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 2, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 2], config }));
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    const help = elements.side.querySelector('.keyhelp')?.textContent ?? '';
    // この端末の人（3P）の説明だけを、1人で使う配置（WASD と矢印とパッド）で出す。
    expect(help).toContain('3P');
    expect(help).not.toContain('1P');
    expect(help).toContain('W A S D');
    expect(help).toContain('↑');
    expect(help).toContain('🎮');
  });

  it('前に選んだ音の設定を、設定の画面に出す', () => {
    // 開き直す前に「無音」を選んでいた。画面が「曲 + 効果音」のままだと、実際と食い違う。
    const { shell, elements } = mount('off');
    shell.showMenu();
    press(elements.menu, '[data-choice="manual"]');
    expect(elements.menu.querySelector('[data-field="sound"] .on')?.textContent).toBe('無音');
  });

  it('ポーズの間は進めず、曲も止める', () => {
    const { shell, elements, music } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    const time = (): string | null | undefined => elements.side.querySelector('.time')?.textContent;

    press(elements.toolbar, '[data-action="pause"]');
    shell.draw(0);
    expect(elements.pause.hidden).toBe(false);
    const stoppedBefore = music.stopped;
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(time()).toBe('3:00');
    expect(music.stopped).toBeGreaterThan(stoppedBefore);

    shell.togglePause();
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.pause.hidden).toBe(true);
    expect(time()).toBe('2:58');
  });

  it('もういっかいで、同じ設定の新しい試合になる', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="versus"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.side.querySelector('.time')?.textContent).toBe('2:58');

    shell.restart();
    shell.draw(0);
    // 同じ遊び方（2人だけ）で、時計が頭から始まっている。
    expect(elements.side.querySelectorAll('.card')).toHaveLength(2);
    expect(elements.side.querySelector('.time')?.textContent).toBe('3:00');
  });

  it('試合を進めると、残り10秒から秒読みが鳴る', () => {
    // 2人だけの遊び方で誰も操作しなければ、時間切れまで進む。
    const { shell, elements, played } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="versus"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    // 51秒ぶん進めると、残り10秒と9秒の2回が鳴っている。
    for (let i = 0; i < 60 * 51; i += 1) shell.tick();
    expect(played.filter((name) => name === 'tick')).toHaveLength(2);
  });
});
