#!/usr/bin/env bash
# dev_stats.sh — 22장의 표들을 만든 그 명령들 (22장)
#
#   ./dev_stats.sh                자기 저장소에서
#   ./dev_stats.sh /경로/저장소
#
# 무엇을 보는가.
#   커밋 수와 기간, 월별 분포, 메시지 접두어, AI 와 함께 쓴 커밋.
#   그리고 **비어 있는 달**. 그것이 이 장에서 가장 할 말이 많았던 자리다.
#   커밋 0건인 두 달이 시스템이 가장 열심히 일한 두 달이었다.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "그런 폴더가 없다: $REPO"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "git 저장소가 아니다: $REPO"; exit 1; }

echo "=== 전체 ========================================================="
total=$(git rev-list --count HEAD)
first=$(git log --reverse --pretty=%ad --date=short | head -1)
last=$(git log -1 --pretty=%ad --date=short)
echo "커밋 $total개 · $first ~ $last"

echo; echo "=== 월별 (빈 달까지 보이게) ========================================"
# 파이썬 없이 awk 로 빈 달을 채운다 — 빈 달이 이 표의 핵심이다
git log --pretty=%ad --date=format:%Y-%m | sort | uniq -c | awk '{print $2, $1}' | awk '
  { cnt[$1]=$2; if ($2>mx) mx=$2; order[NR]=$1; last=NR }
  END {
    if (last==0) { print "커밋이 없다"; exit }
    split(order[1], a, "-"); y=a[1]+0; m=a[2]+0
    split(order[last], b, "-"); ye=b[1]+0; me=b[2]+0
    if (mx<1) mx=1
    empties=""
    while (y<ye || (y==ye && m<=me)) {
      k=sprintf("%04d-%02d", y, m); n=(k in cnt)?cnt[k]+0:0
      bar=""; w=int(n*40/mx+0.5); if (n>0 && w<1) w=1
      for (i=0;i<w;i++) bar=bar "#"
      if (n==0) { printf "%s  %4d  %s   <-- 커밋 없음\n", k, n, bar; empties=empties " " k }
      else      { printf "%s  %4d  %s\n", k, n, bar }
      m++; if (m==13) { y++; m=1 }
    }
    if (empties != "") {
      printf "\n빈 달:%s\n", empties
      print "이 달들에 무엇을 하고 있었는지 기억해 보라. 대개 기계가 일하고 사람이 기다린 시간이다."
    }
  }'

echo; echo "=== 메시지 접두어 ================================================"
git log --pretty=%s | grep -oE "^[a-z][a-z0-9]*:" | sort | uniq -c | sort -rn | awk '{printf "%-14s %s\n", $2, $1}'
noprefix=$(git log --pretty=%s | grep -cvE "^[a-z][a-z0-9]*:" || true)
echo "(접두어 없음: ${noprefix}건)"

echo; echo "=== AI 와 함께 쓴 커밋 ============================================"
echo "Co-Authored 표시: $(git log --grep='Co-Authored' --oneline | wc -l)건"
echo "생성 도구 표시:   $(git log --grep='Generated with' --oneline | wc -l)건"

echo; echo "=== 하루 최다 커밋 ==============================================="
git log --pretty=%ad --date=short | sort | uniq -c | sort -rn | head -5 | awk '{printf "%s  %s건\n", $2, $1}'

echo; echo "=== 되돌린 기록 =================================================="
n=$(git log --grep='^revert' -i --oneline | wc -l)
echo "revert 커밋 ${n}건"
[ "$n" -gt 0 ] && git log --grep='^revert' -i --pretty='  %ad %s' --date=short | head -5
echo
echo "되돌린 적이 있다는 것은 마음껏 시켜 봤다는 뜻이다."
echo "되돌릴 수 없으면 무서워서 시키지 못한다. 그것이 Git 을 쓰는 이유다."
