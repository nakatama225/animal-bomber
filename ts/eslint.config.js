import js from '@eslint/js';
import tseslint from 'typescript-eslint';

/**
 * 型検査で止められないものを、こちらで止める。
 *
 * tsconfig.domain.json は「domain/ がブラウザ API を使うこと」を型エラーにするが、
 * Math.random や Date.now は ES2022 の一部なので型検査は通ってしまう。
 * 決定性を壊すのはむしろこちらなので、domain/ と ai/ に限って禁止する。
 *
 * ai/（CPU の思考）も対象にしているのは、CPU の判断も種から決まる必要が
 * あるため。通信対戦では各端末が同じ CPU を動かすので、1台だけ違う乱数を
 * 引くと、その端末でだけ CPU が別の手を指して試合がずれる。
 *
 * ⚠️ この設定を緩めると、同じ入力で同じ試合にならなくなる。
 * 症状は「たまに結果が違う」という形で出るため、原因にたどり着くまでが長い。
 */

/** domain/ で禁止する呼び出し。message にはその場で読む代替手段を書く。 */
const FORBIDDEN_IN_DOMAIN = [
  {
    object: 'Math',
    property: 'random',
    message:
      'ルールの層では Rng を引数で受け取る。見た目だけの乱数は presentation/CosmeticRng を使う。',
  },
  {
    object: 'Date',
    property: 'now',
    message: '時刻は引数で渡す。時間の進みは tick の回数で表す。',
  },
  {
    object: 'performance',
    property: 'now',
    message: '時刻は引数で渡す。時間の進みは tick の回数で表す。',
  },
  // 超越関数は、同じ式でも実行環境によって最下位ビットが食い違うことが
  // 規格上許されている。ルールの層に入ると、環境をまたいだ通信対戦で
  // 少しずつ状態がずれる。
  // ⚠️ 四則演算と Math.sqrt は正確な丸めが規格で保証されているので禁じていない。
  ...['sin', 'cos', 'tan', 'atan2', 'exp', 'log', 'pow'].map((property) => ({
    object: 'Math',
    property,
    message:
      '結果が環境によって食い違う。ルールの層では使わない（描画のための計算なら presentation へ）。',
  })),
];

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'docs/**', 'coverage/**'] },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    // 検査ツールの設定ファイルは CommonJS で書いている。dependency-cruiser が
    // 設定を require で読み込むため、こちらだけ形式が違う。
    files: ['**/*.cjs'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: { module: 'writable', require: 'readonly', __dirname: 'readonly' },
    },
  },

  {
    files: ['**/*.ts'],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },

  {
    files: ['src/domain/**/*.ts', 'src/ai/**/*.ts'],
    rules: {
      'no-restricted-properties': ['error', ...FORBIDDEN_IN_DOMAIN],
      'no-restricted-syntax': [
        'error',
        {
          selector: 'ForInStatement',
          message:
            'for...in は列挙の順序が保証されない。順序が要るものは配列で持つ。',
        },
        {
          selector: 'NewExpression[callee.name="Date"]',
          message: '時刻は引数で渡す。時間の進みは tick の回数で表す。',
        },
      ],
    },
  },

  {
    // テストは domain の内部を覗いてよい。禁止も緩める。
    files: ['tests/**/*.ts'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
);
