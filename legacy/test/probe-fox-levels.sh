#!/bin/zsh
# きつねが「おに」で特別に壊れているのか、それとも「おに」全体の性質かを測る。
# ⛔ 1回では決まらない（乱数で毎回ちがう盤面になる）ので N 回まわして中央値を見る。
cd "${0:A:h}"
N=${2:-8}
LV=$1
for i in $(seq 1 $N); do node probe-fox-cpu.js $LV; done 2>/dev/null \
 | grep -E "^  (きつね|うさぎ|ぞう|もぐら|かえる)" \
 | sed -E 's/^  ([^ ]+) *生存([0-9]+)s.*訪れたマス *([0-9]+).*置いた爆弾 *([0-9]+).*往復 *([0-9]+)回\(([0-9.-]+)\/秒\).*/\1 \2 \3 \4 \6/' \
 | awk '{a[$1"_alive"]=a[$1"_alive"]" "$2; a[$1"_tile"]=a[$1"_tile"]" "$3; a[$1"_bomb"]=a[$1"_bomb"]" "$4; a[$1"_flip"]=a[$1"_flip"]" "$5; n[$1]++}
        END{ printf "%-6s %5s %6s %6s %8s  (n=標本数)\n","動物","標本","生存s","マス","往復/秒";
             for (k in n){ split(a[k"_alive"],A," "); split(a[k"_tile"],T," "); split(a[k"_bomb"],B," "); split(a[k"_flip"],F," ");
               sa=0;st=0;sb=0;sf=0; for(i in A)sa+=A[i]; for(i in T)st+=T[i]; for(i in B)sb+=B[i]; for(i in F)sf+=F[i];
               printf "%-6s %5d %6.1f %6.1f %8.2f  爆弾%.1f本\n", k, n[k], sa/n[k], st/n[k], sf/n[k], sb/n[k]; } }' \
 | sort -k5 -rn
