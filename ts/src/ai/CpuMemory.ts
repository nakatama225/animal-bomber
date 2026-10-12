import type { Cell } from '../domain/core/Coord.js';
import type { Rng } from '../domain/core/Rng.js';
import type { Tick } from '../domain/core/Tick.js';
import type { CpuMode } from './CpuPlan.js';

/**
 * CPU 1体が覚えていること。
 *
 * ⚠️ これは試合の状態（`WorldState`）ではない。盤面を書き換えず、
 * 状態の要約にも入らない。CPU が返した入力は、1台の試合の記録には `PlayerInput` として
 * 残る。通信対戦では CPU の枠の入力を送らず、どの端末も同じ設定から CPU を作り直して
 * 動かす（docs/05）。どちらの場合も、再生するときにこの記憶を復元する必要はない。
 *
 * ラウンドが変わると作り直す。前のラウンドの経路や狙いを持ち越すと、
 * 作り直された盤面の上で存在しないマスへ歩こうとする。
 */
export interface CpuMemory {
  mode: CpuMode;
  /** 歩く予定のマス。先頭から1つずつ消していく。 */
  path: Cell[];
  /** 着いたら爆弾を置きたいか。 */
  wantBomb: boolean;
  /** 次に判断するまでの tick。0 以下で判断する。 */
  thinkIn: number;
  /**
   * 爆弾を狙う判断を控える残り tick。
   *
   * 「置けない」と分かった直後にすぐ狙い直すと、同じ場所をまた狙って
   * 「置けない → 立て直す → また置けない」を往復する。原型の実測で、
   * 1試合に 100 回を超える往復が出ていた（106 回・147 回）。
   */
  bombBan: number;
  /** とくぎの抽選に外れたあと、次に抽選するまでの残り tick。 */
  skillCool: number;
  /** 危険に気づいていない残り tick。弱い CPU だけが持つ。 */
  blind: number;
  /** 最後に爆弾を置いたマスと、その時刻。 */
  lastBomb: { readonly cell: Cell; readonly at: Tick } | null;
  /**
   * 判断の間隔の揺らぎ（0〜0.4）。
   *
   * 同じ強さの CPU が同じ tick に揃って判断すると、動きが機械的に揃って見える。
   * 1体ずつ少しずらす。
   */
  readonly jitter: number;
}

/** ラウンドの始めの記憶。 */
export function freshMemory(rng: Rng): CpuMemory {
  return {
    mode: 'idle',
    path: [],
    wantBomb: false,
    thinkIn: 0,
    bombBan: 0,
    skillCool: 0,
    blind: 0,
    lastBomb: null,
    jitter: rng.next() * 0.4,
  };
}
