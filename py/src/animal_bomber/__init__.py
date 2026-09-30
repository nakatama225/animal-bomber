"""どうぶつボンバーの Python 版。

層は下から順に domain・content・ai・net・presentation・shell・app と積む。
下の層は上の層を import しない。向きは `pyproject.toml` の import-linter の
設定で検査している。
"""
