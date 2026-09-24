import { defineConfig } from 'vitest/config';

/**
 * ビルドとテストの設定。
 *
 * Vitest は Vite の設定をそのまま使うため、テスト専用の設定ファイルを
 * 別に置いていない。同じ解決規則・同じ変換で動くので、
 * 「テストでは通るがビルドでは通らない」の食い違いが起きない。
 */
export default defineConfig({
  test: {
    // ルールの層はブラウザに依存しないので、テストは node で走る。
    // 描画を差し替える設定も、無効化するフラグも要らない。
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
});
