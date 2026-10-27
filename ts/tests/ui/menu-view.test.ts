// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MenuView } from '../../src/platform/ui/MenuView.js';
import { KEY_HINT_P1, KEY_HINT_P2, KEY_HINT_SOLO } from '../../src/presentation/menu/keyHints.js';
import type { LocalSetup } from '../../src/presentation/menu/localSetup.js';
import { CHANGELOG, MANUAL } from '../../src/presentation/menu/manual.js';
import { HIT_NOTE } from '../../src/presentation/menu/menuText.js';
import { MenuFlow, type SoundSetting } from '../../src/presentation/menu/MenuFlow.js';

/** マウスで押したのと同じクリック（キーボードで起きたクリックは detail が 0 で、捨てられる）。 */
function press(root: HTMLElement, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

/**
 * 画面を組み立てる。
 *
 * 外へ知らせたことは `log` に順に控える（画面の操作の音は `ui`、音の設定は `sound:off` の形）。
 */
function mount(): {
  root: HTMLElement;
  flow: MenuFlow;
  view: MenuView;
  started: LocalSetup[];
  sounds: SoundSetting[];
  lan: number[];
  log: string[];
} {
  const root = document.createElement('div');
  document.body.append(root);
  const flow = new MenuFlow();
  const started: LocalSetup[] = [];
  const sounds: SoundSetting[] = [];
  const lan: number[] = [];
  const log: string[] = [];
  const view = new MenuView(root, flow, {
    start: (setup) => {
      started.push(setup);
      log.push('start');
    },
    soundChanged: (sound) => {
      sounds.push(sound);
      log.push(`sound:${sound}`);
    },
    openLan: () => {
      lan.push(1);
      log.push('lan');
    },
    uiSound: () => log.push('ui'),
  });
  view.render();
  return { root, flow, view, started, sounds, lan, log };
}

const screenOf = (root: HTMLElement): string | null | undefined => root.querySelector('[data-screen]')?.getAttribute('data-screen');
const texts = (root: ParentNode, selector: string): (string | null)[] =>
  [...root.querySelectorAll(selector)].map((element) => element.textContent);

afterEach(() => document.body.replaceChildren());

describe('試合の前の画面', () => {
  it('タイトルから選んで、はじめるまで押していける', () => {
    const { root, started } = mount();
    expect(root.querySelector('.logoPlate .logo')?.textContent).toBe('Nakatando');

    press(root, '[data-choice="duo"]');
    expect(screenOf(root)).toBe('pick');
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
    new MenuView(root, flow, {
      start: (s) => started.push(s),
      soundChanged: () => undefined,
      openLan: () => undefined,
      uiSound: () => undefined,
    }).render();
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

    // 2人 vs CPU×2 では、CPU の強さの行は2つ（原型の buildCpuRows）。
    press(root, '[data-action="back"]');
    press(root, '[data-action="back"]');
    press(root, '[data-choice="duo"]');
    press(root, '[data-action="next"]');
    expect(root.querySelector('[data-field="hits-p2"]')).not.toBeNull();
    expect(root.querySelectorAll('[data-field^="cpu-"]')).toHaveLength(2);
    expect(root.querySelector('[data-field="cpu-2"]')).toBeNull();
    expect(texts(root, '.cols span.lb')).toEqual(['CPU1', 'CPU2']);
  });

  it('設定の画面で音を切り替え、マニュアルを出す', () => {
    const { root, sounds } = mount();
    press(root, '[data-choice="manual"]');
    press(root, '[data-field="sound"] [data-value="off"]');
    expect(sounds).toEqual(['off']);
    expect(root.querySelector('[data-field="sound"] .on')?.textContent).toBe('無音');
    expect(root.querySelector('.manual')?.textContent).toContain('葱ボン');
  });

  it('LAN対戦を選んだら知らせる', () => {
    const { root, lan } = mount();
    press(root, '[data-choice="lan"]');
    expect(lan).toEqual([1]);
  });

  it('キャラ選びのキーの案内は原型の文（1人は1人用の1つ、2人は 1P と 2P のそれぞれ）', () => {
    const { root } = mount();
    press(root, '[data-choice="solo"]');
    expect(texts(root, '.pickhdr .keys')).toEqual([KEY_HINT_SOLO]);
    press(root, '[data-action="back"]');
    press(root, '[data-choice="duo"]');
    expect(texts(root, '.pickhdr .keys')).toEqual([KEY_HINT_P1, KEY_HINT_P2]);
  });
});

describe('試合の前の画面の並び（原型の HTML と同じ要素とクラス名）', () => {
  it('タイトルは箱で包まず、ロゴの銘板・題・版の行と、5つの項目を並べる。下の2つは小さい形', () => {
    const { root } = mount();
    const screen = root.querySelector('[data-screen="title"]');
    expect(screen?.classList.contains('card')).toBe(false);
    expect(root.querySelector('.titleWrap .logoSub')?.textContent).toBe('🐰💣🐘 どうぶつボンバー');
    expect(root.querySelector('.titleWrap .ver')?.textContent).toBe('VERSION v4.3.0');
    const buttons = [...root.querySelectorAll<HTMLElement>('.menu > .mbtn')];
    expect(buttons.map((button) => button.dataset['choice'])).toEqual(['solo', 'duo', 'versus', 'lan', 'manual']);
    expect(buttons.map((button) => button.classList.contains('sub'))).toEqual([false, false, false, true, true]);
    // 題は `.mbtn` の字のまま（要素を作らない）、説明は `.md`。
    const lan = buttons[3]!;
    expect(lan.querySelector('.mi')?.textContent).toBe('📶');
    expect(lan.querySelector('.md')?.textContent).toBe('同じ Wi-Fi 内の別の Mac と対戦する（最大4人）');
    expect(lan.textContent).toBe('📶LAN対戦同じ Wi-Fi 内の別の Mac と対戦する（最大4人）');
  });

  it('タイトルのほかの画面は箱（.card）で包み、頭に「← もどる」・見出し・STEP を並べる', () => {
    const { root } = mount();
    press(root, '[data-choice="solo"]');
    expect(root.querySelector('[data-screen="pick"]')?.classList.contains('card')).toBe(true);
    expect(texts(root, '.shead > *')).toEqual(['← もどる', 'キャラをえらぶ', 'STEP 1 / 2']);
    expect(root.querySelector('.shead .backb')?.tagName).toBe('BUTTON');
    press(root, '[data-action="next"]');
    expect(texts(root, '.shead > *')).toEqual(['← もどる', 'ルールをきめる', 'STEP 2 / 2']);
    press(root, '[data-action="back"]');
    press(root, '[data-action="back"]');
    press(root, '[data-choice="manual"]');
    // 設定の画面には STEP が無い。
    expect(texts(root, '.shead > *')).toEqual(['← もどる', '設定・マニュアル・更新履歴']);
  });

  it('キャラ選びは「P1 のどうぶつ」の見出しと案内を横に並べ、2人なら段の間に 6px の空きを挟む', () => {
    const { root } = mount();
    press(root, '[data-choice="duo"]');
    expect(texts(root, '.pickhdr .who')).toEqual(['P1 のどうぶつ', 'P2 のどうぶつ']);
    const row = root.querySelector('[data-screen="pick"] > .row');
    const children = [...(row?.children ?? [])] as HTMLElement[];
    expect(children.map((child) => child.dataset['human'] ?? child.style.height)).toEqual(['0', '6px', '1']);
    // 1人なら空きを挟まない。
    press(root, '[data-action="back"]');
    press(root, '[data-choice="solo"]');
    expect(root.querySelector('[data-screen="pick"] > .row')?.children).toHaveLength(1);
    // 動物のカードは絵文字・名前・説明。説明は原型の文。
    const card = root.querySelector('[data-animal="mole"]');
    expect(card?.classList.contains('acard')).toBe(true);
    expect(card?.querySelector('.ae')?.textContent).toBe('🦫');
    expect(card?.querySelector('.an')?.textContent).toBe('もぐら');
    expect(card?.querySelector('.ad')?.textContent).toContain('ソフトブロックのみ通り抜け可能');
    // 「つぎへ ▶」は下のボタンの列に置く。
    expect(root.querySelector('.navbar > .go')?.textContent).toBe('つぎへ ▶');
  });

  it('ルールは2列。左の列に体力と CPU の強さ、右の列に勝ち数・制限時間・サドンデス', () => {
    const { root } = mount();
    press(root, '[data-choice="solo"]');
    press(root, '[data-action="next"]');
    const [left, right] = [...(root.querySelector('.cols')?.children ?? [])] as HTMLElement[];
    expect(texts(left!, 'label.lb')).toEqual(['1P が爆風にたえる回数', 'CPU が爆風にたえる回数', 'CPU の強さ（1体ずつ）']);
    // 体力の行の下の注記（ハンデの例と、ぞうの +1回）。
    expect(texts(left!, ':scope > .row:first-child > .note')).toEqual([HIT_NOTE]);
    expect(HIT_NOTE).toContain('🐘ぞうは常に +1回');
    expect(texts(right!, 'label.lb')).toEqual(['何勝先取で優勝', '制限時間', 'サドンデス（同時死・時間切れ）']);
    expect(texts(right!, '.note')).toEqual([
      '1ラウンド勝つと★1つ。先に取りきったら優勝',
      '🌿 葱ボンは残り1分で退場するので、1:00 にすると葱ボンなしになる',
      'ONだと、決着つかない時にソフトブロック全消し・全員MAX装備・60秒で延長',
    ]);
    // 制限時間の注記の真ん中は太字。
    expect(texts(right!, '.note b')).toEqual(['1:00 にすると葱ボンなし']);
    expect(root.querySelector('.navbar > .go')?.textContent).toBe('はじめる');
  });

  it('体力の行の箱は下に 12px、CPU の行の箱は下に 8px を空け、CPU の行の頭の札は label でなく span', () => {
    const { root } = mount();
    press(root, '[data-choice="solo"]');
    press(root, '[data-action="next"]');
    const hits = root.querySelector<HTMLElement>('[data-field="hits-p1"]');
    const cpu = root.querySelector<HTMLElement>('[data-field="cpu-0"]');
    expect(hits?.classList.contains('chips')).toBe(true);
    expect(hits?.style.marginBottom).toBe('12px');
    expect(cpu?.style.marginBottom).toBe('8px');
    // 札は span.lb（原型の CSS は label.lb にだけ当たる）。見出しの label は1つだけ。
    const tags = [...root.querySelectorAll<HTMLElement>('.cols span.lb')];
    expect(tags.map((tag) => tag.textContent)).toEqual(['CPU1', 'CPU2', 'CPU3']);
    expect(Number(tags[0]?.style.opacity)).toBe(0.8);
    expect(tags[0]?.style.marginRight).toBe('8px');
    expect(texts(root, 'label.lb').filter((text) => text?.startsWith('CPU の強さ'))).toEqual(['CPU の強さ（1体ずつ）']);
    // 札は、その行のチップの箱の直前に置く。
    expect(tags[1]?.nextElementSibling).toBe(root.querySelector('[data-field="cpu-1"]'));
    // CPU の注記は改行で2行。
    const note = root.querySelector('.cols > div:first-child > .row:nth-child(2) > .note');
    expect(note?.querySelectorAll('br')).toHaveLength(1);
    expect(note?.textContent).toBe(
      'よわい＝反応が鈍く、危険に気づかず、あまり攻めてこない。おに＝盤面の端からでも追ってくる。CPU の動物はランダムに決まる',
    );
  });

  it('CPU のいない遊び方では、CPU の強さの見出しも札も注記も出さない（箱だけ残す）', () => {
    const { root } = mount();
    press(root, '[data-choice="versus"]');
    press(root, '[data-action="next"]');
    const left = root.querySelector('.cols > div:first-child');
    expect(left?.children).toHaveLength(2);
    expect(left?.children[1]?.childElementCount).toBe(0);
    expect(root.querySelector('.cols span.lb')).toBeNull();
    expect(root.textContent).not.toContain('CPU の強さ');
  });

  it('設定の画面は、音の行・区切り・マニュアル・区切り・更新履歴の順。マニュアルはキーを kbd、太字を b、行を br で区切る', () => {
    const { root } = mount();
    press(root, '[data-choice="manual"]');
    const card = root.querySelector('[data-screen="manual"]');
    const order = [...(card?.children ?? [])].map((child) => child.className);
    expect(order).toEqual(['shead', 'row', 'msec', 'lb', 'manual hb', 'msec', 'row']);
    expect(texts(card!, ':scope > label.lb, :scope > .row > label.lb')).toEqual([
      '① 設定 ／ サウンド',
      '② マニュアル ／ そうさ・ルール',
      '③ 更新履歴',
    ]);
    expect(texts(root, '[data-field="sound"] .chip')).toEqual(['BGM + 効果音', '効果音だけ', '無音']);
    const manual = root.querySelector('.manual');
    const keys = MANUAL.flat().filter((span) => span.kind === 'key').length;
    expect(manual?.querySelectorAll('kbd')).toHaveLength(keys);
    expect(manual?.querySelectorAll('b')).toHaveLength(MANUAL.flat().filter((span) => span.kind === 'bold').length);
    // 行の間に1つずつ（空けた行は br が2つ続く）。
    expect(manual?.querySelectorAll('br')).toHaveLength(MANUAL.length - 1);
    expect(manual?.firstChild?.nodeName).toBe('B');
    expect(manual?.lastChild?.nodeName).not.toBe('BR');
    expect(manual?.querySelector('kbd')?.textContent).toBe('W');
  });

  it('更新履歴は、凡例と 49 項目。MAJOR・MINOR の版は b、PATCH は span。4.2.1 だけ PATCH なのに大きい字', () => {
    const { root } = mount();
    press(root, '[data-choice="manual"]');
    const legend = root.querySelector<HTMLElement>('.msec + .row > .note');
    expect(legend?.style.marginBottom).toBe('8px');
    expect(Number(legend?.style.opacity)).toBe(0.85);
    expect([...(legend?.children ?? [])].map((child) => `${child.tagName}.${child.className}`)).toEqual(['B.vmaj', 'B.vmin', 'SPAN.vpat']);
    expect(legend?.textContent).toBe('MAJOR＝別のゲームになった規模　 MINOR＝足した　 PATCH＝修正した・調整した');

    const entries = [...root.querySelectorAll<HTMLElement>('.log > div')];
    expect(entries).toHaveLength(CHANGELOG.length);
    expect(entries.map((entry) => entry.className)).toEqual(CHANGELOG.map((entry) => (entry.large ? 'lg' : 'lp')));
    const tag = (entry: HTMLElement | undefined): string => `${entry?.firstElementChild?.tagName}.${entry?.firstElementChild?.className}`;
    expect(tag(entries[0])).toBe('B.vmin');
    expect(entries[0]?.firstElementChild?.textContent).toBe('4.3.0');
    expect(entries[1]?.className).toBe('lg');
    expect(tag(entries[1])).toBe('SPAN.vpat');
    expect(tag(entries[4])).toBe('B.vmaj');
    expect(tag(entries[5])).toBe('SPAN.vpat');
    expect(entries[5]?.className).toBe('lp');
    // 本文の太字は b、プログラムの字は code。
    expect(texts(entries[0]!, 'b:not(.vmin)')).toEqual(['Start', 'Select']);
    expect(texts(root, '.log code')).toEqual(['undefined.timer']);
    expect(entries.at(-1)?.textContent).toBe('1.0.0 遊べる形になった（爆弾・葱ボン・アイテム・サウンド・CPU）');
  });
});

describe('画面の操作の音', () => {
  it('タイトルの項目・「つぎへ」・動物のカード・チップ・「← もどる」で鳴らし、「はじめる」では鳴らさない', () => {
    const { root, log } = mount();
    press(root, '[data-choice="solo"]');
    expect(log).toEqual(['ui']);
    press(root, '[data-animal="fox"]');
    press(root, '[data-action="next"]');
    press(root, '[data-field="wins"] [data-value="7"]');
    press(root, '[data-field="cpu-2"] [data-value="oni"]');
    press(root, '[data-field="hits-cpu"] [data-value="2"]');
    expect(log).toEqual(['ui', 'ui', 'ui', 'ui', 'ui', 'ui']);
    press(root, '[data-action="start"]');
    expect(log).toEqual(['ui', 'ui', 'ui', 'ui', 'ui', 'ui', 'start']);
    press(root, '[data-action="back"]');
    expect(log.at(-1)).toBe('ui');
  });

  it('LAN対戦と設定の項目でも鳴らす。「無音」のチップは、鳴らしてから音を切る', () => {
    const { root, log } = mount();
    press(root, '[data-choice="lan"]');
    expect(log).toEqual(['ui', 'lan']);
    press(root, '[data-choice="manual"]');
    log.length = 0;
    press(root, '[data-field="sound"] [data-value="off"]');
    expect(log).toEqual(['ui', 'sound:off']);
  });

  it('音を戻すチップは、音の設定を変えてから鳴らす（戻したあとの設定で操作の音が聞こえる。原型と同じ）', () => {
    // 効果音を切っている間は、操作の音を鳴らしても部品を作らない。先に鳴らすと、原型では聞こえる音が鳴らない。
    const { root, log } = mount();
    press(root, '[data-choice="manual"]');
    press(root, '[data-field="sound"] [data-value="off"]');
    log.length = 0;
    press(root, '[data-field="sound"] [data-value="both"]');
    expect(log).toEqual(['sound:both', 'ui']);
    press(root, '[data-field="sound"] [data-value="sfx"]');
    expect(log).toEqual(['sound:both', 'ui', 'sound:sfx', 'ui']);
    expect(root.querySelector('[data-field="sound"] .on')?.textContent).toBe('効果音だけ');
  });

  it('B で1つ前の画面へ戻ったら鳴らす。タイトルでは何もせず、鳴らさない', () => {
    const { root, view, log } = mount();
    view.back();
    expect(log).toEqual([]);
    expect(screenOf(root)).toBe('title');
    press(root, '[data-choice="duo"]');
    log.length = 0;
    view.back();
    expect(log).toEqual(['ui']);
    expect(screenOf(root)).toBe('title');
  });
});

describe('画面を替えたらページの先頭へ', () => {
  it('画面が替わったときだけ先頭へ戻し、同じ画面で選び直しただけなら動かさない（原型の showScreen）', () => {
    const scrolled = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    try {
      const { root, view } = mount();
      // 組み立てた最初の画面（タイトル）でも戻す。
      expect(scrolled).toHaveBeenCalledTimes(1);
      press(root, '[data-choice="solo"]');
      expect(scrolled).toHaveBeenCalledTimes(2);
      expect(scrolled).toHaveBeenLastCalledWith(0, 0);
      press(root, '[data-animal="frog"]');
      press(root, '[data-animal="fox"]');
      view.render();
      expect(scrolled).toHaveBeenCalledTimes(2);
      press(root, '[data-action="next"]');
      expect(scrolled).toHaveBeenCalledTimes(3);
      press(root, '[data-field="wins"] [data-value="9"]');
      expect(scrolled).toHaveBeenCalledTimes(3);
      view.back();
      expect(scrolled).toHaveBeenCalledTimes(4);
    } finally {
      scrolled.mockRestore();
    }
  });
});
