"""CPU の判断（段階 6）。

CPU は、キーボードやゲームパッドと同じく、1 tick ごとに入力（`PlayerInput`）を返す窓口
（`source.py` の `CpuInputSource`）。ルールの層からは人間と区別がつかない。

原型の CPU（`legacy/animal-bomber.html` の cpuUpdate・planCPU）と同じ手を、入力で指す。
1 tick の中の判断の順も、規則も原型に合わせてある（TypeScript 版の `src/ai/` と同じ
形）。

| モジュール | 持つもの |
|---|---|
| `source.py` | 1 tick の判断の順（原型 cpuUpdate） |
| `chain.py`・`behaviors.py` | 計画を決める規則の並び（原型 planCPU） |
| `bombs.py` | 爆弾を置いてよいか（逃げ切れるか） |
| `tactics.py` | 動物ごとの戦い方（閉じた列挙の `match`） |
| `follow.py` | 経路を押す向きに変える |
| `context.py`・`memory.py`・`plan.py`・`levels.py`・`margins.py` | 判断に使うもの |

⚠️ 乱数は CPU 専用の `Rng` を持ち、試合の乱数（`world.rng`）を引かない。CPU の判断も
種から決まるので、同じ種・同じ盤面なら CPU は毎回同じ手を指す。
"""
