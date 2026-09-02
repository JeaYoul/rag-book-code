# 13장. 툴을 연결하다 — 내 방의 모델로 코딩하기

VS Code 안의 클로드 코드를 **LiteLLM 게이트웨이**를 거쳐 **Spark1의 vLLM(Qwen)**에 붙이는 데 쓴 파일들이다.
책 13장의 그림 그대로다.

```
VS Code / 클로드 코드 --(Anthropic 형식)--> LiteLLM :4000 (Spark2) --(OpenAI 형식)--> vLLM :8000 (Spark1)
```

## 파일

| 파일 | 역할 |
|---|---|
| `litellm_config.yaml` | 통역사 설정. "`qwen`이라 부르면 Spark1의 vLLM으로 넘겨라." |
| `.env.example` | 게이트웨이 열쇠 본보기. 복사해서 `.env`로 만든다 |
| `requirements.txt` | 게이트웨이 설치 목록 |
| `start_litellm.sh` | 게이트웨이를 4000 포트에 띄운다 (포트 충돌도 먼저 검사) |
| `env.sh` | 클로드 코드의 시선을 게이트웨이로 돌리는 환경 변수 (`source env.sh`) |
| `check_connection.sh` | 책에서 말한 "막히는 다섯 자리"를 순서대로 짚는 점검 스크립트 |
| `check_connection.py` | 같은 점검의 파이썬 판 (윈도우 등 bash가 없는 환경용) |
| `litellm-gateway.service` | 부팅 때 자동으로 살아나게 하는 systemd 유닛 (선택) |

## 순서

**1. Spark1에서 vLLM이 떠 있는지 확인한다.** (12장)

```bash
curl -s http://192.168.10.50:8000/v1/models
```

**2. Spark2에 게이트웨이를 설치하고 띄운다.**

```bash
pip install -r requirements.txt
cp .env.example .env        # LITELLM_MASTER_KEY 값을 바꾼다
./start_litellm.sh
```

**3. 연결을 점검한다.** 다섯 자리를 순서대로 짚는다. 어디서 멈추는지가 곧 어디가 어긋났는지다.

```bash
source env.sh
./check_connection.sh
```

**4. 클로드 코드의 시선을 돌린다.** VS Code 터미널에서:

```bash
source env.sh
claude
```

클로드 코드 안에서 `/status`를 치면 내가 적은 게이트웨이 주소가 떠 있어야 한다.

## 막히는 다섯 자리 (책 본문과 같은 순서)

1. **열쇠를 엉뚱한 손잡이에** — 게이트웨이엔 `ANTHROPIC_AUTH_TOKEN`. `ANTHROPIC_API_KEY`는 **지운다**. 둘이 같이 있으면 401.
2. **`http://`를 빠뜨림** — 주소는 반드시 `http://`부터.
3. **게이트웨이가 안 떠 있음** — 도구를 의심하기 전에 `curl .../v1/models`부터.
4. **사설 IP 차단** — 도구가 `192.168.x.x`로 나가는 걸 막는 경우, 신뢰할 내부 주소를 명시.
5. **포트 충돌** — 4000이 이미 쓰이면 비어 있는 번호로 바꾸고 어딘가에 적어 둔다.

## 정직하게 짚어둘 것

- 게이트웨이 너머에 **다른 회사의 모델을 붙이는 것은 공식 지원 범위 밖**이다. 도구가 새 버전으로 올라가면 어느 날 안 될 수 있다.
- 게이트웨이는 내 열쇠와 코드가 지나가는 길목이다. **검증한 버전을 못 박아 설치**한다. `requirements.txt`의 주석을 보라.
- 이 폴더의 IP·포트·사용자명은 내 서버 값이다. 당신 환경에 맞게 바꿔라.
