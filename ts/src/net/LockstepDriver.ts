import type { InputSource } from '../domain/input/InputSource.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import { IDLE_INPUT, packInput, unpackInput, type PlayerInput } from '../domain/input/PlayerInput.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { hashWorld, type WorldState } from '../domain/state/WorldState.js';
import { ConfirmedInputs, NetworkInputSource } from './ConfirmedInputs.js';
import type { InputLog, MatchClock } from './InputLog.js';
import type { HashReport, PeerLink, RelayMessage } from './protocol.js';

/**
 * 自分の入力を何 tick 遅らせて使うか。
 *
 * tick T に押した操作は、全員の手元で tick T+3 に反映される。3 tick（50ms）あれば、
 * 同じ LAN の往復（1〜3ms）に中継での転送を足しても、相手の入力は使う前に届く。
 * 届くのを待って止まることがほぼ無い。
 *
 * これより短いと相手の入力が間に合わずに止まり、長いと押してから動くまでが
 * 遅れて感じられる。
 */
export const INPUT_DELAY = 3;

/**
 * 何 tick ごとに状態の要約を突き合わせるか。
 *
 * ずれは起きた瞬間には見えず、数十秒たってから「相手の画面では当たっているのに」
 * という形で現れる。20 tick（1/3 秒）ごとに比べれば、ずれた場所をその範囲まで絞れる。
 */
export const HASH_INTERVAL = 20;

/**
 * ロックステップで進める試合。`GameSession` がこの形を持つ。
 *
 * 通信の層は `app/` を読めないので、使う部分だけをここで形として決めている。
 */
export interface LockstepSession extends MatchClock {
  readonly world: WorldState;
  readonly match: { readonly finished: boolean };
  readonly tick: () => SimEvent[];
  readonly attach: (source: InputSource) => unknown;
}

/** 中継が知らせてきた、状態のずれ。 */
export interface Desync {
  readonly tick: number;
  readonly reports: readonly HashReport[];
}

export interface LockstepOptions {
  readonly session: LockstepSession;
  readonly link: PeerLink;
  /** この端末で操作するプレイヤー。 */
  readonly localId: PlayerId;
  /** この端末の操作（キーボードなど）。 */
  readonly local: InputSource;
  /** 人間が操作するプレイヤー。自分を含む。試合を始めた時点で中継が決めたもの。 */
  readonly humans: readonly PlayerId[];
  /** 抜けた人を受け持つ窓口を作る。全員の端末で同じものを返すこと（CPU など）。 */
  readonly replacement: (playerId: PlayerId) => InputSource;
  /**
   * この試合の番号（中継が `start` に付けたもの）。送る入力と要約に付け、番号の違う入力は捨てる。
   *
   * 同じ接続で次の試合を始めると、前の試合の入力が遅れて届くことがある。受け取ると
   * 「tick が飛んだ」として止まる。
   */
  readonly match: number;
}

/**
 * ロックステップで試合を進める。
 *
 * ## やり方
 *
 * 全員が同じ試合を手元で進める。送り合うのは1 tick ぶんの入力だけで、盤面は送らない。
 * 同じ種・同じ入力なら全員の手元で同じ試合になる（段階1で作ったリプレイと同じ理屈）。
 *
 * 1. tick T を進める前に、人間全員の tick T の入力が届いているかを見る。
 *    1人でも届いていなければ、進めずに待つ
 * 2. 届いていれば、自分の操作を読んで **tick T+3 の入力**として送る
 * 3. 全員の tick T の入力で試合を1 tick 進める
 * 4. 20 tick ごとに、状態の要約を中継へ送る。中継が全員ぶんを突き合わせる
 *
 * ## 窓口を差し替えるだけで済む
 *
 * 試合の側（`GameSession` と `Simulation`）には、このクラスのための分岐が1つも無い。
 * 人間のプレイヤーに繋ぐ窓口を、キーボードから `NetworkInputSource` に替えただけ。
 * そうできるのは、段階1で操作の出どころを窓口1つに絞っておいたため。
 *
 * ## 抜けた人
 *
 * 中継が知らせた `lastTick` までは届いた入力で進め、その次の tick から
 * `replacement` の窓口（CPU）に替える。全員の端末で同じ tick に替わる。
 * 抜けた人と `lastTick` は、届いた入力の記録（`log`）に書く。記録を1台で再生するときも、
 * 同じ tick で CPU に替えられる。
 *
 * ## 試合が終わったあとも、入力と要約の交換を続ける
 *
 * 試合が終わった端末は盤面を進めないが、tick を数え、何も押していない入力と要約を送り続ける。
 * やめると、試合を決めたラウンドの決着が端末ごとに食い違ったとき（ずれの不具合があるとき）に
 * 気づけない。終わった端末が要約を送らなくなるので、中継の突き合わせが揃わず、
 * 終わっていない端末は入力を待って止まるか、違う勝者を出したまま全員が終わる。
 * 続けていれば、止まった盤面の要約が食い違って、次の突き合わせでずれが分かる。
 */
export class LockstepDriver implements MatchClock {
  readonly #options: LockstepOptions;
  /** 届いた入力と、抜けた人の記録。抜けた人は、ここだけに持つ。 */
  readonly #inputs = new ConfirmedInputs();
  readonly #replaced = new Set<PlayerId>();
  #desync: Desync | null = null;
  #started = false;
  /** 進め終えた tick の数。試合が終わったあとも数え続ける。 */
  #tick = 0;

  /**
   * 人間のプレイヤー全員に、通信で届いた入力を渡す窓口を繋ぐ。
   *
   * @throws Error 試合がもう進んでいるとき、自分が人間の一覧にいないとき
   */
  constructor(options: LockstepOptions) {
    if (options.session.elapsed !== 0) {
      throw new Error('ロックステップは試合の最初から進める必要がある');
    }
    if (!options.humans.includes(options.localId)) {
      throw new Error(`自分（プレイヤー ${options.localId}）が人間の一覧にいない`);
    }
    if (options.local.playerId !== options.localId) {
      throw new Error('自分の操作の窓口が、別のプレイヤーのものになっている');
    }
    this.#options = options;
    for (const playerId of options.humans) {
      options.session.attach(new NetworkInputSource(playerId, this.#inputs, this));
    }
  }

  /**
   * 進め終えた tick の数。進めている最中は、その tick の番号。
   *
   * 試合が終わるまでは `GameSession.elapsed` と同じ値になる。
   */
  get elapsed(): number {
    return this.#tick;
  }

  /** 次の tick を進められるか（始まっていて、ずれておらず、人間全員の入力が届いている）。 */
  get ready(): boolean {
    return this.#started && this.#desync === null && this.waitingFor().length === 0;
  }

  /**
   * 最初の `INPUT_DELAY` tick ぶんを、始まった時点で押している内容で埋めて送る。
   *
   * ⚠️ これが無いと、tick 0 の入力は誰も送らない（最初に送るのは tick 3 の入力）ので、
   * 全員が互いの tick 0 を待ったまま止まる。
   *
   * ⚠️ 埋める値を何も押していない入力にしない。tick 0 に「離した」が届いて、ラウンドの始まりの
   * 「押していた扱い」（`WorldState` の `HELD_AT_ROUND_START`・`actionFired` の true）が外れ、
   * tick 3 に押していた内容が「押した瞬間」として届く。ホストが Enter で「はじめる」を押し、
   * その Enter がまだ押されている、という普通の始め方で、押したまま始まった人（ホスト）が開始位置に爆弾を置く。
   * 手元の入力は1回だけ読み、同じ値を3 tick ぶん送る（押したままのボタンは3 tick とも押している）。
   */
  start(): void {
    if (this.#started) return;
    this.#started = true;
    const { session, local } = this.#options;
    const held = local.next(session.world);
    for (let t = 0; t < INPUT_DELAY; t += 1) this.#sendLocal(t, held);
  }

  /** 中継から届いたメッセージを受け取る。 */
  receive(message: RelayMessage): void {
    switch (message.t) {
      case 'input':
        // 前の試合の入力。中継も配らないが、届く順に頼らないよう、ここでも捨てる。
        if (message.match !== this.#options.match) return;
        this.#receiveInput(message.seat, message.tick, message.bits);
        return;
      case 'peer_left':
        this.#depart(message.seat, message.lastTick);
        return;
      case 'desync':
        // 最初の知らせだけを覚える。ずれた場所に一番近いのは最初の1回。
        this.#desync ??= { tick: message.tick, reports: message.reports };
        return;
      case 'welcome':
      case 'peer_joined':
      case 'start':
      case 'settings':
        // 試合の前の知らせ。始まったあとには関係ない。
        return;
    }
  }

  /**
   * 試合を1 tick 進める。
   *
   * @returns この tick に起きたイベント。試合が終わったあとは、盤面を進めずに空の配列。
   *   入力を待っている・ずれたときは null（進めていない）
   */
  step(): SimEvent[] | null {
    if (!this.ready) return null;
    const { session, local } = this.#options;
    const t = this.#tick;
    const finished = session.match.finished;

    this.#replaceDeparted(t);
    // 試合が終わったあとの操作は何にも反映されないので、何も押していない入力を送る。
    this.#sendLocal(t + INPUT_DELAY, finished ? IDLE_INPUT : local.next(session.world));
    const events = finished ? [] : this.#advance(t);
    this.#tick += 1;
    if ((t + 1) % HASH_INTERVAL === 0) this.#sendHash(t);
    return events;
  }

  /** 次の tick を進めるのに、入力を待っている人間のプレイヤー。 */
  waitingFor(): PlayerId[] {
    const t = this.#tick;
    return this.#options.humans.filter(
      (playerId) => !this.#inputs.log.replacedAt(t, playerId) && !this.#inputs.has(playerId, t),
    );
  }

  /**
   * いま人間が操作しているプレイヤー。抜けて CPU に替わった人は含めない。
   *
   * 替わったと数えるのは、実際に CPU の窓口へ繋ぎ替えた tick から。抜けた知らせが届いた
   * 時点ではまだ届いていた入力で進めているので、画面の名札もそれに合わせる。
   */
  humanPlayers(): PlayerId[] {
    return this.#options.humans.filter((playerId) => !this.#replaced.has(playerId));
  }

  /**
   * 抜けたと知らされた人か。CPU に替わるのは `lastTick` の次の tick からだが、こちらは知らせが
   * 届いた時点で true になる（画面の案内を、替わるのを待たずに変えるため）。
   */
  hasLeft(playerId: PlayerId): boolean {
    return this.#inputs.log.departedAfter(playerId) !== undefined;
  }

  /** 中継が知らせてきたずれ。無ければ null。 */
  get desync(): Desync | null {
    return this.#desync;
  }

  /** 全員の入力の記録。時刻は試合通算の tick。途中で抜けた人と、その人の入力を最後に使う tick も入る。 */
  get log(): InputLog {
    return this.#inputs.log;
  }

  /** 試合を1 tick 進める。試合の tick と通信の tick が揃っていることを確認してから。 */
  #advance(tick: number): SimEvent[] {
    const { session } = this.#options;
    if (session.elapsed !== tick) {
      throw new Error(`試合の tick（${session.elapsed}）と通信の tick（${tick}）が食い違った`);
    }
    return session.tick();
  }

  #receiveInput(playerId: PlayerId, tick: number, bits: number): void {
    const { humans, localId } = this.#options;
    if (playerId === localId) {
      throw new Error('自分の入力が中継から返ってきた');
    }
    if (!humans.includes(playerId)) {
      throw new Error(`人間ではないプレイヤー ${playerId} の入力が届いた`);
    }
    // 抜けた人の、使わないと決まった tick の入力。全員が同じく捨てる。
    if (this.#inputs.log.replacedAt(tick, playerId)) return;
    this.#inputs.put(playerId, tick, unpackInput(bits));
  }

  #depart(playerId: PlayerId, lastTick: number): void {
    const { humans, localId } = this.#options;
    // 人間の一覧にいない人は、始まる前に入りかけていた接続。試合には関係ない。
    if (!humans.includes(playerId) || playerId === localId) return;
    // 同じ人の知らせが2度届いても、最初のものを使う（記録は2度書こうとすると止まる）。
    if (this.#inputs.log.departedAfter(playerId) === undefined) this.#inputs.log.depart(lastTick, playerId);
  }

  /**
   * 抜けた人の窓口を、代わりの窓口に替える。
   *
   * ⭐ `lastTick` の次の tick で替える。どの端末も、その tick を進める直前に
   * ここを通る（その人の入力が届かないので、知らせが届くまでは待っている）。
   */
  #replaceDeparted(tick: number): void {
    for (const playerId of this.#options.humans) {
      if (this.#replaced.has(playerId) || !this.#inputs.log.replacedAt(tick, playerId)) continue;
      this.#options.session.attach(this.#options.replacement(playerId));
      this.#replaced.add(playerId);
    }
  }

  #sendLocal(tick: number, playerInput: PlayerInput): void {
    const { link, localId } = this.#options;
    // 自分の入力は中継から返ってこないので、送るのと同時に自分でも受け取る。
    this.#inputs.put(localId, tick, playerInput);
    link.send({ t: 'input', tick, bits: packInput(playerInput), match: this.#options.match });
  }

  #sendHash(tick: number): void {
    const world = this.#options.session.world;
    // ⭐ 要約（hashWorld）にも乱数の回数は混ざっているが、別に載せる。
    // 回数が食い違っていれば「どこかで乱数を余計に取り出した」と、ずれの種類まで分かる。
    this.#options.link.send({
      t: 'hash',
      tick,
      hash: hashWorld(world),
      rngCalls: world.rng.calls,
      match: this.#options.match,
    });
  }
}
