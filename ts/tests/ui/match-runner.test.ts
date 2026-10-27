import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { LocalMatch } from '../../src/app/MatchRunner.js';
import { tick } from '../../src/domain/core/Tick.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';

describe('1台の試合を止めているか（押してすぐ離したキーを毎フレーム忘れる間）', () => {
  it('ポーズ中と、試合が決まったあとは止めている。そのほかは止めていない', () => {
    const session = new GameSession(defaultMatchConfig(9, ['rabbit', 'frog']));
    const match = new LocalMatch(session, []);
    expect(match.stopped).toBe(false);
    match.togglePause();
    expect(match.stopped).toBe(true);
    match.togglePause();
    expect(match.stopped).toBe(false);
    // 決まった試合は進めても何も起きない（GameSession.tick が空を返す）。押したキーを残しても読まれない。
    session.match.finished = true;
    expect(match.stopped).toBe(true);
    expect(match.paused).toBe(false);
  });
});

describe('1台の試合を止める', () => {
  it('止められるのはラウンドの最中だけ。決着のあとの待ちの間（幕が出ている間）と決まった試合では何もしない（原型 L4215）', () => {
    const session = new GameSession({ ...defaultMatchConfig(9, ['rabbit', 'frog']), roundLimit: tick(60) });
    const match = new LocalMatch(session, []);
    // 誰も操作しなければ、1秒で時間切れになり、延長戦も決まらなければ決着のあとの待ちになる。
    for (let i = 0; i < 20_000 && !session.betweenRounds; i += 1) session.tick();
    expect(session.betweenRounds).toBe(true);
    match.togglePause();
    expect(match.paused).toBe(false);
    // 待ちが尽きて次のラウンドが始まれば、また止められる。
    while (session.betweenRounds) session.tick();
    match.togglePause();
    expect(match.paused).toBe(true);
  });
});
