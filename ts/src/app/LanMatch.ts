import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuIntentSource, cpuSeed } from '../ai/CpuIntentSource.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { LockstepClient } from '../net/LockstepClient.js';
import { REFUSED_CLOSE_CODE, type LanSettings } from '../net/protocol.js';
import { KeyboardIntentSource, SOLO_KEYS, type KeyStateReader } from '../platform/Keyboard.js';
import { lockstepUrl, WebSocketLink } from '../platform/WebSocketLink.js';
import { describeLanPhase } from '../presentation/hud/lanStatus.js';
import { GameSession } from './GameSession.js';
import type { MatchRunner } from './MatchRunner.js';

export interface LanMatchOptions {
  /** 中継サーバの「ホスト名:ポート」（`parseRelayAddress` で確かめたもの）。 */
  readonly address: string;
  /** ホストとして始めるときに配る設定。ゲストの設定は使われない（ホストのものに揃う）。 */
  readonly settings: LanSettings;
  readonly keyboard: KeyStateReader;
  /** 接続の様子を出す場所。 */
  readonly status: HTMLElement;
  /** ホストが試合を始めるボタン。 */
  readonly startButton: HTMLButtonElement;
}

/**
 * 通信対戦の試合。配線だけを行う。
 *
 * 流れは `LockstepClient`、進め方は `LockstepDriver` が持っている。
 * ここでは、それぞれに WebSocket・キーボード・CPU の作り方を渡し、
 * 接続の様子を画面に出す。
 *
 * ⚠️ 始める合図はキーではなく、ボタンのクリックで送る。爆弾のキー（Enter や Space）で始めると、
 * 押したまま試合が始まり、最初の tick で開始位置に爆弾を置いてしまう。ボタンにキーボードで
 * フォーカスして Enter を押した場合も同じなので、キーボードで起きたクリックは受け付けない。
 */
export class LanMatch implements MatchRunner {
  readonly #client: LockstepClient;
  readonly #status: HTMLElement;
  readonly #startButton: HTMLButtonElement;
  #shown: string | null = null;

  constructor(options: LanMatchOptions) {
    const link = new WebSocketLink(lockstepUrl(options.address), {
      onMessage: (text) => this.#client.receive(text),
      onClose: (code) => {
        if (code === REFUSED_CLOSE_CODE) {
          this.#client.disconnected('前の試合が続いているか、定員いっぱいで入れなかった');
        } else {
          this.#client.disconnected();
        }
      },
    });
    this.#client = new LockstepClient(link, {
      createSession: (settings) => new GameSession(settings.match),
      // 1台に1人なので、キーボード全体（WASD と矢印の両方）を1人が使う。
      localSource: (playerId) => new KeyboardIntentSource(playerId, options.keyboard, SOLO_KEYS),
      // 種は試合の設定から作る。全員の端末で同じ CPU が同じ手を指す。
      cpuSource: (playerId, settings) =>
        new CpuIntentSource(playerId, CPU_LEVELS[settings.cpu], cpuSeed(settings.match.seed, playerId)),
    });
    this.#status = options.status;
    this.#startButton = options.startButton;
    this.#status.hidden = false;
    this.#startButton.addEventListener('click', (event: MouseEvent) => {
      // キーボード（Enter・Space）で起きたクリックは detail が 0 になる。
      if (event.detail === 0) return;
      this.#client.requestStart(options.settings);
    });
  }

  get world(): WorldState | null {
    const phase = this.#client.phase;
    return phase.kind === 'playing' ? phase.session.world : null;
  }

  get inProgress(): boolean {
    const phase = this.#client.phase;
    return phase.kind === 'playing' && phase.driver.desync === null && !phase.session.match.finished;
  }

  get ready(): boolean {
    return this.#client.ready;
  }

  step(): SimEvent[] {
    return this.#client.step() ?? [];
  }

  afterDraw(): void {
    const phase = this.#client.phase;
    const text = describeLanPhase(phase);
    // 毎回書き換えない。同じ文を書き直すだけでも、ブラウザは組み直しの手間をかける。
    if (text !== this.#shown) {
      this.#status.textContent = text;
      this.#shown = text;
    }
    this.#startButton.hidden = !(phase.kind === 'lobby' && phase.seat === 0);
  }
}
