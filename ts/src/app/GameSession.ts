import { abilityOf } from '../domain/abilities/registry.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import { IntentGatherer, type IntentSource } from '../domain/intent/IntentSource.js';
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
 * `createWorld`、1 tick 進めるのは `Simulation`。このクラスは
 * その順番を知っているだけで、ゲームのルールを持たない。
 *
 * 束ねる場所を1つ作っておくと、遊ぶとき・記録を再生するとき・
 * 大量に試合を回すときで、同じ形の呼び出しになる。
 */
export class GameSession {
  readonly #simulation = new Simulation();
  readonly #rounds = new RoundSystem();
  readonly #gatherer = new IntentGatherer();
  readonly #config: MatchConfig;
  #world: WorldState;
  #match: MatchState;

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
      bonusOf: startingBonusOf,
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

  /**
   * 操作の出どころを登録する。
   *
   * キーボードでも CPU でも記録の再生でも、同じ形で受け取る。
   * 途中で差し替えれば、接続が切れた席を CPU が引き継ぐこともできる。
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

    const events = this.#simulation.step(this.#world, this.#gatherer.gather(this.#world));

    const outcome = this.#rounds.check(this.#world, this.#config);
    if (outcome === null) return events;

    events.push(...applyOutcome(this.#match, this.#config, outcome));
    if (!this.#match.finished) this.#startNextRound();
    return events;
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
