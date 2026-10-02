// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Shell, type ShellElements, type ShellTools } from '../../src/app/Shell.js';
import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import type { PeerMessage } from '../../src/net/protocol.js';
import type { PadSnapshot } from '../../src/platform/GamepadInput.js';
import type { WebSocketLinkHandlers } from '../../src/platform/WebSocketLink.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import type { SoundSetting } from '../../src/presentation/menu/MenuFlow.js';
import type * as PlayersModule from '../../src/presentation/render/players.js';
import { fakeCanvas } from '../presentation/fakeCanvas.js';

/**
 * 描いたプレイヤーの位置の控え。描く関数は本物をそのまま呼び、渡された位置だけを控える。
 *
 * 補間（前の tick の位置からいまの位置までの間を埋める）が正しいかは、描いた位置の並びでしか
 * 見えない。偽の canvas の命令の列から位置を拾うと、絵の描き方を変えただけで壊れる。
 */
const drawn = vi.hoisted(() => [] as { id: number; x: number }[]);
vi.mock('../../src/presentation/render/players.js', async (importOriginal) => {
  const real = await importOriginal<typeof PlayersModule>();
  return {
    ...real,
    drawPlayer: (...args: Parameters<typeof real.drawPlayer>): void => {
      drawn.push({ id: args[1].player.id, x: args[1].x });
      real.drawPlayer(...args);
    },
  };
});

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

/**
 * 画面を組み立てる。
 *
 * @param held いま押しているキー（`KeyboardEvent.code`）。呼ばれるたびに読むので、途中で変えられる
 * @param pads いまのゲームパッド。同じく呼ばれるたびに読む
 */
function mount(
  sound: SoundSetting = 'both',
  held: () => readonly string[] = () => [],
  pads: () => readonly (PadSnapshot | null)[] = () => [],
): {
  shell: Shell;
  elements: ShellElements;
  played: SoundName[];
  music: { started: number; stopped: number; speeds: number[] };
  captured: ('play' | 'menu')[];
  relay: () => WebSocketLinkHandlers;
  sent: PeerMessage[];
  left: { count: number };
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
  const music = { started: 0, stopped: 0, speeds: [] as number[] };
  const sent: PeerMessage[] = [];
  const left = { count: 0 };
  const captured: ('play' | 'menu')[] = [];
  let relay: WebSocketLinkHandlers | null = null;
  const tools: ShellTools = {
    context: fakeCanvas({ keepLog: false }).context,
    keyboard: { anyOf: (codes) => codes.some((code) => held().includes(code)) },
    gamepads: pads,
    sounds: { play: (name) => played.push(name) },
    music: {
      start: () => (music.started += 1),
      stop: () => (music.stopped += 1),
      setSpeed: (multiplier) => music.speeds.push(multiplier),
    },
    sound,
    setSound: () => undefined,
    captureKeys: (screen) => captured.push(screen),
    newSeed: () => 7,
    openLan: () => undefined,
    leaveLan: () => (left.count += 1),
    connect: (_url, handlers) => {
      relay = handlers;
      return { send: (text) => sent.push(text), close: () => undefined };
    },
  };
  const connected = (): WebSocketLinkHandlers => {
    if (relay === null) throw new Error('つないでいない');
    return relay;
  };
  return { shell: new Shell(elements, tools), elements, played, music, captured, relay: connected, sent, left };
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

  it('試合の画面の間は試合の操作のキーを、メニューの間はメニューのキーを止める', () => {
    const { shell, elements, captured } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    expect(captured.at(-1)).toBe('play');
    press(elements.toolbar, '[data-action="quit"]');
    expect(captured.at(-1)).toBe('menu');
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
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 2], config, match: 1 }));
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

describe('ゲームの速さ', () => {
  function startSolo(shell: Shell, elements: ShellElements): void {
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  /** ツールバーのつまみを動かす（マウスで動かしたときと同じく input が起きる）。 */
  function slide(elements: ShellElements, rate: number): void {
    const input = elements.toolbar.querySelector('[data-field="speed"] input');
    if (!(input instanceof HTMLInputElement)) throw new Error('つまみが無い');
    input.value = String(rate);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  const clock = (elements: ShellElements): string | null | undefined =>
    elements.side.querySelector('.time')?.textContent;

  it('1台の試合では、つまみを2倍にすると、1回の呼び出しで 2 tick 進み、曲も速くなる', () => {
    const { shell, elements, music } = mount();
    startSolo(shell, elements);
    slide(elements, 2);
    // 60回の呼び出しで 120 tick（2秒）。等倍なら 1 秒で「2:59」になる。
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    expect(clock(elements)).toBe('2:58');
    expect(music.speeds).toEqual([2]);
  });

  it('0.5倍なら、2回の呼び出しで 1 tick 進む', () => {
    const { shell, elements } = mount();
    startSolo(shell, elements);
    slide(elements, 0.5);
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(clock(elements)).toBe('2:59');
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(clock(elements)).toBe('2:58');
  });

  it('もういっかいでも速さを保ち、つまみもその倍率から始まる', () => {
    const { shell, elements } = mount();
    startSolo(shell, elements);
    slide(elements, 2);
    shell.restart();
    shell.draw(0);
    expect(elements.toolbar.querySelector('[data-field="speed"] .speed-value')?.textContent).toBe('2×');
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    expect(clock(elements)).toBe('2:58');
  });

  it('0.5倍でも、描く位置は前へ戻らない（補間に渡す進み具合を試合の時間に換える）', () => {
    // 画面は 120Hz（1 tick ぶんの時間に2枚描く）とする。FrameLoop の alpha は実時間の端数なので、
    // そのまま渡すと、tick を進めなかった回に、位置が1つ前の tick の側へ戻る。
    const { shell, elements } = mount('both', () => ['KeyD']);
    startSolo(shell, elements);
    slide(elements, 0.5);
    drawn.length = 0;
    for (let i = 0; i < 20; i += 1) {
      shell.draw(0.5);
      shell.tick();
      shell.draw(0);
    }
    const xs = drawn.filter((view) => view.id === 0).map((view) => view.x);
    expect(xs).toHaveLength(40);
    const backward = xs.flatMap((x, i) => (i > 0 && x < xs[i - 1]! ? [i] : []));
    expect(backward).toEqual([]);
    // 右へ歩いている（止まったままで「戻らない」になっていない）。
    expect(xs.at(-1)! - xs[0]!).toBeGreaterThan(0.2);
  });

  it('通信対戦にはつまみを出さず、前の試合で速くしていても1回の呼び出しで 1 tick だけ進める', () => {
    // 全員の端末が同じ速さで進める必要がある。1台だけ速くしても、ほかの人の入力を待って止まる。
    const { shell, elements, relay, sent, music } = mount();
    startSolo(shell, elements);
    slide(elements, 3);

    shell.startLan('relay.local:8777');
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    // 相手（0番）の入力を先に10 tick ぶん届けておく。待たずに進められる状態にする。
    for (let t = 0; t < 10; t += 1) relay().onMessage(JSON.stringify({ t: 'input', seat: 0, tick: t, bits: 0, match: 1 }));
    shell.draw(0);
    expect(elements.toolbar.querySelector('[data-field="speed"]')).toBeNull();
    // 曲も等倍に戻す。盤面は同じ速さなのに曲だけ速いと、速さが変わったように見える。
    expect(music.speeds).toEqual([3, 1]);

    const inputs = (): number => sent.filter((message) => message.t === 'input').length;
    const before = inputs();
    shell.tick();
    // 1 tick 進めるごとに、自分の入力を1通送る。
    expect(inputs() - before).toBe(1);
  });
});

describe('キーボードでメニューを動かす', () => {
  /** 枠の付いている項目。 */
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];

  it('キーボードだけで、遊び方・動物・ルールを選んで試合を始められる', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    // 最初の「下」は、枠を出したうえで1つ下（2人 vs CPU×2）へ移る。
    shell.navigate('down');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');

    // 画面が替わると、カーソルは先頭（1P の動物の1つ目）へ戻る。
    expect(cursorOf(elements.menu)?.dataset['nav']).toBe('pick-0');
    shell.navigate('right');
    shell.navigate('confirm');
    const second = ANIMAL_LOOKS[1]!;
    const third = ANIMAL_LOOKS[2]!;
    // 選び直しても、カーソルはその行に残る。
    expect(cursorOf(elements.menu)?.dataset['animal']).toBe(second.key);
    shell.navigate('down');
    shell.navigate('right');
    shell.navigate('confirm');
    expect(cursorOf(elements.menu)?.dataset['animal']).toBe(third.key);
    shell.navigate('down');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('rules');

    // 先頭から上へ回ると、いちばん下の「はじめる」。
    shell.navigate('up');
    expect(cursorOf(elements.menu)?.dataset['action']).toBe('start');
    shell.navigate('confirm');
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    const names = [...elements.side.querySelectorAll('.card .name')].map((name) => name.textContent);
    expect(names.slice(0, 2)).toEqual([`${second.name} 1P`, `${third.name} 2P`]);
  });

  it('枠が出ていないときの Enter は、枠を出すだけで押さない', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    expect(cursorOf(elements.menu)).toBeNull();
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('title');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('solo');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
  });

  it('マウスを動かすと枠が消え、次の Enter はまた枠を出すだけになる', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    shell.navigate('down');
    shell.hideCursor();
    expect(cursorOf(elements.menu)).toBeNull();
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('title');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
  });

  it('枠が消えている間にマウスで画面を移っても、画面が替わればカーソルは先頭へ戻る', () => {
    // 画面が替わったことに気づくのが、キーを押したときと枠を出している間だけだと、
    // マウスで行って戻ってきた画面で、前にいた番号からカーソルが動き出す。
    const { shell, elements } = mount();
    shell.showMenu();
    shell.navigate('down');
    shell.navigate('down');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('versus');
    shell.hideCursor();
    press(elements.menu, '[data-choice="solo"]');
    shell.draw(0);
    press(elements.menu, '[data-action="back"]');
    shell.draw(0);
    expect(screenOf(elements)).toBe('title');
    // 先頭（1人）から1つ下へ移る。
    shell.navigate('down');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
  });

  it('遊び方の画面で↑↓を押しても、指す項目が替わらなければページを動かさない', () => {
    // 遊び方の画面でカーソルに載るのは、上の音の設定の1行だけ。↑↓は同じ行へ回るだけなので、
    // そのたびに見える所まで動かすと、下の説明を読んでいる途中でページが上へ引き戻される。
    const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView');
    try {
      const { shell, elements } = mount();
      shell.showMenu();
      press(elements.menu, '[data-choice="manual"]');
      shell.draw(0);
      expect(screenOf(elements)).toBe('manual');
      // 最初の1押しは枠を出す。出した所へは動かす。
      shell.navigate('down');
      const shown = scrolled.mock.calls.length;
      expect(shown).toBe(1);
      shell.navigate('down');
      shell.navigate('up');
      expect(scrolled.mock.calls.length).toBe(shown);
      // 行の中を移ったときは、見える所まで動かす。
      shell.navigate('right');
      expect(scrolled.mock.calls.length).toBe(shown + 1);
    } finally {
      scrolled.mockRestore();
    }
  });

  it('Escape で1つ前の画面へ戻り、タイトルでは何もしない。「← もどる」にはカーソルが乗らない', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    shell.navigate('confirm');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
    expect(elements.menu.querySelector('[data-action="back"]')?.hasAttribute('data-nav')).toBe(false);
    shell.navigate('back');
    expect(screenOf(elements)).toBe('title');
    shell.navigate('back');
    expect(screenOf(elements)).toBe('title');
  });

  it('試合の最中は、矢印や Enter や Escape を押しても何も起きない', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    for (const command of ['down', 'confirm', 'confirm', 'back', 'confirm'] as const) shell.navigate(command);
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    expect(elements.menu.hidden).toBe(true);
    expect(document.querySelector('.navcur')).toBeNull();
    // 試合は作り直されていない（作り直すと時計が 3:00 に戻る）。
    expect(elements.side.querySelector('.time')?.textContent).toBe('2:59');
  });

  it('Enter を押したまま「はじめる」を決めても、開始位置に爆弾を置かない。離して押し直すと置く', () => {
    // Enter は決定のキーで、1人で遊ぶときの爆弾のキーでもある。
    let held: readonly string[] = [];
    const { shell, elements, played } = mount('both', () => held);
    shell.showMenu();
    shell.navigate('confirm');
    shell.navigate('confirm');
    shell.navigate('up');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('rules');
    shell.navigate('up');
    held = ['Enter'];
    shell.navigate('confirm');
    expect(elements.menu.hidden).toBe(true);
    for (let i = 0; i < 30; i += 1) shell.tick();
    expect(played.filter((name) => name === 'place')).toHaveLength(0);
    // 対照：離して押し直せば置く（押しても置かれない、で上が通ってしまわないように）。
    held = [];
    shell.tick();
    held = ['Enter'];
    shell.tick();
    expect(played.filter((name) => name === 'place')).toHaveLength(1);
  });

  /** マウスで、1人・1ラウンド 60 秒の試合を始める。枠は出さない。 */
  function startByMouse(shell: Shell, elements: ShellElements): void {
    shell.showMenu();
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  /** 誰かが優勝して試合が決まった幕が出るまで進め、1枚描く。人間は操作しない（CPU どうしで決まる）。 */
  function playUntilChampion(shell: Shell, elements: ShellElements): void {
    let ticks = 0;
    while (elements.banner.hidden || !elements.banner.textContent?.includes('優勝')) {
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('試合が決まらない');
    }
    shell.draw(0);
  }

  /** 次の試合が始まったか（幕が消え、時計が最初に戻った）。 */
  const restarted = (elements: ShellElements): boolean =>
    elements.banner.hidden && elements.menu.hidden && elements.side.querySelector('.time')?.textContent === '1:00';

  it('キーボードで試合を始めたとき、試合が決まった幕では、キーを押す前から「もういっかい」に枠が付き、1回目の決定で次の試合になる', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    shell.navigate('confirm');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
    shell.navigate('up');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('rules');
    // マウスで押しても枠は消えない（消すのはマウスを動かしたとき）。
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    shell.navigate('up');
    shell.navigate('confirm');
    expect(elements.play.hidden).toBe(false);

    playUntilChampion(shell, elements);
    // 枠は試合の間も出たまま。幕が出たら、描いたときに「もういっかい」へ付け直す。
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('again');
    shell.navigate('confirm');
    shell.draw(0);
    expect(restarted(elements)).toBe(true);
  }, 120_000);

  it('マウスで始めた試合でも、試合が決まった幕の1回目の決定で「もういっかい」になる（原型と同じ）', () => {
    // ほかの画面では、枠が出ていないときの1回目の決定は枠を出すだけ。試合が決まった幕だけは例外にする。
    // 原型もキーボードの Space・Enter でそのまま次へ進め、パッドの A も1回目を飲み込まなかった。
    const { shell, elements } = mount();
    startByMouse(shell, elements);
    playUntilChampion(shell, elements);
    expect(cursorOf(elements.banner)).toBeNull();
    shell.navigate('confirm');
    shell.draw(0);
    expect(restarted(elements)).toBe(true);
  }, 120_000);

  it('試合が決まった幕から「タイトルへ」をキーボードで選ぶと、タイトルの先頭に枠が付き、次の Enter で進む', () => {
    const { shell, elements } = mount();
    startByMouse(shell, elements);
    playUntilChampion(shell, elements);
    // 移動は、枠を出したうえで効く。先頭は「もういっかい」。
    shell.navigate('right');
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('title');
    shell.navigate('confirm');
    expect(elements.menu.hidden).toBe(false);
    expect(screenOf(elements)).toBe('title');
    // 画面が替わったので、描いたときに新しい画面の先頭へ付け直す。見えないまま決まることはない。
    shell.draw(0);
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('solo');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
  }, 120_000);

  it('試合が決まった幕が出るたびに、カーソルは「もういっかい」へ戻る', () => {
    // 戻さないと、前の幕で「タイトルへ」を指したままマウスを動かしていた場合に、次の幕の1回目の
    // 決定で、見えないまま「タイトルへ」が効く。原型も、試合が決まるたびにカーソルを先頭へ戻した。
    const { shell, elements } = mount();
    startByMouse(shell, elements);
    playUntilChampion(shell, elements);
    shell.navigate('right');
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('title');
    shell.hideCursor();
    press(elements.banner, '[data-action="again"]');
    shell.draw(0);
    expect(restarted(elements)).toBe(true);

    playUntilChampion(shell, elements);
    shell.navigate('confirm');
    shell.draw(0);
    expect(restarted(elements)).toBe(true);
  }, 120_000);
});

describe('ゲームパッドとロビーでメニューを動かす', () => {
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];

  /** 押しているボタンの番号を差し替えられるパッド（標準の並び）。 */
  function fakePad(): { read: () => readonly (PadSnapshot | null)[]; hold: (...buttons: number[]) => void } {
    let held = new Set<number>();
    const read = (): readonly (PadSnapshot | null)[] => [
      null,
      {
        mapping: 'standard',
        connected: true,
        index: 1,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
      },
    ];
    return { read, hold: (...buttons) => (held = new Set(buttons)) };
  }
  const A = 0;
  const UP = 12;
  const DOWN = 13;

  /** 押して1枚描き、離して1枚描く。 */
  function tap(shell: Shell, pad: ReturnType<typeof fakePad>, button: number): void {
    pad.hold(button);
    shell.draw(0);
    pad.hold();
    shell.draw(0);
  }

  /** マウスで、その遊び方・1ラウンド 60 秒の試合を始め、誰かが優勝して試合が決まった幕が出るまで進める。 */
  function playToChampionByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    let ticks = 0;
    while (elements.banner.hidden || !elements.banner.textContent?.includes('優勝')) {
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('試合が決まらない');
    }
    shell.draw(0);
  }

  it('2人で遊ぶとき、試合が決まった幕ではパッドを効かせない（原型と同じ）', () => {
    // 2人で遊ぶときはパッドを試合に繋がない。机に置いたパッドに肘が当たっただけで次の試合が
    // 始まらないよう、原型も2人のときは幕でパッドを受け付けなかった（1人と通信対戦のときだけ）。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    playToChampionByMouse(shell, elements, 'duo');
    tap(shell, pad, A);
    expect(elements.banner.hidden).toBe(false);
    expect(elements.menu.hidden).toBe(true);
    // キーボードの決定は効く（原型もキーボードでは人数によらず次へ進めた）。
    shell.navigate('confirm');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
  }, 120_000);

  it('2人の試合の幕でパッドを受け付けない間も、パッドは読み続ける（押したままの A を、タイトルで押し直しと取り違えない）', () => {
    // 受け付けない間に読むのを止めると、前回の状態が古いまま残る。幕で A を押したままキーボードで
    // 「タイトルへ」を選ぶと、タイトルで A が新しい押下に見え、先頭の項目を押してしまう。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    playToChampionByMouse(shell, elements, 'duo');
    pad.hold(A);
    shell.draw(0);
    shell.navigate('right');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('title');
    for (let i = 0; i < 3; i += 1) shell.draw(0);
    expect(screenOf(elements)).toBe('title');
  }, 120_000);

  it('1人で遊ぶとき、試合が決まった幕はパッドの A で次の試合になる', () => {
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    playToChampionByMouse(shell, elements, 'solo');
    tap(shell, pad, A);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.time')?.textContent).toBe('1:00');
  }, 120_000);

  it('メニューでつかんだパッドを試合でもそのまま使い、あとから別のパッドが点いても移らない', () => {
    // 読む側ごとにパッドの番号を覚えると、試合の側が先頭から探し直して、あとから点いた0番をつかむ。
    // 手元の1番では爆弾が置けなくなる（原型も番号を1つだけ持っていた）。
    let awake = false;
    let held = new Set<number>();
    const snapshot = (index: number, pressed: ReadonlySet<number>): PadSnapshot => ({
      mapping: 'standard',
      connected: true,
      index,
      buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: pressed.has(i) })),
      axes: [0, 0, 0, 0],
    });
    const read = (): readonly (PadSnapshot | null)[] => [awake ? snapshot(0, new Set()) : null, snapshot(1, held)];
    const hold = (...buttons: number[]): void => {
      held = new Set(buttons);
    };
    const { shell, elements, played } = mount('both', () => [], read);
    const tapOne = (button: number): void => {
      hold(button);
      shell.draw(0);
      hold();
      shell.draw(0);
    };
    shell.showMenu();
    tapOne(A);
    tapOne(A);
    tapOne(UP);
    tapOne(A);
    expect(screenOf(elements)).toBe('rules');
    // 家族が別のパッドの電源を入れる。
    awake = true;
    tapOne(UP);
    tapOne(A);
    expect(elements.menu.hidden).toBe(true);
    for (let i = 0; i < 10; i += 1) shell.tick();
    hold(A);
    for (let i = 0; i < 3; i += 1) shell.tick();
    expect(played.filter((name) => name === 'place')).toHaveLength(1);
  });

  it('通信対戦でも、ロビーでつかんだパッドを試合でそのまま使う', () => {
    // 通信対戦の試合（LanMatch）も、メニューと同じ PadChoice を読む。試合の側が自分で探すと、
    // ロビーのあとに点いた0番をつかみ、手元の1番の操作が送られない。
    let awake = false;
    let held = new Set<number>();
    const snapshot = (index: number, pressed: ReadonlySet<number>): PadSnapshot => ({
      mapping: 'standard',
      connected: true,
      index,
      buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: pressed.has(i) })),
      axes: [0, 0, 0, 0],
    });
    const read = (): readonly (PadSnapshot | null)[] => [awake ? snapshot(0, new Set()) : null, snapshot(1, held)];
    const { shell, relay, sent } = mount('both', () => [], read);
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    // ロビーを描くと、メニューの側が1番をつかむ。
    shell.draw(0);
    // 試合が始まる前に、家族が別のパッドの電源を入れる。
    awake = true;
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    for (let t = 0; t < 40; t += 1) relay().onMessage(JSON.stringify({ t: 'input', seat: 0, tick: t, bits: 0, match: 1 }));
    shell.draw(0);
    const lastBits = (): number | undefined => {
      const inputs = sent.filter((message) => message.t === 'input');
      const last = inputs.at(-1);
      return last?.t === 'input' ? last.bits : undefined;
    };
    for (let i = 0; i < 5; i += 1) shell.tick();
    // 前提：操作は送っていて、押す前に送った操作はどれも何もしない。
    expect(lastBits()).toBe(0);
    expect(sent.filter((message) => message.t === 'input' && message.bits !== 0)).toEqual([]);
    held = new Set([A]);
    for (let i = 0; i < 3; i += 1) shell.tick();
    expect(lastBits()).toBeGreaterThan(0);
  });

  it('パッドだけで、遊び方を選んで次の画面へ進める', () => {
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    shell.showMenu();
    tap(shell, pad, DOWN);
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
    tap(shell, pad, A);
    expect(screenOf(elements)).toBe('pick');
    expect(elements.menu.querySelectorAll('[data-nav="pick-1"]').length).toBeGreaterThan(0);
  });

  it('A を押したまま次の画面へ移っても、離すまで次の決定は起きない', () => {
    // 前回の状態を画面の切り替えで消すと、押したままの A が次の画面の先頭の項目も押してしまう。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    shell.showMenu();
    tap(shell, pad, A);
    tap(shell, pad, A);
    expect(screenOf(elements)).toBe('pick');
    tap(shell, pad, UP);
    expect(cursorOf(elements.menu)?.dataset['action']).toBe('next');
    pad.hold(A);
    for (let i = 0; i < 5; i += 1) shell.draw(0);
    expect(screenOf(elements)).toBe('rules');
    // 押されていれば、先頭の行（1P の爆風の回数）の1つ目（1回）が選ばれる。
    expect(elements.menu.querySelector('[data-field="hits-p1"] .on')?.textContent).toBe('3回');
  });

  it('パッドの A を押したまま「はじめる」を決めても、開始位置に爆弾を置かない', () => {
    const pad = fakePad();
    const { shell, elements, played } = mount('both', () => [], pad.read);
    shell.showMenu();
    tap(shell, pad, A);
    tap(shell, pad, A);
    tap(shell, pad, UP);
    tap(shell, pad, A);
    expect(screenOf(elements)).toBe('rules');
    tap(shell, pad, UP);
    pad.hold(A);
    shell.draw(0);
    expect(elements.menu.hidden).toBe(true);
    for (let i = 0; i < 30; i += 1) shell.tick();
    expect(played.filter((name) => name === 'place')).toHaveLength(0);
    // 対照：離して押し直せば置く。
    pad.hold();
    shell.tick();
    pad.hold(A);
    shell.tick();
    expect(played.filter((name) => name === 'place')).toHaveLength(1);
  });

  /** 通信対戦のロビーまで進める。 */
  function lobby(seat: number): ReturnType<typeof mount> {
    const mounted = mount();
    mounted.shell.startLan('relay.local:8777');
    mounted.relay().onMessage(JSON.stringify({ t: 'welcome', seat, role: seat === 0 ? 'host' : 'guest', seats: seat === 0 ? [] : [0] }));
    mounted.shell.draw(0);
    return mounted;
  }

  it('ロビーでは、ホストがキーボードで動物を選び、「はじめる」を決められる', () => {
    const { shell, elements, sent } = lobby(0);
    expect(screenOf(elements)).toBe('lobby');
    shell.navigate('right');
    shell.navigate('confirm');
    const second = ANIMAL_LOOKS[1]!;
    expect(cursorOf(elements.menu)?.dataset['nav']).toBe('animal-0');
    // 先頭から上へ回ると、いちばん下の「はじめる」。
    shell.navigate('up');
    expect(cursorOf(elements.menu)?.dataset['action']).toBe('start');
    shell.navigate('confirm');
    const start = sent.find((message) => message.t === 'start');
    expect(start?.t === 'start' ? start.config.match.animals[0] : undefined).toBe(second.key);
  });

  it('ロビーでは、戻るを押しても抜けない。ゲストは何を押しても何も起きない', () => {
    // ぬけるとページを開き直すので、押し間違えると試合ごと抜けてしまう。
    const host = lobby(0);
    host.shell.navigate('back');
    host.shell.navigate('back');
    expect(host.left.count).toBe(0);
    expect(screenOf(host.elements)).toBe('lobby');

    document.body.replaceChildren();
    const guest = lobby(1);
    for (const command of ['down', 'confirm', 'confirm', 'back'] as const) guest.shell.navigate(command);
    expect(guest.left.count).toBe(0);
    expect(cursorOf(guest.elements.menu)).toBeNull();
    expect(guest.sent.filter((message) => message.t === 'start')).toHaveLength(0);
  });
});

describe('通信対戦で、接続を保ったまま次の試合を始める', () => {
  /** 1ラウンド 60 秒・1勝で優勝・体力は爆風1回ぶん。CPU は「おに」なので、人間が動かなくても決まる。 */
  const config = {
    match: { roundLimit: 3600, winsToTake: 1, suddenDeath: true, startingHp: [2, 2, 2, 2], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
    cpu: ['oni', 'oni', 'oni', 'oni'],
  };

  /** 試合が決まった幕が出るまで進める。`others` の人間の入力は、何も押していない入力として中継から届いたことにする。 */
  function playToEnd(shell: Shell, elements: ShellElements, relay: () => WebSocketLinkHandlers, others: readonly number[], match: number): void {
    let delivered = 0;
    let ticks = 0;
    const decided = (): boolean => !elements.banner.hidden && /優勝！|引き分け/.test(elements.banner.textContent ?? '');
    while (!decided()) {
      // 使う前に届くよう、少し先の tick まで届けておく。
      for (; delivered < ticks + 10; delivered += 1) {
        for (const seat of others) relay().onMessage(JSON.stringify({ t: 'input', seat, tick: delivered, bits: 0, match }));
      }
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('試合が決まらない');
    }
  }

  it('ホストだけが、試合が決まった幕の「もういっかい」で次の試合を始められ、幕は次の試合で消える', () => {
    const { shell, elements, relay, sent } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config, match: 1 }));
    shell.draw(0);
    playToEnd(shell, elements, relay, [], 1);

    press(elements.banner, '[data-action="again"]');
    const again = sent.filter((message) => message.t === 'start').at(-1);
    if (again?.t !== 'start') throw new Error('次の試合の合図を送っていない');
    // 同じ設定で、種だけを新しくする（原型も同じ設定のまま次の試合を始めた）。
    expect(again.config.match.animals).toEqual(config.match.animals);
    expect(again.config.match.seed).toBe(7);
    // 中継が配り直すまでは、次の試合を始めない（全員が同じ1通から始める）。
    expect(elements.banner.hidden).toBe(false);

    // 前の試合の通知は、次の試合へ持ち越さない（1台の「もういっかい」と同じ）。
    elements.toasts.append(Object.assign(document.createElement('div'), { className: 'toast', textContent: '前の試合の通知' }));

    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config: again.config, match: 2 }));
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.time')?.textContent).toBe('1:00');
    expect(elements.toasts.childElementCount).toBe(0);
  }, 120_000);

  it('試合が決まったあとにずれが知らされたら、ホストの幕から「もういっかい」を消す', () => {
    // ずれた試合は、決まっていても「決まった」とは扱わない（どの端末の決着が正しいか分からない）。
    // 押しても合図を送らない（LockstepClient.requestStart）ので、ボタンを残すと押しても何も起きない。
    const { shell, elements, relay } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config, match: 1 }));
    shell.draw(0);
    playToEnd(shell, elements, relay, [], 1);
    shell.draw(0);
    expect(elements.banner.querySelector('[data-action="again"]')).not.toBeNull();

    relay().onMessage(JSON.stringify({ t: 'desync', tick: 19, reports: [] }));
    shell.draw(0);
    expect(elements.banner.querySelector('[data-action="again"]')).toBeNull();
  }, 120_000);

  it('ゲストの幕にはボタンを出さず、ホストが次の試合を始めたら幕が消える', () => {
    const { shell, elements, relay } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    playToEnd(shell, elements, relay, [0], 1);

    // 原型もゲストは押せなかった（盤面を進めるのはホストだけ）。
    expect(elements.banner.querySelector('button')).toBeNull();

    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config: { ...config, match: { ...config.match, seed: 2 } }, match: 2 }));
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.time')?.textContent).toBe('1:00');
  }, 120_000);
});
