import type { PlayerId } from '../../domain/state/PlayerState.js';
import type { LanPhase } from '../../net/LockstepClient.js';

/**
 * 止まったあとの案内。
 *
 * ⚠️ 「読み込み直す」だけでは足りない。中継は、前の試合にいた人が1人でもつながっている間は
 * 新しい接続を断る（途中から入った人の入力を、誰の試合にも入れられないため）。
 * 全員が閉じてからでないと、次の試合に入れない。
 */
const START_OVER = 'もう一度遊ぶときは、全員がページを閉じてから開き直す';

/**
 * 通信対戦の、いまの様子を1行の文にする。画面の上に出す。
 *
 * 画面の組み立て（どこに出すか）とは分けてある。文だけならブラウザ無しで確かめられる。
 * タイトルやロビーの画面（段階10）ができるまでの、最小の案内。
 *
 * @returns 出す文。何も出さなくてよいときは空文字
 */
export function describeLanPhase(phase: LanPhase): string {
  switch (phase.kind) {
    case 'connecting':
      return '中継サーバにつないでいる…';
    case 'lobby': {
      const present = `つながっている人：${phase.present.map(label).join('・')}`;
      const next = phase.seat === 0 ? '全員そろったら「はじめる」を押す' : '1P が始めるのを待っている';
      return `あなたは ${label(phase.seat)}。${present}。${next}`;
    }
    case 'playing': {
      const desync = phase.driver.desync;
      if (desync !== null) {
        return `端末どうしで試合がずれたので止めた（tick ${desync.tick}）。${START_OVER}`;
      }
      const waiting = phase.driver.waitingFor();
      if (waiting.length > 0) return `${waiting.map(label).join('・')} の操作を待っている`;
      return phase.session.match.finished ? `試合が終わった。${START_OVER}` : '';
    }
    case 'failed':
      return `${phase.reason}。${START_OVER}`;
  }
}

/** プレイヤー番号の画面での呼び方（0 → 1P）。 */
function label(playerId: PlayerId): string {
  return `${playerId + 1}P`;
}
