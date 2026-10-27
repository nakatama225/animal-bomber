// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { parseLanSettings } from '../../src/net/protocol.js';
import { LobbyView } from '../../src/platform/ui/LobbyView.js';
import { lanSettingsFrom, LobbyChoices, type LanSetup } from '../../src/presentation/menu/lanSetup.js';

function press(root: HTMLElement, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

/**
 * ロビーを組み立てる。外へ知らせたことは `log` に順に控える（画面の操作の音は `ui`）。
 */
function mount(): { root: HTMLElement; view: LobbyView; started: LanSetup[]; changed: LanSetup[]; log: string[] } {
  const root = document.createElement('div');
  document.body.append(root);
  const started: LanSetup[] = [];
  const changed: LanSetup[] = [];
  const log: string[] = [];
  const view = new LobbyView(root, new LobbyChoices(), {
    start: (setup) => {
      started.push(setup);
      log.push('start');
    },
    changed: (setup) => {
      changed.push(setup);
      log.push('changed');
    },
    disconnect: () => log.push('disconnect'),
    uiSound: () => log.push('ui'),
    entered: () => log.push('entered'),
  });
  return { root, view, started, changed, log };
}

const texts = (root: ParentNode, selector: string): (string | null)[] =>
  [...root.querySelectorAll(selector)].map((element) => element.textContent);
const navGroups = (root: ParentNode): string[] => [
  ...new Set([...root.querySelectorAll<HTMLElement>('[data-nav]')].map((element) => element.dataset['nav'] ?? '')),
];

afterEach(() => document.body.replaceChildren());

describe('通信対戦のロビー', () => {
  it('ホストは4つの枠とルールを決めて始められる', () => {
    const { root, view, started } = mount();
    view.show({ seat: 0, present: [0, 2] });
    expect(root.querySelectorAll('.pickhdr[data-slot]')).toHaveLength(4);
    expect(root.querySelector('[data-slot="2"] .keys')?.textContent).toBe('🟢 接続済み');
    expect(root.querySelector('[data-slot="1"] .keys')?.textContent).toBe('⚪ 空き・待機中');

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

  it('枠ごとの行は動物・CPU の強さ・体力の順に並び、CPU の強さはいまつながっていない枠にだけ出す（Python 版と同じ）', () => {
    // カーソルは画面の並びの順に集めるので、この順が上下で辿る順にもなる。
    const { root, view } = mount();
    view.show({ seat: 0, present: [0, 2] });
    expect(navGroups(root)).toEqual([
      'animal-0',
      'hits-0',
      'animal-1',
      'cpu-1',
      'hits-1',
      'animal-2',
      'hits-2',
      'animal-3',
      'cpu-3',
      'hits-3',
      'wins',
      'time',
      'sudden',
      'go',
    ]);
    expect(root.querySelector('[data-field="cpu-0"]')).toBeNull();
    expect(root.querySelector('[data-field="cpu-2"]')).toBeNull();
    // 誰かがつながると、その枠の CPU の強さの行は消える（組み直す）。
    view.show({ seat: 0, present: [0, 1, 2] });
    expect(root.querySelector('[data-field="cpu-1"]')).toBeNull();
    expect(root.querySelector('[data-field="cpu-3"]')).not.toBeNull();
  });

  it('ホストの文と並びは原型と同じ（冒頭の1行・枠の見出し・体力とルールの見出し・「はじめる ▶」）。この版だけの注記は出さない', () => {
    const { root, view } = mount();
    view.show({ seat: 0, present: [0] });
    expect(root.querySelector('.shead > [data-action="leave"]')?.textContent).toBe('← せつぞくを切る');
    expect(root.querySelector('.shead > h2')?.textContent).toBe('ロビー');
    expect(texts(root, '.note')[0]).toBe('あなたは 1P（ホスト）');
    expect(texts(root, '.pickhdr .who')).toEqual(['1P（あなた）', '2P', '3P', '4P']);
    expect(texts(root, 'label.lb')).toEqual([
      'たいりょく（爆風にたえる回数）',
      'たいりょく（爆風にたえる回数）',
      'たいりょく（爆風にたえる回数）',
      'たいりょく（爆風にたえる回数）',
      '何勝先取',
      'じかん',
      'サドンデス',
    ]);
    expect(root.querySelector('.navbar > [data-action="start"]')?.textContent).toBe('はじめる ▶');
    // 待ちの文はゲストだけ。原型に無い注記と、原型に無い見出しの語も出さない。
    expect(root.textContent).not.toContain('ホストが「はじめる」を押すのを待っています');
    expect(root.textContent).not.toContain('途中で抜けた');
    expect(root.textContent).not.toContain('CPU の強さ（');
    expect(root.textContent).not.toContain('倒れるまでの爆風の回数');
  });

  it('様子が前と同じなら組み直さない（毎フレーム呼ばれても、押そうとしたボタンが消えない）', () => {
    const { root, view } = mount();
    view.show({ seat: 0, present: [0] });
    const start = root.querySelector('[data-action="start"]');
    view.show({ seat: 0, present: [0] });
    expect(root.querySelector('[data-action="start"]')).toBe(start);
    view.show({ seat: 0, present: [0, 1] });
    expect(root.querySelector('[data-action="start"]')).not.toBe(start);
  });

  it('初めて写したときだけ、ページの先頭へ戻して知らせる（原型の showScreen("lobby")）', () => {
    const { root, view, log } = mount();
    const scrolled = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    try {
      view.show({ seat: 1, present: [0, 1] });
      expect(log).toEqual(['entered']);
      expect(scrolled).toHaveBeenCalledTimes(1);
      view.show({ seat: 1, present: [0, 1, 2] });
      expect(root.querySelector('[data-slot="2"] .keys')?.textContent).toBe('🟢 接続済み');
      expect(log).toEqual(['entered']);
      expect(scrolled).toHaveBeenCalledTimes(1);
    } finally {
      scrolled.mockRestore();
    }
  });

  it('ホストが選び直すたびに知らせる（始まる前のゲストの画面へ配るため）', () => {
    const { root, view, changed } = mount();
    view.show({ seat: 0, present: [0, 1] });
    press(root, '[data-field="animal-2"] [data-value="mole"]');
    press(root, '[data-field="sudden"] [data-value="false"]');
    expect(changed.map((setup) => [setup.animals[2], setup.suddenDeath])).toEqual([
      ['mole', true],
      ['mole', false],
    ]);
  });

  it('チップ・「← せつぞくを切る」・「はじめる ▶」は操作の音を鳴らしてから反映する。動物のカードは鳴らさない（原型 L5642・L5746-5747・L5843）', () => {
    const { root, view, log } = mount();
    view.show({ seat: 0, present: [0] });
    log.length = 0;
    press(root, '[data-field="animal-1"] [data-value="mole"]');
    expect(log).toEqual(['changed']);
    log.length = 0;
    press(root, '[data-field="hits-1"] [data-value="3"]');
    press(root, '[data-field="cpu-1"] [data-value="oni"]');
    press(root, '[data-field="time"] [data-value="60"]');
    expect(log).toEqual(['ui', 'changed', 'ui', 'changed', 'ui', 'changed']);
    log.length = 0;
    press(root, '[data-action="leave"]');
    press(root, '[data-action="start"]');
    expect(log).toEqual(['ui', 'disconnect', 'ui', 'start']);
  });

  it('ゲストには選ぶ行を出さず、ホストが選んでいる設定を読むだけの1行ずつで出す（原型の形と文）', () => {
    const { root, view } = mount();
    const choices = new LobbyChoices();
    choices.setAnimal(2, 'mole');
    choices.setCpuLevel(1, 'oni');
    choices.setCpuLevel(2, 'oni');
    choices.setHits(3, 4);
    choices.setWinsToTake(7);
    choices.setSuddenDeath(false);
    view.show({ seat: 2, present: [0, 2], hostSettings: choices.setup });

    expect(texts(root, '.note')[0]).toBe('あなたは 3P（ゲスト）');
    expect(texts(root, '.pickhdr .who')).toEqual(['1P', '2P', '3P（あなた）', '4P']);
    // CPU の強さは、いまつながっていない枠（2P・4P）にだけ出す。
    expect(texts(root, '[data-shared-slot]')).toEqual([
      '🐰うさぎ ／ たいりょく 1回',
      '🐸かえる ／ おに ／ たいりょく 1回',
      '🦫もぐら ／ たいりょく 1回',
      '🐘ぞう ／ ふつう ／ たいりょく 4回',
    ]);
    expect(root.querySelector('[data-shared-rules]')?.textContent).toBe('7勝先取 ／ じかん 3:00 ／ サドンデス OFF');
    expect(root.querySelector('.navbar > .note')?.innerHTML).toBe(
      'ルールはホストが決めます（上に出ている内容ではじまります）。<br>ホストが「はじめる」を押すのを待っています…',
    );
    // 読むだけ。カーソルにも載せず、選ぶボタンも「はじめる ▶」も出さない（ゲストが押しても試合には使われない）。
    expect(root.querySelector('[data-nav]')).toBeNull();
    expect(root.querySelector('button[data-value]')).toBeNull();
    expect(root.querySelector('[data-action="start"]')).toBeNull();
  });

  it('ホストの設定がまだ届いていないゲストには、既定の値を出す（原型と同じ）', () => {
    const { root, view } = mount();
    view.show({ seat: 1, present: [0, 1] });
    expect(texts(root, '[data-shared-slot]')).toEqual([
      '🐰うさぎ ／ たいりょく 1回',
      '🐸かえる ／ たいりょく 1回',
      '🦊きつね ／ ふつう ／ たいりょく 1回',
      '🐘ぞう ／ ふつう ／ たいりょく 1回',
    ]);
    expect(root.querySelector('[data-shared-rules]')?.textContent).toBe('3勝先取 ／ じかん 3:00 ／ サドンデス ON');
    expect(root.textContent).not.toContain('設定を待っている');
  });

  it('要素とクラス名は原型と同じ（箱・頭・枠の見出し・動物のカード・見出しの label・チップの箱の下の空き・下のボタンの列）', () => {
    // 見た目の指定（`style.css`）は原型の名前で書いてある。名前が外れると、ロビーだけ素のままの表示になる。
    const { root, view } = mount();
    view.show({ seat: 0, present: [0] });
    const screen = root.querySelector('[data-screen="lobby"]');
    expect(screen?.classList.contains('card')).toBe(true);
    expect([...(screen?.children ?? [])].map((child) => child.className)).toEqual(['shead', '', 'navbar']);
    expect(root.querySelector('.shead > [data-action="leave"]')?.classList.contains('backb')).toBe(true);
    // 動物のカードは絵文字と名前だけ（説明は出さない。原型 L5842）。
    const card = root.querySelector('[data-field="animal-0"].animals > .acard');
    expect([...(card?.children ?? [])].map((child) => child.className)).toEqual(['ae', 'an']);
    expect(root.querySelector('.animals .ad')).toBeNull();
    // チップの箱は下に 10px を空ける（原型が直に付けた値）。
    for (const id of ['cpu-1', 'hits-0', 'wins', 'time', 'sudden']) {
      const box = root.querySelector<HTMLElement>(`[data-field="${id}"]`);
      expect(box?.classList.contains('chips'), id).toBe(true);
      expect(box?.style.marginBottom, id).toBe('10px');
    }
    // 体力の見出しは label.lb で、チップの箱の直前に置く（原型の CSS は label の要素にだけ当たる）。
    const hits = root.querySelector('[data-field="hits-0"]');
    expect(hits?.previousElementSibling?.tagName).toBe('LABEL');
    expect(hits?.previousElementSibling?.classList.contains('lb')).toBe(true);
    // この版だけの区切り（.slot）は無い。
    expect(root.querySelector('.slot, .slot-head')).toBeNull();
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
