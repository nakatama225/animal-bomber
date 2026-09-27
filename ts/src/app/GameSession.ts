import { abilityOf } from '../domain/abilities/registry.js';
import { secondsToTicks, type Tick } from '../domain/core/Tick.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import { IntentGatherer, type IntentSource } from '../domain/intent/IntentSource.js';
import { enterSuddenDeath } from '../domain/mutations/suddenDeath.js';
import { seedForRound, type MatchConfig } from '../domain/rules/MatchConfig.js';
import { createMatch, type MatchState } from '../domain/state/MatchState.js';
import {
  createWorld,
  type StartingBonus,
  type WorldState,
} from '../domain/state/WorldState.js';
import { applyOutcome, RoundSystem } from '../domain/systems/RoundSystem.js';
import { Simulation } from '../domain/systems/Simulation.js';

/**
 * 1試合ぶんの進行をまとめた窓口。
 *
 * 呼び出し側が知る必要があるのは `tick()` と `world` だけになる。
 * 内側で `Simulation` を回し、ラウンドが終われば盤面を作り直し、
 * 勝利数を数える。
 *
 * ## ここが束ねているだけで、判断を持たないこと
 *
 * ラウンドが終わったかを決めるのは `RoundSystem`、盤面を作るのは
 * `createWorld`、延長戦の準備は `enterSuddenDeath`、1 tick 進めるのは
 * `Simulation`。このクラスは
 * その順番を知っているだけで、ゲームのルールを持たない。
 *
 * 束ねる場所を1つ作っておくと、遊ぶとき・記録を再生するとき・
 * 大量に試合を回すときで、同じ形の呼び出しになる。
 */
/**
 * ラウンドが決まってから、次の盤面を作るまでの間。
 *
 * ⚠️ 決まった tick のうちに盤面を作り直すと、決着をつけた爆発も、倒れる瞬間も
 * 画面に1度も描かれない（描く前に次の盤面へ切り替わる）。決着の場面を見せる
 * ために、前の盤面を止めたまま少し待つ。ラウンドの間の幕（`presentation/hud/RoundBanner.ts`）は、
 * この待ちの間に重ねる。
 */
export const ROUND_INTERMISSION: Tick = secondsToTicks(2);

export class GameSession {
  readonly #simulation = new Simulation();
  readonly #rounds = new RoundSystem();
  readonly #gatherer = new IntentGatherer();
  readonly #config: MatchConfig;
  #world: WorldState;
  #match: MatchState;
  /** 次の盤面を作るまでの残り。0 ならラウンドの最中。 */
  #intermission = 0;
  /** 試合が始まってから進め終えた tick の数。 */
  #elapsed = 0;

  constructor(config: MatchConfig) {
    this.#config = config;
    this.#match = createMatch();
    this.#world = this.#makeWorld();
  }

  /**
   * 盤面を作る。
   *
   * 動物ごとの初期値をここで引いて渡している。状態を作る側が
   * 能力の表を引くと、依存が逆流する。
   */
  #makeWorld(): WorldState {
    return createWorld({
      seed: seedForRound(this.#config, this.#match.round),
      animals: this.#config.animals,
      roundLimit: this.#config.roundLimit,
      startingHp: this.#config.startingHp,
      bonusOf: startingBonusOf,
      // ラウンドごとに同じ並びの隅から始める（原型も、ラウンドの始まりのたびに同じ隅へ戻す）。
      ...(this.#config.spawnOrder === undefined ? {} : { spawnOrder: this.#config.spawnOrder }),
    });
  }

  get world(): WorldState {
    return this.#world;
  }

  get match(): MatchState {
    return this.#match;
  }

  get config(): MatchConfig {
    return this.#config;
  }

  /** ラウンドが決まり、次の盤面を作るのを待っている最中か。 */
  get betweenRounds(): boolean {
    return this.#intermission > 0;
  }

  /**
   * 試合が始まってから進め終えた tick の数。`tick()` の中では、いま進めている tick の番号になる。
   *
   * ⚠️ 通信対戦と記録の時刻にはこちらを使い、`world.now` は使わない。
   * `world.now` はラウンドごとに 0 へ戻り、決着のあとの待ち（`ROUND_INTERMISSION`）の間は
   * 盤面を止めているので進まない。同じ `world.now` が試合の中で何度も現れる。
   */
  get elapsed(): number {
    return this.#elapsed;
  }

  /**
   * 操作の出どころを登録する。
   *
   * キーボードでも CPU でも記録の再生でも、同じ形で受け取る。
   * 途中で差し替えれば、接続が切れたプレイヤーを CPU が引き継ぐこともできる。
   */
  attach(source: IntentSource): this {
    this.#gatherer.add(source);
    return this;
  }

  /**
   * 1 tick 進める。ラウンドが終わっていれば次を始める。
   *
   * @returns この tick に起きたイベント
   */
  tick(): SimEvent[] {
    if (this.#match.finished) return [];
    const events = this.#advance();
    this.#elapsed += 1;
    return events;
  }

  #advance(): SimEvent[] {
    // 決着のあとは盤面を止めて待つ。操作は集めない（押しても何も起きない）。
    if (this.#intermission > 0) {
      this.#intermission -= 1;
      if (this.#intermission === 0) this.#startNextRound();
      return [];
    }

    const events = this.#simulation.step(this.#world, this.#gatherer.gather(this.#world));

    const verdict = this.#rounds.judge(this.#world, this.#config, events);
    switch (verdict.type) {
      case 'continue':
        return events;
      case 'suddenDeath':
        events.push(...enterSuddenDeath(this.#world, verdict.players, verdict.reason));
        return events;
      case 'over':
        events.push(...applyOutcome(this.#match, this.#config, verdict.outcome));
        if (!this.#match.finished) this.#intermission = ROUND_INTERMISSION;
        return events;
    }
  }

  /**
   * 次のラウンドの盤面を作る。
   *
   * ⚠️ 種はラウンド番号から導く。試合の種1つから全ラウンドが決まるため、
   * 「3ラウンド目だけ再現したい」も設定だけで足りる。
   */
  #startNextRound(): void {
    this.#world = this.#makeWorld();
  }
}

/** 動物ごとの、始まりの上乗せを引く。 */
export function startingBonusOf(animal: string): StartingBonus {
  const ability = abilityOf(animal);
  return { hp: ability.hpBonus, power: ability.powerBonus, bombs: ability.bombBonus };
}
