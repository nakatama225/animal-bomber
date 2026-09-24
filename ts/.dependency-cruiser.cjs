/**
 * 層の依存方向を検査する。
 *
 * 下の forbidden 配列が、そのまま「この実装の層のルール表」になっている。
 * 覚えるべき記法がほとんどなく、設定ファイルを読めば依存の設計が分かる
 * ことを狙って dependency-cruiser を選んだ。
 *
 * 層は下から順に並ぶ。上の層は下の層を使ってよく、逆は禁じる。
 *
 *   app          … 配線だけ
 *   platform     … キーボード・フレームループ（ブラウザ API を触ってよい唯一の層）
 *   presentation … 描画・音・HUD
 *   net          … 通信対戦
 *   ai           … CPU の思考
 *   content      … 動物などのデータ
 *   domain       … ゲームのルール（何にも依存しない）
 *
 * ⚠️ 型検査 (tsconfig.domain.json) と役割が重なるが、両方を置いている。
 * 型検査が止められるのは「domain/ がブラウザ API を使うこと」までで、
 * 「domain/ が ai/ を import すること」は止められない。そちらをここで止める。
 */
const LAYER_DESCRIPTION = {
  domain: 'ゲームのルール',
  content: '動物などのデータ',
  ai: 'CPU の思考',
  net: '通信対戦',
  presentation: '描画・音・HUD',
  platform: 'ブラウザ API',
  app: '配線',
};

/** 層 `name` が import してはいけない層を1本のルールにする。 */
function forbidUpward(name, forbiddenLayers) {
  return {
    name: `${name}-は-上の層を使わない`,
    comment:
      `${name}（${LAYER_DESCRIPTION[name]}）から ` +
      `${forbiddenLayers.join(' / ')} への import は依存の逆流。`,
    severity: 'error',
    from: { path: `^src/${name}/` },
    to: { path: `^src/(${forbiddenLayers.join('|')})/` },
  };
}

module.exports = {
  forbidden: [
    forbidUpward('domain', ['content', 'ai', 'net', 'presentation', 'platform', 'app']),
    forbidUpward('content', ['ai', 'net', 'presentation', 'platform', 'app']),
    forbidUpward('ai', ['net', 'presentation', 'platform', 'app']),
    forbidUpward('net', ['presentation', 'platform', 'app']),
    forbidUpward('presentation', ['platform', 'app']),
    forbidUpward('platform', ['app']),

    {
      name: '見た目の乱数をルールの層へ持ち込まない',
      comment:
        'CosmeticRng は同期しない乱数。ゲームの結果に影響する場所で使うと、' +
        '同じ入力でも試合が変わる。混ざる経路を物理的に断つため、' +
        'presentation の外からは import できない。',
      severity: 'error',
      from: { pathNot: '^src/presentation/' },
      to: { path: '^src/presentation/CosmeticRng\\.ts$' },
    },

    {
      name: '循環した依存を作らない',
      comment: '層をまたがない循環も、読む順序が決まらなくなるので禁じる。',
      severity: 'error',
      from: {},
      to: { circular: true },
    },

    {
      name: 'どこからも使われていないファイルを残さない',
      comment:
        '設計を変えた後の書き残しを検出する。設定ファイルとテストは除く。',
      severity: 'warn',
      from: {
        orphan: true,
        pathNot: [
          '\\.d\\.ts$',
          '(^|/)\\.[^/]+\\.(js|cjs|mjs|ts)$',
          '(^|/)tsconfig\\.json$',
          '^src/app/main\\.ts$',
        ],
      },
      to: {},
    },

    {
      name: '解決できない import を残さない',
      severity: 'error',
      from: {},
      to: { couldNotResolve: true },
    },
  ],

  options: {
    doNotFollow: { path: 'node_modules' },
    tsConfig: { fileName: 'tsconfig.json' },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'types'],
      extensions: ['.ts', '.js'],
    },
    reporterOptions: {
      dot: { collapsePattern: '^src/[^/]+' },
    },
  },
};
