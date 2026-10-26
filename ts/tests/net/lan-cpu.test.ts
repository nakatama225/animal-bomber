import { describe, expect, it } from 'vitest';

import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { lanCpuSource } from '../../src/net/lanCpu.js';
import type { LanSettings } from '../../src/net/protocol.js';

describe('通信対戦の CPU', () => {
  it('強さは、そのプレイヤーの値を取得する', () => {
    // 取り違えても、全員の端末が同じく取り違えるので状態の要約は一致したまま進む。
    // ずれを見るテストでは検出できないので、ここで直接比べる。
    const settings: LanSettings = {
      match: defaultMatchConfig(3, ['rabbit', 'elephant', 'fox', 'frog']),
      cpu: ['easy', 'normal', 'hard', 'oni'],
    };
    const levels = ([0, 1, 2, 3] as PlayerId[]).map((id) => lanCpuSource(id, settings).level.key);
    expect(levels).toEqual(['easy', 'normal', 'hard', 'oni']);
  });
});
