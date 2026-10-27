import { describe, expect, it } from 'vitest';

import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { PANEL_REFRESH_TICKS, PanelRefresh, refreshesPanel } from '../../src/presentation/hud/panelRefresh.js';
import { makeWorld } from '../helpers.js';

/** 名札と時計を作り直す時（原型の `renderCards` を呼ぶ時。L4406 の 0.25 秒ごとと、被弾などの場面）。 */
describe('横の板の名札と時計を作り直す時', () => {
  it('初めて描くときと、盤面の時刻が 15 tick の区切りを越えたときに作り直す。区切りの中では作り直さない', () => {
    const refresh = new PanelRefresh();
    const world = makeWorld(3, ['rabbit']);
    expect(PANEL_REFRESH_TICKS).toBe(15);
    expect(refresh.due(world)).toBe(true);
    expect(refresh.due(world)).toBe(false);
    world.now = tick(14);
    expect(refresh.due(world)).toBe(false);
    world.now = tick(15);
    expect(refresh.due(world)).toBe(true);
    world.now = tick(29);
    expect(refresh.due(world)).toBe(false);
    // 2つ以上の区切りを一度に越えても（描くのが遅れたとき）、1回だけ作り直す。
    world.now = tick(61);
    expect(refresh.due(world)).toBe(true);
    expect(refresh.due(world)).toBe(false);
  });

  it('盤面が替わったら（ラウンドの始まり）、時刻が同じ区切りでもすぐ作り直す', () => {
    const refresh = new PanelRefresh();
    const first = makeWorld(3, ['rabbit']);
    refresh.due(first);
    expect(refresh.due(makeWorld(3, ['rabbit']))).toBe(true);
  });

  it('すぐ作り直すイベントがあれば、区切りを待たずに次に描くときに1回だけ作り直す', () => {
    const refresh = new PanelRefresh();
    const world = makeWorld(3, ['rabbit']);
    refresh.due(world);
    refresh.observe([{ type: 'bombPlaced', cell: { col: 1, row: 1 }, owner: 0 }]);
    expect(refresh.due(world)).toBe(false);
    refresh.observe([{ type: 'playerHurt', target: 0, by: 1, amount: 1 }]);
    expect(refresh.due(world)).toBe(true);
    expect(refresh.due(world)).toBe(false);
  });

  it('すぐ作り直すのは、原型が renderCards をすぐ呼ぶ場面のイベントだけ', () => {
    const at = { x: 1.5, y: 1.5 };
    const immediate: SimEvent[] = [
      { type: 'playerHurt', target: 0, by: 1, amount: 1 },
      { type: 'playerDown', target: 0, by: 1, at },
      { type: 'revived', player: 0, replaced: 1, at },
      { type: 'lanesClosed', players: [0] },
      { type: 'burntOff', player: 0, cell: { col: 1, row: 1 } },
      { type: 'reachRestored', player: 0, reach: 3 },
      { type: 'suddenDeath', reason: 'timeUp', players: [0, 1] },
      { type: 'roundEnded', round: 1, winner: 0 },
      { type: 'techniqueUsed', player: 0, special: true },
      { type: 'techniqueMoment', player: 0, moment: 'pitDug' },
      { type: 'effectApplied', target: 0, effect: 'pitfall', pushedBy: null },
    ];
    const later: SimEvent[] = [
      { type: 'bombPlaced', cell: { col: 1, row: 1 }, owner: 0 },
      // 通常技は、4 Hz の作り直しで出す（原型も、とくぎのときだけすぐ呼ぶ。L2627）。
      { type: 'techniqueUsed', player: 0, special: false },
      { type: 'techniqueMoment', player: 0, moment: 'digStarted' },
      { type: 'effectApplied', target: 0, effect: 'stun', pushedBy: null },
      { type: 'matchEnded', champion: 0 },
    ];
    expect(immediate.filter((event) => !refreshesPanel(event))).toEqual([]);
    expect(later.filter((event) => refreshesPanel(event))).toEqual([]);
  });
});
