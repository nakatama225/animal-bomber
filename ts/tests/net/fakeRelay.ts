import { GameSession } from '../../src/app/GameSession.js';
import type { InputSource } from '../../src/domain/input/InputSource.js';
import type { PlayerInput } from '../../src/domain/input/PlayerInput.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { LockstepClient, type LanHooks, type LanPhase } from '../../src/net/LockstepClient.js';
import type { LockstepDriver } from '../../src/net/LockstepDriver.js';
import { lanCpuSource } from '../../src/net/lanCpu.js';
import { encodePeerMessage, type LanSettings, type PeerMessage } from '../../src/net/protocol.js';

/**
 * 中継サーバ（`server/` の `LockstepRoom`）の代わりを、同じプロセスの中で務める。
 *
 * 振る舞いは `LockstepRoom` に合わせてある。
 *
 * - 入力は送り主の番号を書き足して、送り主以外の全員へ配る
 * - ホスト（0番）の合図で、その時点の接続を人間の一覧にして全員へ `start` を配る。始まったあとの
 *   ホストの合図は、試合の番号を1つ増やした次の試合にする
 * - 入力と報告は、いまの試合の番号が付いたものだけを扱う
 * - 始まる前のホストの設定（`settings`）を、ホスト以外の全員へ転送する
 * - 抜けた人は、入力を最後に配った tick（`lastTick`）を添えて知らせる
 * - 同じ tick の要約が全員ぶん揃ったら突き合わせ、食い違えば `desync` を配る
 *
 * - 試合が始まったあとの接続は断る。抜けた知らせは1人につき1回だけ配る
 * - 入力と報告は、試合を始めたときの参加者からのものだけを扱い、参加者にだけ配る
 *
 * ⚠️ 真似ていないもの：全員が抜けたあとに次の試合へ戻すこと、送れない相手を外すこと、
 * 読めないメッセージを捨てること。これらは `server/tests/test_lockstep.py` で実物を確認する。
 *
 * ⚠️ メッセージは受け取り手ごとの列に溜まり、`deliver()` を呼ぶまで届かない。
 * 届く時機をテストの側で決めて、遅れ・届く順の違いを作るため。
 * 中身は実物と同じく文字列で運ぶ（送る側の組み立てと、受ける側の読み取りの両方を通す）。
 */
export class FakeRelay {
  readonly #queues = new Map<number, string[]>();
  readonly #receivers = new Map<number, LockstepClient>();
  #members: number[] | null = null;
  /** いまの試合の番号。最初の試合が 1。 */
  #match = 0;
  readonly #lastTick = new Map<number, number>();
  readonly #pending = new Map<number, Map<number, string>>();
  #desynced = false;
  /** 突き合わせて一致した tick。検査が本当に行われたかを確認するのに使う。 */
  readonly agreed: number[] = [];

  /** 新しい端末をつなぐ。番号は空いている最も小さいもの。 */
  connect(hooks: LanHooks): LockstepClient {
    if (this.#members !== null) throw new Error('試合中は入れない（中継は MatchInProgressError で断る）');
    let seat = 0;
    while (this.#receivers.has(seat)) seat += 1;
    const client = new LockstepClient({ send: (m) => this.#fromPeer(seat, m) }, hooks);
    const existing = [...this.#receivers.keys()].sort((a, b) => a - b);
    for (const other of existing) this.#push(other, { t: 'peer_joined', seat });
    this.#receivers.set(seat, client);
    this.#queues.set(seat, []);
    this.#push(seat, { t: 'welcome', seat, role: seat === 0 ? 'host' : 'guest', seats: existing });
    return client;
  }

  /**
   * 溜まっているメッセージを、列が空になるまで届ける。
   *
   * 受け取った端末がその場で送り返したもの（`start` を受けて送る最初の入力など）も、
   * 同じ呼び出しの中で届く。
   */
  deliver(): void {
    let delivered = true;
    while (delivered) {
      delivered = false;
      for (const [seat, queue] of this.#queues) {
        const client = this.#receivers.get(seat);
        while (queue.length > 0) {
          client?.receive(queue.shift() as string);
          delivered = true;
        }
      }
    }
  }

  /** 回線が切れたことにする。まだ届いていないメッセージは捨てる。 */
  leave(seat: number): void {
    if (!this.#receivers.has(seat)) return;
    this.#receivers.delete(seat);
    this.#queues.delete(seat);
    for (const other of this.#receivers.keys()) {
      this.#push(other, { t: 'peer_left', seat, lastTick: this.#lastTick.get(seat) ?? -1 });
    }
    for (const tick of [...this.#pending.keys()].sort((a, b) => a - b)) this.#settle(tick);
  }

  #fromPeer(seat: number, message: PeerMessage): void {
    if (!this.#receivers.has(seat)) return;
    // 実物と同じく文字列にしてから読む。組み立て方の誤りもここで出る。
    const data = JSON.parse(encodePeerMessage(message)) as Record<string, unknown>;
    switch (data['t']) {
      case 'settings': {
        if (seat !== 0 || this.#members !== null) return;
        for (const other of this.#receivers.keys()) {
          if (other !== seat) this.#push(other, { t: 'settings', config: data['config'] });
        }
        return;
      }
      case 'start': {
        if (seat !== 0) return;
        // 始まったあとの合図は次の試合（LockstepRoom と同じ）。前の試合の記録は持ち越さない。
        this.#match += 1;
        this.#members = [...this.#receivers.keys()].sort((a, b) => a - b);
        this.#lastTick.clear();
        this.#pending.clear();
        this.#desynced = false;
        for (const other of this.#members) {
          this.#push(other, { t: 'start', seats: this.#members, config: data['config'], match: this.#match });
        }
        return;
      }
      case 'input': {
        if (this.#members === null || !this.#members.includes(seat) || data['match'] !== this.#match) return;
        // 配り始める前に記録する（LockstepRoom と同じ）。
        this.#lastTick.set(seat, data['tick'] as number);
        for (const other of this.#receivers.keys()) {
          if (other === seat || !this.#members.includes(other)) continue;
          this.#push(other, { t: 'input', seat, tick: data['tick'], bits: data['bits'], match: this.#match });
        }
        return;
      }
      case 'hash': {
        if (this.#members === null || this.#desynced || !this.#members.includes(seat) || data['match'] !== this.#match) {
          return;
        }
        const tick = data['tick'] as number;
        const reports = this.#pending.get(tick) ?? new Map<number, string>();
        reports.set(seat, JSON.stringify([data['hash'], data['rngCalls']]));
        this.#pending.set(tick, reports);
        this.#settle(tick);
        return;
      }
    }
  }

  #settle(tick: number): void {
    const reports = this.#pending.get(tick);
    if (reports === undefined || this.#desynced || this.#members === null) return;
    const connected = this.#members.filter((s) => this.#receivers.has(s));
    if (connected.some((s) => !reports.has(s))) return;
    this.#pending.delete(tick);
    if (new Set(reports.values()).size <= 1) {
      this.agreed.push(tick);
      return;
    }
    this.#desynced = true;
    const list = [...reports.entries()]
      .sort(([a], [b]) => a - b)
      .map(([s, value]) => {
        const [hash, rngCalls] = JSON.parse(value) as [number, number];
        return { seat: s, hash, rngCalls };
      });
    for (const other of this.#receivers.keys()) this.#push(other, { t: 'desync', tick, reports: list });
  }

  #push(seat: number, message: Record<string, unknown>): void {
    this.#queues.get(seat)?.push(JSON.stringify(message));
  }
}

/**
 * 台本どおりに操作する、この端末の入力。人間がキーボードを押す代わり。
 *
 * 台本には「何回目に読まれたか」を渡す。0 回目は試合が始まったとき（`LockstepDriver.start`）に
 * 読まれ、tick 0〜2 に反映される。そのあとは tick を進めるときだけ読まれるので、n 回目（n ≥ 1）に
 * 読まれた入力は、tick n − 1 を進めるときに送られ、tick n + 2 に反映される。
 */
export class ScriptedLocal implements InputSource {
  #calls = 0;

  constructor(
    readonly playerId: PlayerId,
    private readonly script: (call: number) => PlayerInput,
  ) {}

  next(): PlayerInput {
    const playerInput = this.script(this.#calls);
    this.#calls += 1;
    return playerInput;
  }
}

/** 通信対戦の1台ぶん。進めるたびに状態の要約を控える。 */
export class Peer {
  /** 進め終えた tick → その時点の状態の要約。 */
  readonly hashes = new Map<number, number>();

  constructor(readonly client: LockstepClient) {}

  /** いま進めている試合。まだ始まっていなければ例外。 */
  get session(): GameSession {
    return this.#playing().session as GameSession;
  }

  /** 試合を進めているもの。 */
  get driver(): LockstepDriver {
    return this.#playing().driver;
  }

  /**
   * 1 tick 進める。進めたか（入力を待っていれば false）。
   *
   * 要約は通信の tick で控える。試合が終わったあとも tick は進む（盤面は止まる）。
   */
  step(): boolean {
    const events = this.client.step();
    if (events === null) return false;
    this.hashes.set(this.driver.elapsed - 1, hashWorld(this.session.world));
    return true;
  }

  #playing(): Extract<LanPhase, { kind: 'playing' }> {
    const phase = this.client.phase;
    if (phase.kind !== 'playing') throw new Error(`試合が始まっていない: ${phase.kind}`);
    return phase;
  }
}

/** テストで使う試合の作り方。この端末の操作は台本で、残りは設定どおりの CPU。 */
export function hooksWith(script: (playerId: PlayerId, call: number) => PlayerInput): LanHooks {
  return {
    createSession: (settings: LanSettings) => new GameSession(settings.match),
    localSource: (playerId) => new ScriptedLocal(playerId, (call) => script(playerId, call)),
    cpuSource: lanCpuSource,
  };
}
