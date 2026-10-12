/**
 * CPU の強さ。
 *
 * ## ⚠️ 狙いの精度は触らない
 *
 * 弱くする手段として「狙いを外させる」は採らない。原型で試したところ、
 * 置いた爆弾で自滅するだけになり、弱くはならなかった。
 *
 * 下の表で変えているのは、判断の頻度・危険の見落とし・攻めを見送る確率と、
 * 追う距離や同時に置く爆弾の数などの上限。判断の規則そのものは、
 * どの強さでも同じ。
 *
 * 両端の強さ（おに と よわい）で勝ち数が逆転していないことは
 * `tests/ai/balance.test.ts` で確かめている。4段階すべての順はまだ確かめていない。
 */
export interface CpuLevel {
  readonly key: CpuLevelKey;
  /** 画面に出す名前。 */
  readonly label: string;
  /**
   * 次の判断までの間隔（秒）。長いほど反応が鈍い。
   *
   * 秒のまま持つ。原型は、この秒数に 1 体ずつの揺らぎ（`CpuMemory.jitter`）を掛けてから
   * 1/60 秒ずつ減らし、0 以下になったフレームで考え直す。先に tick へ丸めると、揺らぎを掛けたあとの
   * 長さが原型と 1 tick ずれる。
   */
  readonly thinkSeconds: number;
  /** 危ないマスに立っているのに、気づかない確率（判断の機会ごと）。 */
  readonly sloppy: number;
  /** 敵を狙う・爆弾を置く判断に踏み切る確率。1 未満だと消極的になる。 */
  readonly aggression: number;
  /** とくぎを使う確率（使える場面になるたびに抽選する）。 */
  readonly skillUse: number;
  /**
   * 逃げ先を「完全に安全なマス」に限るか。
   *
   * ⚠️ 限らない場合は「今より少しましなマス」で止まることがある。
   * そこはまだ爆風の中なので、着いて止まった瞬間に倒れる。
   * 原型の実測で、自爆が被弾の 80〜100% を占めていた主な原因がこれだった。
   * 強い CPU はかならず限る。弱い CPU の弱さとしてだけ残している。
   */
  readonly strictEscape: boolean;
  /** 危ないときだけ判断の間隔を詰めるか。逃げ遅れを潰す。 */
  readonly sharp: boolean;
  /** 敵を追う距離（マス）。盤面 23×17 の対角は約 36 マス。 */
  readonly huntRange: number;
  /** アイテムを探しに行く距離（マス）。 */
  readonly itemRange: number;
  /**
   * 自分の爆弾を同時に何個まで盤面に残すか。
   *
   * 多すぎると、自分の爆弾で逃げ場を潰して追い詰められる。
   */
  readonly maxLiveBombs: number;
  /** 火力と爆弾を先に集めるか。強くなるのが速い。 */
  readonly greedy: boolean;
  /** 射線に入った相手を、見送らずにかならず狙うか。 */
  readonly ruthless: boolean;
}

export type CpuLevelKey = 'easy' | 'normal' | 'hard' | 'oni';

/**
 * 強さの一覧。値は原型（`legacy/animal-bomber.html` の `CPU_LEVELS`）から持ってきた。
 */
export const CPU_LEVELS: Readonly<Record<CpuLevelKey, CpuLevel>> = {
  easy: {
    key: 'easy',
    label: 'よわい',
    thinkSeconds: 0.52,
    sloppy: 0.55,
    aggression: 0.35,
    skillUse: 0.25,
    strictEscape: false,
    sharp: false,
    huntRange: 14,
    itemRange: 12,
    maxLiveBombs: 1,
    greedy: false,
    ruthless: false,
  },
  normal: {
    key: 'normal',
    label: 'ふつう',
    thinkSeconds: 0.26,
    sloppy: 0.18,
    aggression: 0.8,
    skillUse: 0.7,
    strictEscape: false,
    sharp: false,
    huntRange: 26,
    itemRange: 16,
    maxLiveBombs: 2,
    greedy: false,
    ruthless: false,
  },
  hard: {
    key: 'hard',
    label: 'つよい',
    thinkSeconds: 0.13,
    sloppy: 0,
    aggression: 1,
    skillUse: 1,
    strictEscape: true,
    sharp: true,
    huntRange: 36,
    itemRange: 22,
    maxLiveBombs: 3,
    greedy: false,
    ruthless: false,
  },
  oni: {
    key: 'oni',
    label: 'おに',
    thinkSeconds: 0.05,
    sloppy: 0,
    aggression: 1,
    skillUse: 1,
    strictEscape: true,
    sharp: true,
    huntRange: 99,
    itemRange: 99,
    maxLiveBombs: 4,
    greedy: true,
    ruthless: true,
  },
};

/** 一覧の並び。画面で選ぶときの順番。 */
export const CPU_LEVEL_KEYS: readonly CpuLevelKey[] = ['easy', 'normal', 'hard', 'oni'];
