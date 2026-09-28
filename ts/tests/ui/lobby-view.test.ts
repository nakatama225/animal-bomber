// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { parseLanSettings } from '../../src/net/protocol.js';
import { LobbyView } from '../../src/platform/ui/LobbyView.js';
import { lanSettingsFrom, LobbyChoices, type LanSetup } from '../../src/presentation/menu/lanSetup.js';

function press(root: HTMLElement, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

function mount(): { root: HTMLElement; view: LobbyView; started: LanSetup[]; changed: LanSetup[]; left: number[] } {
  const root = document.createElement('div');
  document.body.append(root);
  const started: LanSetup[] = [];
  const changed: LanSetup[] = [];
  const left: number[] = [];
  const view = new LobbyView(root, new LobbyChoices(), {
    start: (setup) => started.push(setup),
    changed: (setup) => changed.push(setup),
    leave: () => left.push(1),
  });
  return { root, view, started, changed, left };
}

afterEach(() => document.body.replaceChildren());

describe('通信対戦のロビー', () => {
  it('ホストは4つの枠とルールを決めて始められる', () => {
    const { root, view, started } = mount();
    view.show({ kind: 'lobby', seat: 0, present: [0, 2] });
    expect(root.querySelectorAll('[data-slot]')).toHaveLength(4);
    expect(root.querySelector('[data-slot="2"] .slot-head')?.textContent).toContain('つながっている');
    expect(root.querySelector('[data-slot="1"] .slot-head')?.textContent).toContain('空き');

    press(root, '[data-field="animal-3"] [data-value="mole"]');
    press(root, '[data-field="hits-0"] [data-value="1"]');
    press(root, '[data-field="cpu-1"] [data-value="oni"]');
    press(root, '[data-field="wins"] [data-value="7"]');
    press(root, '[data-action="start"]');

    expect(started).toHaveLength(1);
    const setup = started[0]!;
    expect(setup.animals[3]).toBe('mole');
    expect(setup.hits[0]).toBe(1);
    expect(setup.cpuLevels[1]).toBe('oni');
    expect(setup.winsToTake).toBe(7);
  });

  it('枠ごとの行は、動物・CPU の強さ・体力の順に並ぶ（原型と同じ）', () => {
    // カーソルは画面の並びの順に集めるので、この順が上下で辿る順にもなる。
    const { root, view } = mount();
    view.show({ kind: 'lobby', seat: 0, present: [0] });
    const rows = [...root.querySelectorAll<HTMLElement>('[data-slot="1"] [data-nav]')].map((row) => row.dataset['nav']);
    expect([...new Set(rows)]).toEqual(['animal-1', 'cpu-1', 'hits-1']);
  });

  it('様子が前と同じなら組み直さない（毎フレーム呼ばれても、押そうとしたボタンが消えない）', () => {
    const { root, view } = mount();
    view.show({ kind: 'lobby', seat: 0, present: [0] });
    const start = root.querySelector('[data-action="start"]');
    view.show({ kind: 'lobby', seat: 0, present: [0] });
    expect(root.querySelector('[data-action="start"]')).toBe(start);
    view.show({ kind: 'lobby', seat: 0, present: [0, 1] });
    expect(root.querySelector('[data-action="start"]')).not.toBe(start);
  });

  it('ホストが選び直すたびに知らせる（始まる前のゲストの画面へ配るため）', () => {
    const { root, view, changed } = mount();
    view.show({ kind: 'lobby', seat: 0, present: [0, 1] });
    press(root, '[data-field="animal-2"] [data-value="mole"]');
    press(root, '[data-field="sudden"] [data-value="false"]');
    expect(changed.map((setup) => [setup.animals[2], setup.suddenDeath])).toEqual([
      ['mole', true],
      ['mole', false],
    ]);
  });

  it('ゲストには選ぶ行を出さず、待っていることだけを出す', () => {
    const { root, view } = mount();
    view.show({ kind: 'lobby', seat: 2, present: [0, 2] });
    expect(root.querySelector('[data-slot]')).toBeNull();
    expect(root.querySelector('[data-action="start"]')).toBeNull();
    expect(root.textContent).toContain('あなたは 3P');
    // ホストの設定がまだ届いていない。
    expect(root.textContent).toContain('1P（ホスト）の設定を待っている');
  });

  it('ゲストには、ホストが選んでいる設定を読むだけの表で出す', () => {
    const { root, view } = mount();
    const choices = new LobbyChoices();
    choices.setAnimal(2, 'mole');
    choices.setCpuLevel(1, 'oni');
    choices.setHits(3, 1);
    choices.setWinsToTake(7);
    choices.setSuddenDeath(false);
    view.show({ kind: 'lobby', seat: 2, present: [0, 2], hostSettings: choices.setup });

    const field = (id: string): string => root.querySelector(`[data-shared-field="${id}"] span:last-child`)?.textContent ?? '';
    expect(root.querySelectorAll('[data-shared-slot]')).toHaveLength(4);
    expect(root.querySelector('[data-shared-slot="2"] .slot-head')?.textContent).toContain('3P（あなた）');
    expect(field('animal-2')).toBe('🦫もぐら');
    expect(field('animal-0')).toBe('🐰うさぎ');
    expect(field('cpu-1')).toBe('おに');
    expect(field('cpu-0')).toBe('ふつう');
    expect(field('hits-3')).toBe('1回');
    expect(field('wins')).toBe('7勝');
    expect(field('sudden')).toBe('OFF');
    expect(root.querySelector('[data-shared-rules] [data-shared-field="wins"]')).not.toBeNull();
    // 読むだけ。カーソルにも載せず、選ぶボタンも出さない（ゲストが押しても試合には使われない）。
    expect(root.querySelector('[data-nav]')).toBeNull();
    expect(root.querySelector('button[data-value]')).toBeNull();
    expect(root.textContent).not.toContain('1P（ホスト）の設定を待っている');
  });

  it('断られたときは理由と、やり直し方を出す', () => {
    const { root, view } = mount();
    view.show({ kind: 'failed', reason: '前の試合が続いている' });
    expect(root.textContent).toContain('前の試合が続いている');
    expect(root.textContent).toContain('全員がページを閉じてから');
  });

  it('ぬけるを押したら知らせる', () => {
    const { root, view, left } = mount();
    view.show({ kind: 'connecting' });
    press(root, '[data-action="leave"]');
    expect(left).toEqual([1]);
  });
});

describe('ロビーで決めたものから配る設定', () => {
  it('配った設定は、受け取った側でそのまま読める', () => {
    // 作る側と読む側の約束が食い違うと、ゲストだけが試合を作れずに止まる。
    const choices = new LobbyChoices();
    choices.setHits(2, 6);
    choices.setCpuLevel(3, 'easy');
    const settings = lanSettingsFrom(choices.setup, 123);
    expect(parseLanSettings(JSON.parse(JSON.stringify(settings)))).toEqual(settings);
    expect(settings.match.startingHp[2]).toBe(12);
    expect(settings.cpu[3]).toBe('easy');
  });

  it('選べない値は受け付けない', () => {
    const choices = new LobbyChoices();
    expect(() => choices.setHits(0, 9)).toThrow('爆風の回数');
    expect(() => choices.setAnimal(0, 'dragon')).toThrow('知らない動物');
  });
});
