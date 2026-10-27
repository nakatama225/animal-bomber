import { CPU_LEVEL_KEYS, CPU_LEVELS } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS } from '../../content/animals.js';
import { PLAYER_IDS, type PlayerId } from '../../domain/state/PlayerState.js';
import { formatSeconds, HIT_CHOICES, TIME_CHOICES, WIN_CHOICES } from '../../presentation/menu/choices.js';
import { DEFAULT_LAN_SETUP, type LanSetup, type LobbyChoices } from '../../presentation/menu/lanSetup.js';
import {
  CONNECTED,
  DISCONNECT_LABEL,
  hitsLabel,
  LOBBY_HEADING,
  LOBBY_HITS_LABEL,
  LOBBY_START,
  LOBBY_SUDDEN_LABEL,
  LOBBY_TIME_LABEL,
  LOBBY_WAIT,
  LOBBY_WINS_LABEL,
  lobbyMe,
  lobbySharedLine,
  lobbySharedRules,
  lobbySlotName,
  onOff,
  VACANT,
  winsLabel,
} from '../../presentation/menu/menuText.js';
import { chipBox, el, pointerButton, scrollToTop } from './dom.js';

/** ロビーの様子。`LockstepClient` のロビーの段階から、画面に要るものだけを抜き出したもの。 */
export interface LobbyState {
  /** この端末の番号。0（1P）ならホスト。 */
  readonly seat: PlayerId;
  /** つながっている端末（自分を含む）。 */
  readonly present: readonly PlayerId[];
  /** ホストが選んでいる設定（ゲストの画面に出す）。まだ届いていなければ無い。 */
  readonly hostSettings?: LanSetup;
}

export interface LobbyHooks {
  /** ホストが「はじめる ▶」を押した。 */
  readonly start: (setup: LanSetup) => void;
  /** ホストが選び直した。始まる前のゲストの画面へ配るのに使う。 */
  readonly changed: (setup: LanSetup) => void;
  /** 「← せつぞくを切る」を押した（切るかの確認の画面を出す）。 */
  readonly disconnect: () => void;
  /** 画面の操作の音を鳴らす。 */
  readonly uiSound: () => void;
  /** 初めてロビーを写した（原型の `showScreen('lobby')`。確認の画面を畳むのに使う）。 */
  readonly entered: () => void;
}

/** ロビーのチップの箱に、原型が直に付けた下の空き（原型の `box.style.marginBottom='10px'`。L5855・L5871・L5904）。 */
const CHIPS_STYLE = 'margin-bottom:10px';

/**
 * 通信対戦のロビー（原型 L285-297・`buildLobby` L5800-5935。文と並びは Python 版の `lobby_view`）。
 *
 * 冒頭に「あなたは 1P（ホスト）」、枠ごとに見出し（番号とつながっているか）、最後にルール、下に「はじめる ▶」か
 * 待ちの文を並べる。要素とクラス名は原型と同じ（`.pickhdr`・`.animals > .acard`・`label.lb`・`.chips`・`.note`・`.navbar`）。
 *
 * - ホスト（1P）は、4つの枠それぞれの動物・CPU の強さ・体力と、ルールを選ぶ。選び直すたびに `changed` で知らせ、
 *   始まる前のゲストの画面へ配る（原型と同じ）。試合は、ホストが「はじめる ▶」を押した時点の設定から作る
 * - CPU の強さの行は、いまつながっていない枠（始めたら CPU になる枠）にだけ出す（Python 版と同じ。原型は人間の人数を
 *   選び、CPU の枠にだけ出した。この版は人間の人数を選ばない）。人間の枠の CPU の強さ（途中で抜けたときに受け持つ CPU の
 *   強さ）は、その枠がつながる前に選んだもののまま
 * - ゲストには、ホストが選んでいるものを読むだけの1行ずつで出す（ホストの設定が届くまでは既定の値。原型と同じ）。
 *   ⚠️ 選ぶボタンにしない。ゲストが押しても試合には使われないので、押せる形にすると、選んだのに反映されない、という
 *   体験になる。カーソル（`data-nav`）にも載せないので、ゲストのカーソルは何も指さない（原型と同じ）
 *
 * 枠ごとの行は、その枠の動物・CPU の強さ・体力の順（原型と同じ）。カーソルは画面の並びの順に集めるので、上下で辿る順も
 * この順になる。
 *
 * 画面の操作の音は原型と同じ所で鳴らす：チップ全部（原型の `chips`。L5642）・「← せつぞくを切る」・「はじめる ▶」
 * （原型の `on()`。L5746-5747）。動物のカードは鳴らさない（原型 L5843。キャラ選びのカードと違うのも原型のまま）。
 */
export class LobbyView {
  readonly #root: HTMLElement;
  readonly #choices: LobbyChoices;
  readonly #hooks: LobbyHooks;
  /** 最後に写した様子。まだ写していなければ null。 */
  #state: LobbyState | null = null;

  constructor(root: HTMLElement, choices: LobbyChoices, hooks: LobbyHooks) {
    this.#root = root;
    this.#choices = choices;
    this.#hooks = hooks;
  }

  /**
   * ロビーの様子を写す。前と同じなら何もしない（誰かの出入りのたびにだけ組み直す。押そうとしたボタンが消えない）。
   *
   * 初めて写したときは、ページの先頭へ戻し、外へ知らせる（原型の `showScreen('lobby')`）。
   */
  show(state: LobbyState): void {
    const first = this.#state === null;
    if (!first && JSON.stringify(state) === JSON.stringify(this.#state)) return;
    this.#state = state;
    this.render();
    if (!first) return;
    scrollToTop(this.#root);
    this.#hooks.entered();
  }

  render(): void {
    const state = this.#state;
    if (state === null) return;
    const host = state.seat === 0;
    this.#root.replaceChildren(
      el('div', { className: 'card', data: { screen: 'lobby' } }, [
        el('div', { className: 'shead' }, [
          pointerButton(DISCONNECT_LABEL, this.#sounded(() => this.#hooks.disconnect()), {
            className: 'backb',
            data: { action: 'leave' },
          }),
          el('h2', { text: LOBBY_HEADING }),
        ]),
        el('div', {}, [
          el('div', { className: 'note', text: lobbyMe(state.seat) }),
          ...(host ? this.#host(state) : this.#guest(state)),
        ]),
        el(
          'div',
          { className: 'navbar' },
          host
            ? [
                pointerButton(LOBBY_START, this.#sounded(() => this.#hooks.start(this.#choices.setup)), {
                  className: 'go',
                  data: { action: 'start', nav: 'go' },
                }),
              ]
            : [el('div', { className: 'note' }, [document.createTextNode(LOBBY_WAIT[0]), el('br'), document.createTextNode(LOBBY_WAIT[1])])],
        ),
      ]),
    );
  }

  /** 枠の見出し（原型の `.pickhdr`：番号と、つながっているか）。 */
  #slotHead(slot: PlayerId, state: LobbyState): HTMLElement {
    return el('div', { className: 'pickhdr', data: { slot: String(slot) } }, [
      el('span', { className: 'who', text: lobbySlotName(slot, state.seat) }),
      el('span', { className: 'keys', text: state.present.includes(slot) ? CONNECTED : VACANT }),
    ]);
  }

  #host(state: LobbyState): HTMLElement[] {
    const setup = this.#choices.setup;
    const slots = PLAYER_IDS.flatMap((slot) => {
      const connected = state.present.includes(slot);
      return [
        this.#slotHead(slot, state),
        el(
          'div',
          { className: 'animals', data: { field: `animal-${slot}` } },
          ANIMAL_LOOKS.map((look) => {
            // 動物のカードは操作の音を鳴らさない（原型 L5843）。説明も出さない（絵文字と名前だけ。原型 L5842）。
            const card = pointerButton('', () => this.#choose(() => this.#choices.setAnimal(slot, look.key)), {
              className: setup.animals[slot] === look.key ? 'acard on' : 'acard',
              data: { value: look.key, nav: `animal-${slot}` },
            });
            card.append(el('div', { className: 'ae', text: look.emoji }), el('div', { className: 'an', text: look.name }));
            return card;
          }),
        ),
        connected
          ? null
          : this.#chips(`cpu-${slot}`, CPU_LEVEL_KEYS, setup.cpuLevels[slot], (key) => CPU_LEVELS[key].label, (key) =>
              this.#choices.setCpuLevel(slot, key),
            ),
        el('label', { className: 'lb', text: LOBBY_HITS_LABEL }),
        this.#chips(`hits-${slot}`, HIT_CHOICES, setup.hits[slot], hitsLabel, (n) => this.#choices.setHits(slot, n)),
      ].filter((node): node is HTMLElement => node !== null);
    });
    return [
      ...slots,
      el('label', { className: 'lb', text: LOBBY_WINS_LABEL }),
      this.#chips('wins', WIN_CHOICES, setup.winsToTake, winsLabel, (n) => this.#choices.setWinsToTake(n)),
      el('label', { className: 'lb', text: LOBBY_TIME_LABEL }),
      this.#chips('time', TIME_CHOICES, setup.roundSeconds, formatSeconds, (n) => this.#choices.setRoundSeconds(n)),
      el('label', { className: 'lb', text: LOBBY_SUDDEN_LABEL }),
      this.#chips('sudden', [true, false], setup.suddenDeath, onOff, (on) => this.#choices.setSuddenDeath(on)),
    ];
  }

  /** ゲストの、読むだけの行（枠ごとに1行と、ルールの1行）。ホストの設定が届くまでは既定の値を出す（原型と同じ）。 */
  #guest(state: LobbyState): HTMLElement[] {
    const setup = state.hostSettings ?? DEFAULT_LAN_SETUP;
    return [
      ...PLAYER_IDS.flatMap((slot) => [
        this.#slotHead(slot, state),
        el('div', { className: 'note', data: { sharedSlot: String(slot) }, text: lobbySharedLine(setup, slot, state.present.includes(slot)) }),
      ]),
      el('div', { className: 'note', data: { sharedRules: '' }, text: lobbySharedRules(setup) }),
    ];
  }

  /** ロビーのチップの箱。押されたら操作の音を鳴らしてから選ぶ（原型 L5642 と同じ順）。 */
  #chips<T>(id: string, choices: readonly T[], current: T, text: (value: T) => string, choose: (value: T) => void): HTMLElement {
    return chipBox(id, choices, current, text, (value) => this.#sounded(() => this.#choose(() => choose(value)))(), CHIPS_STYLE);
  }

  /** 選び直したら、ゲストの画面へ配るために知らせ、写し直す。 */
  #choose(change: () => void): void {
    change();
    this.#hooks.changed(this.#choices.setup);
    this.render();
  }

  /** 操作の音を鳴らしてから `action` を呼ぶ関数を返す。 */
  #sounded(action: () => void): () => void {
    return () => {
      this.#hooks.uiSound();
      action();
    };
  }
}
