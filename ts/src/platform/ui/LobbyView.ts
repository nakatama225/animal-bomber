import { CPU_LEVEL_KEYS, CPU_LEVELS } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS, lookOf } from '../../content/animals.js';
import { PLAYER_IDS, type PlayerId } from '../../domain/state/PlayerState.js';
import { START_OVER } from '../../presentation/hud/lanStatus.js';
import { formatSeconds, HIT_CHOICES, TIME_CHOICES, WIN_CHOICES } from '../../presentation/menu/choices.js';
import type { LanSetup, LobbyChoices } from '../../presentation/menu/lanSetup.js';
import { chipRow, el, pointerButton } from './dom.js';

/** ロビーの様子。`LockstepClient` の段階から、画面に要るものだけを抜き出したもの。 */
export type LobbyState =
  | { readonly kind: 'connecting' }
  | { readonly kind: 'lobby'; readonly seat: PlayerId; readonly present: readonly PlayerId[] }
  | { readonly kind: 'failed'; readonly reason: string };

export interface LobbyHooks {
  /** ホストが「はじめる」を押した。 */
  readonly start: (setup: LanSetup) => void;
  /** 「ぬける」を押した。 */
  readonly leave: () => void;
}

/**
 * 通信対戦のロビー。
 *
 * ホスト（1P）は4つの枠それぞれの動物・体力・CPU の強さと、ルールを決める。
 * ゲストはホストが決めるのを待つ。決めた内容は、試合が始まるときに全員へ配られる
 * （始まる前のゲストの画面には出ない。出すには中継に新しい種類のメッセージが要る）。
 *
 * キーボードとパッドでも動かせる（選択肢の行と「はじめる」に `data-nav`。選択肢の行は `chipRow` が付ける）。
 * 枠ごとの行は、その枠の動物・体力・CPU の強さの順に並ぶ（原型と同じ）。ゲストには動かすものが無い。
 */
export class LobbyView {
  readonly #root: HTMLElement;
  readonly #choices: LobbyChoices;
  readonly #hooks: LobbyHooks;
  #state: LobbyState = { kind: 'connecting' };

  constructor(root: HTMLElement, choices: LobbyChoices, hooks: LobbyHooks) {
    this.#root = root;
    this.#choices = choices;
    this.#hooks = hooks;
  }

  /** ロビーの様子を写す。前と同じなら何もしない（誰かの出入りのたびにだけ組み直す）。 */
  show(state: LobbyState): void {
    if (JSON.stringify(state) === JSON.stringify(this.#state) && this.#root.childElementCount > 0) return;
    this.#state = state;
    this.render();
  }

  render(): void {
    const state = this.#state;
    this.#root.replaceChildren(
      el('div', { className: 'menu-card', data: { screen: 'lobby' } }, [
        el('div', { className: 'menu-head' }, [
          pointerButton('← ぬける', () => this.#hooks.leave(), { className: 'small-button', data: { action: 'leave' } }),
          el('h2', { text: '通信対戦のロビー' }),
        ]),
        ...this.#body(state),
      ]),
    );
  }

  #body(state: LobbyState): HTMLElement[] {
    switch (state.kind) {
      case 'connecting':
        return [el('p', { className: 'note', text: '中継サーバにつないでいる…' })];
      case 'failed':
        return [
          el('p', { text: state.reason }),
          el('p', { className: 'note', text: START_OVER }),
        ];
      case 'lobby':
        return state.seat === 0 ? this.#host(state.present) : this.#guest(state.seat, state.present);
    }
  }

  #guest(seat: PlayerId, present: readonly PlayerId[]): HTMLElement[] {
    return [
      el('p', { text: `あなたは ${seat + 1}P。つながっている人：${present.map((id) => `${id + 1}P`).join('・')}` }),
      el('p', { className: 'note', text: '動物とルールは 1P（ホスト）が決める。1P が「はじめる」を押すのを待っている' }),
    ];
  }

  /** 選ぶ行。選んだら写し直す。 */
  #row<T>(label: string, id: string, choices: readonly T[], current: T, text: (value: T) => string, choose: (value: T) => void): HTMLElement {
    return chipRow(label, id, choices, current, text, (value) => {
      choose(value);
      this.render();
    });
  }

  #host(present: readonly PlayerId[]): HTMLElement[] {
    const setup = this.#choices.setup;
    const slots = PLAYER_IDS.map((slot) => {
      const connected = present.includes(slot);
      const who = slot === 0 ? '1P（あなた）' : connected ? `${slot + 1}P 🟢 つながっている` : `${slot + 1}P ⚪ 空き（CPU）`;
      return el('div', { className: 'slot', data: { slot: String(slot) } }, [
        el('div', { className: 'slot-head', text: `${lookOf(setup.animals[slot]).emoji} ${who}` }),
        this.#row('どうぶつ', `animal-${slot}`, ANIMAL_LOOKS.map((look) => look.key), setup.animals[slot], (key) =>
          `${lookOf(key).emoji}${lookOf(key).name}`, (key) => this.#choices.setAnimal(slot, key)),
        this.#row('倒れるまでの爆風の回数', `hits-${slot}`, HIT_CHOICES, setup.hits[slot], (n) => `${n}回`, (n) =>
          this.#choices.setHits(slot, n)),
        this.#row(
          slot === 0 ? 'CPU の強さ（抜けたとき）' : 'CPU の強さ（空いているとき・抜けたとき）',
          `cpu-${slot}`,
          CPU_LEVEL_KEYS,
          setup.cpuLevels[slot],
          (key) => CPU_LEVELS[key].label,
          (key) => this.#choices.setCpuLevel(slot, key),
        ),
      ]);
    });
    return [
      el('p', { className: 'note', text: '始まった時点でつながっていない枠は CPU が受け持つ。途中で抜けた人も CPU に替わる' }),
      ...slots,
      el('div', { className: 'slot' }, [
        this.#row('何勝で優勝', 'wins', WIN_CHOICES, setup.winsToTake, (n) => `${n}勝`, (n) => this.#choices.setWinsToTake(n)),
        this.#row('制限時間', 'time', TIME_CHOICES, setup.roundSeconds, formatSeconds, (n) => this.#choices.setRoundSeconds(n)),
        this.#row('サドンデス', 'sudden', [true, false], setup.suddenDeath, (on) => (on ? 'ON' : 'OFF'), (on) =>
          this.#choices.setSuddenDeath(on)),
      ]),
      pointerButton('はじめる', () => this.#hooks.start(this.#choices.setup), { className: 'go', data: { action: 'start', nav: 'go' } }),
    ];
  }
}
