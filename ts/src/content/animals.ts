/**
 * 動物の見た目と説明。**データだけで、振る舞いを持たない。**
 *
 * 動物の能力（速さ・火力・技）はルールの層の `domain/abilities/` にある。
 * ここにあるのは、画面に描くときの色や体型と、選ぶ画面に出す説明文だけ。
 * 分けてあるのは、変わる理由が違うから。色を変えても試合は1ミリも変わらず、
 * 能力を変えても絵は変わらない。
 *
 * 値は原型から持ってきた。
 */

/** 尻尾の形。 */
export type TailKind = 'ball' | 'thin' | 'bushy' | 'none';

/**
 * 体型。基準の体型に対する倍率で持つ。
 *
 * 2頭身の体を、頭・胴・脚の大きさの比で描き分ける。
 * 絵を動物ごとに一から描かずに済み、6匹目を足すときも数字を決めるだけで
 * それらしい体になる。頭だけは動物ごとに描き分けている。
 */
export interface AnimalBuild {
  readonly head: number;
  readonly bodyWidth: number;
  readonly bodyHeight: number;
  readonly legHeight: number;
  readonly tail: TailKind;
  /** お腹など明るい部分の色。 */
  readonly fur: string;
  /** 足先を大きく描くか。 */
  readonly bigFeet: boolean;
}

export interface AnimalLook {
  /** 能力の鍵と同じ文字列。 */
  readonly key: string;
  readonly name: string;
  readonly emoji: string;
  /** 体の色。足元の輪にも使う。 */
  readonly color: string;
  /** 影になる部分の色。 */
  readonly shade: string;
  readonly build: AnimalBuild;
  /** とくぎの名前と、状態の表示に出す絵文字。 */
  readonly special: { readonly name: string; readonly emoji: string };
  /**
   * 技のボタンの呼び方（原型の `skillLabelOf`。L5551-5558）。横の板のキーの案内の、技の行の頭に出す。
   *
   * 通常技を持たない動物は、技のボタンでもとくぎが出るので「とくぎ🍗」と書く（原型の注記 L5550）。
   */
  readonly skillLabel: string;
  /** 選ぶ画面に出す説明。 */
  readonly description: string;
}

export const ANIMAL_LOOKS: readonly AnimalLook[] = [
  {
    key: 'rabbit',
    name: 'うさぎ',
    emoji: '🐰',
    color: '#ff2d78',
    shade: '#a30f46',
    build: { head: 0.96, bodyWidth: 0.9, bodyHeight: 0.94, legHeight: 1.15, tail: 'ball', fur: '#ffe3ee', bigFeet: false },
    special: { name: 'うんこポロポロ', emoji: '💩' },
    skillLabel: 'とぶ',
    description:
      '移動が速い。技のボタンで1マス跳んでブロックを越える（2秒に1回）。' +
      'とくぎは、自分のまわり 5×5 のマスをうんこで埋め尽くす。',
  },
  {
    key: 'elephant',
    name: 'ぞう',
    emoji: '🐘',
    color: '#2f7fe0',
    shade: '#12457f',
    build: { head: 1.16, bodyWidth: 1.22, bodyHeight: 1.18, legHeight: 0.92, tail: 'thin', fur: '#cfdeed', bigFeet: false },
    special: { name: '突進', emoji: '🐗' },
    skillLabel: 'はなみず',
    description:
      '爆風が2マス長く、体力が1つ多い。技のボタンで鼻水を吹き、正面2マスの爆弾とうんこを消す（5秒に1回）。' +
      'とくぎは 1.5 秒の長押しで出る突進。柱に当たるまでブロックを壊しながら進む。',
  },
  {
    key: 'mole',
    name: 'もぐら',
    emoji: '🦫',
    color: '#c07321',
    shade: '#6d3c0c',
    build: { head: 1.02, bodyWidth: 1.2, bodyHeight: 1.06, legHeight: 0.72, tail: 'thin', fur: '#e8c9a0', bigFeet: true },
    special: { name: '落とし穴', emoji: '🕳️' },
    skillLabel: 'とくぎ🍗',
    description:
      '壊せるブロックを通り抜けられる。' +
      'とくぎは見えない落とし穴。踏んだ相手は3秒動けない。',
  },
  {
    key: 'fox',
    name: 'きつね',
    emoji: '🦊',
    color: '#ff6a00',
    shade: '#8a3000',
    build: { head: 1, bodyWidth: 0.96, bodyHeight: 0.94, legHeight: 1.02, tail: 'bushy', fur: '#fff3e4', bigFeet: false },
    special: { name: '狐火', emoji: '🔵' },
    skillLabel: 'ドン置き',
    description:
      '爆弾を最初から1個多く持つ。技のボタンで、1マス前から手持ちの爆弾を一列に並べる。' +
      'とくぎは相手を追いかける青い炎。放つ瞬間に短い無敵がつく。',
  },
  {
    key: 'frog',
    name: 'かえる',
    emoji: '🐸',
    color: '#3fb814',
    shade: '#1d5c07',
    build: { head: 1.12, bodyWidth: 1.12, bodyHeight: 0.88, legHeight: 0.82, tail: 'none', fur: '#dcf7c0', bigFeet: true },
    special: { name: '粘膜爆弾', emoji: '🟢' },
    skillLabel: 'した',
    description:
      'アイテムの効果が2倍（悪いものも2倍）。技のボタンで舌を伸ばし、遠くのアイテムを引き寄せる。' +
      'とくぎは跳ね回ってから爆発する爆弾。',
  },
];

/**
 * 動物の見た目を取得する。
 *
 * ⚠️ 登録されていない動物は例外にする。既定の見た目で黙って描くと、
 * 綴りを間違えたことに画面を見るまで気づかない。
 */
export function lookOf(key: string): AnimalLook {
  const look = ANIMAL_LOOKS.find((candidate) => candidate.key === key);
  if (look === undefined) throw new Error(`見た目が登録されていない動物: ${key}`);
  return look;
}
