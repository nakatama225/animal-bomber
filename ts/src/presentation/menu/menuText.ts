import { CPU_LEVELS } from '../../ai/CpuLevel.js';
import { lookOf } from '../../content/animals.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';
import { numberedName } from '../hud/roster.js';
import { formatSeconds } from './choices.js';
import type { LanSetup } from './lanSetup.js';
import type { ManualSpan } from './manual.js';
import type { PlayMode } from './localSetup.js';
import type { SoundSetting } from './MenuFlow.js';

/**
 * 試合の外の画面（起動の幕・タイトル・キャラ選び・ルール・設定とマニュアルと更新履歴・LAN の画面・ロビー）と、
 * 確認の画面に出す文。
 *
 * 文の正は Python 版（`py/src/animal_bomber/presentation/menu/screens.py`・`choices.py`）。どちらも原型の文を
 * 写したもので、リポジトリの文の決まりで書かない語に当たる所だけを言い換えてある（この画面の文には当たる所が無い）。
 * ただし LAN の画面の注記の2文目は、Python 版がブラウザのページでないために書き換えた文なので、原型の文に戻してある
 * （`LAN_NOTE`）。
 * 写す側（`platform/ui/MenuView.ts`・`platform/ui/LobbyView.ts`・`platform/ui/Splash.ts`・`platform/ui/ConfirmDialog.ts`）は、
 * ここを読んで要素に写すだけにする。
 * マニュアルと更新履歴の文は `manual.ts`、キャラ選びのキーの案内は `keyHints.ts`、動物の説明は
 * `content/animals.ts` にある。
 */

/** タイトルと起動の幕のロゴ（原型 L247・L554）。 */
export const LOGO = 'Nakatando';

/** ロゴの下の題（原型 L248・L555）。 */
export const SUBTITLE = '🐰💣🐘 どうぶつボンバー';

/** 起動の幕の、点滅する案内（原型 L558）。 */
export const SPLASH_PROMPT = 'クリック か なにかキーを押す';

/** 画面の頭の戻るボタン（原型 L303・L318・L355）。 */
export const BACK_LABEL = '← もどる';

/** タイトルの項目で選ぶもの。3つの遊び方と、LAN対戦と、設定・マニュアル・更新履歴。 */
export type TitleChoice = PlayMode | 'lan' | 'manual';

/** タイトルの項目1つ（原型の `.mbtn`）。 */
export interface TitleItem {
  readonly choice: TitleChoice;
  readonly icon: string;
  readonly title: string;
  /** 題の下の小さい字（原型の `.md`）。 */
  readonly detail: string;
  /** 小さい形で出すか（原型の `.mbtn.sub`。LAN対戦と、設定・マニュアル・更新履歴）。 */
  readonly small: boolean;
}

/** タイトルの項目（原型 L252-261。上から順に）。 */
export const TITLE_ITEMS: readonly TitleItem[] = [
  { choice: 'solo', icon: '🕹️', title: '1人 vs CPU×3', detail: 'CPU の強さは あとで1体ずつ決められる', small: false },
  { choice: 'duo', icon: '👥', title: '2人 vs CPU×2', detail: '1P と 2P が協力せず殴り合ってもいい', small: false },
  { choice: 'versus', icon: '⚔️', title: '2人タイマン', detail: 'CPU なし。1P vs 2P だけ', small: false },
  { choice: 'lan', icon: '📶', title: 'LAN対戦', detail: '同じ Wi-Fi 内の別の Mac と対戦する（最大4人）', small: true },
  {
    choice: 'manual',
    icon: '📖',
    title: '設定・マニュアル・更新履歴',
    detail: 'サウンド設定／そうさとルールの説明／バージョンの履歴',
    small: true,
  },
];

/** キャラ選びの見出しと、右の小さい字（原型 L304-305）。 */
export const PICK_HEADING = 'キャラをえらぶ';
export const PICK_STEP = 'STEP 1 / 2';

/** キャラ選びの下のボタン（原型 L309）。 */
export const NEXT_LABEL = 'つぎへ ▶';

/**
 * キャラ選びの、人間1人ぶんの段の見出し（原型の `${k.toUpperCase()} のどうぶつ`。L6004）。
 *
 * 原型の鍵（`p1`・`p2`）を大文字にした形なので「P1」になる（名札の「1P」とは並びが逆。原型のまま）。
 */
export function pickerHeading(human: 0 | 1): string {
  return `P${human + 1} のどうぶつ`;
}

/** ルールの画面の見出しと、右の小さい字（原型 L319-320）。 */
export const RULES_HEADING = 'ルールをきめる';
export const RULES_STEP = 'STEP 2 / 2';

/** ルールの画面の、体力の行の見出し（原型 L5972-5974）。 */
export const HIT_LABELS: Readonly<Record<'p1' | 'p2' | 'cpu', string>> = {
  p1: '1P が爆風にたえる回数',
  p2: '2P が爆風にたえる回数',
  cpu: 'CPU が爆風にたえる回数',
};

/** 体力の行の注記（原型 L5988）。 */
export const HIT_NOTE = 'ハンデをつけたい時に使う（例：1P だけ 3回にする）。🐘ぞうは常に +1回';

/** CPU の強さの見出し（原型 L5945）。CPU のいない遊び方では、見出しも行も注記も出さない。 */
export const CPU_HEADING = 'CPU の強さ（1体ずつ）';

/** CPU の行の頭の札（原型の `CPU${i+1}`。L5953）。`index` は CPU の何体目か（0 から）。 */
export function cpuTag(index: number): string {
  return `CPU${index + 1}`;
}

/** CPU の強さの注記（原型 L5961-5962。`<br>` で2行）。 */
export const CPU_NOTE: readonly [string, string] = [
  'よわい＝反応が鈍く、危険に気づかず、あまり攻めてこない。おに＝盤面の端からでも追ってくる。',
  'CPU の動物はランダムに決まる',
];

/** 勝ち数の見出しと注記（原型 L329・L331）。 */
export const WINS_LABEL = '何勝先取で優勝';
export const WINS_NOTE = '1ラウンド勝つと★1つ。先に取りきったら優勝';

/** 制限時間の見出しと注記（原型 L334・L336。注記の真ん中は太字）。 */
export const TIME_LABEL = '制限時間';
export const TIME_NOTE: readonly ManualSpan[] = [
  { kind: 'text', text: '🌿 葱ボンは残り1分で退場するので、' },
  { kind: 'bold', text: '1:00 にすると葱ボンなし' },
  { kind: 'text', text: 'になる' },
];

/** 延長戦の見出しと注記（原型 L339・L341）。 */
export const SUDDEN_LABEL = 'サドンデス（同時死・時間切れ）';
export const SUDDEN_NOTE = 'ONだと、決着つかない時にソフトブロック全消し・全員MAX装備・60秒で延長';

/** ルールの画面の下のボタン（原型 L346）。 */
export const START_LABEL = 'はじめる';

/** 設定の画面の見出し（原型 L356。右の小さい字は無い）。 */
export const MANUAL_HEADING = '設定・マニュアル・更新履歴';

/** 設定の画面の、3つの区切りの見出し（原型 L359・L364・L445）。 */
export const SOUND_LABEL = '① 設定 ／ サウンド';
export const MANUAL_LABEL = '② マニュアル ／ そうさ・ルール';
export const LOG_LABEL = '③ 更新履歴';

/** 音の設定のチップ（原型 L5778。曲だけを鳴らす選択肢は無い）。 */
export const SOUND_CHOICES: readonly { readonly value: SoundSetting; readonly label: string }[] = [
  { value: 'both', label: 'BGM + 効果音' },
  { value: 'sfx', label: '効果音だけ' },
  { value: 'off', label: '無音' },
];

/** 爆風の回数のチップの字（原型の `${n}回`）。 */
export function hitsLabel(hits: number): string {
  return `${hits}回`;
}

/** 勝ち数のチップの字（原型の `${n}勝`）。 */
export function winsLabel(wins: number): string {
  return `${wins}勝`;
}

/** 延長戦のチップの字（原型の 'ON'・'OFF'）。 */
export function onOff(on: boolean): string {
  return on ? 'ON' : 'OFF';
}

/**
 * 確認の画面の種類（原型の `askConfirm` を使う2か所。L3384-3398）。
 *
 * - `backToSetup`：試合中にパッドの Select から開く（原型の `askBackToSetup`）
 * - `disconnect`：通信対戦のロビーと、つないでいる最中の LAN の画面から開く（原型の `askDisconnect`）
 */
export type DialogKind = 'backToSetup' | 'disconnect';

/** 確認の画面の文と、右のボタンの文（原型 L3386・L3396。Python 版の `DialogKind` と同じ）。 */
export const DIALOG_TEXTS: Readonly<Record<DialogKind, { readonly message: string; readonly yes: string }>> = {
  backToSetup: { message: '設定へもどりますか？', yes: '設定へもどる' },
  disconnect: { message: 'せつぞくを切ります。よいですか？', yes: 'せつぞくを切る' },
};

/** 確認の画面の左のボタン（原型 L3365）。カーソルは初めにここを指す（危ない側を初めの位置にしない）。 */
export const DIALOG_NO = 'やめる';

/** LAN の画面の見出し（原型 L270）。 */
export const LAN_HEADING = 'LAN対戦';

/**
 * LAN の画面の注記（原型 L272-273。HTML の改行は空白1つになる）。
 *
 * 2文目は原型の文。Python 版は「あらかじめ「たてる」を押す Mac で中継サーバを立てておくこと。」に書き換えたが、それは
 * Python 版がブラウザのページでないため。この版は原型と同じく、中継が配ったページを開いて遊ぶ。
 */
export const LAN_NOTE = '同じ Wi-Fi（LAN）につながっている Mac 同士で対戦する。 あらかじめ表示された URL をブラウザで開いていること。';

/** LAN の画面の2つの項目（原型 L275-278。どちらも同じ中継につなぐ。ホストかゲストかは中継が決める）。 */
export const LAN_ITEMS: readonly { readonly action: 'host' | 'join'; readonly icon: string; readonly title: string; readonly detail: string }[] = [
  { action: 'host', icon: '🏠', title: 'たてる', detail: 'この端末が試合を進める（ホスト）' },
  { action: 'join', icon: '🚪', title: 'さんかする', detail: '別の端末の試合に参加する（ゲスト）' },
];

/** LAN の画面で、つなぎ始めてから出す文（原型 L5737）。 */
export const CONNECTING = '接続しています…';

/** ロビーの頭の戻るボタン（原型 L288）。押すと確認の画面を開く。 */
export const DISCONNECT_LABEL = '← せつぞくを切る';

/** ロビーの見出し（原型 L289）。 */
export const LOBBY_HEADING = 'ロビー';

/** ロビーの、ホストだけが押す下のボタン（原型 L293）。ルールの画面の「はじめる」と違い、▶ が付く。 */
export const LOBBY_START = 'はじめる ▶';

/** ロビーで、ゲストに出す待ちの文（原型 L294。`<br>` で2行）。 */
export const LOBBY_WAIT: readonly [string, string] = [
  'ルールはホストが決めます（上に出ている内容ではじまります）。',
  'ホストが「はじめる」を押すのを待っています…',
];

/** ロビーの、枠ごとの体力の見出し（原型 L5868）。 */
export const LOBBY_HITS_LABEL = 'たいりょく（爆風にたえる回数）';

/** ロビーの、勝ち数の見出し（原型 L5908。ルールの画面と文が違うのも原型のまま）。 */
export const LOBBY_WINS_LABEL = '何勝先取';

/** ロビーの、制限時間の見出し（原型 L5910）。 */
export const LOBBY_TIME_LABEL = 'じかん';

/** ロビーの、延長戦の見出し（原型 L5912）。 */
export const LOBBY_SUDDEN_LABEL = 'サドンデス';

/** ロビーの枠の見出しの右（つながっている。原型 L5832）。 */
export const CONNECTED = '🟢 接続済み';

/** ロビーの枠の見出しの右（つながっていない。原型 L5832）。 */
export const VACANT = '⚪ 空き・待機中';

/** ゲストの読むだけの行の区切り（原型の `bits.join(' ／ ')`。L5891・L5918）。 */
const SHARED_SEPARATOR = ' ／ ';

/** ロビーの冒頭の1行（原型の `あなたは ${NET.seat+1}P（ホスト／ゲスト）`。L5811）。ホストは 1P。 */
export function lobbyMe(seat: PlayerId): string {
  return `あなたは ${numberedName(seat)}（${seat === 0 ? 'ホスト' : 'ゲスト'}）`;
}

/**
 * ロビーの枠の見出しの左（「1P」「2P（あなた）」。原型 L5831）。
 *
 * 原型は CPU の枠を「CPU」と書くが、この版はロビーで人間の人数を選ばないので、どの枠も番号で書く
 * （つながっていない枠は、あとから誰かがつながれば人間になる。Python 版と同じ）。
 */
export function lobbySlotName(slot: PlayerId, seat: PlayerId): string {
  return `${numberedName(slot)}${slot === seat ? '（あなた）' : ''}`;
}

/**
 * ゲストの、枠1つぶんの読むだけの行（「🐰うさぎ ／ ふつう ／ たいりょく 1回」。原型 L5882-5891）。
 *
 * CPU の強さは、いまつながっていない枠（始めたら CPU になる枠）にだけ出す（Python 版と同じ。原型は CPU の枠だけ）。
 */
export function lobbySharedLine(setup: LanSetup, slot: PlayerId, connected: boolean): string {
  const look = lookOf(setup.animals[slot]);
  const bits = [`${look.emoji}${look.name}`];
  if (!connected) bits.push(CPU_LEVELS[setup.cpuLevels[slot]].label);
  bits.push(`たいりょく ${hitsLabel(setup.hits[slot])}`);
  return bits.join(SHARED_SEPARATOR);
}

/** ゲストの、読むだけのルールの行（「3勝先取 ／ じかん 3:00 ／ サドンデス ON」。原型 L5915-5918）。 */
export function lobbySharedRules(setup: LanSetup): string {
  return [`${winsLabel(setup.winsToTake)}先取`, `じかん ${formatSeconds(setup.roundSeconds)}`, `サドンデス ${onOff(setup.suddenDeath)}`].join(
    SHARED_SEPARATOR,
  );
}
