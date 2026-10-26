// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { tick } from '../../src/domain/core/Tick.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { BannerOverlay } from '../../src/platform/ui/BannerOverlay.js';
import { activate, pointerButton } from '../../src/platform/ui/dom.js';
import { SidePanel, type KeyHelpFor } from '../../src/platform/ui/SidePanel.js';
import { Toasts } from '../../src/platform/ui/Toasts.js';
import { describeKeyHelp } from '../../src/presentation/hud/keyHelp.js';
import type { Roster } from '../../src/presentation/hud/roster.js';
import type { HudSource } from '../../src/presentation/hud/scoreboard.js';

/**
 * 画面に写す部分を、ブラウザの代わりの DOM（happy-dom）で組んで確認する。
 *
 * 中身の文は `tests/presentation/hud.test.ts` が見ている。ここで見るのは、
 * 写し方（要素ができるか・書き換えを省くか・押したら呼ばれるか）だけ。
 */

const ROSTER: Roster = [
  { kind: 'human', label: '1P', local: true },
  { kind: 'cpu', level: 'normal' },
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

describe('横の板', () => {
  it('時計・名札・キーの案内を並べる', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp());
    panel.update(hud().source());

    expect(root.querySelector('[data-part="clock"] .time')?.textContent).toBe('3:00');
    expect(root.querySelectorAll('.card')).toHaveLength(2);
    expect(root.querySelector('[data-player="0"] .tag')?.textContent).toBe('1P（あなた）');
    expect(root.querySelector('[data-player="1"] .tag')?.textContent).toBe('CPU・ふつう');
    // 行は文のまま並べる。太字だけの行は b、キーは空白で区切る。
    const rows = [...(root.querySelector('.keyhelp .help')?.children ?? [])];
    expect(rows.map((row) => [row.tagName, row.textContent])).toEqual([
      ['B', 'そうさ'],
      ['DIV', 'うごく W A S D / ↑ ← ↓ →'],
      ['DIV', 'ばくだん Space Enter Z /'],
      ['DIV', 'とぶ E Q X C R Shift（長押しでとくぎ🍗）'],
      ['DIV', 'P ポーズ'],
    ]);
  });

  it('キーの案内が変われば（ポーズ中の Select の行など）、書き直す', () => {
    const root = document.createElement('div');
    let paused = false;
    const panel = new SidePanel(root, (source) =>
      describeKeyHelp({ world: source.world, roster: source.roster, padConnected: true, padInMatch: true, paused, canPause: true }),
    );
    const { source } = hud();
    panel.update(source());
    expect(root.querySelector('.keyhelp')?.textContent).not.toContain('設定へもどる');
    paused = true;
    panel.update(source());
    expect(root.querySelector('.keyhelp')?.textContent).toContain('Select 設定へもどる');
  });

  it('中身が変わらなければ要素を作り直さない', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => []);
    const { session, source } = hud();
    panel.update(source());
    const before = root.querySelector('.card');

    panel.update(source());
    expect(root.querySelector('.card')).toBe(before);

    session.world.players[1]!.hp -= 2;
    panel.update(source());
    expect(root.querySelector('.card')).not.toBe(before);
  });

  it('人間が葱ボンになったら、いちばん上に葱ボンの段を出す（CPU がなっても出さない）', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, keyHelp());
    const { session, source } = hud();
    // 番号1 は CPU。番号1 を見て判断する取り違えも検出する。
    session.world.players[1]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source());
    expect(root.querySelector('.keyhelp')?.textContent).not.toContain('葱を発射');

    session.world.players[0]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source());
    const help = root.querySelector('.keyhelp .help');
    expect(help?.firstElementChild?.textContent).toBe('🌿 うさぎ は葱ボン＝場外');
    expect(help?.textContent).toContain('葱を発射 Space か Enter');
    // 区切りの行（破線）は、まだ写さずに飛ばす。空の行を残さない（葱ボンの段 4 行・そうさの段 4 行・ポーズの行）。
    const children = [...(help?.children ?? [])];
    expect(children).toHaveLength(9);
    expect(children.some((child) => child.textContent === '')).toBe(false);
  });

  it('試合が無ければ空にする', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => []);
    panel.update(hud().source());
    panel.update(null);
    expect(root.querySelector('.card')).toBeNull();
    expect(root.querySelector('[data-part="clock"]')).toBeNull();
  });
});

describe('幕', () => {
  const ROUND = { emoji: '🐰', title: 'ラウンド1', lines: ['あと2勝'], final: false };
  const FINAL = { emoji: '🏆', title: '優勝', lines: [], final: true };

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
  it('出して、時間がたったら消す', () => {
    vi.useFakeTimers();
    const root = document.createElement('div');
    const toasts = new Toasts(root);
    toasts.show('うさぎ（1P）：🍌すべる');
    expect(root.textContent).toBe('うさぎ（1P）：🍌すべる');

    vi.advanceTimersByTime(3000);
    expect(root.childElementCount).toBe(0);
  });

  it('多すぎたら古いものから消す', () => {
    vi.useFakeTimers();
    const root = document.createElement('div');
    const toasts = new Toasts(root);
    for (let i = 0; i < 6; i += 1) toasts.show(`通知${i}`);
    expect(root.childElementCount).toBe(4);
    expect(root.firstElementChild?.textContent).toBe('通知2');
  });
});
