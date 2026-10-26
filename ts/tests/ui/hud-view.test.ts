// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { tick } from '../../src/domain/core/Tick.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { keyHelpFor } from '../../src/platform/keyHelp.js';
import { SOLO_KEYS } from '../../src/platform/Keyboard.js';
import { BannerOverlay } from '../../src/platform/ui/BannerOverlay.js';
import { activate, pointerButton } from '../../src/platform/ui/dom.js';
import { SidePanel } from '../../src/platform/ui/SidePanel.js';
import { Toasts } from '../../src/platform/ui/Toasts.js';
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

describe('横の板', () => {
  it('時計・名札・キー配置の説明を並べる', () => {
    const root = document.createElement('div');
    const panel = new SidePanel(root, () => [{ playerId: 0, help: keyHelpFor('1P', SOLO_KEYS) }]);
    panel.update(hud().source());

    expect(root.querySelector('[data-part="clock"] .time')?.textContent).toBe('3:00');
    expect(root.querySelectorAll('.card')).toHaveLength(2);
    expect(root.querySelector('[data-player="0"] .tag')?.textContent).toBe('1P（あなた）');
    expect(root.querySelector('[data-player="1"] .tag')?.textContent).toBe('CPU・ふつう');
    expect(root.querySelector('.keyhelp')?.textContent).toContain('W A S D');
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

  it('自分が葱ボンになったら、葱ボンの操作を足す（ほかの人がなっても足さない）', () => {
    const root = document.createElement('div');
    // 説明を出すのは 2P（番号1）。番号0 の人を見て判断する取り違えも検出する。
    const panel = new SidePanel(root, () => [{ playerId: 1, help: keyHelpFor('2P', SOLO_KEYS) }]);
    const { session, source } = hud();
    session.world.players[0]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source());
    expect(root.querySelector('.keyhelp .note')).toBeNull();

    session.world.players[1]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    panel.update(source());
    expect(root.querySelector('.keyhelp .note')?.textContent).toContain('葱を撃つ');
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
