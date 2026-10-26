import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
import { cellOf, centerOf } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import type { ItemKind } from '../../src/domain/rules/items.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { PlayerId, PlayerState } from '../../src/domain/state/PlayerState.js';
import { ActorSystem } from '../../src/domain/systems/ActorSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { clearBoard, grantSpecial, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

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

  it('ひきわけで終わったラウンドでは、ひきわけの音を鳴らす（原型の endGame L4507）', () => {
    const { played, presenter } = recorder();
    presenter.consume([{ type: 'roundEnded', round: 2, winner: null }], makeWorld());
    expect(played).toEqual(['draw']);
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
        { type: 'techniqueMoment', player: 0, moment: 'ringScattered' },
        { type: 'effectApplied', target: 1, effect: 'pitfall', pushedBy: null },
        { type: 'effectApplied', target: 1, effect: 'stun', pushedBy: null },
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
      'poop',
      'pitFall',
      'cry',
    ]);
  });

  it('爆発でブロックを壊したら、壊した数によらず連鎖1回につき1回だけブロックの音を鳴らす（原型の explodeChain）', () => {
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'exploded', cell: { col: 3, row: 3 }, owner: 0, chained: 2, blocks: 3 },
        { type: 'blockDestroyed', cell: { col: 3, row: 4 } },
        { type: 'blockDestroyed', cell: { col: 4, row: 3 } },
        { type: 'blockDestroyed', cell: { col: 2, row: 3 } },
        { type: 'exploded', cell: { col: 9, row: 9 }, owner: 1, chained: 1, blocks: 0 },
      ],
      makeWorld(),
    );
    expect(played).toEqual(['explode', 'breakBlock', 'explode']);
  });

  it('体当たりで壊したブロックと、爆風で焼けたアイテムには、音を鳴らさない（原型と同じ）', () => {
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'blockDestroyed', cell: { col: 3, row: 4 } },
        { type: 'itemBurned', cell: { col: 3, row: 5 }, kind: 'fire' },
      ],
      makeWorld(),
    );
    expect(played).toEqual([]);
  });
});

describe('原型が1回しか鳴らさない場面を、1 tick ぶんのイベントの並びで見分ける（同じ音をまとめる仕組みは持たない）', () => {
  const placed = (owner: PlayerId): SimEvent => ({ type: 'bombPlaced', cell: { col: 1, row: 1 }, owner });
  const used = (player: PlayerId, special = false): SimEvent => ({ type: 'techniqueUsed', player, special });
  const foxWorld = (): ReturnType<typeof makeWorld> => makeWorld(1, ['fox', 'rabbit']);

  it('ボタンで置いた爆弾は、1つにつき置く音1回', () => {
    const { played, presenter } = recorder();
    presenter.consume([placed(0), placed(1)], foxWorld());
    expect(played).toEqual(['place', 'place']);
  });

  it('技が一列に並べた爆弾は、何本でも置く音1回（原型の placeLineBombs）。技そのものの音は無い', () => {
    const { played, presenter } = recorder();
    presenter.consume([used(0), placed(0), placed(0), placed(0)], foxWorld());
    expect(played).toEqual(['place']);
  });

  it('ボタンの爆弾と一列置きが同じ tick なら、2回', () => {
    const { played, presenter } = recorder();
    presenter.consume([placed(0), used(0), placed(0), placed(0)], foxWorld());
    expect(played).toEqual(['place', 'place']);
  });

  it('技のすぐあとでも、ほかのプレイヤーの爆弾は1つずつ鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume([used(0), placed(1), placed(1)], foxWorld());
    expect(played).toEqual(['place', 'place']);
  });

  it('技とのあいだにほかのプレイヤーの爆弾があれば、技が並べたものとしない', () => {
    const { played, presenter } = recorder();
    presenter.consume([used(0), placed(1), placed(0)], foxWorld());
    expect(played).toEqual(['place', 'place']);
  });

  it('試合で一列に置くと、置く音は1回', () => {
    const world = foxWorld();
    clearBoard(world);
    const fox = world.players[0]!;
    fox.position = centerOf({ col: 3, row: 5 });
    fox.facing = 'right';
    fox.maxBombs = 3;
    const { played, presenter } = recorder();
    const events = new Simulation().step(world, onlyFor(world, 0, press({ action: true })));
    expect(events.filter((event) => event.type === 'bombPlaced')).toHaveLength(3);
    presenter.consume(events, world);
    expect(played).toEqual(['place']);
  });

  it('同じ tick に2体が葱を撃てば、2回鳴らす（まとめない）', () => {
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'leekThrown', player: 0, from: { x: 1.5, y: -0.31 }, facing: 'down' },
        { type: 'leekThrown', player: 1, from: { x: 2.5, y: -0.31 }, facing: 'down' },
      ],
      foxWorld(),
    );
    expect(played).toEqual(['leek', 'leek']);
  });
});

describe('アイテムと被弾の音（原型の applyItem・hurt・spitPowerup）', () => {
  const taken = (kind: ItemKind): SimEvent => ({ type: 'itemTaken', cell: { col: 1, row: 1 }, kind, taker: 0, swept: false });
  const hurt = (target: PlayerId): SimEvent => ({ type: 'playerHurt', target, by: 1, amount: 2 });
  const dropped = (kind: ItemKind): SimEvent => ({ type: 'itemDropped', cell: { col: 2, row: 1 }, kind });
  const down = (target: PlayerId): SimEvent => ({ type: 'playerDown', target, by: 1, at: { x: 1.5, y: 1.5 } });

  it('強くなるアイテムは拾った音、チキンはチキンの音。悪いアイテムは、かかった状態の音だけ', () => {
    const { played, presenter } = recorder();
    for (const kind of ['bomb', 'fire', 'shoe', 'chicken'] as const) presenter.consume([taken(kind)], makeWorld());
    expect(played).toEqual(['item', 'item', 'item', 'chicken']);
    played.length = 0;
    presenter.consume(
      [taken('banana'), { type: 'effectApplied', target: 0, effect: 'slide', pushedBy: null }],
      makeWorld(),
    );
    presenter.consume([taken('onion'), { type: 'effectApplied', target: 0, effect: 'stun', pushedBy: null }], makeWorld());
    presenter.consume([taken('poop'), { type: 'effectApplied', target: 0, effect: 'slow', pushedBy: null }], makeWorld());
    expect(played).toEqual(['slip', 'cry', 'poop']);
  });

  it('体力が残れば、吐き出す音と被弾の音。吐き出す場所が無ければ被弾の音だけ', () => {
    const { played, presenter } = recorder();
    presenter.consume([hurt(0), dropped('fire')], makeWorld());
    expect(played).toEqual(['spit', 'hurt']);
    played.length = 0;
    presenter.consume([hurt(0)], makeWorld());
    expect(played).toEqual(['hurt']);
  });

  it('体力が尽きれば、倒れる音だけ（被弾の音は鳴らさない）。倒れたのが別のプレイヤーなら被弾の音を鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume([hurt(0), dropped('bomb'), down(0)], makeWorld());
    expect(played).toEqual(['spit', 'down']);
    played.length = 0;
    presenter.consume([hurt(0), down(1)], makeWorld());
    expect(played).toEqual(['hurt', 'down']);
  });

  it('吐き出せなかった被弾のすぐあとに撒いたうんこが落ちても、吐き出す音を鳴らさない（落ちたのが強くなるアイテムのときだけ）', () => {
    const { played, presenter } = recorder();
    presenter.consume([hurt(0), dropped('poop')], makeWorld());
    expect(played).toEqual(['hurt']);
  });

  it('試合で爆風に当たると、原型と同じ音（残れば吐き出す音と被弾の音、尽きれば吐き出す音と倒れる音）', () => {
    for (const [hp, expected] of [
      [4, ['spit', 'hurt']],
      [1, ['spit', 'down']],
    ] as const) {
      const world = makeWorld(5, ['rabbit', 'elephant']);
      clearBoard(world);
      world.items = [];
      const rabbit = world.players[0]!;
      rabbit.position = centerOf({ col: 3, row: 5 });
      rabbit.hp = hp;
      rabbit.invulnerableUntil = tick(0);
      addBlast(world, cellOf(rabbit.position), 1, true);
      const { played, presenter } = recorder();
      presenter.consume(new Simulation().step(world, sameForAll(world, press({}))), world);
      expect(played, `体力 ${hp}`).toEqual(expected);
    }
  });

  it('根元まで焼けた舌を出そうとしたら画面の操作の音（原型 L2498）。焼けた舌が戻っても音は鳴らさない', () => {
    const { played, presenter } = recorder();
    presenter.consume([{ type: 'techniqueRefused', player: 0, wait: tick(60) }], makeWorld());
    expect(played).toEqual(['ui']);
    played.length = 0;
    presenter.consume([{ type: 'reachRestored', player: 0, reach: 4 }], makeWorld());
    expect(played).toEqual([]);
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
      // 放った炎は盤面の物として進める（当たりは、動いたあとの `settle` で見る）。
      collect(abilityOf('fox').onHold!(world, fox).events);
      const actors = new ActorSystem();
      for (let t = 0; t < 40; t += 1) collect(actors.step(world));
    }
    // 撒く（輪を撒いたとき）
    {
      const world = makeWorld(5, ['rabbit', 'fox']);
      clearBoard(world);
      const scatter = new ScatterActor({ col: 9, row: 7 }, 0);
      for (let t = 0; t < 130; t += 1) collect(scatter.tick(world).events);
    }

    expect([...moments].sort()).toEqual(
      [
        'chaserCast',
        'chaserHit',
        'digStarted',
        'itemsSpat',
        'pitDug',
        'rammed',
        'ringScattered',
        'slimeHopped',
        'tongueCaught',
      ].sort(),
    );
  });

  it('撒く技は、1つでも撒けた輪ごとに知らせる（原型 1・40・80 tick 目。撒けない輪は知らせない）', () => {
    const rings = (blocked: boolean): number[] => {
      const world = makeWorld(5, ['rabbit', 'fox']);
      clearBoard(world);
      world.items = [];
      // 2周目の輪をすべて塞ぐ。
      if (blocked) {
        for (let col = 7; col <= 11; col += 1) {
          for (let row = 5; row <= 9; row += 1) {
            if (Math.max(Math.abs(col - 9), Math.abs(row - 7)) === 2) world.board.set({ col, row }, 'soft');
          }
        }
      }
      const scatter = new ScatterActor({ col: 9, row: 7 }, 0);
      const at: number[] = [];
      for (let t = 1; t <= 130; t += 1) {
        const events = scatter.tick(world).events;
        if (events.some((e) => e.type === 'techniqueMoment' && e.moment === 'ringScattered')) at.push(t);
      }
      return at;
    };
    expect(rings(false)).toEqual([1, 40, 80]);
    expect(rings(true)).toEqual([1, 40]);
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
    grantSpecial(player, 1);
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

  it('うさぎは、共通の音とうんこを踏んだときの音を鳴らし、足元の輪を撒いた音も同じ tick に鳴らす（原型の rabbitPoroporo）', () => {
    expect(soundsOfSpecial(makeWorld(5, ['rabbit', 'fox']))).toEqual(['special', 'poop', 'poop']);
  });

  it('掘れないマス（壊せるブロックの中）のもぐらは、共通の音だけ（対照：掘れるマスなら掘る音も鳴る）', () => {
    const blocked = makeWorld(5, ['mole', 'rabbit']);
    blocked.board.set(cellOf(blocked.players[0]!.position), 'soft');
    expect(soundsOfSpecial(blocked)).toEqual(['special']);
    expect(soundsOfSpecial(makeWorld(5, ['mole', 'rabbit']))).toEqual(['special', 'dig']);
  });
});
