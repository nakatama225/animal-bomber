import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { cellOf, centerOf } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

function recorder(): { played: SoundName[]; presenter: Presenter } {
  const played: SoundName[] = [];
  return { played, presenter: new Presenter({ play: (name) => played.push(name) }) };
}

describe('イベントから音へ', () => {
  it('優勝が決まった tick は、ファンファーレだけを鳴らす', () => {
    // ラウンドの終わりの曲と重ねると、どちらも聞き取れない。
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'roundEnded', round: 3, winner: 0 },
        { type: 'matchEnded', champion: 0 },
      ],
      makeWorld(),
    );
    expect(played).toEqual(['fanfare']);
  });

  it('優勝が決まらないラウンドの終わりでは、ラウンドの音を鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume([{ type: 'roundEnded', round: 1, winner: 0 }], makeWorld());
    expect(played).toEqual(['roundEnd']);
  });

  it('技の音は、使った動物で決まる。とくぎはどの動物でも共通の音を先に鳴らす（原型の useSpecial）', () => {
    const { played, presenter } = recorder();
    const world = makeWorld(1, ['rabbit', 'elephant', 'fox', 'mole']);
    presenter.consume(
      [
        { type: 'techniqueUsed', player: 0, special: false },
        { type: 'techniqueUsed', player: 1, special: true },
        { type: 'techniqueUsed', player: 1, special: false },
        { type: 'techniqueUsed', player: 2, special: true },
        { type: 'techniqueUsed', player: 3, special: false },
      ],
      world,
    );
    expect(played).toEqual(['hop', 'special', 'charge', 'snot', 'special', 'foxLeap']);
  });

  it('技の途中で起きたこと・落とし穴は、原型と同じ専用の音を鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'techniqueMoment', player: 0, moment: 'tongueCaught' },
        { type: 'techniqueMoment', player: 0, moment: 'digStarted' },
        { type: 'techniqueMoment', player: 0, moment: 'pitDug' },
        { type: 'techniqueMoment', player: 0, moment: 'slimeHopped' },
        { type: 'techniqueMoment', player: 0, moment: 'itemsSpat' },
        { type: 'techniqueMoment', player: 0, moment: 'rammed' },
        { type: 'techniqueMoment', player: 0, moment: 'chaserCast' },
        { type: 'techniqueMoment', player: 0, moment: 'chaserHit' },
        { type: 'effectApplied', target: 1, effect: 'pitfall' },
        { type: 'effectApplied', target: 1, effect: 'stun' },
      ],
      makeWorld(),
    );
    expect(played).toEqual([
      'tongueCatch',
      'dig',
      'pitDone',
      'slimeHop',
      'spit',
      'charge',
      'foxfire',
      'foxfireHit',
      'pitFall',
      'cry',
    ]);
  });
});

describe('技の途中で起きたことを、ルールの層が知らせる', () => {
  // 音を鳴らす側が受け取れるかは上で見た。ここでは、ルールの層がその瞬間に知らせるかを見る。
  it('舌が掴んだ・穴を掘り始めた／掘り終えた・跳ね回る爆弾が跳ねた・体当たりが当たった・抱えたものを撒いた・炎を放った／当たった', () => {
    const moments = new Set<string>();
    const collect = (events: readonly SimEvent[]): void => {
      for (const event of events) if (event.type === 'techniqueMoment') moments.add(event.moment);
    };

    // 舌
    {
      const world = makeWorld(5, ['frog', 'rabbit']);
      clearBoard(world);
      world.items = [{ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'fire' }];
      const frog = world.players[0]!;
      frog.position = centerOf({ col: 3, row: 7 });
      frog.facing = 'right';
      const tongue = new TongueAction(cellOf(frog.position), frog.facing);
      for (let t = 0; t < 60; t += 1) collect(tongue.tick(world, frog).events);
    }
    // 穴（掘り始めたときと、掘り終えたとき）
    {
      const world = makeWorld(5, ['mole', 'rabbit']);
      clearBoard(world);
      const mole = world.players[0]!;
      collect(abilityOf('mole').onHold!(world, mole).events);
      const dig = new PitAction(cellOf(mole.position));
      for (let t = 0; t < 120; t += 1) if (dig.tick(world, mole).done) break;
      collect(dig.finish(world, mole));
    }
    // 跳ね回る爆弾
    {
      const world = makeWorld(5, ['frog', 'rabbit']);
      clearBoard(world);
      const slime = new SlimeBombActor({ col: 9, row: 7 }, world.players[0]!, 5);
      for (let t = 0; t < 60; t += 1) collect(slime.tick(world).events);
    }
    // 体当たり（通り道に相手）と、抱えたものを撒く（通り道にたまねぎ、相手は通り道の外）
    for (const scene of ['hit', 'spit'] as const) {
      const world = makeWorld(5, ['elephant', 'rabbit']);
      clearBoard(world);
      world.items = scene === 'spit' ? [{ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'onion' }] : [];
      const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
      elephant.position = centerOf({ col: 3, row: 7 });
      rabbit.position = centerOf(scene === 'hit' ? { col: 8, row: 7 } : { col: 19, row: 13 });
      rabbit.invulnerableUntil = tick(0);
      elephant.action = new ChargeAction('right');
      const sim = new Simulation();
      for (let t = 0; t < 120; t += 1) collect(sim.step(world, sameForAll(world, press({}))));
    }
    // 炎（放ったときと、当たったとき）
    {
      const world = makeWorld(5, ['fox', 'rabbit']);
      clearBoard(world);
      const [fox, rabbit] = world.players as [PlayerState, PlayerState];
      fox.position = centerOf({ col: 3, row: 7 });
      rabbit.position = centerOf({ col: 5, row: 7 });
      rabbit.invulnerableUntil = tick(0);
      collect(abilityOf('fox').onHold!(world, fox).events);
      const fire = new FoxfireActor(fox.position, fox.id);
      for (let t = 0; t < 40; t += 1) collect(fire.tick(world).events);
    }

    expect([...moments].sort()).toEqual(
      [
        'chaserCast',
        'chaserHit',
        'digStarted',
        'itemsSpat',
        'pitDug',
        'rammed',
        'slimeHopped',
        'tongueCaught',
      ].sort(),
    );
  });
});

describe('とくぎが空振りしたときの音（原型の useSpecial：技が出なければ、その技の音の手前で返る）', () => {
  /**
   * 0番のプレイヤーに長押しでとくぎを出させ、その間に鳴った音を返す。押した瞬間の通常技は、
   * 間隔の途中にして出さない（通常技の無い動物は、押した瞬間にとくぎが出る）。
   */
  function soundsOfSpecial(world: ReturnType<typeof makeWorld>): SoundName[] {
    const { played, presenter } = recorder();
    const player = world.players[0]!;
    player.specialCharges = 1;
    player.abilityCooldown = tick(600);
    const sim = new Simulation();
    presenter.consume(sim.step(world, sameForAll(world, press({}))), world);
    for (let i = 0; i < abilityOf(player.animal).holdTicks; i += 1) {
      presenter.consume(sim.step(world, onlyFor(world, 0, press({ action: true }))), world);
    }
    expect(player.specialCharges).toBe(0);
    return played;
  }

  it('盤面に相手がいないきつねは、共通の音と跳ぶ音だけ（対照：相手がいれば炎の音も鳴る）', () => {
    const alone = makeWorld(5, ['fox', 'rabbit']);
    alone.players[1]!.life = OUT;
    expect(soundsOfSpecial(alone)).toEqual(['special', 'foxLeap']);
    expect(soundsOfSpecial(makeWorld(5, ['fox', 'rabbit']))).toEqual(['special', 'foxLeap', 'foxfire']);
  });

  it('掘れないマス（壊せるブロックの中）のもぐらは、共通の音だけ（対照：掘れるマスなら掘る音も鳴る）', () => {
    const blocked = makeWorld(5, ['mole', 'rabbit']);
    blocked.board.set(cellOf(blocked.players[0]!.position), 'soft');
    expect(soundsOfSpecial(blocked)).toEqual(['special']);
    expect(soundsOfSpecial(makeWorld(5, ['mole', 'rabbit']))).toEqual(['special', 'dig']);
  });
});
