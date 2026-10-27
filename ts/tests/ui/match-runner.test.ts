import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { LocalMatch } from '../../src/app/MatchRunner.js';
import { tick } from '../../src/domain/core/Tick.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';

/** 誰も操作しなければ、1秒で時間切れになり、延長戦も決まらなければ決着のあとの待ちになる試合。 */
function shortSession(): GameSession {
  return new GameSession({ ...defaultMatchConfig(9, ['rabbit', 'frog']), roundLimit: tick(60) });
}

/** 決着のあとの待ちまで進める。 */
function toIntermission(session: GameSession): void {
  for (let i = 0; i < 20_000 && !session.betweenRounds; i += 1) session.tick();
  expect(session.betweenRounds).toBe(true);
}

describe('1台の試合を止めているか（押してすぐ離したキーを毎フレーム忘れる間）', () => {
  it('ポーズ中と、試合が決まったあとは止めている（ラウンドの幕の間は下のテスト）。ラウンドの最中は止めていない', () => {
    const session = new GameSession(defaultMatchConfig(9, ['rabbit', 'frog']));
    const match = new LocalMatch(session, []);
    expect(match.stopped).toBe(false);
    match.togglePause();
    expect(match.stopped).toBe(true);
    match.togglePause();
    expect(match.stopped).toBe(false);
    // 決まる前は進め、試合の最中に数える。
    expect([match.ready, match.inProgress]).toEqual([true, true]);
    // 決まった試合は止めている（押したキーを残しても読まれない）。
    session.match.finished = true;
    expect(match.stopped).toBe(true);
    expect(match.paused).toBe(false);
    // 決まった試合も進めない（原型の loop も play の間だけ update を呼ぶ。進めると、優勝の幕の下で粒子と揺れが動き続ける）。
    expect([match.ready, match.inProgress]).toEqual([false, false]);
  });

  it('ラウンドの幕の間（決着のあとの待ち）は止めていて、進めず、試合の最中に数えない（曲を止める）。送ると戻る', () => {
    const session = shortSession();
    const match = new LocalMatch(session, []);
    expect([match.stopped, match.ready, match.inProgress]).toEqual([false, true, true]);
    toIntermission(session);
    expect([match.stopped, match.ready, match.inProgress]).toEqual([true, false, false]);
    expect(match.paused).toBe(false);
    match.startNextRound();
    expect(session.betweenRounds).toBe(false);
    expect([match.stopped, match.ready, match.inProgress]).toEqual([false, true, true]);
  });
});

describe('1台の試合を止める', () => {
  it('止められるのはラウンドの最中だけ。決着のあとの待ちの間（幕が出ている間）と決まった試合では何もしない（原型 L4215）', () => {
    const session = shortSession();
    const match = new LocalMatch(session, []);
    toIntermission(session);
    match.togglePause();
    expect(match.paused).toBe(false);
    // 幕を送って次のラウンドが始まれば、また止められる。
    match.startNextRound();
    match.togglePause();
    expect(match.paused).toBe(true);
  });
});

describe('ラウンドの幕を送る（原型の advanceBanner の startRound）', () => {
  it('次のラウンドの盤面を作る。待ちの最中でなければ何もしない（ラウンドの最中に盤面を替えない）', () => {
    const session = shortSession();
    const match = new LocalMatch(session, []);
    const first = session.world;
    match.startNextRound();
    expect(session.world).toBe(first);
    toIntermission(session);
    const decided = session.world;
    match.startNextRound();
    expect(session.world).not.toBe(decided);
    expect(session.match.round).toBe(2);
    expect(session.world.now).toBe(0);
  });
});
