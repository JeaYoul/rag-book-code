# 21장. 파수꾼 — 손 안의 에이전트

지켜보다가, 달라졌을 때만 부른다. 전부 합쳐 600줄이 안 된다.

```
notify.py ─ send() 텔레그램 한 통 · load/save_state() 지난번의 기억 · diff_bool() 상태 전이
   ├ health_guardian.py    열 곳을 네 가지 방법으로 · 죽을 때와 살아날 때만
   ├ login_guardian.py     두 기계의 접속자 · 조회 실패와 아무도 없음을 구분
   ├ raglogin_guardian.py  앱 로그인·실패·잠금 · 처음 본 사용자는 건너뜀
   ├ paper_guardian.py     월요일 아침 PubMed · 오탐과 오역에서 배운 것
   ├ daily_brief.py        아침 날씨 · 이것만 아무 일 없어도 말한다
   └ rag_bot.py            내가 먼저 묻는다 · 한국어를 영어 키워드로
```

## 파일

| 파일 | 역할 |
|---|---|
| `notify.py` | 공용 셋. 텔레그램 발송, 상태 파일 읽기·쓰기, 상태 전이 골라내기 |
| `health_guardian.py` | 여러 곳을 http·port·svc·proc 네 방법으로 확인. `--demo` 로 침묵 규칙을 눈으로 |
| `login_guardian.py` | 서버 접속자. `--demo` 로 조회 실패를 잘못 다루면 어떻게 되는지 |
| `raglogin_guardian.py` | 18장 `users` 표의 세 칸을 읽어 로그인·실패·잠금. `--demo` |
| `paper_guardian.py` | PubMed 세 갈래. `[Title/Abstract]` 한정과 번역 금지 지시문 |
| `daily_brief.py` | 아침 날씨. 확률보다 강수량을 앞에 |
| `rag_bot.py` | 텔레그램 논문 봇. `to_en()` 한 함수가 쓸모를 갈랐다 |
| `guardian.cron.example` | 크론 본보기. 절대경로 함정과 중복 한 줄 사고를 주석으로 |
| `guardian_env.example` | 토큰 파일 본보기 |

## 해보기 (토큰도 서버도 없이)

```bash
python health_guardian.py --demo
```

다섯 번 돌면서 알림이 두 번만 가는 것을 보여 준다. 처음 켰을 때 조용하고, 계속 정상이어도 조용하고, 죽을 때와 살아날 때만 운다.

```bash
python login_guardian.py --demo
python raglogin_guardian.py --demo
python rag_bot.py --ask "설포라판의 HDAC 억제 기전은?" --fake
python daily_brief.py --fake
python paper_guardian.py --fake --dry-run
```

`~/.guardian_env` 가 없으면 모든 파수꾼이 연습 모드로 돈다. 보낼 내용을 화면에 찍고 끝낸다.

## 실제로

```bash
cp guardian_env.example ~/.guardian_env && chmod 600 ~/.guardian_env   # 토큰 채우기
python health_guardian.py            # 첫 실행 — 상태 파일만 만들고 조용하다
python health_guardian.py            # 두 번째 — 달라진 것이 없으면 여전히 조용하다
```

크론에 걸 때는 `guardian.cron.example` 을 보라. **인터프리터를 절대경로로 적어야 한다.** 크론은 로그인 셸의 PATH를 물려받지 않아서, `python` 이라고만 쓰면 conda 환경이 아니라 시스템 파이썬이 잡히고 import 부터 실패한다.

로그가 쌓이므로 [ch20-ops/logrotate/guardian](../ch20-ops/logrotate/guardian) 도 함께 넣어라.

## 이 폴더에서 배울 것 하나만 고르면

`notify.py` 의 이 여섯 줄이다.

```python
def diff_bool(prev, now):
    down = [k for k, v in now.items() if prev.get(k) is True and not v]
    back = [k for k, v in now.items() if prev.get(k) is False and v]
    return down, back
```

살아 있던 것이 죽었을 때, 죽었던 것이 살아났을 때. 그 두 순간에만 말한다. 처음 보는 이름은 어느 쪽에도 넣지 않는다. **알림의 기술은 말하는 기술이 아니라 침묵하는 기술이다.**

## 정직하게

- 실제 헬스 파수꾼은 열 곳을 본다. 여기서는 여덟만 넣었다. 나머지 둘은 내 환경에만 있는 것이라 뼈대에서 뺐다.
- 메일 파수꾼은 넣지 않았다. 구글 인증 절차가 이 장의 요지와 상관없이 길고, 실제 시스템에서도 지금은 꺼 두었다. 대신 그 파수꾼의 규칙만 본문에 적었다. 중요도 3 미만은 침묵하고, 답장 초안은 쓰되 보내지 않는다.
- `paper_guardian.py` 의 검색어와 번역 금지 지시문은 실제로 겪은 두 번의 실패에서 나온 것이다. 시약으로 쓰인 논문이 딸려 온 것, 학명이 임의로 번역된 것.
- 이 저장소에서 자동 검증한 것: 상태 전이 규칙(첫 실행·무변화·중단·지속·복구 다섯 경우), 조회 실패 처리, 처음 본 사용자 건너뛰기, 봇의 한국어→영어 변환과 답 조립. 실제 텔레그램 발송과 PubMed 조회는 토큰과 네트워크가 있는 곳에서 확인해야 한다.

> 📖 본문 — 21장. 파수꾼 — 손 안의 에이전트
