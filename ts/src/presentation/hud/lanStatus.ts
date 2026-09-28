import type { PlayerId } from '../../domain/state/PlayerState.js';
import type { LanPhase } from '../../net/LockstepClient.js';

/**
 * 止まったあと（ずれ・切断・断られた）の案内。
 *
 * ⚠️ 「読み込み直す」だけでは足りない。中継は、前の試合にいた人が1人でもつながっている間は
 * 新しい接続を断る（途中から入った人の入力を、誰の試合にも入れられないため）。
 * 全員が閉じてからでないと、次の試合に入れない。
 * 試合が決まったあとは、閉じずに「もういっかい」で次の試合を始められる（`FINISHED_HOST`）。
 */
export const START_OVER = 'もう一度遊ぶときは、全員がページを閉じてから開き直す';

/** 試合が決まったあとの、ホストへの案内。幕の「もういっかい」で、接続を保ったまま次の試合を始める。 */
const FINISHED_HOST = '試合が終わった。「もういっかい」で、同じ人・同じ設定のまま次の試合を始める';

/** 試合が決まったあとの、ゲストへの案内。ゲストの幕にはボタンが無い（原型も、次の試合を始めるのはホストだけ）。 */
const FINISHED_GUEST = '試合が終わった。1P（ホスト）が「もういっかい」を押すと、次の試合が始まる';

/**
 * 通信対戦の、いまの様子を1行の文にする。画面の上に出す。
 *
 * 画面の組み立て（どこに出すか）とは分けてある。文だけならブラウザ無しで確かめられる。
 *
 * @param waiting 「操作を待っている」と出す人。省くと、いま待っている人全員。
 *   一瞬の待ちまで出すと文がちらつくので、画面では `WaitingNotice` を通した値を渡す
 * @returns 出す文。何も出さなくてよいときは空文字
 */
export function describeLanPhase(
  phase: LanPhase,
  waiting: readonly PlayerId[] = phase.kind === 'playing' ? phase.driver.waitingFor() : [],
): string {
  switch (phase.kind) {
    case 'connecting':
    case 'lobby':
      // 始まる前は、ロビーの画面（`platform/ui/LobbyView.ts`）が様子を出す。
      return '';
    case 'playing': {
      const desync = phase.driver.desync;
      if (desync !== null) {
        return `端末どうしで試合がずれたので止めた（tick ${desync.tick}）。${START_OVER}`;
      }
      if (waiting.length > 0) return `${waiting.map(label).join('・')} の操作を待っている`;
      if (!phase.session.match.finished) return '';
      return phase.seat === 0 ? FINISHED_HOST : FINISHED_GUEST;
    }
    case 'failed':
      return `${phase.reason}。${START_OVER}`;
  }
}

/**
 * 待ちの案内を出すまでに、待ちが続いたフレーム数。1秒に60回描く画面で約0.5秒。
 *
 * 入力は数 tick 先の分まで送り合っているので、ふだんは待たない。回線が一瞬詰まっただけの
 * 待ちまで出すと、文が出たり消えたりする。続いたときだけ出す。
 */
const WAIT_NOTICE_FRAMES = 30;

/**
 * 「操作を待っている」の案内を、待ちがしばらく続いたときだけ出すための数え役。
 *
 * 描くたびに、いま待っている人を渡す。
 */
export class WaitingNotice {
  #frames = 0;

  /** @returns 案内に出す人。まだ出さないときは空 */
  observe(waiting: readonly PlayerId[]): readonly PlayerId[] {
    if (waiting.length === 0) {
      this.#frames = 0;
      return [];
    }
    this.#frames += 1;
    return this.#frames >= WAIT_NOTICE_FRAMES ? waiting : [];
  }
}

/** プレイヤー番号の画面での呼び方（0 → 1P）。 */
function label(playerId: PlayerId): string {
  return `${playerId + 1}P`;
}
