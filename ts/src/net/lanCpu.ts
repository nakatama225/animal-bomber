import { CpuIntentSource, cpuSeed } from '../ai/CpuIntentSource.js';
import { CPU_LEVELS } from '../ai/CpuLevel.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { cpuLevelOf, type LanSettings } from './protocol.js';

/**
 * 通信対戦で、そのプレイヤーを受け持つ CPU を作る。人間のいない枠と、抜けた人の代わりに使う。
 *
 * 強さはホストが配った設定から、そのプレイヤーのものを引く。種は試合の種から作る。
 * どちらも全員の端末で同じなので、全員の手元で同じ CPU が同じ手を指す。
 *
 * ⚠️ 1か所にまとめてあるのは、別のプレイヤーの強さを引く取り違えが、ずれとしては
 * 見つからないから。全員の端末が同じ取り違えをするので、状態の要約は一致したまま進む。
 * 取り違えはここのテストでしか捕まらない。
 */
export function lanCpuSource(playerId: PlayerId, settings: LanSettings): CpuIntentSource {
  return new CpuIntentSource(playerId, CPU_LEVELS[cpuLevelOf(settings, playerId)], cpuSeed(settings.match.seed, playerId));
}
