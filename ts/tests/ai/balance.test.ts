import { describe, expect, it } from 'vitest';

import { CpuIntentSource, cpuSeed } from '../../src/ai/CpuIntentSource.js';
import { CPU_LEVELS, type CpuLevelKey } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';

/** CPU どうしの試合を、画面なしで決まったラウンド数だけ回した結果。 */
interface Tally {
  /** プレイヤー番号の順の勝ち数。 */
  readonly wins: number[];
  /** 時間切れの引き分け。 */
  readonly draws: number;
  /** 被弾の回数。 */
  readonly hurts: number;
  /** そのうち自分の爆風によるもの。 */
  readonly selfHurts: number;
}

function play(seed: number, animals: string[], levels: CpuLevelKey[], rounds: number): Tally {
  const config = { ...defaultMatchConfig(seed, animals), winsToTake: rounds + 1 };
  const game = new GameSession(config);
  levels.forEach((level, index) => {
    const id = index as PlayerId;
    game.attach(new CpuIntentSource(id, CPU_LEVELS[level], cpuSeed(seed, id)));
  });

  const wins = levels.map(() => 0);
  let draws = 0;
  let hurts = 0;
  let selfHurts = 0;
  let finished = 0;
  while (finished < rounds) {
    for (const event of game.tick()) {
      if (event.type === 'playerHurt') {
        hurts += 1;
        if (event.by === event.target) selfHurts += 1;
      }
      if (event.type === 'roundEnded') {
        finished += 1;
        if (event.winner === null) draws += 1;
        else wins[event.winner] = (wins[event.winner] ?? 0) + 1;
      }
    }
  }
  return { wins, draws, hurts, selfHurts };
}

/**
 * CPU の強さの検査。
 *
 * ⚠️ 強さの表で変えているのは判断の頻度・危険の見落とし・攻めを見送る確率と
 * 各種の上限で、判断の規則はどの強さでも同じ。弱くしたつもりが強くなる、の
 * 逆転が起きていないかを見る。
 *
 * 試合は種で決まるので、この検査の結果は毎回同じになる（揺れない）。
 * 規則や数値を変えたときにだけ結果が動く。
 */
describe('CPU の強さ', () => {
  it('おには、よわいより3倍以上多く勝つ', () => {
    // 同じ動物どうしで、開始位置の有利不利が混ざらないよう開始位置を入れ替えて回す。
    let oni = 0;
    let easy = 0;
    for (let s = 0; s < 4; s += 1) {
      const left = play(100 + s, ['rabbit', 'rabbit'], ['oni', 'easy'], 2);
      const right = play(200 + s, ['rabbit', 'rabbit'], ['easy', 'oni'], 2);
      oni += (left.wins[0] ?? 0) + (right.wins[1] ?? 0);
      easy += (left.wins[1] ?? 0) + (right.wins[0] ?? 0);
    }
    expect(oni).toBeGreaterThanOrEqual(easy * 3);
    expect(oni).toBeGreaterThan(0);
  }, 120_000);
});

/**
 * 数値の計測。環境変数 `MEASURE=1` のときだけ走る。
 *
 * 関門に届いていない数値（自爆の割合、4段階の強さの順）を、同じ条件で
 * 測り直すためのもの。結果は標準出力に表で出す。
 */
describe.runIf(process['env']['MEASURE'] === '1')('計測', () => {
  it('強さと自爆の割合', () => {
    const rows: string[] = [];
    const strong = play(11, ['rabbit', 'elephant', 'fox', 'frog'], ['hard', 'hard', 'hard', 'hard'], 6);
    const ratio = Math.round((100 * strong.selfHurts) / Math.max(1, strong.hurts));
    rows.push(
      `つよい×4  勝ち ${strong.wins.join('/')}  引分 ${strong.draws}  ` +
        `自爆 ${strong.selfHurts}/${strong.hurts} (${ratio}%)`,
    );
    const mixed = play(12, ['mole', 'fox', 'frog', 'elephant'], ['easy', 'normal', 'hard', 'oni'], 6);
    rows.push(`よわい/ふつう/つよい/おに  勝ち ${mixed.wins.join('/')}  引分 ${mixed.draws}`);
    process.stdout.write(`\n${rows.join('\n')}\n`);
  }, 600_000);
});
