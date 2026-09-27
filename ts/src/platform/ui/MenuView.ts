import { CPU_LEVEL_KEYS, CPU_LEVELS } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS } from '../../content/animals.js';
import {
  formatSeconds,
  HIT_CHOICES,
  TIME_CHOICES,
  WIN_CHOICES,
} from '../../presentation/menu/choices.js';
import type { LocalSetup, PlayMode } from '../../presentation/menu/localSetup.js';
import type { MenuFlow, SoundSetting } from '../../presentation/menu/MenuFlow.js';
import { keyHelpFor } from '../keyHelp.js';
import { PLAYER1_KEYS, PLAYER2_KEYS, SOLO_KEYS } from '../Keyboard.js';
import { chipRow, el, pointerButton } from './dom.js';
import { describeManual } from './manual.js';

/** 画面の外へ知らせること。 */
export interface MenuHooks {
  /** 「はじめる」が押された。 */
  readonly start: (setup: LocalSetup) => void;
  /** 音の設定が変わった。 */
  readonly soundChanged: (sound: SoundSetting) => void;
  /** 通信対戦を選んだ。 */
  readonly openLan: () => void;
}

/** タイトルに並べる遊び方。 */
const MODES: readonly { readonly mode: PlayMode; readonly icon: string; readonly title: string; readonly detail: string }[] = [
  { mode: 'solo', icon: '🕹️', title: '1人 vs CPU×3', detail: 'CPU の強さは あとで1体ずつ決められる' },
  { mode: 'duo', icon: '👥', title: '2人 vs CPU×2', detail: '1台のキーボードを左右に分けて遊ぶ' },
  { mode: 'versus', icon: '⚔️', title: '2人タイマン', detail: 'CPU なし。1P と 2P だけ' },
];

const SOUNDS: readonly { readonly value: SoundSetting; readonly label: string }[] = [
  { value: 'both', label: '曲 + 効果音' },
  { value: 'sfx', label: '効果音だけ' },
  { value: 'off', label: '無音' },
];

/**
 * 試合の前の画面（タイトル・動物を選ぶ・ルールを決める・遊び方）。
 *
 * どの画面にいて何を選んだかは `MenuFlow` が持つ。ここはそれを写し、押されたら
 * `MenuFlow` を呼んで写し直すだけ。
 *
 * ⚠️ ボタンは全部 `pointerButton`（キーボードで起きたクリックを捨てる）で作る。
 * 「はじめる」を Enter や Space で押すと、爆弾のキーを押したまま試合が始まる。
 */
export class MenuView {
  readonly #root: HTMLElement;
  readonly #flow: MenuFlow;
  readonly #hooks: MenuHooks;

  constructor(root: HTMLElement, flow: MenuFlow, hooks: MenuHooks) {
    this.#root = root;
    this.#flow = flow;
    this.#hooks = hooks;
  }

  /** いまの画面を組み立て直す。 */
  render(): void {
    const screen = this.#flow.screen;
    const body = {
      title: () => this.#title(),
      pick: () => this.#pick(),
      rules: () => this.#rules(),
      manual: () => this.#manual(),
    }[screen]();
    this.#root.replaceChildren(el('div', { className: 'menu-card', data: { screen } }, body));
  }

  /** 押されたら `change` を呼んで、画面を写し直す。 */
  #act(change: () => void): () => void {
    return () => {
      change();
      this.render();
    };
  }

  #title(): HTMLElement[] {
    const item = (icon: string, title: string, detail: string, onPress: () => void, id: string): HTMLElement => {
      const button = pointerButton('', onPress, { className: 'menu-button', data: { choice: id } });
      button.append(
        el('span', { className: 'icon', text: icon }),
        el('span', {}, [el('span', { className: 'title', text: title }), el('span', { className: 'detail', text: detail })]),
      );
      return button;
    };
    return [
      el('div', { className: 'logo' }, [
        el('div', { className: 'logo-plate', text: 'Nakatando' }),
        el('div', { className: 'logo-sub', text: '🐰💣🐘 どうぶつボンバー' }),
      ]),
      el('div', { className: 'menu-list' }, [
        ...MODES.map((m) => item(m.icon, m.title, m.detail, this.#act(() => this.#flow.chooseMode(m.mode)), m.mode)),
        item('📶', '通信対戦', '同じ Wi-Fi の別の Mac と遊ぶ（最大4人）', () => this.#hooks.openLan(), 'lan'),
        item('📖', '設定・遊び方', '音の設定／そうさとルールの説明', this.#act(() => this.#flow.openManual()), 'manual'),
      ]),
    ];
  }

  #head(title: string, step?: string): HTMLElement {
    return el('div', { className: 'menu-head' }, [
      pointerButton('← もどる', this.#act(() => this.#flow.back()), { className: 'small-button', data: { action: 'back' } }),
      el('h2', { text: title }),
      step === undefined ? null : el('span', { className: 'step', text: step }),
    ]);
  }

  #pick(): HTMLElement[] {
    const { humans } = this.#flow.sizes;
    const bindings = humans === 1 ? [SOLO_KEYS] : [PLAYER1_KEYS, PLAYER2_KEYS];
    const sections = bindings.map((binding, index) => {
      const human = index as 0 | 1;
      const chosen = this.#flow.setup.picks[human];
      return el('div', { className: 'field', data: { human: String(human) } }, [
        el('span', { className: 'field-label', text: `${human + 1}P のどうぶつ` }),
        el('div', { className: 'note', text: keyHelpFor('', binding).lines[0] ?? '' }),
        el(
          'div',
          { className: 'animals' },
          ANIMAL_LOOKS.map((look) => {
            const card = pointerButton('', this.#act(() => this.#flow.pick(human, look.key)), {
              className: `animal${look.key === chosen ? ' on' : ''}`,
              data: { animal: look.key },
            });
            card.append(
              el('span', { className: 'emoji', text: look.emoji }),
              el('span', {}, [
                el('div', { className: 'name', text: look.name }),
                el('div', { className: 'description', text: look.description }),
              ]),
            );
            return card;
          }),
        ),
      ]);
    });
    return [
      this.#head('キャラをえらぶ', 'STEP 1 / 2'),
      ...sections,
      pointerButton('つぎへ ▶', this.#act(() => this.#flow.next()), { className: 'go', data: { action: 'next' } }),
    ];
  }

  #rules(): HTMLElement[] {
    const { humans, cpus } = this.#flow.sizes;
    const setup = this.#flow.setup;
    const hitsRows: HTMLElement[] = [
      this.#chips('1P が倒れるまでの爆風の回数', 'hits-p1', HIT_CHOICES, setup.hits.p1, (n) => `${n}回`, (n) =>
        this.#flow.setHits('p1', n),
      ),
    ];
    if (humans > 1) {
      hitsRows.push(
        this.#chips('2P が倒れるまでの爆風の回数', 'hits-p2', HIT_CHOICES, setup.hits.p2, (n) => `${n}回`, (n) =>
          this.#flow.setHits('p2', n),
        ),
      );
    }
    if (cpus > 0) {
      hitsRows.push(
        this.#chips('CPU が倒れるまでの爆風の回数', 'hits-cpu', HIT_CHOICES, setup.hits.cpu, (n) => `${n}回`, (n) =>
          this.#flow.setHits('cpu', n),
        ),
      );
    }
    const cpuRows = setup.cpuLevels.slice(0, cpus).map((level, index) =>
      this.#chips(`CPU${index + 1} の強さ`, `cpu-${index}`, CPU_LEVEL_KEYS, level, (key) => CPU_LEVELS[key].label, (key) =>
        this.#flow.setCpuLevel(index as 0 | 1 | 2, key),
      ),
    );
    return [
      this.#head('ルールをきめる', 'STEP 2 / 2'),
      ...hitsRows,
      el('div', { className: 'note', text: 'ハンデをつけたいときに使う。🐘ぞうは始まりの体力が1回ぶん多い' }),
      ...cpuRows,
      ...(cpus > 0 ? [el('div', { className: 'note', text: 'CPU の動物は、選ばれなかった動物から決まる' })] : []),
      this.#chips('何勝で優勝', 'wins', WIN_CHOICES, setup.winsToTake, (n) => `${n}勝`, (n) => this.#flow.setWinsToTake(n)),
      this.#chips('制限時間', 'time', TIME_CHOICES, setup.roundSeconds, formatSeconds, (n) => this.#flow.setRoundSeconds(n)),
      el('div', { className: 'note', text: '🌿 葱ボンは残り1分で退場するので、1:00 にすると葱ボンなしになる' }),
      this.#chips('サドンデス（同時に倒れた・時間切れ）', 'sudden', [true, false], setup.suddenDeath, (on) => (on ? 'ON' : 'OFF'), (on) =>
        this.#flow.setSuddenDeath(on),
      ),
      pointerButton('はじめる', () => this.#hooks.start(this.#flow.setup), { className: 'go', data: { action: 'start' } }),
    ];
  }

  #manual(): HTMLElement[] {
    return [
      this.#head('設定・遊び方'),
      this.#chips('音', 'sound', SOUNDS.map((s) => s.value), this.#flow.sound, (value) =>
        SOUNDS.find((s) => s.value === value)?.label ?? value, (value) => {
        this.#flow.setSound(value);
        this.#hooks.soundChanged(value);
      }),
      el(
        'div',
        { className: 'manual' },
        describeManual().flatMap((section) => [
          el('h3', { text: section.title }),
          ...section.lines.map((line) => el('p', { text: line })),
        ]),
      ),
    ];
  }

  /** 選ぶ行。選んだら写し直す。 */
  #chips<T>(
    label: string,
    id: string,
    choices: readonly T[],
    current: T,
    text: (value: T) => string,
    choose: (value: T) => void,
  ): HTMLElement {
    return chipRow(label, id, choices, current, text, (value) => {
      choose(value);
      this.render();
    });
  }
}
