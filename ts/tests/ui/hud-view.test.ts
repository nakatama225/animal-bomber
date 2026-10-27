// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { tick } from '../../src/domain/core/Tick.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { BannerOverlay } from '../../src/platform/ui/BannerOverlay.js';
import type { BannerView } from '../../src/presentation/hud/RoundBanner.js';
import { activate, pointerButton } from '../../src/platform/ui/dom.js';
import { SidePanel, type KeyHelpFor, type SideControls, type SideFrame } from '../../src/platform/ui/SidePanel.js';
import { Toasts, type ToastClock } from '../../src/platform/ui/Toasts.js';
import { describeKeyHelp } from '../../src/presentation/hud/keyHelp.js';
import { localRoster, type Roster } from '../../src/presentation/hud/roster.js';
import type { HudSource } from '../../src/presentation/hud/scoreboard.js';

/**
 * 画面に写す部分を、ブラウザの代わりの DOM（happy-dom）で組んで確認する。
 *
 * 中身の文は `tests/presentation/hud.test.ts` が見ている。ここで見るのは、
 * 写し方（要素ができるか・書き換えを省くか・押したら呼ばれるか）だけ。
 */

const ROSTER: Roster = [
  { kind: 'human', label: '1P', local: true },
  { kind: 'cpu', number: 1, level: 'normal' },
];

function hud(): { session: GameSession; source: () => HudSource } {
  const session = new GameSession(defaultMatchConfig(9, ['rabbit', 'frog']));
  for (const player of session.world.players) session.attach(new IdleInputSource(player.id));
  return {
    session,
    source: () => ({
      world: session.world,
      match: session.match,
      config: session.config,
      roster: ROSTER,
      betweenRounds: session.betweenRounds,
    }),
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

/** キーの案内（1台の試合・パッドなし）。ポーズ中かは呼ぶたびに読む。 */
function keyHelp(paused: () => boolean = () => false): KeyHelpFor {
  return (source) =>
    describeKeyHelp({
      world: source.world,
      roster: source.roster,
      padConnected: false,
      padInMatch: true,
      paused: paused(),
      canPause: true,
    });
}

/** つまみも「ポーズ」も無い板の操作（通信対戦の形）。「設定へ」は何もしない。 */
const QUIT_ONLY: SideControls = { speed: null, pause: null, quit: () => undefined };

/** 名札と時計を作り直す（原型の 0.25 秒の区切りの）フレーム。 */
const REFRESH: SideFrame = { refresh: true, paused: false };

/** 名札と時計を作り直さないフレーム。 */
const KEEP: SideFrame = { refresh: false, paused: false };

/** キーの案内の行を [タグ, クラス, 文（キーは [] で囲む）] の並びにする。 */
function helpRows(root: HTMLElement): [string, string, string][] {
  return [...(root.querySelector('.keyhelp')?.children ?? [])].map((row) => {
    const copy = row.cloneNode(true) as HTMLElement;
    for (const key of copy.querySelectorAll('.k')) key.textContent = `[${key.textContent ?? ''}]`;
    return [row.tagName, row.className, copy.textContent ?? ''];
  });
}

describe('横の板', () => {
  it('上から、時計・名札・キーの案内・ツールバーを並べる（原型の #side の並び。L516-538）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp(), QUIT_ONLY);
    panel.update(hud().source(), REFRESH);

    expect([...root.children].map((child) => child.className)).toEqual(['clock', '', 'keyhelp', 'toolbar']);
    expect(root.querySelector('.clock .t')?.textContent).toBe('3:00');
    expect(root.querySelector('.clock .rnd')?.textContent).toBe('ROUND 1\u30003勝先取');
    expect(root.querySelector('.clock .lbl')?.textContent).toBe('TIME');
    expect(root.querySelectorAll('.pcard')).toHaveLength(2);
    // 原型の名札は「（あなた）」を付けない（L5508）。CPU は何体目かと強さ（L5507）。札の地の色はクラスで分ける。
    expect(root.querySelector('[data-player="0"] .pn .tag')?.textContent).toBe('1P');
    expect(root.querySelector('[data-player="0"] .tag')?.className).toBe('tag');
    expect(root.querySelector('[data-player="1"] .tag')?.textContent).toBe('CPU1・ふつう');
    expect(root.querySelector('[data-player="1"] .tag')?.className).toBe('tag cpu');
    // 名札の中の並び（原型 L5531-5537）。💣🔥👟 は3つの span（間を CSS の gap で空ける。L98）。
    const card = root.querySelector('[data-player="0"]');
    expect(card?.className).toBe('pcard');
    expect([...(card?.querySelector('.pi')?.children ?? [])].map((child) => child.className)).toEqual([
      'pn',
      'score',
      'hearts',
      'stats',
      'fx',
    ]);
    expect(card?.querySelector('.pe')?.textContent).toBe('🐰');
    expect([...(card?.querySelectorAll('.stats > span') ?? [])].map((span) => span.textContent)).toEqual([
      '💣1',
      '🔥1',
      '👟0',
    ]);
    // 太字だけの行は b のまま、ほかの行は .r。キーは .k。行に直に書く空きと薄さは style（原型 L5608）。
    expect(helpRows(root)).toEqual([
      ['B', '', 'そうさ'],
      ['DIV', 'r', 'うごく [W][A][S][D] / [↑][←][↓][→]'],
      ['DIV', 'r', 'ばくだん [Space][Enter][Z][/]'],
      ['DIV', 'r', 'とぶ [E][Q][X][C][R][Shift]（長押しでとくぎ🍗）'],
      ['DIV', 'r', '[P] ポーズ'],
    ]);
    const pauseRow = root.querySelector<HTMLElement>('.keyhelp > :last-child');
    expect([pauseRow?.style.marginTop, pauseRow?.style.opacity]).toEqual(['7px', '0.8']);
    expect(root.querySelector('.keyhelp > .r')?.getAttribute('style')).toBeNull();
  });

  it('1台の試合では、時計と名札の間につまみを置き、ツールバーに「⏸ ポーズ」と「設定へ」を並べる。押すと呼ぶ', () => {
    const root = document.createElement('div');
    const pressed: string[] = [];
    const panel = new SidePanel(root, keyHelp(), {
      speed: { rate: 2, change: (rate) => pressed.push(`speed ${rate}`) },
      pause: () => pressed.push('pause'),
      quit: () => pressed.push('quit'),
    });
    panel.update(hud().source(), REFRESH);
    expect([...root.children].map((child) => child.className)).toEqual(['clock', 'speed fast', '', 'keyhelp', 'toolbar']);
    expect(root.querySelector('.speed .sv')?.textContent).toBe('2×');
    const buttons = [...root.querySelectorAll<HTMLElement>('.toolbar > .tbtn')];
    expect(buttons.map((button) => button.textContent)).toEqual(['⏸ ポーズ', '設定へ']);
    for (const button of buttons) button.dispatchEvent(new MouseEvent('click', { detail: 1 }));
    expect(pressed).toEqual(['pause', 'quit']);
  });

  it('止めている間は「ポーズ」のボタンの字を「▶ 再開」にし、再開したら戻す（原型 L4217）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp(), { ...QUIT_ONLY, pause: () => undefined });
    const { source } = hud();
    const label = (): string | null | undefined => root.querySelector('[data-action="pause"]')?.textContent;
    panel.update(source(), REFRESH);
    expect(label()).toBe('⏸ ポーズ');
    panel.update(source(), { refresh: false, paused: true });
    expect(label()).toBe('▶ 再開');
    panel.update(source(), KEEP);
    expect(label()).toBe('⏸ ポーズ');
  });

  it('通信対戦の形では、つまみも「ポーズ」も出さず、「設定へ」だけを出す', () => {
    const root = document.createElement('div');
    new SidePanel(root, keyHelp(), QUIT_ONLY).update(hud().source(), REFRESH);
    expect(root.querySelector('[data-field="speed"]')).toBeNull();
    expect([...root.querySelectorAll('.toolbar > button')].map((button) => button.textContent)).toEqual(['設定へ']);
  });

  it('キーの案内が変われば（ポーズ中の Select の行など）、名札を作り直さないフレームでも書き直す', () => {
    const root = document.createElement('div');
    let paused = false;
    const panel = new SidePanel(
      root,
      (source) =>
        describeKeyHelp({ world: source.world, roster: source.roster, padConnected: true, padInMatch: true, paused, canPause: true }),
      QUIT_ONLY,
    );
    const { source } = hud();
    panel.update(source(), REFRESH);
    expect(root.querySelector('.keyhelp')?.textContent).not.toContain('設定へもどる');
    paused = true;
    panel.update(source(), KEEP);
    expect(root.querySelector('.keyhelp')?.textContent).toContain('Select 設定へもどる');
  });

  it('名札と時計は、作り直すと渡されたフレームでだけ作り直す（原型は 0.25 秒ごと）。中身が同じなら作り直さない', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => [], QUIT_ONLY);
    const { session, source } = hud();
    panel.update(source(), REFRESH);
    const before = root.querySelector('.pcard');
    const hearts = (): string | null | undefined => root.querySelector('[data-player="1"] .hearts')?.textContent;
    const full = hearts();

    session.world.players[1]!.hp -= 2;
    session.world.now = tick(60);
    panel.update(source(), KEEP);
    expect(root.querySelector('.pcard')).toBe(before);
    expect(hearts()).toBe(full);
    expect(root.querySelector('.clock .t')?.textContent).toBe('3:00');

    panel.update(source(), REFRESH);
    expect(root.querySelector('.pcard')).not.toBe(before);
    expect(hearts()).not.toBe(full);
    expect(root.querySelector('.clock .t')?.textContent).toBe('2:59');

    // 作り直すフレームでも、中身が前と同じなら要素に触れない。
    const after = root.querySelector('.pcard');
    panel.update(source(), REFRESH);
    expect(root.querySelector('.pcard')).toBe(after);
  });

  it('時計は作り直さず、字と warn の印だけを替える（残り 30 秒からの明滅のアニメーションを頭に戻さない）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => [], QUIT_ONLY);
    const { session, source } = hud();
    panel.update(source(), REFRESH);
    const clock = root.querySelector('.clock');
    const digits = root.querySelector('.clock .t');
    expect(clock?.classList.contains('warn')).toBe(false);

    session.world.now = tick(session.world.endsAt - 30 * 60);
    panel.update(source(), REFRESH);
    expect(root.querySelector('.clock')).toBe(clock);
    expect(root.querySelector('.clock .t')).toBe(digits);
    expect(digits?.textContent).toBe('0:30');
    expect(clock?.classList.contains('warn')).toBe(true);
  });

  it('人間が葱ボンになったら、いちばん上に葱ボンの段と破線の区切りを出す（CPU がなっても出さない）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp(), QUIT_ONLY);
    const { session, source } = hud();
    // 番号1 は CPU。番号1 を見て判断する取り違えも検出する。
    session.world.players[1]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source(), REFRESH);
    expect(root.querySelector('.keyhelp')?.textContent).not.toContain('葱を発射');

    session.world.players[0]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source(), REFRESH);
    const rows = helpRows(root);
    // 葱ボンの段 4 行・破線・そうさの段 4 行・ポーズの行（原型 L5577-5582）。
    expect(rows.slice(0, 5)).toEqual([
      ['B', '', '🌿 うさぎ は葱ボン＝場外'],
      ['DIV', 'r', '外周を移動 [W][A][S][D] / [↑][←][↓][→]'],
      ['DIV', 'r', '葱を発射 [Space] か [Enter]'],
      ['DIV', 'r', '生きてるヤツに当てると交代して復活（HP1・パワーアップは維持）。残り1分で退場'],
      ['DIV', '', ''],
    ]);
    expect(rows).toHaveLength(10);
    const note = root.querySelector<HTMLElement>('.keyhelp > :nth-child(4)');
    expect(note?.querySelector('b')?.textContent).toBe('交代して復活');
    expect([note?.style.opacity, note?.style.marginTop]).toEqual(['0.85', '5px']);
    // 破線の行は原型が直に書いた style のまま（happy-dom は var() を含む一括の指定を正しく読めないので、属性の文で見る）。
    const rule = root.querySelector<HTMLElement>('.keyhelp > :nth-child(5)');
    expect(rule?.getAttribute('style')).toBe('border-top:1px dashed var(--line);margin:9px 0');
  });

  it('2人で遊ぶときは、1P の頭を b のまま置き、2P の頭は上の空き 7px の .r で包んだ b にする（原型 L5590-5593）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp(), QUIT_ONLY);
    const { source } = hud();
    panel.update({ ...source(), roster: localRoster(2, []) }, REFRESH);
    expect(helpRows(root)).toEqual([
      ['B', '', '1P 🐰'],
      ['DIV', 'r', '[W][A][S][D] ／ ばくだん [Space][Z]'],
      ['DIV', 'r', 'とぶ [E][Q][X][C][R][左Shift]（長押しでとくぎ🍗）'],
      ['DIV', 'r', '2P 🐸'],
      ['DIV', 'r', '[↑][←][↓][→] ／ ばくだん [Enter][/]'],
      ['DIV', 'r', 'した [右Shift][.][,][M][N]（長押しでとくぎ🍗）'],
      ['DIV', 'r', '[P] ポーズ'],
    ]);
    const second = root.querySelector<HTMLElement>('.keyhelp > :nth-child(4)');
    expect(second?.style.marginTop).toBe('7px');
    expect([...(second?.children ?? [])].map((child) => [child.tagName, child.textContent])).toEqual([['B', '2P 🐸']]);
    // 1P の頭の行は空きの無い素の b（原型は .r で包まない）。
    expect(root.querySelector('.keyhelp > :first-child')?.getAttribute('style')).toBeNull();
  });

  it('外周にいるプレイヤーの名札には「negi」の印と、操作する側の札のあとに「葱ボン」の札を足す（原型 L5502・L5509）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => [], QUIT_ONLY);
    const { session, source } = hud();
    session.world.players[1]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source(), REFRESH);
    const tags = (id: number): [string | null, string][] =>
      [...root.querySelectorAll(`[data-player="${id}"] .tag`)].map((tag) => [tag.textContent, tag.className]);
    expect(tags(1)).toEqual([
      ['CPU1・ふつう', 'tag cpu'],
      ['葱ボン', 'tag negi'],
    ]);
    expect(tags(0)).toEqual([['1P', 'tag']]);
    expect(root.querySelector('[data-player="1"]')?.className).toBe('pcard negi');
    expect(root.querySelector('[data-player="1"] .hearts')?.textContent).toBe('🌿 葱ボン（場外）');
  });

  it('退場したプレイヤーの名札には「dead」の印を付ける（原型 L5502）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => [], QUIT_ONLY);
    const { session, source } = hud();
    session.world.players[1]!.life = OUT;
    panel.update(source(), REFRESH);
    expect(root.querySelector('[data-player="1"]')?.className).toBe('pcard dead');
    expect(root.querySelector('[data-player="0"]')?.className).toBe('pcard');
  });

  it('試合がまだ無ければ（通信対戦のロビー）、名札とキーの案内を空にする。時計は固定の要素なので残す', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp(), QUIT_ONLY);
    panel.update(hud().source(), REFRESH);
    panel.update(null, REFRESH);
    expect(root.querySelector('.pcard')).toBeNull();
    expect(root.querySelector('.keyhelp')?.childElementCount).toBe(0);
    expect(root.querySelector('.clock')).not.toBeNull();
  });
});

describe('幕', () => {
  const ROUND: BannerView = {
    emoji: '🐰',
    title: 'ラウンド1',
    summary: 'あと2勝',
    board: '🐰1\u3000🐘0',
    note: null,
    button: 'つぎのラウンド ▶',
    final: false,
  };
  const FINAL: BannerView = { ...ROUND, emoji: '🏆', title: '優勝', note: null, button: 'もういっかい', final: true };

  it('出して、null で隠す', () => {
    const root = document.createElement('div');
    const overlay = new BannerOverlay(root);
    expect(root.hidden).toBe(true);

    overlay.show(ROUND);
    expect(root.hidden).toBe(false);
    expect(root.textContent).toContain('ラウンド1');

    overlay.show(null);
    expect(root.hidden).toBe(true);
  });

  it('題の下の行・勝ち数の行・延長戦の行を、この順に1行ずつ並べる（無い行は並べない）', () => {
    const root = document.createElement('div');
    const overlay = new BannerOverlay(root);
    const lines = (): (string | null)[] => [...root.querySelectorAll('.banner-line')].map((line) => line.textContent);
    overlay.show(ROUND);
    expect(lines()).toEqual(['あと2勝', '🐰1\u3000🐘0']);
    overlay.show({ ...ROUND, note: '⚡サドンデス決着' });
    expect(lines()).toEqual(['あと2勝', '🐰1\u3000🐘0', '⚡サドンデス決着']);
  });

  it('ボタンは試合が決まった幕にだけ並べる', () => {
    const root = document.createElement('div');
    const overlay = new BannerOverlay(root);
    const again = pointerButton('もういっかい', () => undefined);

    overlay.show(ROUND, [again]);
    expect(root.contains(again)).toBe(false);

    overlay.show(FINAL, [again]);
    expect(root.contains(again)).toBe(true);
  });
});

describe('ボタン', () => {
  it('マウスで押したときだけ呼ぶ。キーボードで起きたクリックは捨てる', () => {
    let pressed = 0;
    const button = pointerButton('はじめる', () => (pressed += 1));
    document.body.append(button);

    // Enter や Space で起きたクリックは detail が 0。click() も同じ形で届く。
    button.click();
    expect(pressed).toBe(0);

    button.dispatchEvent(new MouseEvent('click', { detail: 1 }));
    expect(pressed).toBe(1);
    expect(button.tabIndex).toBe(-1);
  });

  it('メニューのカーソルで決めたときは、クリックを通さずに同じ中身を呼ぶ', () => {
    let pressed = 0;
    const button = pointerButton('はじめる', () => (pressed += 1));
    expect(activate(button)).toBe(true);
    expect(pressed).toBe(1);
    // pointerButton で作っていない要素は押せない（黙って何もしない）。
    expect(activate(document.createElement('button'))).toBe(false);
    expect(pressed).toBe(1);
  });
});

describe('通知', () => {
  /** 時刻を手で進める時計。`advance` で進めると、その時刻までに頼まれたものを順に呼ぶ。 */
  function manualClock(): ToastClock & { advance: (ms: number) => void } {
    let now = 0;
    let queue: { at: number; callback: () => void }[] = [];
    return {
      now: () => now,
      after: (callback, ms) => queue.push({ at: now + ms, callback }),
      advance: (ms) => {
        const until = now + ms;
        for (;;) {
          const next = queue.filter((item) => item.at <= until).sort((a, b) => a.at - b.at)[0];
          if (next === undefined) break;
          queue = queue.filter((item) => item !== next);
          now = next.at;
          next.callback();
        }
        now = until;
      },
    };
  }

  it('1つの要素に文を書いて出し、出してから 1400 ms で on を外す（文は残す。原型の toast）', () => {
    const root = document.createElement('div');
    const clock = manualClock();
    const toasts = new Toasts(root, clock);
    toasts.show('🍌 うさぎ すべる！');
    expect(root.textContent).toBe('🍌 うさぎ すべる！');
    expect(root.classList.contains('on')).toBe(true);
    expect(root.childElementCount).toBe(0);

    clock.advance(1399);
    expect(root.classList.contains('on')).toBe(true);
    clock.advance(1);
    expect(root.classList.contains('on')).toBe(false);
    expect(root.textContent).toBe('🍌 うさぎ すべる！');
  });

  it('新しい文は積まずに置き換え、消え始めるまでを新しい文から数え直す', () => {
    const root = document.createElement('div');
    const clock = manualClock();
    const toasts = new Toasts(root, clock);
    toasts.show('前の通知');
    clock.advance(1000);
    toasts.show('新しい通知');
    expect(root.textContent).toBe('新しい通知');
    expect(root.childElementCount).toBe(0);
    // 前の通知から 1400 ms たっても、新しい通知から 1400 ms たつまでは出す。
    clock.advance(1399);
    expect(root.classList.contains('on')).toBe(true);
    clock.advance(1);
    expect(root.classList.contains('on')).toBe(false);
  });

  it('時計を渡さなければ実時間で数える（1400 ms で on を外す）', () => {
    vi.useFakeTimers();
    const root = document.createElement('div');
    const toasts = new Toasts(root);
    toasts.show('🎮 コントローラーを認識しました');
    vi.advanceTimersByTime(1399);
    expect(root.classList.contains('on')).toBe(true);
    vi.advanceTimersByTime(1);
    expect(root.classList.contains('on')).toBe(false);
  });
});
