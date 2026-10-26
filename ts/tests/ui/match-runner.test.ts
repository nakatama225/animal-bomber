import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { LocalMatch } from '../../src/app/MatchRunner.js';
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
