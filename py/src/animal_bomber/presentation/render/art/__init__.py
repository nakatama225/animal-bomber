"""原型の描く関数の写し。

`legacy/animal-bomber.html` の描く関数（drawTile・drawItem・drawBomb・drawBlast・
drawAnimalBody とその部品）を、canvas の命令の順と値まで同じに写す。受け手は canvas の口
（`render/canvas/protocol.py`）で、記録する canvas に渡すと原型の記録と突き合わせられ、
pygame の面に描く canvas に渡すと絵になる。

原型の入力は秒（経過時間・導火線の残り・爆風の残り）だが、この版の試合は tick で数える。
描く関数は tick の数を秒に直してから（`timing.py`）、原型と同じ式に入れる。
試合の状態は読むだけで書き換えない。
"""
