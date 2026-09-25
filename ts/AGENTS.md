# TypeScript 版への指示

[リポジトリ共通の指示](../AGENTS.md) を先に読んでください。ここには
TypeScript 版に固有のものだけを書いています。

## 層の依存方向

```text
app → platform → presentation → net → ai → content → domain
```

逆向きの import を追加しないでください。

## `domain/` と `ai/` の中で使ってはいけないもの

- `Math.random` / `Date.now` / `performance.now`
- ブラウザ API（`document` / `window` / `canvas` など）

乱数と時刻は引数として渡します。`domain/` と `ai/` 専用の TypeScript 設定から
DOM の型定義を外してあるので、ブラウザ API を書くと型エラーになります。
**この設定を緩めないでください。**

`ai/`（CPU の思考）も対象なのは、CPU の判断も種から決まる必要があるためです。
通信対戦では各端末が同じ CPU を動かします。CPU は自分専用の乱数（`Rng`）を持ち、
試合の乱数（`world.rng`）には触れません。

## 動物の能力を追加するとき

共通の interface を実装し、登録の1行を足すだけで済む形になっています。
既存の動物のファイルにも、ゲーム本体にも手を入れないでください。
手を入れないと追加できない場合は、抽象の引き方が間違っているので報告してください。

CPU の戦い方も同じ形です。`src/ai/tactics/` に戦い方を1つ書き、
`src/ai/tactics/registry.ts` に登録の1行を足します。書かなくても、
省略時の戦い方（足元に爆弾を置く・技は使わない）でその動物は戦えます。

⛔ 共通の処理（`domain/systems/` `domain/mutations/` `domain/query/` `ai/` 直下 `ai/behaviors/`）に
動物の名前を書かないでください。**コメントも含みます。** 書くと
`tests/boundary/guards.test.ts` が落ちます。

## CPU の判断の規則を足すとき

`src/ai/behaviors/` に `CpuBehavior` を1つ書き、`DefaultChain.ts` の配列に並べます。
配列の順番がそのまま優先順位です。

⛔ 「袋小路では爆弾を置かない」を足さないでください。開幕はどこも袋小路なので、
CPU が永久に爆弾を置かなくなります（原型で実際に起きました）。

## 数値の調整

CPU の強さや自爆の割合は、画面なしで測れます。

```sh
MEASURE=1 npx vitest run tests/ai/balance.test.ts
```

## 絵と音（`src/presentation/`）

- 試合の状態は読むだけにしてください。書き換えると、画面を出したときだけ試合が変わります
- 見た目の乱数は `CosmeticRng` を使い、`Math.random` を直接呼ばないでください
- ファイルの一番外側（関数の外）で `window` `document` `AudioContext` に触れないでください。
  テストは node で走るので、読み込んだ時点で落ちます
- 描画のテストで使う偽の canvas（`tests/presentation/fakeCanvas.ts`）は、ブラウザが例外を出す
  呼び方（負の半径など）で同じく例外を出します。**この検査を緩めないでください**
