import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IdleIntentSource } from '../../src/domain/intent/IntentSource.js';
import { placeBomb, placeBombAt } from '../../src/domain/mutations/bombs.js';
import { detonate } from '../../src/domain/mutations/explode.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import {
  SUDDEN_DEATH_HP,
  SUDDEN_DEATH_INVULNERABLE,
  SUDDEN_DEATH_LENGTH,
} from '../../src/domain/rules/suddenDeath.js';
import { MAX_BOMBS, MAX_POWER, MAX_SHOES, SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import { OUT } from '../../src/domain/state/Life.js';
import { isAlive, type PlayerState } from '../../src/domain/state/PlayerState.js';
import { RoundSystem } from '../../src/domain/systems/RoundSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, makeWorld, onlyFor, press } from '../helpers.js';

const THREE = ['rabbit', 'elephant', 'mole'];

function session(overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {}): GameSession {
  const config = { ...defaultMatchConfig(777, ['rabbit', 'elephant']), ...overrides };
  const game = new GameSession(config);
  for (const player of game.world.players) game.attach(new IdleIntentSource(player.id));
  return game;
}

/** 条件を満たすイベントが出るまで進め、そのイベントを返す。 */
function runUntil(game: GameSession, match: (event: SimEvent) => boolean, limit: number): SimEvent | null {
  for (let i = 0; i < limit; i += 1) {
    const hit = game.tick().find(match);
    if (hit !== undefined) return hit;
  }
  return null;
}

describe('延長戦（サドンデス）に入る条件', () => {
  const rounds = new RoundSystem();
  const config = defaultMatchConfig(777, THREE);
  const down = (target: 0 | 1 | 2): SimEvent => ({ type: 'playerDown', target, by: null, at: { x: 1.5, y: 1.5 } });

  it('時間切れで2人以上残っていれば、延長戦に入る', () => {
    const game = session({ roundLimit: secondsToTicks(0.05) });
    const event = runUntil(game, (e) => e.type === 'suddenDeath' || e.type === 'roundEnded', 10);
    expect(event).toEqual({ type: 'suddenDeath', reason: 'timeUp', players: [0, 1] });
    expect(game.match.round).toBe(1);
    expect(game.world.suddenDeath).toBe(true);
    expect(game.world.endsAt - game.world.now).toBe(SUDDEN_DEATH_LENGTH);
  });

  it('延長戦は1ラウンドに1回だけ。延長戦でも決まらなければ引き分け', () => {
    const game = session({ roundLimit: secondsToTicks(0.05) });
    const seen: SimEvent[] = [];
    for (let i = 0; i < SUDDEN_DEATH_LENGTH + 20 && !seen.some((e) => e.type === 'roundEnded'); i += 1) {
      seen.push(...game.tick());
    }
    expect(seen.filter((e) => e.type === 'suddenDeath')).toHaveLength(1);
    expect(seen.find((e) => e.type === 'roundEnded')).toMatchObject({ winner: null });
  });

  it('2人が同じ爆風で倒れると、その2人で延長戦が始まる', () => {
    // 判定だけでなく、試合を進める窓口を通しても延長戦に入ることを見る。
    const game = session();
    const world = game.world;
    clearBoard(world);
    const [left, right] = world.players as [PlayerState, PlayerState];
    left.position = centerOf({ col: 3, row: 1 });
    right.position = centerOf({ col: 5, row: 1 });
    left.hp = 1;
    right.hp = 1;
    left.power = 2;
    placeBombAt(world, left, { col: 4, row: 1 })!.fuse = tick(1);

    const event = runUntil(game, (e) => e.type === 'suddenDeath' || e.type === 'roundEnded', 5);
    expect(event).toEqual({ type: 'suddenDeath', reason: 'allDown', players: [0, 1] });
    expect(world.players.every(isAlive)).toBe(true);
    expect(game.world).toBe(world);
  });

  it('残っていた全員が同じ tick に倒れたら、倒れた者だけで延長戦に入る', () => {
    const world = makeWorld(3, THREE);
    // プレイヤー2は前に倒れていた。同じ tick に倒れたのは 0 と 1。
    for (const player of world.players) player.life = OUT;
    const verdict = rounds.judge(world, config, [down(1), down(0)]);
    expect(verdict).toEqual({ type: 'suddenDeath', reason: 'allDown', players: [0, 1] });
  });

  it('同じ tick に倒れたのが1人なら、延長戦にせず引き分け', () => {
    const world = makeWorld(3, THREE);
    for (const player of world.players) player.life = OUT;
    expect(rounds.judge(world, config, [down(2)])).toEqual({
      type: 'over',
      outcome: { winner: null, reason: 'allDown' },
    });
  });

  it('延長戦の最中に全員倒れたら引き分け', () => {
    const world = makeWorld(3, THREE);
    world.suddenDeath = true;
    for (const player of world.players) player.life = OUT;
    expect(rounds.judge(world, config, [down(0), down(1)])).toMatchObject({ type: 'over' });
  });

  it('延長戦を切ってあれば、全員倒れても引き分け', () => {
    const world = makeWorld(3, THREE);
    for (const player of world.players) player.life = OUT;
    const off = { ...config, suddenDeath: false };
    expect(rounds.judge(world, off, [down(0), down(1)])).toMatchObject({ type: 'over' });
  });

  it('盤面に1人なら、時間が残っていても決着', () => {
    const world = makeWorld(3, THREE);
    world.players[1]!.life = OUT;
    world.players[2]!.life = OUT;
    expect(rounds.judge(world, config, [])).toEqual({
      type: 'over',
      outcome: { winner: 0, reason: 'lastStanding' },
    });
  });
});

describe('延長戦の準備', () => {
  it('壊せるブロック・爆弾・爆風・アイテム・飛び道具を片付ける', () => {
    const world = makeWorld(3, THREE);
    placeBomb(world, world.players[0]!);
    placeBomb(world, world.players[1]!);
    detonate(world, world.bombs[0]!);
    world.items.push({ id: world.ids.take(), cell: { col: 3, row: 3 }, kind: 'fire' });
    world.actors.push(new FoxfireActor({ x: 5.5, y: 5.5 }, 0));
    expect(world.bombs.length).toBeGreaterThan(0);
    expect(world.blasts.length).toBeGreaterThan(0);
    enterSuddenDeath(world, [0, 1, 2], 'timeUp');
    const softLeft = [...world.board.cells()].filter(({ tile }) => tile === 'soft');
    expect(softLeft).toHaveLength(0);
    expect(world.bombs).toHaveLength(0);
    expect(world.blasts).toHaveLength(0);
    expect(world.items).toHaveLength(0);
    expect(world.actors).toHaveLength(0);
    expect(world.players.every((p) => p.activeBombs === 0)).toBe(true);
  });

  it('加わる者はプレイヤー番号の順に開始位置の表の隅へ移り、体力1つ・爆弾と火力と靴が上限・しばらく無敵になる', () => {
    const world = makeWorld(3, THREE);
    world.now = tick(500);
    const player = world.players[2]!;
    player.position = centerOf({ col: 9, row: 9 });
    player.specialCharges = 2;
    player.effects.add('slow', tick(300), tick(300));
    player.action = new PitAction();
    enterSuddenDeath(world, [0, 2], 'allDown');
    // 開始位置は加わる者にプレイヤー番号の順で割り当てる。プレイヤー2は2番目。
    expect(player.position).toEqual(centerOf(SPAWN_CELLS[1]!));
    expect(isAlive(player)).toBe(true);
    expect(player.hp).toBe(SUDDEN_DEATH_HP);
    expect(player.maxBombs).toBe(MAX_BOMBS);
    expect(player.power).toBe(MAX_POWER);
    expect(player.shoes).toBe(MAX_SHOES);
    expect(player.invulnerableUntil).toBe(500 + SUDDEN_DEATH_INVULNERABLE);
    expect(player.specialCharges).toBe(0);
    expect(player.effects.active()).toEqual([]);
    // 技の途中でも外す。外さないと、技の続きが移った先の隅で走る。
    expect(player.action).toBeNull();
  });

  it('長押しの途中で延長戦に入っても、離したときに通常技が出ない', () => {
    // 押した長さを 0 に戻すと、長押しの途中が短い押しに化け、離した瞬間に通常技が出る。
    // 延長戦を挟まない場合と同じく、何も起きないのが正しい。
    const world = makeWorld(3, ['fox', 'rabbit']);
    const fox = world.players[0]!;
    const sim = new Simulation();
    const hold = abilityOf(fox.animal).holdTicks;
    fox.actionHeld = tick(0);
    advance(world, onlyFor(world, 0, press({ action: true })), hold + 10, sim);
    enterSuddenDeath(world, [0, 1], 'timeUp');
    advance(world, onlyFor(world, 0, press({ action: true })), 10, sim);
    const released = sim.step(world, onlyFor(world, 0, press({})));
    expect(released.filter((e) => e.type === 'techniqueUsed')).toEqual([]);
    expect(world.bombs).toHaveLength(0);
  });

  it('加わらない者は退場する', () => {
    const world = makeWorld(3, THREE);
    enterSuddenDeath(world, [0, 2], 'allDown');
    expect(world.players[1]!.life).toBe(OUT);
  });

  it('乱数を引かない', () => {
    // 盤面を作り直すと乱数を引く。延長戦に入った試合だけ以降の抽選がずれる。
    const world = makeWorld(3, THREE);
    const calls = world.rng.calls;
    enterSuddenDeath(world, [0, 1, 2], 'timeUp');
    expect(world.rng.calls).toBe(calls);
  });
});
