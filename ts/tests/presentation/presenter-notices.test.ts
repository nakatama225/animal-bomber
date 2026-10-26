import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { BurntTongueActor, TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { IDLE_INPUT, type PlayerInput } from '../../src/domain/input/PlayerInput.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { sendToLane } from '../../src/domain/mutations/negibon.js';
import type { ItemKind } from '../../src/domain/rules/items.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { PlayerId, PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { lanRoster, localRoster, type Roster } from '../../src/presentation/hud/roster.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/**
 * イベントを通知に変える所（`Presenter` の通知）の検査。
 *
 * 出す場面・順・呼び方は原型（`legacy/animal-bomber.html`）の `toast`・`flash` の呼び出しに合わせる
 * （Python 版の `tests/presentation/test_presenter_notices.py` と同じ場面）。イベントの並べ方や盤面を
 * 読んで決める所は、作ったイベントの並びのほかに、試合を実際に進めて出たイベントでも見る。
 */

const HOLE = '\u{1F573}\uFE0F';

/** 0 番が人間（1P）、1 番が CPU。 */
const ROSTER: Roster = localRoster(1, ['normal']);

/** 1 tick ぶんのイベントで出す通知（出す順）。 */
function noticesOf(events: readonly SimEvent[], world: WorldState, roster: Roster = ROSTER): string[] {
  const shown: string[] = [];
  new Presenter(undefined, { show: (message) => shown.push(message) }, () => roster).consume(events, world);
  return shown;
}

/** 壊せるブロックとアイテムを片付けた盤面。0 番は (3, 5) で右を向く。 */
function arena(animals: [string, string]): { world: WorldState; first: PlayerState; second: PlayerState } {
  const world = makeWorld(2468, animals);
  clearBoard(world);
  world.items = [];
  const [first, second] = world.players as [PlayerState, PlayerState];
  first.position = centerOf({ col: 3, row: 5 });
  first.facing = 'right';
  second.position = centerOf({ col: 19, row: 13 });
  return { world, first, second };
}

function putItem(world: WorldState, cell: Cell, kind: ItemKind): void {
  world.items.push({ id: world.ids.take(), cell, kind });
}

/** 試合を 1 tick ずつ進め、通知を控える（画面のループと同じく毎 tick 渡す）。 */
function recorder(world: WorldState, roster: Roster = ROSTER): (inputs?: ReadonlyMap<PlayerId, PlayerInput>) => string[] {
  const shown: string[] = [];
  const presenter = new Presenter(undefined, { show: (message) => shown.push(message) }, () => roster);
  const sim = new Simulation();
  return (inputs = sameForAll(world, IDLE_INPUT)) => {
    const before = shown.length;
    presenter.consume(sim.step(world, inputs), world);
    return shown.slice(before);
  };
}

const effect = (target: PlayerId, kind: Extract<SimEvent, { type: 'effectApplied' }>['effect'], pushedBy: PlayerId | null = null): SimEvent => ({
  type: 'effectApplied',
  target,
  effect: kind,
  pushedBy,
});

describe('アイテム', () => {
  it('バナナ・たまねぎ・うんこは動物の名前で、効果が2倍の動物にはそう添える（原型の applyItem L1609・L1613・L1633）', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(
      noticesOf([effect(0, 'slide'), effect(1, 'slide'), effect(0, 'stun'), effect(1, 'reverse'), effect(0, 'weak')], world),
    ).toEqual([
      '🍌 ぞう すべる！',
      '🍌 かえる すべる！（2倍！）',
      '🧅 ぞう 涙で動けない！',
      '💩 かえる そうさ反転！（2倍！）',
      '💩 ぞう 爆風1マス！',
    ]);
  });

  it('チキンは、とくぎの名前と、2回ぶん溜まる動物なら回数（原型 L1619）。良いアイテムは何も出さない', () => {
    const { world } = arena(['elephant', 'frog']);
    const events: SimEvent[] = [
      { type: 'itemTaken', cell: { col: 1, row: 1 }, kind: 'chicken', taker: 0, swept: false },
      { type: 'itemTaken', cell: null, kind: 'chicken', taker: 1, swept: false },
      { type: 'itemTaken', cell: { col: 1, row: 1 }, kind: 'fire', taker: 0, swept: false },
    ];
    expect(noticesOf(events, world)).toEqual(['🍗 ぞう とくぎ「突進」！', '🍗 かえる とくぎ「粘膜爆弾」 ×2！']);
  });

  it('跳び上がる・撒く身ぶりは知らせない（原型は applyItem を通らない）', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(noticesOf([effect(0, 'leap'), effect(0, 'scattering')], world)).toEqual([]);
  });

  it('盤面にいない番号は、番号で呼ぶ', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(noticesOf([effect(3 as PlayerId, 'slide')], world)).toEqual(['🍌 4P すべる！']);
  });
});

describe('葱ボン', () => {
  it('盤面で倒れて外周へ回った人間には、外周から撃てと出す（原型の toNegibon L2269。CPU には出さない）', () => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    sendToLane(world, world.players[0]!);
    sendToLane(world, world.players[1]!);
    const down: SimEvent[] = [
      { type: 'playerDown', target: 0, by: 1, at: { x: 1.5, y: 1.5 } },
      { type: 'playerDown', target: 1, by: 0, at: { x: 2.5, y: 1.5 } },
    ];
    expect(noticesOf(down, world)).toEqual(['🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ']);
  });

  it('外周が閉じていて退場したなら、出さない', () => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    world.players[0]!.life = OUT;
    expect(noticesOf([{ type: 'playerDown', target: 0, by: 1, at: { x: 1.5, y: 1.5 } }], world)).toEqual([]);
  });

  it('入れ替わりは原型の label で呼ぶ（人間は番号、CPU は動物の名前。原型の negiHit L2354）。当たった側が人間なら、外周へ送る通知を先に出す', () => {
    const { world } = arena(['elephant', 'frog']);
    const at = { x: 5.5, y: 5.5 };
    expect(noticesOf([{ type: 'revived', player: 0, replaced: 1, at }], world)).toEqual([
      '🌿 1P 復活！ かえる が葱ボンへ',
    ]);
    expect(noticesOf([{ type: 'revived', player: 1, replaced: 0, at }], world)).toEqual([
      '🌿 ぞう は葱ボンへ！ 外周から葱を撃って復活をねらえ',
      '🌿 かえる 復活！ 1P が葱ボンへ',
    ]);
  });

  it('通信対戦で抜けて CPU に替わったプレイヤーは、入れ替わりの通知で元の番号のまま呼ぶ（原型 L3793 は label を書き換えない）', () => {
    const { world } = arena(['elephant', 'frog']);
    const roster = lanRoster([0, 1], [0, 1], 0, [1], () => 'normal');
    const at = { x: 5.5, y: 5.5 };
    expect(noticesOf([{ type: 'revived', player: 1, replaced: 0, at }], world, roster)).toEqual([
      '🌿 ぞう は葱ボンへ！ 外周から葱を撃って復活をねらえ',
      '🌿 2P 復活！ 1P が葱ボンへ',
    ]);
    const shown = noticesOf([{ type: 'revived', player: 0, replaced: 1, at }], world, roster);
    expect(shown).toEqual(['🌿 1P 復活！ 2P が葱ボンへ']);
    expect(shown.join('')).not.toContain('かえる');
  });

  it('外周が閉じたら、退場したと出す（原型の negibonCutoff L2362）', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(noticesOf([{ type: 'lanesClosed', players: [1] }], world)).toEqual(['🌿 葱ボン 退場！ もう復活できない']);
  });

  it('試合で倒れて外周へ回ると出し、CPU には出さない', () => {
    for (const [roster, expected] of [
      [ROSTER, ['🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ']],
      [localRoster(0, ['normal', 'normal']), []],
    ] as const) {
      const { world, first: rabbit } = arena(['rabbit', 'frog']);
      rabbit.hp = 1;
      rabbit.invulnerableUntil = tick(0);
      addBlast(world, cellOf(rabbit.position), 1, true);
      expect(recorder(world, roster)()).toEqual(expected);
      expect(rabbit.life.kind).toBe('negibon');
    }
  });
});

describe('画面のループと同じ渡し方', () => {
  it('進める前に控えた盤面を渡しても、通知は進めたあとの盤面で決まる（試合の窓口は盤面を書き換えて進め、差し替えるのは待ちが尽きた tick だけ）', () => {
    // `Shell` の `#step` は、進める前に `hud.world` を控えて `consume` に渡す。倒れて外周へ回ったかは、その盤面で見る。
    const session = new GameSession(defaultMatchConfig(5, ['rabbit', 'frog']));
    for (const player of session.world.players) session.attach(new IdleInputSource(player.id));
    const rabbit = session.world.players[0]!;
    rabbit.hp = 1;
    rabbit.invulnerableUntil = tick(0);
    addBlast(session.world, cellOf(rabbit.position), 1, true);
    const shown: string[] = [];
    const presenter = new Presenter(undefined, { show: (message) => shown.push(message) }, () => ROSTER);
    const before = session.world;
    presenter.consume(session.tick(), before);
    expect(session.world).toBe(before);
    expect(shown).toEqual(['🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ']);
  });
});

describe('舌', () => {
  it('焼き切れたら伸ばせる長さを出し、たまねぎの通知は出さない（原型の tongueBurnCheck L2488 は applyItem を通らない）', () => {
    const { world, first: frog } = arena(['frog', 'rabbit']);
    const step = recorder(world);
    frog.action = new TongueAction({ col: 3, row: 5 }, 'right');
    let shown: string[] = [];
    for (let t = 0; t < 60 && shown.length === 0; t += 1) {
      if (t === 40) addBlast(world, { col: 5, row: 5 }, 1, false);
      shown = step();
    }
    expect(shown).toEqual(['👅🔥 かえる の舌が焼き切れた！このラウンドは 1マスまで']);
  });

  it('焼き切れた知らせのすぐあとの泣く状態には、たまねぎの通知を出さない（対照：ほかのプレイヤーの泣く状態には出す）', () => {
    const { world } = arena(['elephant', 'frog']);
    const burnt: SimEvent = { type: 'burntOff', player: 1, cell: { col: 2, row: 1 } };
    expect(noticesOf([burnt, effect(1, 'stun')], world)).toEqual(['👅🔥 かえる の舌が焼き切れた！このラウンドは 10マスまで']);
    expect(noticesOf([burnt, effect(0, 'stun')], world)).toEqual([
      '👅🔥 かえる の舌が焼き切れた！このラウンドは 10マスまで',
      '🧅 ぞう 涙で動けない！',
    ]);
  });

  it('根元まで焼けた舌を出そうとすると、戻るまでの秒を切り上げて出す（原型の startTongue L2498）', () => {
    const { world } = arena(['frog', 'rabbit']);
    world.actors.push(new BurntTongueActor(0, 0));
    const step = recorder(world);
    expect(step()).toEqual([]);
    expect(step(onlyFor(world, 0, press({ action: true })))).toEqual(['👅🔥 かえる の舌は焼け落ちてる（10秒で1マス戻る）']);
    expect(noticesOf([{ type: 'techniqueRefused', player: 0, wait: tick(61) }], world)).toEqual([
      '👅🔥 かえる の舌は焼け落ちてる（2秒で1マス戻る）',
    ]);
  });

  it('焼けた舌が1マス戻ると、戻った長さを出す（原型 L4307）', () => {
    const { world } = arena(['frog', 'rabbit']);
    const scar = new BurntTongueActor(0, 3);
    // 戻るまでの残りを 1 tick にする（10 秒 = 600 tick）。
    for (let i = 0; i < 599; i += 1) scar.tick();
    world.actors.push(scar);
    expect(recorder(world)()).toEqual(['👅 かえる の舌が1マス回復（4マス）']);
    expect(noticesOf([{ type: 'reachRestored', player: 0, reach: 10 }], world)).toEqual(['👅 かえる の舌が1マス回復（10マス）']);
  });
});

describe('穴ととくぎ', () => {
  it('掘り終えた・はまった（原型の updateDigging L2575・pitfallCheck L2597）。掘り始めは出さない', () => {
    const { world } = arena(['mole', 'rabbit']);
    const events: SimEvent[] = [
      { type: 'techniqueMoment', player: 0, moment: 'digStarted' },
      { type: 'techniqueMoment', player: 0, moment: 'pitDug' },
      effect(1, 'pitfall'),
    ];
    expect(noticesOf(events, world)).toEqual([`${HOLE} もぐら 落とし穴をしかけた`, `${HOLE} うさぎ 落とし穴！ 3秒うごけない`]);
  });

  it('とくぎを使ったら、とくぎの絵文字と名前（原型の useSpecial L2611。CPU のとくぎでも出す）。通常技では出さない', () => {
    const { world } = arena(['elephant', 'frog']);
    const events: SimEvent[] = [
      { type: 'techniqueUsed', player: 0, special: true },
      { type: 'techniqueUsed', player: 1, special: true },
      { type: 'techniqueUsed', player: 0, special: false },
    ];
    expect(noticesOf(events, world)).toEqual(['🐗 ぞう 突進！', '🟢 かえる 粘膜爆弾！']);
  });
});

describe('体当たりと鼻水', () => {
  it('押しつけたアイテムは、それぞれの通知のあとに何個ぶつけたかを出す（原型の updateCharge L2879-2880）', () => {
    const { world } = arena(['elephant', 'frog']);
    const events: SimEvent[] = [
      effect(1, 'stun', 0),
      effect(1, 'reverse', 0),
      { type: 'techniqueMoment', player: 0, moment: 'rammed' },
      { type: 'playerHurt', target: 1, by: 0, amount: 2 },
    ];
    expect(noticesOf(events, world)).toEqual([
      '🧅 かえる 涙で動けない！（2倍！）',
      '💩 かえる そうさ反転！（2倍！）',
      '💥 ぞう が かえる に 2個 ぶつけた！',
    ]);
  });

  it('押しつけたプレイヤーが違えば、別々に数える', () => {
    const world = makeWorld(1, ['elephant', 'frog', 'elephant']);
    const events: SimEvent[] = [effect(1, 'stun', 0), effect(1, 'slide', 2)];
    expect(noticesOf(events, world, localRoster(1, ['normal', 'normal']))).toEqual([
      '🧅 かえる 涙で動けない！（2倍！）',
      '💥 ぞう が かえる に 1個 ぶつけた！',
      '🍌 かえる すべる！（2倍！）',
      '💥 ぞう が かえる に 1個 ぶつけた！',
    ]);
  });

  it('同じプレイヤーが押しつけても、相手が違えば別々に数える', () => {
    const world = makeWorld(1, ['elephant', 'frog', 'rabbit']);
    const events: SimEvent[] = [effect(1, 'stun', 0), effect(2, 'slide', 0)];
    expect(noticesOf(events, world, localRoster(1, ['normal', 'normal']))).toEqual([
      '🧅 かえる 涙で動けない！（2倍！）',
      '💥 ぞう が かえる に 1個 ぶつけた！',
      '🍌 うさぎ すべる！',
      '💥 ぞう が うさぎ に 1個 ぶつけた！',
    ]);
  });

  it('試合で押しつけると、何個ぶつけたかを出す', () => {
    const { world, first: elephant, second: rabbit } = arena(['elephant', 'rabbit']);
    for (const player of world.players) player.invulnerableUntil = tick(9999);
    rabbit.position = centerOf({ col: 8, row: 5 });
    putItem(world, { col: 4, row: 5 }, 'onion');
    putItem(world, { col: 5, row: 5 }, 'banana');
    elephant.action = new ChargeAction('right');
    const step = recorder(world);
    let shown: string[] = [];
    for (let t = 0; t < 120 && shown.length === 0; t += 1) shown = step();
    expect(shown).toEqual(['🧅 うさぎ 涙で動けない！', '🍌 うさぎ すべる！', '💥 ぞう が うさぎ に 2個 ぶつけた！']);
  });

  it('体当たりで進む間に取った良いアイテムは、吸い込んだと出す。チキンはとくぎの通知のあとに出す（原型の chargeSweep L2818）', () => {
    const { world, first: elephant } = arena(['elephant', 'rabbit']);
    putItem(world, { col: 4, row: 5 }, 'fire');
    putItem(world, { col: 6, row: 5 }, 'chicken');
    elephant.action = new ChargeAction('right');
    const step = recorder(world);
    const shown: string[] = [];
    for (let t = 0; t < 60; t += 1) shown.push(...step());
    expect(shown).toEqual([
      '🔥 ぞう 突進で 火力+1 を吸い込んだ！',
      '🍗 ぞう とくぎ「突進」！',
      '🍗 ぞう 突進で チキン を吸い込んだ！',
    ]);
  });

  it('体当たりしていなければ、足元で拾っても吸い込んだとは出さない', () => {
    const { world, first: elephant } = arena(['elephant', 'rabbit']);
    putItem(world, cellOf(elephant.position), 'fire');
    expect(recorder(world)()).toEqual([]);
    expect(world.items).toEqual([]);
  });

  it('吸い込んだと出すのは、吸い込んだ印のある取得だけ（体当たりの最中の盤面でも、印の無い取得には出さない）', () => {
    const { world, first: elephant } = arena(['elephant', 'rabbit']);
    elephant.action = new ChargeAction('right');
    const events: SimEvent[] = [
      { type: 'itemTaken', cell: { col: 4, row: 5 }, kind: 'fire', taker: 0, swept: true },
      { type: 'itemTaken', cell: { col: 5, row: 5 }, kind: 'shoe', taker: 0, swept: false },
      { type: 'itemTaken', cell: null, kind: 'bomb', taker: 0, swept: false },
    ];
    expect(noticesOf(events, world)).toEqual(['🔥 ぞう 突進で 火力+1 を吸い込んだ！']);
    elephant.action = null;
    expect(noticesOf([{ type: 'itemTaken', cell: { col: 4, row: 5 }, kind: 'shoe', taker: 0, swept: true }], world)).toEqual([
      '👟 ぞう 突進で スピード+ を吸い込んだ！',
    ]);
  });

  describe('体当たりが終わった tick（吸い込んだと出すのは体当たりの最中だけ。原型 L2818）', () => {
    /** 残りが 1 tick の体当たり。右の柱の手前で 299 回進め（柱に当たる回は進まずに残りだけが減る）、残りを 1 にする。 */
    function lastCharge(): ChargeAction {
      const charge = new ChargeAction('right');
      const dummy = makeWorld(1, ['elephant', 'rabbit']);
      const body = dummy.players[0]!;
      for (let i = 0; i < 299; i += 1) {
        body.position = centerOf({ col: 21, row: 1 });
        expect(charge.tick(dummy, body).done).toBe(true);
      }
      return charge;
    }
    const itemAt = (world: WorldState, col: number, row: number): boolean =>
      world.items.some((item) => item.cell.col === col && item.cell.row === row);

    it('時間切れで終わった tick に歩いて拾ったものには出さない（最後の1歩はマスの手前で止まり、ふつうの移動で拾う。原型 L4312-4317・L4342）', () => {
      const { world, first: elephant } = arena(['elephant', 'rabbit']);
      elephant.position = { x: 3.78, y: 5.5 };
      elephant.action = lastCharge();
      putItem(world, { col: 4, row: 5 }, 'fire');
      const shown = recorder(world)(onlyFor(world, 0, press({ right: true })));
      expect(elephant.action).toBeNull();
      expect(itemAt(world, 4, 5)).toBe(false);
      expect(shown.filter((text) => text.includes('吸い込んだ'))).toEqual([]);
    });

    it('最後の1歩でマスに入ったなら、吸い込んだと出す', () => {
      const { world, first: elephant } = arena(['elephant', 'rabbit']);
      elephant.position = { x: 3.81, y: 5.5 };
      elephant.action = lastCharge();
      putItem(world, { col: 4, row: 5 }, 'fire');
      const shown = recorder(world)(onlyFor(world, 0, press({ right: true })));
      expect(elephant.action).toBeNull();
      expect(shown).toEqual(['🔥 ぞう 突進で 火力+1 を吸い込んだ！']);
    });

    it('柱で終わった tick に歩いて拾ったものには出さない（原型は柱に当たると突進を消して戻り、ふつうに動いて拾う。L2863・L4342）', () => {
      const { world, first: elephant } = arena(['elephant', 'rabbit']);
      // 上の柱 (4, 4) の手前で上へ体当たりを始め、最初の1歩で柱に当たって終わる。同じ tick に右へ歩いてマス 5 で拾う。
      elephant.position = { x: 4.97, y: 5.5 };
      elephant.facing = 'up';
      elephant.action = new ChargeAction('up');
      putItem(world, { col: 5, row: 5 }, 'fire');
      const shown = recorder(world)(onlyFor(world, 0, press({ right: true })));
      expect(elephant.action).toBeNull();
      expect(itemAt(world, 5, 5)).toBe(false);
      expect(shown.filter((text) => text.includes('吸い込んだ'))).toEqual([]);
    });
  });

  it('鼻水は、すぐ前に消した爆弾の数と、流したうんこの数を出す。何も消さなければ出さない（原型の elephantSnot L3034-3036）', () => {
    const { world } = arena(['elephant', 'frog']);
    const both: SimEvent[] = [
      { type: 'techniqueUsed', player: 0, special: false },
      { type: 'bombDoused', cell: { col: 4, row: 5 }, owner: 1 },
      { type: 'bombDoused', cell: { col: 5, row: 5 }, owner: 1 },
      { type: 'sprayed', player: 0, cells: [{ col: 4, row: 5 }, { col: 5, row: 5 }], facing: 'right', washed: 1 },
    ];
    expect(noticesOf(both, world)).toEqual(['💧 ぞう 鼻水で 爆弾2個の火を消した・うんこ1個を流した！']);
    expect(
      noticesOf([{ type: 'sprayed', player: 0, cells: [{ col: 4, row: 5 }], facing: 'right', washed: 0 }], world),
    ).toEqual([]);
  });

  it('試合で吹くと、消したものを出す', () => {
    const { world, second: rabbit } = arena(['elephant', 'rabbit']);
    const bomb = placeBombAt(world, rabbit, { col: 4, row: 5 });
    if (bomb === undefined) throw new Error('爆弾を置けなかった');
    bomb.fuse = tick(999);
    putItem(world, { col: 5, row: 5 }, 'poop');
    const step = recorder(world);
    step();
    expect(step(onlyFor(world, 0, press({ action: true })))).toEqual(['💧 ぞう 鼻水で 爆弾1個の火を消した・うんこ1個を流した！']);
  });
});

describe('延長戦と決着', () => {
  it('延長戦に入ったら、わけと延長戦の決まりを出す（原型の enterSuddenDeath L4463）', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(noticesOf([{ type: 'suddenDeath', reason: 'timeUp', players: [0, 1] }], world)).toEqual([
      '⚡ サドンデス！（時間切れ） 全員HP1・💣13・🔥13・👟13・60秒',
    ]);
  });

  it('全員が同じ tick に倒れて延長戦に入ったら、わけは「同時にやられた」。盤面へ戻った人間には、外周へ回った通知を出さない', () => {
    // 原型はこのとき葱ボンへの通知を出してから延長戦の通知で置き換えるので、見える通知は同じ（`Presenter` の説明）。
    const session = new GameSession(defaultMatchConfig(5, ['rabbit', 'frog']));
    for (const player of session.world.players) session.attach(new IdleInputSource(player.id));
    for (const player of session.world.players) {
      player.hp = 1;
      player.invulnerableUntil = tick(0);
      addBlast(session.world, cellOf(player.position), player.id, true);
    }
    const shown: string[] = [];
    const presenter = new Presenter(undefined, { show: (message) => shown.push(message) }, () => ROSTER);
    const before = session.world;
    presenter.consume(session.tick(), before);
    expect(session.world.suddenDeath).toBe(true);
    expect(session.world.players.map((player) => player.life.kind)).toEqual(['alive', 'alive']);
    expect(shown).toEqual(['⚡ サドンデス！（同時にやられた） 全員HP1・💣13・🔥13・👟13・60秒']);
  });

  it('ラウンドと試合の決着は通知に出さない（幕が出す）', () => {
    const { world } = arena(['elephant', 'frog']);
    expect(noticesOf([{ type: 'roundEnded', round: 1, winner: 0 }], world)).toEqual([]);
    expect(noticesOf([{ type: 'roundEnded', round: 2, winner: null }], world)).toEqual([]);
    expect(
      noticesOf(
        [
          { type: 'roundEnded', round: 3, winner: 0 },
          { type: 'matchEnded', champion: 0 },
        ],
        world,
      ),
    ).toEqual([]);
  });
});

it('同じ tick の通知は、起きた順に出す（通知は1枚で置き換わるので、順が違うと見える通知が原型と変わる）', () => {
  const { world } = arena(['elephant', 'frog']);
  const events: SimEvent[] = [
    { type: 'itemTaken', cell: { col: 1, row: 1 }, kind: 'chicken', taker: 0, swept: false },
    { type: 'techniqueUsed', player: 0, special: true },
    { type: 'lanesClosed', players: [1] },
  ];
  expect(noticesOf(events, world)).toEqual(['🍗 ぞう とくぎ「突進」！', '🐗 ぞう 突進！', '🌿 葱ボン 退場！ もう復活できない']);
});
