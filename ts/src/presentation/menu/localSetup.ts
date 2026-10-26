import type { CpuLevelKey } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS } from '../../content/animals.js';
import { Rng } from '../../domain/core/Rng.js';
import { secondsToTicks } from '../../domain/core/Tick.js';
import type { MatchConfig } from '../../domain/rules/MatchConfig.js';
import { DUEL_SPAWN_ORDER, ROUND_SECONDS, STARTING_HP, WINS_TO_TAKE_MATCH } from '../../domain/rules/tuning.js';
import type { Roster } from '../hud/roster.js';
import { hitsForHp, hpForHits } from './choices.js';

/**
 * 1台で遊ぶときの遊び方。
 *
 * | | 人間 | CPU |
 * |---|---|---|
 * | `solo` | 1人（キーボード全体とゲームパッド） | 3体 |
 * | `duo` | 2人（キーボードの左右） | 2体 |
 * | `versus` | 2人（キーボードの左右） | なし |
 */
export type PlayMode = 'solo' | 'duo' | 'versus';

/** 遊び方ごとの人数。 */
export const MODE_SIZES: Readonly<Record<PlayMode, { readonly humans: number; readonly cpus: number }>> = {
  solo: { humans: 1, cpus: 3 },
  duo: { humans: 2, cpus: 2 },
  versus: { humans: 2, cpus: 0 },
};

/**
 * 遊び方ごとの、プレイヤーが始まる隅（`SPAWN_CELLS` の番号。人間が先、CPU があと）。原型の `setupPlayers` と同じ。
 *
 * - 1P は左上（0）
 * - 人間が2人のときの 2P は右下（3）。対角から始める
 * - CPU は、残りの隅を右上（1）・左下（2）・右下（3）の順に使う
 *
 * 1人と2人だけの試合は、試合の設定を省いたときの並び（番号の順・2人なら対角）と同じ。違うのは
 * 2人＋CPU2体だけで、番号の順だと 2P が右上から始まる。3つとも書くのは、誰がどこから始まるかを
 * ここだけで読めるようにするため。
 */
const LOCAL_SPAWN_ORDER: Readonly<Record<PlayMode, readonly number[]>> = {
  solo: [0, 1, 2, 3],
  duo: [0, 3, 1, 2],
  versus: DUEL_SPAWN_ORDER,
};

/**
 * 1台で遊ぶときに、画面で選んだもの。
 *
 * 人間と CPU の数は遊び方で決まる。値は多めに持っておき、使うぶんだけ前から使う
 * （遊び方を行き来しても、選んだ値が消えないように）。
 */
export interface LocalSetup {
  readonly mode: PlayMode;
  /** 人間ごとの動物。1P・2P の順。 */
  readonly picks: readonly [string, string];
  /** 爆風何回で倒れるか。1P・2P・CPU（全員同じ）。 */
  readonly hits: { readonly p1: number; readonly p2: number; readonly cpu: number };
  /** CPU ごとの強さ。CPU の1体目から。 */
  readonly cpuLevels: readonly [CpuLevelKey, CpuLevelKey, CpuLevelKey];
  readonly winsToTake: number;
  /** 1ラウンドの制限時間（秒）。 */
  readonly roundSeconds: number;
  readonly suddenDeath: boolean;
}

/** はじめて開いたときの選択。 */
export const DEFAULT_SETUP: LocalSetup = {
  mode: 'solo',
  picks: ['rabbit', 'frog'],
  hits: { p1: hitsForHp(STARTING_HP), p2: hitsForHp(STARTING_HP), cpu: hitsForHp(STARTING_HP) },
  cpuLevels: ['normal', 'normal', 'normal'],
  winsToTake: WINS_TO_TAKE_MATCH,
  roundSeconds: ROUND_SECONDS,
  suddenDeath: true,
};

/**
 * 操作の出どころ。試合を始めるときに、`app/` が実物（キーボードの窓口・CPU）に置き換える。
 *
 * この層はキーボードを知らない（層が上にある）。どの配置を使うかだけを決める。
 */
export type LocalController =
  | {
      readonly kind: 'keys';
      /** キーボード全体を1人で使うか、左右に分けて2人で使うか。 */
      readonly layout: 'solo' | 'left' | 'right';
    }
  | { readonly kind: 'cpu'; readonly level: CpuLevelKey };

/** 選んだものから作った、1試合ぶんの段取り。 */
export interface LocalPlan {
  readonly config: MatchConfig;
  /** プレイヤー番号の順。 */
  readonly controllers: readonly LocalController[];
  readonly roster: Roster;
}

/**
 * 選んだものから試合の設定を作る。
 *
 * 人間を先に（1P が 0番、2P が 1番）、CPU をそのあとに並べる。
 * CPU の動物は、人間が選ばなかった動物から種で選ぶ（同じ種なら同じ顔ぶれになる）。
 *
 * @param seed 試合の種。起動の入口が実時間から作って渡す
 */
export function planLocalMatch(setup: LocalSetup, seed: number): LocalPlan {
  const { humans, cpus } = MODE_SIZES[setup.mode];
  const humanAnimals = setup.picks.slice(0, humans);
  const cpuAnimals = pickCpuAnimals(humanAnimals, cpus, seed);

  const humanHits = [setup.hits.p1, setup.hits.p2].slice(0, humans);
  const cpuLevels = setup.cpuLevels.slice(0, cpus);
  const layouts: readonly ('solo' | 'left' | 'right')[] = humans === 1 ? ['solo'] : ['left', 'right'];

  return {
    config: {
      roundLimit: secondsToTicks(setup.roundSeconds),
      winsToTake: setup.winsToTake,
      suddenDeath: setup.suddenDeath,
      startingHp: [...humanHits, ...cpuLevels.map(() => setup.hits.cpu)].map(hpForHits),
      seed,
      animals: [...humanAnimals, ...cpuAnimals],
      spawnOrder: LOCAL_SPAWN_ORDER[setup.mode],
    },
    controllers: [
      ...layouts.map((layout): LocalController => ({ kind: 'keys', layout })),
      ...cpuLevels.map((level): LocalController => ({ kind: 'cpu', level })),
    ],
    roster: [
      // 「あなた」の印は付けない。1台を囲んでいる全員が同じ画面を見ている。
      ...layouts.map((_, index) => ({ kind: 'human' as const, label: `${index + 1}P`, local: false })),
      ...cpuLevels.map((level) => ({ kind: 'cpu' as const, level })),
    ],
  };
}

/**
 * CPU の動物を選ぶ。人間が選んでいない動物から、重ならないように。
 *
 * ⚠️ 乱数は試合の乱数（`world.rng`）とは別に、試合の種から作る。試合の乱数を使うと、
 * 盤面を作る前に乱数を余計に取り出してしまい、同じ種でも別の盤面になる。
 */
function pickCpuAnimals(humanAnimals: readonly string[], count: number, seed: number): string[] {
  const pool = ANIMAL_LOOKS.map((look) => look.key).filter((key) => !humanAnimals.includes(key));
  new Rng((seed ^ 0x5bd1e995) >>> 0).shuffle(pool);
  if (pool.length < count) throw new Error(`CPU に割り当てる動物が足りない（${pool.length} < ${count}）`);
  return pool.slice(0, count);
}
