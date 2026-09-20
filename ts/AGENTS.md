# TypeScript 版への指示

[リポジトリ共通の指示](../AGENTS.md) を先に読んでください。ここには
TypeScript 版に固有のものだけを書いています。

## 層の依存方向

```text
app → platform → presentation → net → ai → content → domain
```

逆向きの import を追加しないでください。

## `domain/` の中で使ってはいけないもの

- `Math.random` / `Date.now` / `performance.now`
- ブラウザ API（`document` / `window` / `canvas` など）

乱数と時刻は引数として渡します。`domain/` 専用の TypeScript 設定から
DOM の型定義を外してあるので、ブラウザ API を書くと型エラーになります。
**この設定を緩めないでください。**

## 動物の能力を追加するとき

共通の interface を実装し、登録の1行を足すだけで済む形になっています。
既存の動物のファイルにも、ゲーム本体にも手を入れないでください。
手を入れないと追加できない場合は、抽象の引き方が間違っているので報告してください。
