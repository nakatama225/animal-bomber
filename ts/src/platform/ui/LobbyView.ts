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
  | {
      readonly kind: 'lobby';
      readonly seat: PlayerId;
      readonly present: readonly PlayerId[];
      /** ホストが選んでいる設定（ゲストの画面に出す）。まだ届いていなければ無い。 */
      readonly hostSettings?: LanSetup;
    }
  | { readonly kind: 'failed'; readonly reason: string };

export interface LobbyHooks {
  /** ホストが「はじめる」を押した。 */
  readonly start: (setup: LanSetup) => void;
  /** ホストが選び直した。始まる前のゲストの画面へ配るのに使う。 */
  readonly changed: (setup: LanSetup) => void;
  /** 「ぬける」を押した。 */
  readonly leave: () => void;
}

/**
 * 通信対戦のロビー。
 *
 * ホスト（1P）は4つの枠それぞれの動物・体力・CPU の強さと、ルールを決める。選び直すたびに
 * `changed` で知らせ、始まる前のゲストの画面へ配る（原型と同じ）。ゲストには、ホストが選んでいる
 * ものを読むだけの表で出す。試合は、ホストが「はじめる」を押した時点の設定から作る。
 *
 * キーボードとパッドでも動かせる（選択肢の行と「はじめる」に `data-nav`。選択肢の行は `chipRow` が付ける）。
 * 枠ごとの行は、その枠の動物・CPU の強さ・体力の順に並ぶ（原型と同じ。原型は体力を「その枠のキャラ・
 * CPU 強さの直下」に置いていた）。カーソルは画面の並びの順に集めるので、上下で辿る順もこの順になる。
 * 原型は CPU の枠にだけ CPU の強さを出したが、この版は人間の枠にも出す（抜けたときに CPU が受け持つ強さ）。
 * ゲストには動かすものが無い（読むだけの表はカーソルに載せない）。
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
      el('div', { className: 'card', data: { screen: 'lobby' } }, [
        el('div', { className: 'shead' }, [
          pointerButton('← ぬける', () => this.#hooks.leave(), { className: 'backb', data: { action: 'leave' } }),
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
        return state.seat === 0 ? this.#host(state.present) : this.#guest(state.seat, state.present, state.hostSettings);
    }
  }

  #guest(seat: PlayerId, present: readonly PlayerId[], shared: LanSetup | undefined): HTMLElement[] {
    return [
      el('p', { text: `あなたは ${seat + 1}P。つながっている人：${present.map((id) => `${id + 1}P`).join('・')}` }),
      el('p', { className: 'note', text: '動物とルールは 1P（ホスト）が決める。1P が「はじめる」を押すのを待っている' }),
      ...(shared === undefined
        ? [el('p', { className: 'note', text: '1P（ホスト）の設定を待っている…' })]
        : this.#sharedTable(seat, present, shared)),
    ];
  }

  /**
   * ホストが選んでいるものを、読むだけの表で出す。並びはホストの画面と同じ（動物・CPU の強さ・体力）。
   *
   * ⚠️ 選ぶボタンにしない。ゲストが押しても試合には使われないので、押せる形にすると、選んだのに
   * 反映されない、という体験になる。カーソル（`data-nav`）にも載せない。
   */
  #sharedTable(seat: PlayerId, present: readonly PlayerId[], setup: LanSetup): HTMLElement[] {
    const line = (label: string, id: string, value: string): HTMLElement =>
      el('div', { className: 'row', data: { sharedField: id } }, [
        el('label', { className: 'lb', text: label }),
        el('span', { text: value }),
      ]);
    const slots = PLAYER_IDS.map((slot) => {
      const look = lookOf(setup.animals[slot]);
      const who = `${slot + 1}P${slot === seat ? '（あなた）' : ''}${slot === 0 ? '（ホスト）' : ''}`;
      const connected = present.includes(slot) ? '🟢 つながっている' : '⚪ 空き（CPU）';
      return el('div', { className: 'slot', data: { sharedSlot: String(slot) } }, [
        el('div', { className: 'slot-head', text: `${look.emoji} ${who} ${connected}` }),
        line('どうぶつ', `animal-${slot}`, `${look.emoji}${look.name}`),
        line(
          slot === 0 ? 'CPU の強さ（抜けたとき）' : 'CPU の強さ（空いているとき・抜けたとき）',
          `cpu-${slot}`,
          CPU_LEVELS[setup.cpuLevels[slot]].label,
        ),
        line('倒れるまでの爆風の回数', `hits-${slot}`, `${setup.hits[slot]}回`),
      ]);
    });
    return [
      ...slots,
      el('div', { className: 'slot', data: { sharedRules: '' } }, [
        line('何勝で優勝', 'wins', `${setup.winsToTake}勝`),
        line('制限時間', 'time', formatSeconds(setup.roundSeconds)),
        line('サドンデス', 'sudden', setup.suddenDeath ? 'ON' : 'OFF'),
      ]),
    ];
  }

  /** 選ぶ行。選んだら写し直す。 */
  #row<T>(label: string, id: string, choices: readonly T[], current: T, text: (value: T) => string, choose: (value: T) => void): HTMLElement {
    return chipRow(label, id, choices, current, text, (value) => {
      choose(value);
      this.#hooks.changed(this.#choices.setup);
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
        this.#row(
          slot === 0 ? 'CPU の強さ（抜けたとき）' : 'CPU の強さ（空いているとき・抜けたとき）',
          `cpu-${slot}`,
          CPU_LEVEL_KEYS,
          setup.cpuLevels[slot],
          (key) => CPU_LEVELS[key].label,
          (key) => this.#choices.setCpuLevel(slot, key),
        ),
        this.#row('倒れるまでの爆風の回数', `hits-${slot}`, HIT_CHOICES, setup.hits[slot], (n) => `${n}回`, (n) =>
          this.#choices.setHits(slot, n)),
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
