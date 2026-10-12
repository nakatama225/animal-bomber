import { secondsToTicks } from '../domain/core/Tick.js';
import { BOMB_FUSE } from '../domain/rules/tuning.js';

/**
 * CPU の判断に使う余裕の長さ。値は原型から持ってきた（秒を tick に直してある）。
 *
 * どれも「このくらい前から避ける」という慎重さの度合いで、
 * 大きくすれば安全側に倒れるが、逃げ道や通り道が見つかりにくくなる。
 */

/**
 * 歩き回るとき、この時間以内に燃えるマスは通らない。
 *
 * アイテムを拾いに行く・相手を追う・ブロックを壊しに行く・うろつく、の
 * すべてで同じ値を使う。
 */
export const ROUTE_AVOID = secondsToTicks(1.6);

/**
 * 逃げるとき、この時間以内に燃えるマスは通らない。
 *
 * 歩き回るときより小さい。逃げる最中は多少危ないマスでも抜けるしかない。
 */
export const FLEE_AVOID = secondsToTicks(0.35);

/**
 * 完全に安全なマスが見つからないとき、いまより少なくともこれだけ
 * 長く持つマスへ逃げる。
 *
 * ⚠️ そこはまだ爆風の中。弱い CPU だけが使う妥協。
 */
export const FALLBACK_MARGIN = secondsToTicks(0.6);

/**
 * 爆弾を置いたあと逃げ切れるかを見るとき、導火線からこれだけ引いた時間で
 * 逃げ切れることを求める。ざっくり安全側に見るための余裕。
 */
export const ESCAPE_MARGIN = secondsToTicks(0.7);

/**
 * 逃げ切れるかの見積もりで、自分の速さにかける倍率。
 *
 * 曲がり角での減速や、通路の中央への寄せのぶん、実際には
 * 最高の速さでは走れない。7 割で見積もる。
 */
export const ESCAPE_SPEED_RATIO = 0.7;

/**
 * 同じマスに爆弾を置き直さない期間。
 *
 * ⛔ これが無いと「置く → 自分の爆風から逃げて離れる → 爆発が終わると同じマスへ
 * 戻ってまた置く」を延々と繰り返し、3マスの範囲から出られなくなる。
 * 原型の実測で、1秒あたり 5.1 回この往復をしていた。
 */
export const SAME_SPOT_BAN = secondsToTicks(4.5);

/** 置いたら逃げ切れない場所だと分かったあと、爆弾を狙わない期間。 */
export const UNSAFE_SPOT_BAN = secondsToTicks(0.8);

/**
 * 手持ちの爆弾を出し切っているとき、爆弾を狙わない期間。
 *
 * これは「場所が悪い」のではなく「今は待つ」だけなので短い。
 * 長くすると置かなくなる。原型で、往復 288 回を測って決めた値。
 */
export const OUT_OF_BOMBS_BAN = secondsToTicks(0.35);

/** 危ないときに判断を詰める場合の間隔（秒。`CpuLevel.thinkSeconds` と同じく、揺らぎを掛けてから tick にする）。 */
export const SHARP_THINK_SECONDS = 0.03;

/**
 * 立っているマスに、この tick 数より早く爆風が届くなら「危ない」とみなす（原型 cpuUpdate の
 * `danger[ty][tx] < BOMB_FUSE + 0.2`）。どの爆弾も導火線より長くは持たないので、爆風の届くマスはどれも危ない。
 */
export const NOTICE_WITHIN = BOMB_FUSE + secondsToTicks(0.2);

/** 弱い CPU が危険に気づかない長さの、最短と揺れ幅（秒）。 */
export const BLIND_MIN_SECONDS = 0.35;
export const BLIND_SPREAD_SECONDS = 0.5;
