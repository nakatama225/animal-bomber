// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Shell, type ShellElements, type ShellTools } from '../../src/app/Shell.js';
import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import type { PeerMessage } from '../../src/net/protocol.js';
import type { PadSnapshot } from '../../src/platform/GamepadInput.js';
import { KeyboardWatcher, type KeyboardState } from '../../src/platform/Keyboard.js';
import { SidePanel } from '../../src/platform/ui/SidePanel.js';
import { Toasts } from '../../src/platform/ui/Toasts.js';
import type { WebSocketLinkHandlers } from '../../src/platform/WebSocketLink.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { PanelRefresh } from '../../src/presentation/hud/panelRefresh.js';
import type { SoundSetting } from '../../src/presentation/menu/MenuFlow.js';
import type * as PlayersModule from '../../src/presentation/render/players.js';
import { Renderer } from '../../src/presentation/render/Renderer.js';
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
 * 試合は本物（`GameSession`）を実行する。描画は偽の canvas に描く（ブラウザが例外を出す
 * 呼び方では同じく例外を出す）。音は鳴らさず、鳴らした名前だけを控える。
 */

function press(root: ParentNode, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

/** 横の板のキーの案内の文。キー（原型の `.k`）は [] で囲む（`keyHelpText` と同じ書き方）。 */
function keyHelpOf(root: ParentNode): string {
  const help = root.querySelector('.keyhelp');
  if (help === null) return '';
  const copy = help.cloneNode(true) as HTMLElement;
  for (const key of copy.querySelectorAll('.k')) key.textContent = `[${key.textContent ?? ''}]`;
  return copy.textContent ?? '';
}

/**
 * 画面を組み立てる。
 *
 * @param held いま押しているキー（`KeyboardEvent.code`）。呼ばれるたびに読むので、途中で変えられる。
 *   押した瞬間は残さない（押してすぐ離したキーを見るテストは `keyboard` に本物を渡す）
 * @param pads いまのゲームパッド。同じく呼ばれるたびに読む
 * @param keyboard キーボード。省くと `held` から答える
 * @param context 盤面を描く先。省くと、命令を残さない偽の canvas
 * @param relayAddress 起動の入口が渡す中継の場所（LAN の画面の「たてる」「さんかする」でつなぐ先）
 */
function mount(
  sound: SoundSetting = 'both',
  held: () => readonly string[] = () => [],
  pads: () => readonly (PadSnapshot | null)[] = () => [],
  keyboard?: KeyboardState,
  context: CanvasRenderingContext2D = fakeCanvas({ keepLog: false }).context,
  relayAddress = 'relay.local:8777',
): {
  shell: Shell;
  elements: ShellElements;
  played: SoundName[];
  /** 音の解錠（`unlock`）と鳴らした音の名前を、起きた順に。 */
  audio: string[];
  music: { started: number; stopped: number; speeds: number[] };
  /** いちばん新しい接続の、中継からの知らせの受け口。 */
  relay: () => WebSocketLinkHandlers;
  sent: PeerMessage[];
  /** 作った接続（古い順）。`url` はつないだ先、`closed` は閉じた回数。 */
  links: { url: string; handlers: WebSocketLinkHandlers; closed: number }[];
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
    confirm: make('cfmWrap'),
    toast: make('toast'),
    lanStatus: make('lan-status'),
  };
  const played: SoundName[] = [];
  const audio: string[] = [];
  const music = { started: 0, stopped: 0, speeds: [] as number[] };
  const sent: PeerMessage[] = [];
  const links: { url: string; handlers: WebSocketLinkHandlers; closed: number }[] = [];
  const pressed = (codes: readonly string[]): boolean => codes.some((code) => held().includes(code));
  const tools: ShellTools = {
    context,
    keyboard: keyboard ?? { anyOf: pressed, buttonAnyOf: pressed, forgetTaps: () => undefined },
    gamepads: pads,
    sounds: {
      play: (name) => {
        played.push(name);
        audio.push(name);
      },
    },
    unlockAudio: () => audio.push('unlock'),
    music: {
      start: () => (music.started += 1),
      stop: () => (music.stopped += 1),
      setSpeed: (multiplier) => music.speeds.push(multiplier),
    },
    sound,
    setSound: () => undefined,
    newSeed: () => 7,
    relayAddress,
    connect: (url, handlers) => {
      const link = { url, handlers, closed: 0 };
      links.push(link);
      return { send: (text) => sent.push(text), close: () => (link.closed += 1) };
    },
  };
  const connected = (): WebSocketLinkHandlers => {
    const link = links.at(-1);
    if (link === undefined) throw new Error('つないでいない');
    return link.handlers;
  };
  return { shell: new Shell(elements, tools), elements, played, audio, music, relay: connected, sent, links };
}

afterEach(() => document.body.replaceChildren());

/** 幕（ラウンドの幕か優勝の幕）が出るまで tick を進め、1枚描く。人間は操作しない（CPU どうしで決まる）。 */
function playUntilBanner(shell: Shell, elements: ShellElements, limit = 200_000): void {
  let ticks = 0;
  while (elements.banner.hidden) {
    shell.tick();
    if (ticks % 30 === 0) shell.draw(0);
    ticks += 1;
    if (ticks > limit) throw new Error('幕が出ない');
  }
  shell.draw(0);
}

/**
 * 誰かが優勝して試合が決まった幕が出るまで進め、1枚描く。人間は操作しない（CPU どうしで決まる）。
 * 1台の試合のラウンドの幕は、送るまで次のラウンドへ進まない（原型と同じ）ので、「つぎのラウンド ▶」をマウスで押して送る。
 */
function playUntilChampion(shell: Shell, elements: ShellElements): void {
  for (;;) {
    playUntilBanner(shell, elements);
    if (elements.banner.textContent?.includes('優勝')) return;
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
  }
}

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
    expect(elements.side.querySelectorAll('.pcard')).toHaveLength(4);

    // 人間は操作しない（キーは何も押されていない）。CPU どうしで決まるまで進める。
    playUntilChampion(shell, elements);
    // 幕の「もういっかい」で、同じ設定の新しい試合になる（タイトルへは戻らない）。
    expect(elements.banner.querySelector('[data-action="advance"]')?.textContent).toBe('もういっかい');
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(elements.menu.hidden).toBe(true);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.t')?.textContent).toBe('1:00');

    // 横の板の「設定へ」は、確認を出さずにタイトルへ戻る（原型の注記 L3377-3380）。
    expect(elements.side.querySelector('[data-action="quit"]')?.textContent).toBe('設定へ');
    press(elements.side, '[data-action="quit"]');
    expect(elements.menu.hidden).toBe(false);
    expect(elements.play.hidden).toBe(true);
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
    // 前の試合のものを残さない（横の板は空にする）。
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.childElementCount).toBe(0);
  }, 120_000);

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
    const help = keyHelpOf(elements.side);
    // この端末のプレイヤー（3P のかえる）の案内だけを、1人の形（「そうさ」・WASD と矢印）で出す。
    expect(help).toContain('そうさ');
    expect(help).toContain('した [E][Q][X][C][R][Shift]');
    expect(help).not.toContain('1P');
    expect(help).toContain('[W][A][S][D] / [↑][←][↓][→]');
    // パッドを認識していないので、パッドの段は出さない。通信対戦ではポーズできないので、ポーズの行も出さない。
    expect(help).not.toContain('🎮');
    expect(help).not.toContain('ポーズ');
  });

  it('通信対戦の横の板には、つまみも「⏸ ポーズ」も出さず、「設定へ」だけを出す（押すと接続を閉じ、同じページのタイトルへ戻る）', () => {
    const { shell, elements, relay, links } = mount();
    shell.startLan('relay.local:8777');
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    expect(elements.side.querySelector('[data-field="speed"]')).toBeNull();
    expect([...elements.side.querySelectorAll('.toolbar > .tbtn')].map((button) => button.textContent)).toEqual(['設定へ']);
    press(elements.side, '[data-action="quit"]');
    expect(links.map((link) => link.closed)).toEqual([1]);
    expect(elements.play.hidden).toBe(true);
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
  });

  it('音の設定は起動の間だけ持ち、通信対戦へ移ってタイトルへ戻っても残す（ページを開き直さないので、ブラウザに残さない）', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="manual"]');
    press(elements.menu, '[data-field="sound"] [data-value="off"]');
    press(elements.menu, '[data-action="back"]');
    press(elements.menu, '[data-choice="lan"]');
    press(elements.menu, '[data-action="host"]');
    press(elements.menu, '[data-action="back"]');
    press(elements.confirm, '[data-action="yes"]');
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
    press(elements.menu, '[data-choice="manual"]');
    expect(elements.menu.querySelector('[data-field="sound"] .on')?.textContent).toBe('無音');
  });

  it('ポーズの間は進めず、曲も止め、盤面にポーズの幕を描き、ボタンの字を「▶ 再開」にする', () => {
    const drawn = vi.spyOn(Renderer.prototype, 'draw');
    try {
      const { shell, elements, music } = mount();
      shell.showMenu();
      press(elements.menu, '[data-choice="solo"]');
      press(elements.menu, '[data-action="next"]');
      press(elements.menu, '[data-action="start"]');
      shell.draw(0);
      const time = (): string | null | undefined => elements.side.querySelector('.t')?.textContent;
      const button = (): string | null | undefined => elements.side.querySelector('[data-action="pause"]')?.textContent;
      /** 最後に描いたときに、ポーズの幕を描くと渡したか。 */
      const pausedDrawn = (): unknown => drawn.mock.calls.at(-1)?.[2];
      expect(button()).toBe('⏸ ポーズ');
      expect(pausedDrawn()).toBe(false);

      press(elements.side, '[data-action="pause"]');
      shell.draw(0);
      expect(button()).toBe('▶ 再開');
      expect(pausedDrawn()).toBe(true);
      // 試合の画面に、ポーズの表示の要素は置かない（原型と同じく盤面に描く）。
      expect(document.querySelector('#pause')).toBeNull();
      const stoppedBefore = music.stopped;
      for (let i = 0; i < 120; i += 1) shell.tick();
      shell.draw(0);
      expect(time()).toBe('3:00');
      expect(music.stopped).toBeGreaterThan(stoppedBefore);

      shell.togglePause();
      for (let i = 0; i < 120; i += 1) shell.tick();
      shell.draw(0);
      expect(button()).toBe('⏸ ポーズ');
      expect(pausedDrawn()).toBe(false);
      expect(time()).toBe('2:58');
    } finally {
      drawn.mockRestore();
    }
  });

  it('もういっかいで、同じ設定の新しい試合になる', () => {
    const { shell, elements } = mount();
    shell.showMenu();
    press(elements.menu, '[data-choice="versus"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    for (let i = 0; i < 120; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.side.querySelector('.t')?.textContent).toBe('2:58');

    shell.restart();
    shell.draw(0);
    // 同じ遊び方（2人だけ）で、時計が頭から始まっている。
    expect(elements.side.querySelectorAll('.pcard')).toHaveLength(2);
    expect(elements.side.querySelector('.t')?.textContent).toBe('3:00');
  });

  it('試合を始めるたびに（はじめる・もういっかい）ページの先頭へ戻す（原型の startGame → showScreen）', () => {
    // ルールの画面を下まで動かして「はじめる」を押したとき、盤面の上と時計を窓の外に残さない。
    const toTop = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    try {
      const { shell, elements } = mount();
      shell.showMenu();
      press(elements.menu, '[data-choice="solo"]');
      press(elements.menu, '[data-action="next"]');
      press(elements.menu, '[data-field="wins"] [data-value="5"]');
      const before = toTop.mock.calls.length;
      press(elements.menu, '[data-action="start"]');
      expect(toTop.mock.calls.length).toBe(before + 1);
      expect(toTop).toHaveBeenLastCalledWith(0, 0);
      // 試合を進めている間は戻さない。
      for (let i = 0; i < 60; i += 1) shell.tick();
      shell.draw(0);
      expect(toTop.mock.calls.length).toBe(before + 1);
      // 「もういっかい」は試合の画面のまま次の試合になる。それでも戻す。
      shell.restart();
      shell.draw(0);
      expect(elements.play.hidden).toBe(false);
      expect(toTop.mock.calls.length).toBe(before + 2);
      expect(toTop).toHaveBeenLastCalledWith(0, 0);
    } finally {
      toTop.mockRestore();
    }
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
    const input = elements.side.querySelector('[data-field="speed"] input');
    if (!(input instanceof HTMLInputElement)) throw new Error('つまみが無い');
    input.value = String(rate);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  const clock = (elements: ShellElements): string | null | undefined =>
    elements.side.querySelector('.t')?.textContent;

  it('1台の試合では、つまみを2倍にすると、1回の呼び出しで 2 tick 進み、曲も速くなる', () => {
    const { shell, elements, music } = mount();
    startSolo(shell, elements);
    slide(elements, 2);
    // 60回の呼び出しで 120 tick（2秒）。等倍なら 1 秒で「2:59」になる。
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    expect(clock(elements)).toBe('2:58');
    // 1つ目の 1 は、試合を始めたときに曲をそのときのつまみの倍率（等倍）に合わせたもの。
    expect(music.speeds).toEqual([1, 2]);
  });

  it('通信対戦のあとに始めた1台の試合では、曲の速さをつまみの倍率に戻す（通信対戦は曲を等倍にする）', () => {
    // 合わせないと、盤面はつまみの倍率で進むのに、曲は等倍のまま鳴る（Python 版は1台の試合を始めるたびに合わせる）。
    const { shell, elements, music } = mount();
    startSolo(shell, elements);
    slide(elements, 2);
    shell.startLan('relay.local:8777');
    shell.showMenu();
    expect(music.speeds).toEqual([1, 2, 1]);
    startSolo(shell, elements);
    expect(music.speeds).toEqual([1, 2, 1, 2]);
    expect(elements.side.querySelector('[data-field="speed"] .sv')?.textContent).toBe('2×');
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
    expect(elements.side.querySelector('[data-field="speed"] .sv')?.textContent).toBe('2×');
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

  it('止めている間（ポーズ・ラウンドの幕・決まった試合）は、いまの tick の位置に描く（1つ前の tick の位置との間を往復させない）', () => {
    // 止めている間は tick を進めないので、1つ前の tick の位置の控えが取り直されない。進み具合をそのまま渡すと、
    // 止めた tick に歩いていたプレイヤーが、画面のループの進み具合に合わせて前後に揺れて見える。
    const { shell, elements } = mount('both', () => ['KeyD']);
    startSolo(shell, elements);
    for (let i = 0; i < 5; i += 1) shell.tick();
    const xsOf = (): number[] => drawn.filter((view) => view.id === 0).map((view) => view.x);
    // 対照：進めている間は、進み具合で描く位置が変わる（右へ歩いている）。
    drawn.length = 0;
    for (const alpha of [0, 0.5, 1]) shell.draw(alpha);
    const moving = xsOf();
    expect(moving[1]!).toBeGreaterThan(moving[0]!);
    expect(moving[2]!).toBeGreaterThan(moving[1]!);
    shell.togglePause();
    drawn.length = 0;
    for (const alpha of [0, 0.5, 1]) shell.draw(alpha);
    // どの進み具合でも、いまの tick の位置（進めている間の進み具合 1 と同じ所）。
    expect(xsOf()).toEqual([moving[2], moving[2], moving[2]]);
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
    expect(elements.side.querySelector('[data-field="speed"]')).toBeNull();
    // 曲も等倍に戻す。盤面は同じ速さなのに曲だけ速いと、速さが変わったように見える（1つ目の 1 は、1台の試合を
    // 始めたときに、曲をそのときのつまみの倍率に合わせたもの）。
    expect(music.speeds).toEqual([1, 3, 1]);

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
    const names = [...elements.side.querySelectorAll('.pcard .pn')].map((name) => name.textContent);
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

  it('カーソルを動かしても、ページは動かさない（原型と同じ。画面を替えたときに先頭へ戻すだけ）', () => {
    // 原型は、指す項目が替わっても見える所まで動かさない。窓より縦に長い画面では、窓の外の項目は
    // ホイールで動かしたときに見える。
    const intoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => undefined);
    const toTop = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    try {
      const { shell, elements } = mount();
      shell.showMenu();
      shell.navigate('down');
      shell.navigate('confirm');
      expect(screenOf(elements)).toBe('pick');
      const screens = toTop.mock.calls.length;
      for (const command of ['right', 'right', 'down', 'left', 'down', 'up', 'up'] as const) shell.navigate(command);
      shell.draw(0);
      expect(cursorOf(elements.menu)).not.toBeNull();
      expect(intoView).not.toHaveBeenCalled();
      // 同じ画面の中で動かしただけなら、ページの先頭へも戻さない。
      expect(toTop.mock.calls.length).toBe(screens);
      // 画面を替えたら、ページの先頭へ戻す。
      shell.navigate('back');
      expect(screenOf(elements)).toBe('title');
      expect(toTop.mock.calls.length).toBe(screens + 1);
      expect(toTop).toHaveBeenLastCalledWith(0, 0);
    } finally {
      intoView.mockRestore();
      toTop.mockRestore();
    }
  });

  it('キーボードで決めても画面の操作の音を鳴らし、鳴らす前に音を出せるようにする。「はじめる」は鳴らさない', () => {
    const { shell, elements, audio } = mount();
    shell.showMenu();
    shell.navigate('confirm');
    expect(audio).toEqual([]);
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
    expect(audio).toEqual(['unlock', 'ui']);
    // B で戻ると鳴らす。タイトルの B は何もせず、鳴らさない。
    shell.navigate('back');
    expect(audio).toEqual(['unlock', 'ui', 'unlock', 'ui']);
    shell.navigate('back');
    expect(audio).toHaveLength(4);
    // 「はじめる」は鳴らさない（原型 L6027）。
    shell.navigate('confirm');
    shell.navigate('up');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('rules');
    audio.length = 0;
    shell.navigate('up');
    expect(cursorOf(elements.menu)?.dataset['action']).toBe('start');
    shell.navigate('confirm');
    expect(elements.menu.hidden).toBe(true);
    expect(audio.filter((name) => name === 'ui')).toEqual([]);
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
    expect(elements.side.querySelector('.t')?.textContent).toBe('2:59');
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

  /** マウスで、その遊び方・1ラウンド 60 秒の試合を始める。枠は出さない。 */
  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo' = 'solo'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  /** 次の試合が始まったか（幕が消え、時計が最初に戻った）。 */
  const restarted = (elements: ShellElements): boolean =>
    elements.banner.hidden && elements.menu.hidden && elements.side.querySelector('.t')?.textContent === '1:00';

  /** ラウンドの番号（時計の見出し）。 */
  const roundOf = (elements: ShellElements): string | null | undefined => elements.side.querySelector('.rnd')?.textContent;

  it('キーボードで試合を始めたとき、試合が決まった幕では、キーを押す前から「もういっかい」に枠が付き、Enter で次の試合になる', () => {
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
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('advance');
    shell.navigate('confirm');
    shell.draw(0);
    expect(restarted(elements)).toBe(true);
  }, 120_000);

  it('枠が出ていない幕でも（2人で遊ぶ形）、1回目の Enter でそのまま送る（原型の keydown は幕の Space・Enter で advanceBanner を呼ぶ）', () => {
    // ほかの画面では、枠が出ていないときの1回目の決定は枠を出すだけ。幕は例外（原型 L3082-3084）。
    const { shell, elements } = mount();
    startByMouse(shell, elements, 'duo');
    playUntilBanner(shell, elements);
    expect(roundOf(elements)).toContain('ROUND 1');
    expect(cursorOf(elements.banner)).toBeNull();
    shell.navigate('confirm');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
  }, 120_000);

  it('キーボードで始めた2人の試合でも、幕のボタンに枠を付けない（原型は2人で遊ぶ形の幕を塗らない）。Enter はそのまま送る', () => {
    // メニューで出した枠を持ち越すと、描くたびに幕を塗る形では「つぎのラウンド ▶」に枠が付く。
    const { shell, elements } = mount();
    shell.showMenu();
    shell.navigate('down');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('pick');
    press(elements.menu, '[data-action="next"]');
    expect(screenOf(elements)).toBe('rules');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    shell.navigate('up');
    expect(cursorOf(elements.menu)?.dataset['action']).toBe('start');
    shell.navigate('confirm');
    expect(elements.play.hidden).toBe(false);

    playUntilBanner(shell, elements);
    expect(roundOf(elements)).toContain('ROUND 1');
    expect(cursorOf(elements.banner)).toBeNull();
    shell.navigate('confirm');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
  }, 120_000);

  it('幕では、キーボードの矢印と Escape は何もしない（カーソルを動かせるのはパッドだけ。「⚙ 設定をやりなおす」はマウスかパッドで押す）', () => {
    const { shell, elements } = mount();
    startByMouse(shell, elements, 'duo');
    playUntilBanner(shell, elements);
    for (const command of ['down', 'right', 'up', 'left', 'back'] as const) shell.navigate(command);
    shell.draw(0);
    expect(elements.banner.hidden).toBe(false);
    expect(elements.menu.hidden).toBe(true);
    // 枠も出さない（原型の keydown は、幕では矢印を MENU.nav へ渡さない）。
    expect(cursorOf(elements.banner)).toBeNull();
    expect(roundOf(elements)).toContain('ROUND 1');
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
  const B = 1;
  const SELECT = 8;
  const START = 9;
  const UP = 12;
  const DOWN = 13;
  const RIGHT = 15;

  /** 押して1枚描き、離して1枚描く。 */
  function tap(shell: Shell, pad: ReturnType<typeof fakePad>, button: number): void {
    pad.hold(button);
    shell.draw(0);
    pad.hold();
    shell.draw(0);
  }

  /** マウスで、その遊び方・1ラウンド 60 秒の試合を始める。 */
  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  it('2人で遊ぶとき、幕ではパッドを受け付けない（原型と同じ）', () => {
    // 2人で遊ぶときはパッドを試合に繋がない。机に置いたパッドに肘が当たっただけで次のラウンドへ
    // 進まないよう、原型も2人のときは幕でパッドを受け付けなかった（1人と通信対戦のときだけ）。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'duo');
    playUntilBanner(shell, elements);
    tap(shell, pad, A);
    tap(shell, pad, START);
    expect(elements.banner.hidden).toBe(false);
    expect(elements.menu.hidden).toBe(true);
    // 枠も出さない（原型は2人の形では、幕の分かれ道で枠を出す前に帰る。L3622）。
    expect(cursorOf(elements.banner)).toBeNull();
    // キーボードの決定は受け付ける（原型もキーボードでは人数によらず次へ進めた）。
    shell.navigate('confirm');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
  }, 120_000);

  it('2人の試合の幕でパッドを受け付けない間も、パッドは読み続ける（押したままの A を、タイトルで押し直しと取り違えない）', () => {
    // 受け付けない間に読むのを止めると、前回の状態が古いまま残る。幕で A を押したままマウスで
    // 「⚙ 設定をやりなおす」を押すと、タイトルで A が新しい押下に見え、先頭の項目を押してしまう。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'duo');
    playUntilBanner(shell, elements);
    pad.hold(A);
    shell.draw(0);
    press(elements.banner, '[data-action="setup"]');
    expect(screenOf(elements)).toBe('title');
    for (let i = 0; i < 3; i += 1) shell.draw(0);
    expect(screenOf(elements)).toBe('title');
  }, 120_000);

  it('1人で遊ぶとき、試合が決まった幕はパッドの A で次の試合になる', () => {
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilChampion(shell, elements);
    tap(shell, pad, A);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.t')?.textContent).toBe('1:00');
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

  it('パッドだけで決めても、画面の操作の音を鳴らす前に音を出せるようにする（キーもクリックも無いので、ここでしか解錠しない）', () => {
    const pad = fakePad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    shell.showMenu();
    tap(shell, pad, DOWN);
    expect(audio).toEqual([]);
    tap(shell, pad, A);
    expect(screenOf(elements)).toBe('pick');
    expect(audio).toEqual(['unlock', 'ui']);
  });

  it('A を押したまま次の画面へ移っても、離すまで次の決定は起きない', () => {
    // 前回の状態を画面の切り替えで消すと、押したままの A が次の画面の先頭の項目も押してしまう。
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    shell.showMenu();
    // 先頭の行（1P の爆風の回数）を、マウスで1つ目（1回）でない値にしておく。既定は1つ目と同じ 1回 なので、
    // そのままでは押されたかどうかを見分けられない。
    press(elements.menu, '[data-choice="solo"]');
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="hits-p1"] [data-value="3"]');
    press(elements.menu, '[data-action="back"]');
    press(elements.menu, '[data-action="back"]');
    shell.draw(0);
    expect(screenOf(elements)).toBe('title');
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

  it('ホストのロビーの戻るは「せつぞくを切ります。よいですか？」を開き（枠は「やめる」）、もう一度の戻るは「やめる」（原型 L3335）', () => {
    const host = lobby(0);
    host.audio.length = 0;
    host.shell.navigate('back');
    // 開いたときは、画面の操作の音を鳴らさない（原型の MENU.back は SE.ui を呼ばない）。
    expect(host.audio).toEqual([]);
    expect(host.elements.confirm.hidden).toBe(false);
    expect(host.elements.confirm.querySelector('.cfmMsg')?.textContent).toBe('せつぞくを切ります。よいですか？');
    expect([...host.elements.confirm.querySelectorAll('.chip')].map((chip) => chip.textContent)).toEqual(['やめる', 'せつぞくを切る']);
    expect(cursorOf(host.elements.confirm)?.dataset['action']).toBe('no');
    host.shell.navigate('back');
    expect(host.elements.confirm.hidden).toBe(true);
    expect(host.links.map((link) => link.closed)).toEqual([0]);
    expect(screenOf(host.elements)).toBe('lobby');
    // 「せつぞくを切る」を選ぶと、接続を閉じてタイトルへ戻り、枠を消す。
    host.shell.navigate('back');
    host.shell.navigate('right');
    host.shell.navigate('confirm');
    expect(host.links.map((link) => link.closed)).toEqual([1]);
    expect(screenOf(host.elements)).toBe('title');
    expect(cursorOf(host.elements.menu)).toBeNull();
  });

  it('ゲストのロビーは、キーでは何を押しても何も起きない（項目が無い。原型のコードのとおり）。「← せつぞくを切る」は確認の画面を開き、枠は出さない', () => {
    const guest = lobby(1);
    for (const command of ['down', 'confirm', 'confirm', 'back'] as const) guest.shell.navigate(command);
    expect(guest.elements.confirm.hidden).toBe(true);
    expect(cursorOf(guest.elements.menu)).toBeNull();
    expect(guest.sent.filter((message) => message.t === 'start')).toHaveLength(0);
    // マウスで押したときは、枠を出さない（原型の askDisconnect は MENU.on を立てない。L3381-3383）。
    guest.shell.hideCursor();
    guest.audio.length = 0;
    press(guest.elements.menu, '[data-action="leave"]');
    guest.shell.draw(0);
    expect(guest.audio).toEqual(['unlock', 'ui']);
    expect(guest.elements.confirm.hidden).toBe(false);
    expect(cursorOf(guest.elements.confirm)).toBeNull();
    press(guest.elements.confirm, '[data-action="yes"]');
    expect(guest.links.map((link) => link.closed)).toEqual([1]);
    expect(screenOf(guest.elements)).toBe('title');
  });

  // 盤面が無い間（ロビーと、つないでいる最中の LAN の画面）は、パッドの操作をカーソルへ渡す（原型の pollGamepads は、
  // メニューとロビーでパッドの操作を MENU.nav へ渡す。L3612-3652）。試合の分かれ道（Start でポーズ・Select で設定へ）へは渡さない。

  /** パッドを1つ繋いで、通信対戦のロビーまで進める。 */
  function padLobby(seat: number, pad: ReturnType<typeof fakePad>): ReturnType<typeof mount> {
    const mounted = mount('both', () => [], pad.read);
    mounted.shell.startLan('relay.local:8777');
    mounted.relay().onMessage(JSON.stringify({ t: 'welcome', seat, role: seat === 0 ? 'host' : 'guest', seats: seat === 0 ? [] : [0] }));
    mounted.shell.draw(0);
    return mounted;
  }

  it('ホストのロビーでは、パッドの十字で動物を動かし、A で選べる', () => {
    const pad = fakePad();
    const { shell, elements } = padLobby(0, pad);
    expect(screenOf(elements)).toBe('lobby');
    const first = elements.menu.querySelector('[data-field="animal-0"] .on')?.getAttribute('data-value');
    tap(shell, pad, RIGHT);
    tap(shell, pad, A);
    const second = ANIMAL_LOOKS[1]!;
    expect(first).not.toBe(second.key);
    expect(cursorOf(elements.menu)?.dataset['nav']).toBe('animal-0');
    expect(elements.menu.querySelector('[data-field="animal-0"] .on')?.getAttribute('data-value')).toBe(second.key);
  });

  it('ホストのロビーでパッドの B を押すと「せつぞくを切ります。よいですか？」を開き（枠は「やめる」）、もう一度の B は「やめる」', () => {
    const pad = fakePad();
    const { shell, elements, links } = padLobby(0, pad);
    tap(shell, pad, B);
    expect(elements.confirm.hidden).toBe(false);
    expect(elements.confirm.querySelector('.cfmMsg')?.textContent).toBe('せつぞくを切ります。よいですか？');
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('no');
    tap(shell, pad, B);
    expect(elements.confirm.hidden).toBe(true);
    expect(links.map((link) => link.closed)).toEqual([0]);
    expect(screenOf(elements)).toBe('lobby');
  });

  it('つないでいる最中の LAN の画面でも、パッドの B で「せつぞくを切ります。よいですか？」を開く（カーソルの項目が無くても）', () => {
    const pad = fakePad();
    const { shell, elements, links } = mount('both', () => [], pad.read);
    shell.startLan('relay.local:8777');
    shell.draw(0);
    expect(screenOf(elements)).toBe('lan');
    tap(shell, pad, B);
    expect(elements.confirm.hidden).toBe(false);
    expect(elements.confirm.querySelector('.cfmMsg')?.textContent).toBe('せつぞくを切ります。よいですか？');
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('no');
    expect(links.map((link) => link.closed)).toEqual([0]);
  });

  it('つないでいる最中の LAN の画面とロビーでは、パッドの Select で「設定へもどりますか？」を開かない（枠を出すだけ）', () => {
    const pad = fakePad();
    const { shell, elements, relay } = mount('both', () => [], pad.read);
    shell.startLan('relay.local:8777');
    shell.draw(0);
    tap(shell, pad, SELECT);
    expect(elements.confirm.hidden).toBe(true);
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('lobby');
    tap(shell, pad, SELECT);
    expect(elements.confirm.hidden).toBe(true);
    expect(elements.confirm.textContent).not.toContain('設定へもどりますか？');
    expect(cursorOf(elements.menu)).not.toBeNull();
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
    // 試合が決まるのは優勝者が出たときだけ（原型の endGame の3つの形。優勝者のいない「引き分け」の幕は無い）。
    const decided = (): boolean => !elements.banner.hidden && /優勝！/.test(elements.banner.textContent ?? '');
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
    // ホストには「もういっかい」と「⚙ 設定をやりなおす」を出す。
    expect([...elements.banner.querySelectorAll('button')].map((button) => button.textContent)).toEqual([
      'もういっかい',
      '⚙ 設定をやりなおす',
    ]);

    press(elements.banner, '[data-action="advance"]');
    const again = sent.filter((message) => message.t === 'start').at(-1);
    if (again?.t !== 'start') throw new Error('次の試合の合図を送っていない');
    // 同じ設定で、種だけを新しくする（原型も同じ設定のまま次の試合を始めた）。
    expect(again.config.match.animals).toEqual(config.match.animals);
    expect(again.config.match.seed).toBe(7);
    // 中継が配り直すまでは、次の試合を始めない（全員が同じ1通から始める）。
    expect(elements.banner.hidden).toBe(false);

    // 出ている通知は、次の試合が始まっても消さない（時間でだけ消える。原型と同じ）。
    elements.toast.textContent = '前の試合の通知';
    elements.toast.classList.add('on');

    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config: again.config, match: 2 }));
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.t')?.textContent).toBe('1:00');
    expect(elements.toast.textContent).toBe('前の試合の通知');
    expect(elements.toast.classList.contains('on')).toBe(true);
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
    expect(elements.banner.querySelector('[data-action="advance"]')).not.toBeNull();

    relay().onMessage(JSON.stringify({ t: 'desync', tick: 19, reports: [] }));
    shell.draw(0);
    expect(elements.banner.querySelector('[data-action="advance"]')).toBeNull();
    // 抜ける道は残す。
    expect(elements.banner.querySelector('[data-action="setup"]')).not.toBeNull();
  }, 120_000);

  it('ラウンドの最中（決着の前）にずれが知らされたら、曲を止めて鳴らし直さない。帯に理由を出す', () => {
    const { shell, elements, relay, music } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config, match: 1 }));
    shell.draw(0);
    for (let i = 0; i < 5; i += 1) shell.tick();
    shell.draw(0);
    // 前提：ラウンドの最中で、曲は鳴っている。
    expect(elements.banner.hidden).toBe(true);
    const started = music.started;
    expect(started).toBeGreaterThan(0);
    const stopped = music.stopped;

    relay().onMessage(JSON.stringify({ t: 'desync', tick: 3, reports: [] }));
    shell.draw(0);
    shell.draw(0);
    expect(music.started).toBe(started);
    expect(music.stopped).toBe(stopped + 2);
    expect(elements.lanStatus.textContent).toContain('端末どうしで試合がずれたので止めた');
    expect(elements.banner.hidden).toBe(true);
  });

  it('ゲストの幕には「⚙ 設定をやりなおす」だけを出し（押すと抜ける）、ホストが次の試合を始めたら幕が消える', () => {
    const { shell, elements, relay, sent, links } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    playToEnd(shell, elements, relay, [0], 1);
    shell.draw(0);

    // 次の試合を始められるのはホストだけ（原型も盤面を進めるのはホストだけ）。全員に幕を出すので、ゲストにも抜ける道を出す。
    expect([...elements.banner.querySelectorAll('button')].map((button) => button.dataset['action'])).toEqual(['setup']);
    // Enter でも合図を送らない。
    shell.navigate('confirm');
    expect(sent.filter((message) => message.t === 'start')).toEqual([]);

    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config: { ...config, match: { ...config.match, seed: 2 } }, match: 2 }));
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.t')?.textContent).toBe('1:00');

    playToEnd(shell, elements, relay, [0], 2);
    shell.draw(0);
    press(elements.banner, '[data-action="setup"]');
    expect(links.map((link) => link.closed)).toEqual([1]);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
  }, 120_000);

  it('ラウンドの幕にはボタンを出さず、決着のあとの待ち（2 秒）で消える。幕の間は曲を止め、次のラウンドで鳴らし直す', () => {
    const { shell, elements, relay, music } = mount();
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config: { ...config, match: { ...config.match, winsToTake: 3 } }, match: 1 }));
    shell.draw(0);
    let ticks = 0;
    while (elements.banner.hidden) {
      shell.tick();
      shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('幕が出ない');
    }
    expect(elements.banner.textContent).toContain('ラウンド1');
    expect(elements.banner.querySelector('button')).toBeNull();
    // パッドもキーボードも受け付けない（送る口が無い）。曲は止める。
    shell.navigate('confirm');
    const started = music.started;
    shell.draw(0);
    expect(music.started).toBe(started);
    let rest = 0;
    while (!elements.banner.hidden) {
      shell.tick();
      shell.draw(0);
      rest += 1;
      if (rest > 200) throw new Error('幕が消えない');
    }
    // 2 秒（120 tick）の待ちが尽きた tick に、次のラウンドの盤面になる。
    expect(rest).toBe(120);
    expect(music.started).toBe(started + 1);
  }, 120_000);
});

describe('通信対戦の画面の流れ（同じページでつなぎ、切ってタイトルへ戻る）', () => {
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];
  const lanStatusOf = (elements: ShellElements): string | null | undefined => elements.menu.querySelector('[data-lan-status]')?.textContent;
  const dialogOpen = (elements: ShellElements): boolean => !elements.confirm.hidden;
  const message = (value: object): string => JSON.stringify(value);
  const config = {
    match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'frog'] },
    cpu: ['easy', 'hard'],
  };

  /** タイトルから「LAN対戦」→「たてる」まで、マウスで押す。 */
  function connectByMouse(shell: Shell, elements: ShellElements, action: 'host' | 'join' = 'host'): void {
    press(elements.menu, '[data-choice="lan"]');
    press(elements.menu, `[data-action="${action}"]`);
    shell.draw(0);
  }

  it('タイトルの「LAN対戦」で同じページの LAN の画面へ移り、「たてる」で起動の入口から受け取った中継へつなぐ。番号を受け取るとロビーへ', () => {
    // 起動の入口が渡す中継は、テストのほかの所で使う場所と違う値にする（決め打ちの場所へつないでも通らないように）。
    const { shell, elements, links } = mount(undefined, undefined, undefined, undefined, undefined, 'other.local:9000');
    shell.showMenu();
    press(elements.menu, '[data-choice="lan"]');
    expect(screenOf(elements)).toBe('lan');
    expect(links).toHaveLength(0);
    press(elements.menu, '[data-action="host"]');
    shell.draw(0);
    expect(links.map((link) => link.url)).toEqual(['ws://other.local:9000/lockstep']);
    // つないでいる最中は「接続しています…」と「← もどる」だけ（「たてる」「さんかする」は出さない）。
    expect(screenOf(elements)).toBe('lan');
    expect(lanStatusOf(elements)).toBe('接続しています…');
    expect(elements.menu.querySelectorAll('[data-nav]')).toHaveLength(0);
    // もう一度つなごうとしても、2本目はつながない。
    shell.startLan('relay.local:8777');
    expect(links).toHaveLength(1);

    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('lobby');
    expect(elements.play.hidden).toBe(true);
  });

  it('切って、タイトルへ戻って、同じページでもう一度つなぐ。前の接続のもの（試合・案内の帯・カーソル・確認の画面・「接続しています…」）を残さない', () => {
    // 試合の最中にパッドの Select で確認の画面を開くため、パッドを1つ繋いでおく。
    let held = new Set<number>();
    const pad = (): readonly (PadSnapshot | null)[] => [
      {
        mapping: 'standard',
        connected: true,
        index: 0,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
      },
    ];
    const SELECT = 8;
    const { shell, elements, links, sent } = mount('both', () => [], pad);
    shell.showMenu();
    connectByMouse(shell, elements);
    const first = links[0]!.handlers;
    first.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [1] }));
    shell.draw(0);
    // ホストが2P の動物を選び（これは次の接続にも残す。原型の CFG と同じ）、キーで枠を出してから始める。
    press(elements.menu, '[data-field="animal-1"] [data-value="mole"]');
    shell.navigate('down');
    expect(cursorOf(elements.menu)).not.toBeNull();
    press(elements.menu, '[data-action="start"]');
    const start = sent.find((sentMessage) => sentMessage.t === 'start');
    if (start?.t !== 'start') throw new Error('はじめるの合図を送っていない');
    first.onMessage(message({ t: 'start', seats: [0, 1], config: start.config, match: 1 }));
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    // 2P の入力は届かないので、先に送ってある分を使い切ると待ち、待ちが続くと案内の帯に出る。
    for (let i = 0; i < 100; i += 1) shell.tick();
    for (let i = 0; i < 40; i += 1) shell.draw(0);
    expect(elements.lanStatus.hidden).toBe(false);
    expect(elements.lanStatus.textContent).toContain('2P の操作を待っている');

    // 確認の画面を開いたまま抜ける（通信対戦のパッドの Select は、試合の最中ならいつでも「設定へもどりますか？」を開く）。
    // ブラウザでは確認の画面が横の板を覆うが、接続が切れたときなど、開いたまま抜ける道はあり、どれも showMenu を通る。
    held = new Set([SELECT]);
    shell.draw(0);
    held = new Set();
    shell.draw(0);
    expect(dialogOpen(elements)).toBe(true);
    press(elements.side, '[data-action="quit"]');
    shell.draw(0);
    expect(links.map((link) => link.closed)).toEqual([1]);
    expect(dialogOpen(elements)).toBe(false);
    expect(screenOf(elements)).toBe('title');
    expect(elements.lanStatus.hidden).toBe(true);
    expect(elements.lanStatus.textContent).toBe('');
    expect(cursorOf(elements.menu)).toBeNull();

    // もう一度 LAN の画面を開くと、つないでいない形（「接続しています…」は出ない）。
    press(elements.menu, '[data-choice="lan"]');
    expect(lanStatusOf(elements)).toBe('');
    expect(elements.menu.querySelectorAll('.menu > .mbtn')).toHaveLength(2);
    press(elements.menu, '[data-action="join"]');
    shell.draw(0);
    expect(links).toHaveLength(2);
    expect(lanStatusOf(elements)).toBe('接続しています…');

    // 前の接続から遅れて届いた知らせは、何もしない（前の接続を持つ試合はもう無い）。通知も替えない（出ているのは、パッドを
    // 見つけた知らせ）。
    const toastBefore = elements.toast.textContent;
    first.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    first.onClose(1006, true);
    shell.draw(0);
    expect(screenOf(elements)).toBe('lan');
    expect(lanStatusOf(elements)).toBe('接続しています…');
    expect(elements.toast.textContent).toBe(toastBefore);
    expect(elements.toast.textContent).not.toContain('接続が切れました');

    links[1]!.handlers.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('lobby');
    expect(dialogOpen(elements)).toBe(false);
    expect(cursorOf(elements.menu)).toBeNull();
    expect(elements.lanStatus.hidden).toBe(true);
    expect(elements.menu.querySelector('[data-field="animal-1"] .on')?.getAttribute('data-value')).toBe('mole');
    // 2本目の接続で始めた試合は、前の試合を引き継がない（1試合目から）。
    press(elements.menu, '[data-action="start"]');
    const again = sent.filter((sentMessage) => sentMessage.t === 'start').at(-1);
    if (again?.t !== 'start') throw new Error('はじめるの合図を送っていない');
    links[1]!.handlers.onMessage(message({ t: 'start', seats: [0], config: again.config, match: 1 }));
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    expect(elements.side.querySelector('.t')?.textContent).toBe('3:00');
  });

  it('つないでいる最中の LAN の画面の B（Escape）は「せつぞくを切ります。よいですか？」を開く。開いたままロビーへ移ったら畳む', () => {
    const { shell, elements, links, audio } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    audio.length = 0;
    shell.navigate('back');
    expect(dialogOpen(elements)).toBe(true);
    expect(elements.confirm.querySelector('.cfmMsg')?.textContent).toBe('せつぞくを切ります。よいですか？');
    // B で開いたときは、画面の操作の音を鳴らさない（原型の MENU.back は SE.ui を呼ばない）。
    expect(audio).toEqual([]);
    // キーで開いたので、枠を出してカーソルを「やめる」に置く。
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('no');
    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('lobby');
    expect(dialogOpen(elements)).toBe(false);
  });

  it('つないでいる最中に「せつぞくを切る」を選ぶと、接続を閉じてタイトルへ戻り、「接続しています…」を消す。「← もどる」でも同じ確認を出す', () => {
    const { shell, elements, links, audio } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    audio.length = 0;
    press(elements.menu, '[data-action="back"]');
    shell.draw(0);
    expect(audio).toEqual(['unlock', 'ui']);
    expect(dialogOpen(elements)).toBe(true);
    // マウスで開いたので、枠は出さない（原型の askDisconnect は MENU.on を立てない。L3381-3383）。
    expect(cursorOf(elements.confirm)).toBeNull();
    press(elements.confirm, '[data-action="yes"]');
    shell.draw(0);
    expect(links.map((link) => link.closed)).toEqual([1]);
    expect(screenOf(elements)).toBe('title');
    press(elements.menu, '[data-choice="lan"]');
    expect(lanStatusOf(elements)).toBe('');
  });

  it('ロビーで確認の画面を開いたまま、ホストが始めたら畳む（原型の showScreen の closeDialog。N2）', () => {
    const { shell, elements, links } = mount();
    shell.showMenu();
    connectByMouse(shell, elements, 'join');
    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    shell.draw(0);
    press(elements.menu, '[data-action="leave"]');
    expect(dialogOpen(elements)).toBe(true);
    links[0]!.handlers.onMessage(message({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    expect(elements.play.hidden).toBe(false);
    expect(dialogOpen(elements)).toBe(false);
    expect(elements.confirm.childElementCount).toBe(0);
  });

  it('ロビーへ移る前に断られたら、LAN の画面に留まって理由を出す。また押せて、押すと新しい接続でつなぐ', () => {
    const { shell, elements, links, audio } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    links[0]!.handlers.onClose(1013, true);
    shell.draw(0);
    expect(screenOf(elements)).toBe('lan');
    expect(lanStatusOf(elements)).toBe('前の試合が続いているか、定員いっぱいで入れなかった');
    expect(links[0]!.closed).toBe(1);
    // 断られた理由は帯に出さない。止まった接続の START_OVER（「設定へ」でタイトルへ）も添えない。
    expect(elements.menu.textContent).not.toContain('もう一度遊ぶときは');
    expect(elements.lanStatus.hidden).toBe(true);
    expect(elements.menu.querySelectorAll('.menu > .mbtn')).toHaveLength(2);
    press(elements.menu, '[data-action="join"]');
    shell.draw(0);
    expect(links).toHaveLength(2);
    expect(lanStatusOf(elements)).toBe('接続しています…');
    links[1]!.handlers.onClose(1006, false);
    shell.draw(0);
    expect(lanStatusOf(elements)).toBe('中継（relay.local:8777）につなげなかった');
    // LAN の画面の B は、つないでいないのでタイトルへ戻る（確認を出さない）。1つ前の画面へ戻ったので、操作の音を鳴らす。
    audio.length = 0;
    shell.navigate('back');
    expect(dialogOpen(elements)).toBe(false);
    expect(screenOf(elements)).toBe('title');
    expect(audio).toEqual(['unlock', 'ui']);
  });

  it('つないでいる最中に開いた確認の画面は、ロビーへ移る前に断られたら畳む。また押してつないだロビーにも残さない', () => {
    const { shell, elements, links } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    shell.navigate('back');
    expect(dialogOpen(elements)).toBe(true);
    // 開いたまま断られる。接続を手放すので、切るかを聞く画面を残さない（原型にこの道は無い。タイトルへ戻る道と同じく畳む）。
    links[0]!.handlers.onClose(1013, true);
    shell.draw(0);
    expect(dialogOpen(elements)).toBe(false);
    expect(elements.confirm.childElementCount).toBe(0);
    expect(screenOf(elements)).toBe('lan');
    expect(lanStatusOf(elements)).toBe('前の試合が続いているか、定員いっぱいで入れなかった');
    // また押してつなぎ、ロビーへ移っても、前の接続で開いた確認の画面は出ない。
    press(elements.menu, '[data-action="join"]');
    links[1]!.handlers.onMessage(message({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('lobby');
    expect(dialogOpen(elements)).toBe(false);
  });

  it('ロビーへ移ったあとに中継との接続が切れたら、タイトルへ戻して「サーバとの接続が切れました」を出す（試合の最中も。原型の onclose）', () => {
    const lobby = mount();
    lobby.shell.showMenu();
    connectByMouse(lobby.shell, lobby.elements);
    lobby.links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    lobby.shell.draw(0);
    lobby.links[0]!.handlers.onClose(1006, true);
    lobby.shell.draw(0);
    expect(screenOf(lobby.elements)).toBe('title');
    expect(lobby.elements.toast.textContent).toBe('サーバとの接続が切れました');

    document.body.replaceChildren();
    const { shell, elements, links } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    links[0]!.handlers.onMessage(message({ t: 'start', seats: [0], config, match: 1 }));
    shell.draw(0);
    for (let i = 0; i < 5; i += 1) shell.tick();
    expect(elements.play.hidden).toBe(false);
    links[0]!.handlers.onClose(1006, true);
    shell.draw(0);
    expect(elements.play.hidden).toBe(true);
    expect(screenOf(elements)).toBe('title');
    expect(elements.toast.textContent).toBe('サーバとの接続が切れました');
    expect(elements.side.childElementCount).toBe(0);
    expect(elements.lanStatus.hidden).toBe(true);
    expect(cursorOf(elements.menu)).toBeNull();
  });

  it('ロビーでホストが抜けたら、タイトルへ戻して「ホストとの接続が切れました」を出す（原型 L3779-3789）', () => {
    const { shell, elements, links } = mount();
    shell.showMenu();
    connectByMouse(shell, elements, 'join');
    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    shell.draw(0);
    links[0]!.handlers.onMessage(message({ t: 'peer_left', seat: 0, lastTick: -1 }));
    shell.draw(0);
    expect(screenOf(elements)).toBe('title');
    expect(elements.toast.textContent).toBe('ホストとの接続が切れました');
    expect(links[0]!.closed).toBe(1);
  });

  it('URL の ?relay で開いたときと同じく、startLan はすぐ LAN の画面を出してつなぐ（起動の幕からタイトルを通らない）', () => {
    const { shell, elements, links } = mount();
    shell.startLan('other.local:9000');
    expect(screenOf(elements)).toBe('lan');
    expect(lanStatusOf(elements)).toBe('接続しています…');
    expect(links.map((link) => link.url)).toEqual(['ws://other.local:9000/lockstep']);
  });

  it('通信対戦の試合が始まって盤面へ移るときは、ページの先頭へ戻す。つないだときには戻さない（原型の startGame → showScreen と joinLan）', () => {
    const scrolled = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    try {
      const { shell, elements, links } = mount();
      shell.showMenu();
      press(elements.menu, '[data-choice="lan"]');
      const beforeConnect = scrolled.mock.calls.length;
      press(elements.menu, '[data-action="host"]');
      shell.draw(0);
      expect(scrolled.mock.calls.length).toBe(beforeConnect);
      links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
      shell.draw(0);
      // ロビーへ移ったとき（原型の showScreen('lobby')）。
      expect(scrolled.mock.calls.length).toBe(beforeConnect + 1);
      links[0]!.handlers.onMessage(message({ t: 'start', seats: [0], config, match: 1 }));
      shell.draw(0);
      expect(scrolled.mock.calls.length).toBe(beforeConnect + 2);
      expect(scrolled).toHaveBeenLastCalledWith(0, 0);
    } finally {
      scrolled.mockRestore();
    }
  });

  it('試合の途中で抜けたプレイヤーを CPU が引き継いだら、通知を出し、名札をすぐ作り直す（原型 L3793）', () => {
    const { shell, elements, links } = mount();
    shell.showMenu();
    connectByMouse(shell, elements);
    links[0]!.handlers.onMessage(message({ t: 'welcome', seat: 0, role: 'host', seats: [1] }));
    links[0]!.handlers.onMessage(message({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    const tagOf = (index: number): string => elements.side.querySelectorAll('.pcard')[index]?.textContent ?? '';
    expect(tagOf(1)).toContain('2P');
    // 2P は1通も送らずに抜けた。次の tick から CPU が受け持つ。
    links[0]!.handlers.onMessage(message({ t: 'peer_left', seat: 1, lastTick: -1 }));
    shell.draw(0);
    expect(elements.toast.textContent).toBe('');
    shell.tick();
    expect(elements.toast.textContent).toBe('かえる の回線が切れた → CPU が引き継ぐ');
    // 名札の作り直しの区切り（15 tick）を待たずに、次に描くときに札を替える。
    shell.draw(0);
    expect(tagOf(1)).toContain('CPU1・つよい');
  });
});

describe('押してすぐ離したキーとボタン（押した瞬間を忘れる時）', () => {
  const watcher = new KeyboardWatcher();
  afterEach(() => watcher.detach());

  function keydown(code: string): void {
    window.dispatchEvent(new KeyboardEvent('keydown', { code, cancelable: true }));
  }
  function keyup(code: string): void {
    window.dispatchEvent(new KeyboardEvent('keyup', { code }));
  }
  /** tick と tick の間に押して離す。 */
  function tapKey(code: string): void {
    keydown(code);
    keyup(code);
  }

  /** マウスで、その遊び方の試合を始める。2人タイマンなら CPU がいないので、置いた爆弾は人間のものだけ。 */
  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'versus'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  /** ツールバーのつまみで、ゲームの速さを変える。 */
  function slide(elements: ShellElements, rate: number): void {
    const input = elements.side.querySelector('[data-field="speed"] input');
    if (!(input instanceof HTMLInputElement)) throw new Error('つまみが無い');
    input.value = String(rate);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  const places = (played: readonly SoundName[]): number => played.filter((name) => name === 'place').length;

  it('tick と tick の間に押して離した爆弾のキーも、次の tick で読んで爆弾を置く', () => {
    watcher.attach();
    const { shell, elements, played } = mount('both', () => [], () => [], watcher);
    startByMouse(shell, elements, 'versus');
    // ラウンドの始まりは、爆弾のボタンを押していた扱い。一度離した tick を通す。
    shell.tick();
    shell.tick();
    tapKey('Space');
    shell.tick();
    expect(places(played)).toBe(1);
  });

  it('0.5 倍で tick を進めない回と描く回をはさんでも、押してすぐ離したキーを忘れずに、次に進めた tick で読む', () => {
    watcher.attach();
    const { shell, elements, played } = mount('both', () => [], () => [], watcher);
    startByMouse(shell, elements, 'versus');
    slide(elements, 0.5);
    // 0.5 倍は、2回の呼び出しで 1 tick 進む（進まない回・進む回の順）。
    for (let i = 0; i < 4; i += 1) shell.tick();
    tapKey('Space');
    shell.tick();
    shell.draw(0);
    expect(places(played)).toBe(0);
    shell.tick();
    expect(places(played)).toBe(1);
  });

  it('ポーズの間に押して離したキーは、再開した最初の tick に残らない（止めている間は毎フレーム忘れる）', () => {
    watcher.attach();
    const { shell, elements, played } = mount('both', () => [], () => [], watcher);
    startByMouse(shell, elements, 'versus');
    shell.tick();
    shell.tick();
    press(elements.side, '[data-action="pause"]');
    tapKey('Space');
    shell.tick();
    shell.draw(0);
    shell.togglePause();
    shell.tick();
    expect(places(played)).toBe(0);
    // 対照：再開したあとに押して離せば置く（置けない状況で上が通ってしまわないように）。
    tapKey('Space');
    shell.tick();
    expect(places(played)).toBe(1);
  });

  it('決定のキーを押したまま「はじめる」を決めても、開始位置に爆弾を置かない。離してもう一度押すと置く', () => {
    // Enter は決定のキーで、2人タイマンの 2P の爆弾のキーでもある。押した瞬間を残しても、ラウンドの始まりは
    // 押していた扱いなので置かない（`HELD_AT_ROUND_START`）。
    watcher.attach();
    const { shell, elements, played } = mount('both', () => [], () => [], watcher);
    shell.showMenu();
    press(elements.menu, '[data-choice="versus"]');
    press(elements.menu, '[data-action="next"]');
    // 先頭から上へ回ると、いちばん下の「はじめる」（枠を出したうえで移る）。
    shell.navigate('up');
    expect(elements.menu.querySelector('.navcur')?.getAttribute('data-action')).toBe('start');
    keydown('Enter');
    shell.navigate('confirm');
    expect(elements.menu.hidden).toBe(true);
    for (let i = 0; i < 30; i += 1) shell.tick();
    expect(places(played)).toBe(0);
    keyup('Enter');
    shell.tick();
    keydown('Enter');
    shell.tick();
    expect(places(played)).toBe(1);
  });

  it('忘れるのは、進めた tick のあとと、止めている間・試合の外の毎フレームだけ', () => {
    let forgets = 0;
    const keyboard: KeyboardState = { anyOf: () => false, buttonAnyOf: () => false, forgetTaps: () => (forgets += 1) };
    const { shell, elements, relay } = mount('both', () => [], () => [], keyboard);
    const counted = (act: () => void): number => {
      const before = forgets;
      act();
      return forgets - before;
    };
    shell.showMenu();
    // 試合の外：描くたびに忘れる。
    expect(counted(() => shell.draw(0))).toBe(1);
    startByMouse(shell, elements, 'versus');
    // 試合の最中：進めた tick のあとに1回ずつ。描いても忘れない。
    expect(counted(() => shell.tick())).toBe(1);
    expect(counted(() => shell.draw(0))).toBe(0);
    slide(elements, 2);
    expect(counted(() => shell.tick())).toBe(2);
    slide(elements, 0.5);
    expect(counted(() => shell.tick())).toBe(0);
    expect(counted(() => shell.draw(0))).toBe(0);
    // 止めている間：進めないので tick では忘れず、描くたびに忘れる。
    shell.togglePause();
    expect(counted(() => shell.tick())).toBe(0);
    expect(counted(() => shell.draw(0))).toBe(1);

    // 通信対戦：ロビー（盤面が無い）は描くたびに忘れる。入力を待って進めない間は忘れない。
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    expect(counted(() => shell.draw(0))).toBe(1);
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    expect(counted(() => shell.tick())).toBe(0);
    expect(counted(() => shell.draw(0))).toBe(0);
    // 相手の入力が届けば進めて、送ったあとに忘れる。
    relay().onMessage(JSON.stringify({ t: 'input', seat: 0, tick: 0, bits: 0, match: 1 }));
    expect(counted(() => shell.tick())).toBe(1);
  });

  it('パッドも、0.5 倍で tick を進めない回に押して離した A を、次に進めた tick で読んで爆弾を置く', () => {
    // パッドは描くたびに読むので、そこで押した瞬間を残す（試合の側は tick を進めるときにしか読まない）。
    // パッドを試合に繋ぐのは1人で遊ぶときだけで、CPU も爆弾を置く。同じ種で A を押さない試合を対照に実行し、
    // 置いた数の差で見る（CPU が同じ tick に置いても、押しを読まなければ差は 0 になる）。
    const placedBy = (tapA: boolean): number => {
      let held = new Set<number>();
      const read = (): readonly (PadSnapshot | null)[] => [
        {
          mapping: 'standard',
          connected: true,
          index: 0,
          buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
          axes: [0, 0, 0, 0],
        },
      ];
      const { shell, elements, played } = mount('both', () => [], read);
      startByMouse(shell, elements, 'solo');
      slide(elements, 0.5);
      for (let i = 0; i < 4; i += 1) shell.tick();
      const before = places(played);
      shell.tick();
      if (tapA) held = new Set([0]);
      shell.draw(0);
      held = new Set();
      shell.draw(0);
      expect(places(played)).toBe(before);
      shell.tick();
      document.body.replaceChildren();
      return places(played) - before;
    };
    expect(placedBy(true)).toBe(placedBy(false) + 1);
  });
});

describe('通知（配線）', () => {
  it('盤面で倒れて外周へ回った通知は、名札の一覧で人間のプレイヤーにだけ出し、CPU には出さない（名札の一覧を通知へ渡す）', () => {
    // 通知は1枚で、新しいものが前のものを置き換えるので、出した通知は出す所で控える。
    const shown = vi.spyOn(Toasts.prototype, 'show');
    try {
      const { shell, elements } = mount();
      shell.showMenu();
      press(elements.menu, '[data-choice="solo"]');
      press(elements.menu, '[data-action="next"]');
      press(elements.menu, '[data-action="start"]');
      shell.draw(0);
      // 人間は操作しない。人間と CPU の両方が外周へ回ったのを名札で見るまで進める。
      const lane = { human: new Set<string>(), cpu: new Set<string>() };
      let ticks = 0;
      while (lane.human.size === 0 || lane.cpu.size === 0) {
        shell.tick();
        shell.draw(0);
        for (const card of elements.side.querySelectorAll('.pcard.negi')) {
          const name = card.querySelector('.pn')?.firstChild?.textContent?.trim() ?? '';
          const cpu = [...card.querySelectorAll('.tag')].some((tag) => tag.textContent?.startsWith('CPU'));
          (cpu ? lane.cpu : lane.human).add(name);
        }
        ticks += 1;
        if (ticks > 20_000) throw new Error('人間と CPU の両方が外周へ回らない');
      }
      // 同じ動物どうしだと、通知の呼び方（動物の名前）で見分けられない。
      expect([...lane.cpu].filter((name) => lane.human.has(name))).toEqual([]);
      const toLane = shown.mock.calls.map(([message]) => message).filter((message) => message.includes('は葱ボンへ'));
      expect(toLane).toEqual([...lane.human].map((name) => `🌿 ${name} は葱ボンへ！ 外周から葱を撃って復活をねらえ`));
    } finally {
      shown.mockRestore();
    }
  });
});

describe('横の板のキーの案内（配線）', () => {
  /** つながっているだけで何も押していないパッド。 */
  const idlePad = (): readonly (PadSnapshot | null)[] => [
    {
      mapping: 'standard',
      connected: true,
      index: 0,
      buttons: Array.from({ length: 17 }, () => ({ pressed: false })),
      axes: [0, 0, 0, 0],
    },
  ];

  function start(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo'): () => string {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
    return () => keyHelpOf(elements.side);
  }

  it('1人で遊ぶとき、パッドを認識していればパッドの段と Start を出し、ポーズ中は Select の行を足す', () => {
    const { shell, elements } = mount('both', () => [], idlePad);
    const help = start(shell, elements, 'solo');
    expect(help()).toContain('そうさ');
    expect(help()).toContain('🎮 [十字][スティック] うごく ／ ばくだん [A][R1]');
    expect(help()).toContain('[P][Start] ポーズ');
    expect(help()).not.toContain('Select');
    press(elements.side, '[data-action="pause"]');
    shell.draw(0);
    expect(help()).toContain('[Select] 設定へもどる');
  });

  it('パッドが無ければ、パッドの段も Start も Select も出さない', () => {
    const { shell, elements } = mount();
    const help = start(shell, elements, 'solo');
    expect(help()).toContain('[P] ポーズ');
    press(elements.side, '[data-action="pause"]');
    shell.draw(0);
    expect(help()).not.toMatch(/🎮|Start|Select/);
  });

  it('2人で遊ぶときは、パッドを認識していてもパッドの段を出さず、1P と 2P の形で出す', () => {
    const { shell, elements } = mount('both', () => [], idlePad);
    const help = start(shell, elements, 'duo');
    expect(help()).toContain('[W][A][S][D] ／ ばくだん [Space][Z]');
    expect(help()).toContain('[↑][←][↓][→] ／ ばくだん [Enter][/]');
    expect(help()).not.toContain('🎮');
    expect(help()).toContain('[P][Start] ポーズ');
  });
});

describe('パッドのボタンをまとめてカーソルへ渡す', () => {
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];

  function fakePad(): { read: () => readonly (PadSnapshot | null)[]; press: (...buttons: number[]) => void } {
    let held = new Set<number>();
    const read = (): readonly (PadSnapshot | null)[] => [
      {
        mapping: 'standard',
        connected: true,
        index: 0,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
      },
    ];
    return { read, press: (...buttons) => (held = new Set(buttons)) };
  }

  it('枠が出ていないとき、A と十字を同じ回に押すと、枠を出すだけで十字も飲み込む（原型の MENU.nav）', () => {
    const pad = fakePad();
    const { shell, elements } = mount('both', () => [], pad.read);
    shell.showMenu();
    pad.press(0, 13);
    shell.draw(0);
    expect(screenOf(elements)).toBe('title');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('solo');
    pad.press();
    shell.draw(0);
    pad.press(13);
    shell.draw(0);
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('duo');
  });

  it('メニューでは、Start・Select・X などほかのボタンでも枠が出る（カーソルは動かさない）', () => {
    for (const button of [9, 8, 2, 3, 4, 5]) {
      const pad = fakePad();
      const { shell, elements } = mount('both', () => [], pad.read);
      shell.showMenu();
      expect(cursorOf(elements.menu)).toBeNull();
      pad.press(button);
      shell.draw(0);
      expect(cursorOf(elements.menu)?.dataset['choice'], String(button)).toBe('solo');
      pad.press();
      shell.draw(0);
      pad.press(button);
      shell.draw(0);
      expect(cursorOf(elements.menu)?.dataset['choice'], String(button)).toBe('solo');
      expect(screenOf(elements), String(button)).toBe('title');
      document.body.replaceChildren();
    }
  });
});

describe('試合の画面（パッドの Start・パッドの通知・通知の消え方・盤面の大きさ）', () => {
  const START = 9;

  /** 押しているボタンを差し替えられるパッド。`devices` の前に、ほかの機器を並べられる。 */
  function padWith(devices: readonly (PadSnapshot | null)[] = []): {
    read: () => readonly (PadSnapshot | null)[];
    hold: (...buttons: number[]) => void;
  } {
    let held = new Set<number>();
    const read = (): readonly (PadSnapshot | null)[] => [
      ...devices,
      {
        mapping: 'standard',
        connected: true,
        index: devices.length,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
        id: 'Standard Pad',
      },
    ];
    return { read, hold: (...buttons) => (held = new Set(buttons)) };
  }

  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo' | 'versus', time?: number): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    if (time !== undefined) press(elements.menu, `[data-field="time"] [data-value="${time}"]`);
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  const pauseLabel = (elements: ShellElements): string | null | undefined =>
    elements.side.querySelector('[data-action="pause"]')?.textContent;

  it('1人で遊ぶとき、パッドの Start で止め、もう一度押すと再開する（原型 L3643-3645）', () => {
    const pad = padWith();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    const tapStart = (): void => {
      pad.hold(START);
      shell.draw(0);
      pad.hold();
      shell.draw(0);
    };
    tapStart();
    expect(pauseLabel(elements)).toBe('▶ 再開');
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.side.querySelector('.t')?.textContent).toBe('3:00');
    // 押したままでは、もう一度は切り替えない（押し始めだけを見る）。
    pad.hold(START);
    for (let i = 0; i < 3; i += 1) shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
    pad.hold();
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
  });

  it('2人で遊ぶときは、パッドの Start で止めない（パッドを試合に繋がない。机に置いたパッドに肘が当たってポーズ、を防ぐ）', () => {
    const pad = padWith();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'duo');
    pad.hold(START);
    shell.draw(0);
    pad.hold();
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
    // 対照：ツールバーの「⏸ ポーズ」なら止まる（2人でも止められる試合で、パッドだけを受け付けない）。
    press(elements.side, '[data-action="pause"]');
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('▶ 再開');
  });

  it('決着のあとの待ちの間（幕が出ている間）は、「⏸ ポーズ」も P も止めない（原型の togglePause は play の間だけ）', () => {
    // 2人タイマンで誰も操作しなければ、時間切れ・延長戦も時間切れで、ひきわけの幕が出る。
    const { shell, elements } = mount();
    startByMouse(shell, elements, 'versus', 60);
    let ticks = 0;
    while (elements.banner.hidden) {
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 20_000) throw new Error('幕が出ない');
    }
    // ボタンと P（`pressPauseKey`）を1回ずつ試し、そのたびに見る（2回続けて切り替えると、止めて再開した形と区別できない）。
    press(elements.side, '[data-action="pause"]');
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
    shell.pressPauseKey();
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
    expect(elements.banner.hidden).toBe(false);
    // 1台の幕は、送るまで消えない（tick を進めても、次のラウンドは始まらない）。
    for (let i = 0; i < 600; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.banner.hidden).toBe(false);
    expect(elements.side.querySelector('.rnd')?.textContent).toContain('ROUND 1');
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.side.querySelector('.rnd')?.textContent).toContain('ROUND 2');
    // 次のラウンドが始まれば、また止められる。
    shell.pressPauseKey();
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('▶ 再開');
  });

  it('ツールバーの「⏸ ポーズ」と「設定へ」は、画面の操作の音を鳴らさない（原型 L6038・L6080）', () => {
    const { shell, elements, audio } = mount();
    startByMouse(shell, elements, 'solo');
    audio.length = 0;
    press(elements.side, '[data-action="pause"]');
    press(elements.side, '[data-action="pause"]');
    press(elements.side, '[data-action="quit"]');
    expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
    expect(audio).not.toContain('ui');
  });

  it('パッドを初めて見つけたら、メニューの間でも「🎮 コントローラーを認識しました」を1回だけ出す', () => {
    const shown = vi.spyOn(Toasts.prototype, 'show');
    try {
      const pad = padWith();
      const { shell, elements } = mount('both', () => [], pad.read);
      shell.showMenu();
      shell.draw(0);
      expect(elements.toast.textContent).toBe('🎮 コントローラーを認識しました');
      expect(elements.toast.classList.contains('on')).toBe(true);
      for (let i = 0; i < 5; i += 1) shell.draw(0);
      startByMouse(shell, elements, 'solo');
      for (let i = 0; i < 30; i += 1) shell.tick();
      shell.draw(0);
      expect(shown.mock.calls.map(([message]) => message)).toEqual(['🎮 コントローラーを認識しました']);
    } finally {
      shown.mockRestore();
    }
  });

  it('標準の並びでない機器が先にあれば、名前を添えて1回だけ知らせる（そのあと見つけたパッドの通知が置き換える）', () => {
    const shown = vi.spyOn(Toasts.prototype, 'show');
    try {
      const odd: PadSnapshot = { mapping: '', connected: true, index: 0, buttons: [], axes: [], id: 'Odd Stick (Vendor: 1234)' };
      const pad = padWith([odd]);
      const { shell, elements } = mount('both', () => [], pad.read);
      shell.showMenu();
      for (let i = 0; i < 5; i += 1) shell.draw(0);
      expect(shown.mock.calls.map(([message]) => message)).toEqual([
        '🎮 このコントローラーには対応していません（Odd Stick (Vendor: 1234)）',
        '🎮 コントローラーを認識しました',
      ]);
      expect(elements.toast.textContent).toBe('🎮 コントローラーを認識しました');
    } finally {
      shown.mockRestore();
    }
  });

  it('対応していない機器しか無いときも、知らせるのは1回だけ（毎フレーム出すと画面が埋まる）', () => {
    const shown = vi.spyOn(Toasts.prototype, 'show');
    try {
      const odd: PadSnapshot = { mapping: '', connected: true, index: 0, buttons: [], axes: [], id: 'Odd Stick' };
      const { shell } = mount('both', () => [], () => [odd]);
      shell.showMenu();
      for (let i = 0; i < 5; i += 1) shell.draw(0);
      expect(shown.mock.calls.map(([message]) => message)).toEqual(['🎮 このコントローラーには対応していません（Odd Stick）']);
    } finally {
      shown.mockRestore();
    }
  });

  it('通知は、試合を抜けてタイトルへ戻っても消さず、出してから 1.4 秒で薄れる（原型の backToSetup は通知に触らない）', () => {
    vi.useFakeTimers();
    try {
      const pad = padWith();
      const { shell, elements } = mount('both', () => [], pad.read);
      startByMouse(shell, elements, 'solo');
      expect(elements.toast.classList.contains('on')).toBe(true);
      press(elements.side, '[data-action="quit"]');
      shell.draw(0);
      expect(elements.menu.querySelector('[data-screen="title"]')).not.toBeNull();
      expect(elements.toast.textContent).toBe('🎮 コントローラーを認識しました');
      expect(elements.toast.classList.contains('on')).toBe(true);
      vi.advanceTimersByTime(1400);
      expect(elements.toast.classList.contains('on')).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('横の板の名札と時計は、盤面の時刻の 15 tick の区切りで作り直す。進めた tick のイベントはすべて PanelRefresh へ渡す', () => {
    const updates = vi.spyOn(SidePanel.prototype, 'update');
    const observed = vi.spyOn(PanelRefresh.prototype, 'observe');
    try {
      const { shell, elements } = mount();
      startByMouse(shell, elements, 'versus');
      const refreshed = (): unknown => updates.mock.calls.at(-1)?.[1].refresh;
      // 始めて最初に描くときは作り直す。
      expect(refreshed()).toBe(true);
      shell.draw(0);
      expect(refreshed()).toBe(false);
      const flags: unknown[] = [];
      for (let i = 1; i <= 30; i += 1) {
        shell.tick();
        shell.draw(0);
        flags.push(refreshed());
      }
      // 誰も操作しない2人タイマンなので、すぐ作り直すイベントは起きない。15 tick と 30 tick の区切りだけ。
      expect(flags.flatMap((flag, index) => (flag === true ? [index + 1] : []))).toEqual([15, 30]);
      expect(observed).toHaveBeenCalledTimes(30);
    } finally {
      updates.mockRestore();
      observed.mockRestore();
    }
  });

  it('盤面の大きさを窓の大きさから決め、試合の途中で窓の大きさが替わったら、描く寸法も替える（原型の fitBoard と resize）', () => {
    const canvas = fakeCanvas();
    const { shell, elements } = mount('both', () => [], () => [], undefined, canvas.context);
    shell.fitBoard(1440, 900);
    expect([elements.canvas.width, elements.canvas.height]).toEqual([1115, 839]);
    expect([elements.canvas.style.width, elements.canvas.style.height]).toEqual(['1115px', '839px']);
    startByMouse(shell, elements, 'solo');
    const pauseAt = (): readonly unknown[] | undefined =>
      canvas.log.filter((call) => call.name === 'fillText' && call.args[0] === 'PAUSE').at(-1)?.args;
    /** 左上の隅の柱（マス 0,0）を塗った四角。マスの大きさで決まる。 */
    const cornerDrawn = (tile: number): boolean =>
      canvas.log.some(
        (call) => call.name === 'fillRect' && JSON.stringify(call.args) === JSON.stringify([0.62 * tile, 0.62 * tile, tile, tile]),
      );
    shell.togglePause();
    shell.draw(0);
    // 試合を始めたあとに作った描く部品も、窓から決めた寸法で描く（真ん中に PAUSE。マスは 46）。
    expect(pauseAt()).toEqual(['PAUSE', 557.5, 419.5]);
    expect(cornerDrawn(46)).toBe(true);

    canvas.log.length = 0;
    shell.fitBoard(1024, 768);
    shell.draw(0);
    expect([elements.canvas.width, elements.canvas.height]).toEqual([703, 529]);
    expect(pauseAt()).toEqual(['PAUSE', 351.5, 264.5]);
    expect(cornerDrawn(29)).toBe(true);
    expect(cornerDrawn(46)).toBe(false);
  });
});

describe('ラウンドの幕と優勝の幕（1台の試合。原型どおりボタンで送る）', () => {
  const A = 0;
  const START = 9;
  const DOWN = 13;
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];
  const roundOf = (elements: ShellElements): string | null | undefined => elements.side.querySelector('.rnd')?.textContent;
  const buttonsOf = (elements: ShellElements): (string | null)[] =>
    [...elements.banner.querySelectorAll('button')].map((button) => button.textContent);

  /** 押しているボタンを差し替えられるパッド（標準の並び）。 */
  function heldPad(): { read: () => readonly (PadSnapshot | null)[]; hold: (...buttons: number[]) => void } {
    let held = new Set<number>();
    const read = (): readonly (PadSnapshot | null)[] => [
      {
        mapping: 'standard',
        connected: true,
        index: 0,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
        id: 'Standard Pad',
      },
    ];
    return { read, hold: (...buttons) => (held = new Set(buttons)) };
  }

  /** 押して1枚描き、離して1枚描く。 */
  function tap(shell: Shell, pad: ReturnType<typeof heldPad>, button: number): void {
    pad.hold(button);
    shell.draw(0);
    pad.hold();
    shell.draw(0);
  }

  /** マウスで、その遊び方・1ラウンド 60 秒の試合を始める。 */
  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo' | 'versus'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-field="time"] [data-value="60"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  it('ラウンドの幕にも「つぎのラウンド ▶」と「⚙ 設定をやりなおす」を出し、送るまで試合を進めない。送ると次のラウンドになる', () => {
    // 2人タイマンで誰も操作しなければ、時間切れ・延長戦も時間切れで、ひきわけの幕が出る。
    const { shell, elements } = mount();
    startByMouse(shell, elements, 'versus');
    playUntilBanner(shell, elements);
    expect(elements.banner.textContent).toContain('ラウンド1　ひきわけ');
    expect(buttonsOf(elements)).toEqual(['つぎのラウンド ▶', '⚙ 設定をやりなおす']);
    // 決着のあとの待ち（2 秒）を過ぎても、幕は消えず、次のラウンドも始まらない（原型の loop は play の間だけ update）。
    for (let i = 0; i < 600; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.banner.hidden).toBe(false);
    expect(roundOf(elements)).toContain('ROUND 1');

    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
    expect(elements.side.querySelector('.t')?.textContent).toBe('1:00');
    // 次のラウンドは進む。
    for (let i = 0; i < 60; i += 1) shell.tick();
    shell.draw(0);
    expect(elements.side.querySelector('.t')?.textContent).toBe('0:59');
  }, 120_000);

  it('ラウンドが決まったら曲を止め、幕の間は鳴らさず、送ったら次のラウンドで鳴らし直す（原型の endGame の BGM.stop と startRound の BGM.start）', () => {
    const { shell, elements, music } = mount();
    startByMouse(shell, elements, 'versus');
    shell.draw(0);
    const playing = music.started;
    expect(playing).toBeGreaterThan(0);
    playUntilBanner(shell, elements);
    const started = music.started;
    const stopped = music.stopped;
    for (let i = 0; i < 3; i += 1) shell.draw(0);
    expect(music.started).toBe(started);
    expect(music.stopped).toBe(stopped + 3);
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(music.started).toBe(started + 1);
  }, 120_000);

  it('幕の間は、押したキーを毎フレーム忘れる（止めている間と同じ。再開した最初の tick に残さない）', () => {
    let forgets = 0;
    const keyboard: KeyboardState = { anyOf: () => false, buttonAnyOf: () => false, forgetTaps: () => (forgets += 1) };
    const { shell, elements } = mount('both', () => [], () => [], keyboard);
    startByMouse(shell, elements, 'versus');
    playUntilBanner(shell, elements);
    const before = forgets;
    shell.tick();
    expect(forgets).toBe(before);
    shell.draw(0);
    expect(forgets).toBe(before + 1);
  }, 120_000);

  it('優勝の幕の間も tick を進めない（粒子と画面の揺れも止める。原型の loop は play の間だけ update を呼ぶ）。「もういっかい」の次の試合は進む', () => {
    const { shell, elements } = mount();
    startByMouse(shell, elements, 'solo');
    playUntilChampion(shell, elements);
    const before = vi.spyOn(Renderer.prototype, 'beforeTick');
    const after = vi.spyOn(Renderer.prototype, 'afterTick');
    try {
      for (let i = 0; i < 30; i += 1) shell.tick();
      shell.draw(0);
      expect(elements.banner.hidden).toBe(false);
      expect(before).not.toHaveBeenCalled();
      expect(after).not.toHaveBeenCalled();
      press(elements.banner, '[data-action="advance"]');
      shell.draw(0);
      shell.tick();
      expect(before).toHaveBeenCalledTimes(1);
      expect(after).toHaveBeenCalledTimes(1);
    } finally {
      before.mockRestore();
      after.mockRestore();
    }
  }, 120_000);

  it('「⚙ 設定をやりなおす」でタイトルへ戻り、カーソルの枠を消す（原型の backToSetup の MENU.on = false）。幕のボタンは操作の音を鳴らさない', () => {
    const pad = heldPad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilBanner(shell, elements);
    // 1人で遊ぶときは、幕の間は枠が出ている（パッドを押さなくても。原型 L3637）。カーソルは1つ目のボタン。
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('advance');
    audio.length = 0;
    tap(shell, pad, DOWN);
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('setup');
    tap(shell, pad, A);
    expect(elements.menu.hidden).toBe(false);
    expect(screenOf(elements)).toBe('title');
    shell.draw(0);
    expect(cursorOf(elements.menu)).toBeNull();
    expect(elements.banner.hidden).toBe(true);
    expect(audio).not.toContain('ui');
    // 枠が消えているので、次の Enter は枠を出すだけ。
    shell.navigate('confirm');
    expect(screenOf(elements)).toBe('title');
    expect(cursorOf(elements.menu)?.dataset['choice']).toBe('solo');
  }, 120_000);

  it('1人で遊ぶときは、幕の間は毎フレーム枠を出す（パッドが無くても・マウスで消しても次のフレームで出し直す）。2人のときは出さない', () => {
    const solo = mount();
    startByMouse(solo.shell, solo.elements, 'solo');
    playUntilBanner(solo.shell, solo.elements);
    expect(cursorOf(solo.elements.banner)?.dataset['action']).toBe('advance');
    solo.shell.hideCursor();
    expect(cursorOf(solo.elements.banner)).toBeNull();
    solo.shell.draw(0);
    expect(cursorOf(solo.elements.banner)?.dataset['action']).toBe('advance');

    document.body.replaceChildren();
    const duo = mount();
    startByMouse(duo.shell, duo.elements, 'duo');
    playUntilBanner(duo.shell, duo.elements);
    duo.shell.draw(0);
    expect(cursorOf(duo.elements.banner)).toBeNull();
  }, 120_000);

  it('幕の1つ目のボタン（「つぎのラウンド ▶」「もういっかい」）も、マウスで押してもパッドの A で押しても、操作の音を鳴らさない（原型 L6032）', () => {
    // 試合の中でも操作の音を鳴らすことがある（焼けた舌を出そうとしたとき）ので、押した直後だけを見る。
    const pad = heldPad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilBanner(shell, elements);
    audio.length = 0;
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
    expect(audio).toEqual([]);
    playUntilBanner(shell, elements);
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('advance');
    audio.length = 0;
    tap(shell, pad, A);
    expect(elements.banner.hidden).toBe(true);
    expect(audio).toEqual([]);
  }, 120_000);

  it('マウスを動かして枠を消した直後のフレームでも、パッドの A は飲み込まずに1つ目のボタンを押す（原型は L3637 で枠を出してから MENU.nav へ渡す）', () => {
    // 描く側が毎フレーム枠を出し直すだけだと、マウスを動かした直後に押した A が、枠を出すだけで終わる。
    // マウスが動き続けている間（トラックパッドに手が触れている、など）は、毎回そうなる。
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilBanner(shell, elements);
    shell.hideCursor();
    expect(cursorOf(elements.banner)).toBeNull();
    pad.hold(A);
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
  }, 120_000);

  it('パッドの Start は幕を送る近道（カーソルが「⚙ 設定をやりなおす」にあっても次のラウンドへ。原型 L3631）', () => {
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilBanner(shell, elements);
    tap(shell, pad, DOWN);
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('setup');
    tap(shell, pad, START);
    expect(elements.banner.hidden).toBe(true);
    expect(elements.menu.hidden).toBe(true);
    expect(roundOf(elements)).toContain('ROUND 2');
  }, 120_000);

  it('幕が出るたびに、カーソルは1つ目のボタンへ戻る（原型の endGame の MENU.reset）', () => {
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    playUntilBanner(shell, elements);
    tap(shell, pad, DOWN);
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('setup');
    press(elements.banner, '[data-action="advance"]');
    shell.draw(0);
    expect(elements.banner.hidden).toBe(true);
    playUntilBanner(shell, elements);
    expect(roundOf(elements)).toContain('ROUND 2');
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('advance');
  }, 120_000);

  it('Enter を押したまま幕を送っても、次のラウンドの開始位置に爆弾を置かない。離して押し直すと置く', () => {
    // Enter は決定のキーで、2人タイマンの 2P の爆弾のキーでもある（CPU がいないので、置いた爆弾は人間のものだけ）。
    let held: readonly string[] = [];
    const { shell, elements, played } = mount('both', () => held);
    startByMouse(shell, elements, 'versus');
    playUntilBanner(shell, elements);
    const before = played.filter((name) => name === 'place').length;
    held = ['Enter'];
    shell.navigate('confirm');
    shell.draw(0);
    expect(roundOf(elements)).toContain('ROUND 2');
    for (let i = 0; i < 30; i += 1) shell.tick();
    expect(played.filter((name) => name === 'place').length).toBe(before);
    // 対照：離して押し直せば置く（押しても置かれない、で上が通ってしまわないように）。
    held = [];
    shell.tick();
    held = ['Enter'];
    shell.tick();
    expect(played.filter((name) => name === 'place').length).toBe(before + 1);
  }, 120_000);

  it('パッドの A を押したまま幕を送っても、次のラウンドの開始位置に爆弾を置かない', () => {
    // 1人で遊ぶ形は CPU も爆弾を置くので、同じ種でマウスで送った試合を対照にし、置いた数の差で見る。
    const placedAfterAdvance = (byPad: boolean, pressAgain: boolean): number => {
      const pad = heldPad();
      const { shell, elements, played } = mount('both', () => [], pad.read);
      startByMouse(shell, elements, 'solo');
      playUntilBanner(shell, elements);
      const before = played.filter((name) => name === 'place').length;
      if (byPad) {
        pad.hold(A);
        shell.draw(0);
      } else {
        press(elements.banner, '[data-action="advance"]');
        shell.draw(0);
      }
      expect(roundOf(elements)).toContain('ROUND 2');
      for (let i = 0; i < 30; i += 1) shell.tick();
      if (pressAgain) {
        pad.hold();
        shell.draw(0);
        shell.tick();
        pad.hold(A);
        shell.draw(0);
      } else {
        shell.tick();
      }
      shell.tick();
      const placed = played.filter((name) => name === 'place').length - before;
      document.body.replaceChildren();
      return placed;
    };
    const control = placedAfterAdvance(false, false);
    expect(placedAfterAdvance(true, false)).toBe(control);
    // 対照：離して押し直せば置く。
    expect(placedAfterAdvance(true, true)).toBe(control + 1);
  }, 120_000);
});

describe('確認の画面（原型の askConfirm）', () => {
  const A = 0;
  const SELECT = 8;
  const START = 9;
  const RIGHT = 15;
  const cursorOf = (root: HTMLElement): HTMLElement | null => root.querySelector('.navcur');
  const screenOf = (elements: ShellElements): string | undefined =>
    elements.menu.querySelector<HTMLElement>('[data-screen]')?.dataset['screen'];
  const pauseLabel = (elements: ShellElements): string | null | undefined =>
    elements.side.querySelector('[data-action="pause"]')?.textContent;
  const dialogOf = (elements: ShellElements): { open: boolean; message: string | null | undefined; buttons: (string | null)[] } => ({
    open: !elements.confirm.hidden,
    message: elements.confirm.querySelector('.cfmMsg')?.textContent,
    buttons: [...elements.confirm.querySelectorAll('.cfmBtns > .chip')].map((button) => button.textContent),
  });

  function heldPad(): { read: () => readonly (PadSnapshot | null)[]; hold: (...buttons: number[]) => void } {
    let held = new Set<number>();
    const read = (): readonly (PadSnapshot | null)[] => [
      {
        mapping: 'standard',
        connected: true,
        index: 0,
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
        axes: [0, 0, 0, 0],
        id: 'Standard Pad',
      },
    ];
    return { read, hold: (...buttons) => (held = new Set(buttons)) };
  }

  function tap(shell: Shell, pad: ReturnType<typeof heldPad>, ...buttons: number[]): void {
    pad.hold(...buttons);
    shell.draw(0);
    pad.hold();
    shell.draw(0);
  }

  function startByMouse(shell: Shell, elements: ShellElements, mode: 'solo' | 'duo'): void {
    shell.showMenu();
    press(elements.menu, `[data-choice="${mode}"]`);
    press(elements.menu, '[data-action="next"]');
    press(elements.menu, '[data-action="start"]');
    shell.draw(0);
  }

  it('1人で遊ぶとき、ポーズ中のパッドの Select で「設定へもどりますか？」を開き、枠を出してカーソルを「やめる」に置く。止めていなければ開かない', () => {
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, SELECT);
    expect(dialogOf(elements).open).toBe(false);
    tap(shell, pad, START);
    expect(pauseLabel(elements)).toBe('▶ 再開');
    tap(shell, pad, SELECT);
    expect(dialogOf(elements)).toEqual({ open: true, message: '設定へもどりますか？', buttons: ['やめる', '設定へもどる'] });
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('no');
  });

  it('Start と Select を同じ回に押すと、止めてから開く（原型は togglePause のあとで G.paused を見る）', () => {
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, START, SELECT);
    expect(pauseLabel(elements)).toBe('▶ 再開');
    expect(dialogOf(elements).open).toBe(true);
  });

  it('開いている間は、P もパッドの Start も届かない。Escape と B は「やめる」（音を鳴らし、ポーズのまま戻る）', () => {
    const pad = heldPad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, START);
    tap(shell, pad, SELECT);
    shell.pressPauseKey();
    tap(shell, pad, START);
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('▶ 再開');
    expect(dialogOf(elements).open).toBe(true);
    audio.length = 0;
    shell.navigate('back');
    expect(dialogOf(elements).open).toBe(false);
    expect(audio).toEqual(['unlock', 'ui']);
    expect(pauseLabel(elements)).toBe('▶ 再開');
    // パッドの B も同じ。
    tap(shell, pad, SELECT);
    expect(dialogOf(elements).open).toBe(true);
    tap(shell, pad, 1);
    expect(dialogOf(elements).open).toBe(false);
    // 閉じたら P がまた届く。
    shell.pressPauseKey();
    shell.draw(0);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
  });

  it('「設定へもどる」を選ぶと、音を鳴らしてタイトルへ戻り、枠を消す。開き直すとカーソルはまた「やめる」', () => {
    const pad = heldPad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, START);
    tap(shell, pad, SELECT);
    tap(shell, pad, RIGHT);
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('yes');
    tap(shell, pad, 1);
    tap(shell, pad, SELECT);
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('no');
    tap(shell, pad, RIGHT);
    audio.length = 0;
    tap(shell, pad, A);
    expect(audio).toEqual(['unlock', 'ui']);
    expect(dialogOf(elements).open).toBe(false);
    expect(elements.menu.hidden).toBe(false);
    expect(screenOf(elements)).toBe('title');
    expect(cursorOf(elements.menu)).toBeNull();
  });

  it('マウスでも押せる（どちらも操作の音を鳴らす）。開いたまま試合を抜けたとき・次の試合を始めたときは、音を鳴らさずに畳む', () => {
    const pad = heldPad();
    const { shell, elements, audio } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, START);
    tap(shell, pad, SELECT);
    audio.length = 0;
    press(elements.confirm, '[data-action="no"]');
    expect(dialogOf(elements).open).toBe(false);
    expect(audio).toEqual(['unlock', 'ui']);
    tap(shell, pad, SELECT);
    audio.length = 0;
    shell.showMenu();
    expect(dialogOf(elements).open).toBe(false);
    expect(elements.confirm.childElementCount).toBe(0);
    expect(audio).toEqual([]);
    // 試合の画面のまま次の試合を始めたときも畳む（原型の startGame → showScreen の closeDialog）。
    startByMouse(shell, elements, 'solo');
    tap(shell, pad, START);
    tap(shell, pad, SELECT);
    expect(dialogOf(elements).open).toBe(true);
    shell.restart();
    shell.draw(0);
    expect(dialogOf(elements).open).toBe(false);
    expect(pauseLabel(elements)).toBe('⏸ ポーズ');
  });

  it('2人で遊ぶときは、パッドの Select で開かない（パッドを試合に繋がない）', () => {
    const pad = heldPad();
    const { shell, elements } = mount('both', () => [], pad.read);
    startByMouse(shell, elements, 'duo');
    press(elements.side, '[data-action="pause"]');
    tap(shell, pad, SELECT);
    expect(dialogOf(elements).open).toBe(false);
  });

  it('通信対戦では、止めずにいつでも開き、開いている間も試合への入力を送る（原型と同じ）。次の試合が始まったら畳む', () => {
    const pad = heldPad();
    const { shell, elements, relay, sent } = mount('both', () => [], pad.read);
    const config = {
      match: { roundLimit: 3600, winsToTake: 1, suddenDeath: true, startingHp: [2, 2, 2, 2], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['oni', 'oni', 'oni', 'oni'],
    };
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    let delivered = 0;
    const deliver = (until: number): void => {
      for (; delivered < until; delivered += 1) relay().onMessage(JSON.stringify({ t: 'input', seat: 0, tick: delivered, bits: 0, match: 1 }));
    };
    deliver(20);
    shell.draw(0);
    for (let i = 0; i < 5; i += 1) shell.tick();
    tap(shell, pad, SELECT);
    expect(dialogOf(elements)).toEqual({ open: true, message: '設定へもどりますか？', buttons: ['やめる', '設定へもどる'] });
    // 開いている間も、パッドの十字は自分のプレイヤーの向きとして送る（原型 L3592-3597 は確認の画面より前に注入する）。
    // 同じ押しで、確認の画面のカーソルも動く。
    const pressedBefore = sent.filter((message) => message.t === 'input' && message.bits !== 0).length;
    pad.hold(RIGHT);
    shell.draw(0);
    for (let i = 0; i < 3; i += 1) shell.tick();
    expect(sent.filter((message) => message.t === 'input' && message.bits !== 0).length).toBeGreaterThan(pressedBefore);
    expect(cursorOf(elements.confirm)?.dataset['action']).toBe('yes');
    pad.hold();
    shell.draw(0);
    expect(dialogOf(elements).open).toBe(true);

    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config: { ...config, match: { ...config.match, seed: 2 } }, match: 2 }));
    shell.draw(0);
    expect(dialogOf(elements).open).toBe(false);
  });

  it('通信対戦の「設定へもどる」は抜ける（横の板の「設定へ」と同じ）', () => {
    const pad = heldPad();
    const { shell, elements, relay, links } = mount('both', () => [], pad.read);
    const config = {
      match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['easy', 'easy', 'easy', 'easy'],
    };
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0, 1], config, match: 1 }));
    shell.draw(0);
    tap(shell, pad, SELECT);
    shell.navigate('right');
    shell.navigate('confirm');
    expect(links.map((link) => link.closed)).toEqual([1]);
    expect(screenOf(elements)).toBe('title');
  });

  /**
   * 通信対戦のホスト（ほかの枠は CPU）で、優勝の幕が出るまで進める。`withDialog` なら、試合の最中にパッドの Select で
   * 確認の画面を開き、開いたまま進める（通信対戦は止めずに開けるので、開いたまま試合が決まることがある）。
   */
  function lanChampion(withDialog: boolean): ReturnType<typeof mount> & { pad: ReturnType<typeof heldPad>; starts: () => number } {
    const pad = heldPad();
    const mounted = mount('both', () => [], pad.read);
    const { shell, elements, relay, sent } = mounted;
    const config = {
      match: { roundLimit: 3600, winsToTake: 1, suddenDeath: true, startingHp: [2, 2, 2, 2], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] },
      cpu: ['oni', 'oni', 'oni', 'oni'],
    };
    shell.startLan('relay.local:8777');
    relay().onMessage(JSON.stringify({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    relay().onMessage(JSON.stringify({ t: 'start', seats: [0], config, match: 1 }));
    shell.draw(0);
    if (withDialog) {
      tap(shell, pad, SELECT);
      expect(dialogOf(elements).open).toBe(true);
    }
    let ticks = 0;
    while (elements.banner.hidden || !elements.banner.textContent?.includes('優勝')) {
      shell.tick();
      if (ticks % 30 === 0) shell.draw(0);
      ticks += 1;
      if (ticks > 200_000) throw new Error('試合が決まらない');
    }
    shell.draw(0);
    expect(dialogOf(elements).open).toBe(withDialog);
    expect([...elements.banner.querySelectorAll('button')].map((button) => button.dataset['action'])).toEqual(['advance', 'setup']);
    return { ...mounted, pad, starts: () => sent.filter((message) => message.t === 'start').length };
  }

  it('通信対戦の幕でパッドの B を押しても、「せつぞくを切ります。よいですか？」を開かない（原型の MENU_BACK に幕が無い）', () => {
    // 盤面がまだ無い間（ロビー・つないでいる最中）の B だけが、切るかの確認の画面を開く。
    const { shell, elements, pad, links } = lanChampion(false);
    tap(shell, pad, 1);
    expect(dialogOf(elements).open).toBe(false);
    expect(elements.confirm.childElementCount).toBe(0);
    expect(elements.banner.hidden).toBe(false);
    expect(links.map((link) => link.closed)).toEqual([0]);
  }, 120_000);

  it('開いたまま優勝の幕が出ても、キーの Enter は確認の画面を動かし、幕を送らない（原型の keydown は確認の画面を先に見る。L3074-3078）', () => {
    const { shell, elements, starts } = lanChampion(true);
    const before = starts();
    shell.navigate('confirm');
    // カーソルは「やめる」にあるので、Enter は確認の画面を閉じるだけ。次の試合の合図は送らない。
    expect(starts()).toBe(before);
    expect(dialogOf(elements).open).toBe(false);
    expect(elements.banner.hidden).toBe(false);
    // 閉じたら、カーソルは幕の1つ目のボタンへ戻る（原型の MENU.closeDialog の MENU.reset）。
    shell.draw(0);
    expect(cursorOf(elements.banner)?.dataset['action']).toBe('advance');
  }, 120_000);

  it('開いたまま優勝の幕が出たら、パッドの Start は確認の画面が開いていても幕を送る（原型の pollGamepads は幕の分かれ道で先に Start を見る。L3631）', () => {
    const { shell, elements, pad, starts } = lanChampion(true);
    const before = starts();
    tap(shell, pad, START);
    expect(starts()).toBe(before + 1);
    // 次の試合は、中継が配り直した start を受け取ってから始まり、そのときに畳む（上の「次の試合が始まったら畳む」）。
    expect(dialogOf(elements).open).toBe(true);
  }, 120_000);
});
