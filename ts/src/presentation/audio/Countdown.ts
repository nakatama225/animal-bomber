import type { WorldState } from '../../domain/state/WorldState.js';
import { remainingSeconds } from '../hud/scoreboard.js';
import type { SoundBank } from './SoundBank.js';

/** 秒読みを始める残り秒数。 */
const COUNT_FROM = 10;

/**
 * 残り時間の秒読み。残り10秒から1秒まで、1秒ごとに短い音を鳴らす。
 *
 * 残り0秒では鳴らさない（原型は鳴らしていた）。0秒の tick にはラウンドが決まるか延長戦に入り、
 * その音（引き分け・延長戦）が同じ tick に鳴る。重ねると、どちらも聞き取りにくい。
 *
 * 試合の側にこのためのイベントは無い。残り時間は盤面から計算できるので、
 * 秒の境目をこちらで数える。
 *
 * 前に見た秒は、盤面が替わったら捨てる。捨てないと、次の盤面が前の盤面の最後と同じ秒から
 * 始まったとき（制限時間が10秒以下のとき）に、最初の1回を鳴らさない。画面で選べる制限時間は
 * 1分からなので起きないが、試合の設定は画面を通らずにも作れる。
 *
 * 延長戦では同じ盤面のまま残り時間が延びる。延びた先でまた10秒を切れば、そこから鳴る。
 * 決着のあとの待ちの間は盤面が止まっていて秒が変わらないので、鳴らない。
 */
export class Countdown {
  #world: Readonly<WorldState> | null = null;
  #last: number | null = null;

  constructor(private readonly sounds: SoundBank) {}

  /** tick を進めるたびに、進めたあとの盤面を渡す。 */
  observe(world: Readonly<WorldState>): void {
    if (world !== this.#world) {
      this.#world = world;
      this.#last = null;
    }
    const left = remainingSeconds(world);
    if (left === this.#last) return;
    this.#last = left;
    if (left >= 1 && left <= COUNT_FROM) this.sounds.play('tick');
  }
}
