import { CPU_LEVEL_KEYS, type CpuLevelKey } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS } from '../../content/animals.js';
import { secondsToTicks } from '../../domain/core/Tick.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';
import { ROUND_SECONDS, STARTING_HP, WINS_TO_TAKE_MATCH } from '../../domain/rules/tuning.js';
import type { LanSettings } from '../../net/protocol.js';
import { assertChoice, HIT_CHOICES, hitsForHp, hpForHits, TIME_CHOICES, WIN_CHOICES } from './choices.js';

/** 通信対戦の枠の数。中継の定員と同じ。 */
export const LAN_SLOTS = 4;

type Four<T> = readonly [T, T, T, T];

/**
 * 通信対戦で、ホストがロビーで決めるもの。
 *
 * 4つの枠それぞれに動物・体力・CPU の強さを持つ。始まった時点で人間がつながっていない枠は
 * CPU が受け持ち、人間の枠でも、その人が抜けたらここで決めた強さの CPU に替わる。
 *
 * ゲストは決めない（見るだけ）。ゲストが自分の手元で選んでも、試合はホストが配った設定で
 * 作られるので、選んだのに反映されない、という体験になる（原型でも同じ判断をした）。
 */
export interface LanSetup {
  readonly animals: Four<string>;
  /** 爆風何回で倒れるか。 */
  readonly hits: Four<number>;
  readonly cpuLevels: Four<CpuLevelKey>;
  readonly winsToTake: number;
  readonly roundSeconds: number;
  readonly suddenDeath: boolean;
}

export const DEFAULT_LAN_SETUP: LanSetup = {
  animals: ['rabbit', 'frog', 'fox', 'elephant'],
  hits: [hitsForHp(STARTING_HP), hitsForHp(STARTING_HP), hitsForHp(STARTING_HP), hitsForHp(STARTING_HP)],
  cpuLevels: ['normal', 'normal', 'normal', 'normal'],
  winsToTake: WINS_TO_TAKE_MATCH,
  roundSeconds: ROUND_SECONDS,
  suddenDeath: true,
};

/** ホストが全員へ配る設定を作る。 */
export function lanSettingsFrom(setup: LanSetup, seed: number): LanSettings {
  return {
    match: {
      roundLimit: secondsToTicks(setup.roundSeconds),
      winsToTake: setup.winsToTake,
      suddenDeath: setup.suddenDeath,
      startingHp: setup.hits.map(hpForHits),
      seed,
      animals: [...setup.animals],
    },
    cpu: [...setup.cpuLevels],
  };
}

/**
 * ロビーで選んでいるもの。選べない値は例外にする（画面の作りの誤り）。
 */
export class LobbyChoices {
  #setup: LanSetup;

  constructor(setup: LanSetup = DEFAULT_LAN_SETUP) {
    this.#setup = setup;
  }

  get setup(): LanSetup {
    return this.#setup;
  }

  setAnimal(slot: PlayerId, animal: string): void {
    if (!ANIMAL_LOOKS.some((look) => look.key === animal)) throw new Error(`知らない動物: ${animal}`);
    this.#setup = { ...this.#setup, animals: replaced(this.#setup.animals, slot, animal) };
  }

  setHits(slot: PlayerId, hits: number): void {
    assertChoice(HIT_CHOICES, hits, '爆風の回数');
    this.#setup = { ...this.#setup, hits: replaced(this.#setup.hits, slot, hits) };
  }

  setCpuLevel(slot: PlayerId, level: CpuLevelKey): void {
    assertChoice(CPU_LEVEL_KEYS, level, 'CPU の強さ');
    this.#setup = { ...this.#setup, cpuLevels: replaced(this.#setup.cpuLevels, slot, level) };
  }

  setWinsToTake(wins: number): void {
    assertChoice(WIN_CHOICES, wins, '勝ち数');
    this.#setup = { ...this.#setup, winsToTake: wins };
  }

  setRoundSeconds(seconds: number): void {
    assertChoice(TIME_CHOICES, seconds, '制限時間');
    this.#setup = { ...this.#setup, roundSeconds: seconds };
  }

  setSuddenDeath(on: boolean): void {
    this.#setup = { ...this.#setup, suddenDeath: on };
  }
}

function replaced<T>(items: Four<T>, slot: PlayerId, value: T): Four<T> {
  const copy: [T, T, T, T] = [...items];
  copy[slot] = value;
  return copy;
}
