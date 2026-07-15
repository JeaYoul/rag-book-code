# 9장 — 두 대의 기계, 두 개의 역할 (인프라 설정)

『산골 농부의 RAG 개발 야화』 9장에서 다룬 인프라 구성을 실제로 세울 때 참고할 설정 파일 묶음입니다.

> ⚠️ **먼저 읽어주세요**
> 아래 파일들은 모두 **템플릿(예시)**입니다. 모델 경로, MAC 주소, 인터페이스 이름, IP 같은 값은
> `<이렇게>` 표시된 자리에 **당신의 실제 값**을 넣어야 합니다.
> 그대로 복사해 실행하면 동작하지 않습니다. 자기 환경에 맞게 바꾸세요.
> (어떤 값을 넣어야 할지 모르겠다면, 각 파일 주석을 읽고 그래도 막히면 AI에게 물어보세요.)

---

## 전체 그림

```
인터넷
  │
  ├── Spark1 (192.168.10.50)  — 두뇌: LLM 전용 (vLLM)
  │
  └── Spark2 (192.168.10.51)  — 몸통: DB · 리랭커 · 파싱 · 앱 · MCP
        │
   두 대는 QSFP 케이블 한 가닥(200Gbps)으로 직결
```

- **Spark1** = LLM만 돌린다. 여유가 곧 안정.
- **Spark2** = 나머지 전부. 데이터베이스, 리랭커, 파싱, 앱, MCP 서버.
- 두 대는 QSFP로 직결하되 **포트 하나만** 쓴다. (본딩은 불안정 — 9장 참조)

---

## 파일 목록

| 파일 | 무엇 | 어디에 두나 |
|---|---|---|
| `serve_llm.sh` | Spark1에서 vLLM으로 LLM 띄우기 | Spark1 (실행 스크립트) |
| `vllm-server.service` | 위 스크립트를 systemd로 살려두기 | Spark1 `/etc/systemd/system/` |
| `70-persistent-net.rules` | 네트워크 인터페이스 이름 고정 (udev) | 두 대 `/etc/udev/rules.d/` |
| `netplan-static-ip.yaml` | 고정 IP 설정 (netplan) | 두 대 `/etc/netplan/` |
| `docker-compose.yml` | Spark2의 DB(PostgreSQL+pgvector, MongoDB) 컨테이너 | Spark2 |

---

## 설치 순서 (권장)

1. **OS는 이미 깔려 있다.** DGX OS 대시보드에서 커널·펌웨어를 최신으로 업데이트한다. (다시 깔 필요 없음)
2. **사용자 계정**에 `sudo` 권한을 주고, `docker` 그룹에 추가한다.
   ```bash
   sudo usermod -aG docker $USER   # 재로그인 후 적용
   ```
3. **네트워크 고정** — `70-persistent-net.rules`로 인터페이스 이름을 못 박고, `netplan-static-ip.yaml`로 IP를 고정한다. (움직이는 것 위에는 아무것도 세우지 않는다)
4. **Spark2에 DB를 띄운다** — `docker-compose.yml`로 PostgreSQL과 MongoDB를 올린다.
5. **Spark1에 LLM을 띄운다** — `serve_llm.sh`를 `vllm-server.service`로 등록해 자동 실행·자동 복구되게 한다.

---

## 주의

- 이 파일들에는 **비밀번호·토큰·실제 IP 같은 민감 정보를 절대 커밋하지 마세요.** 템플릿의 `<...>` 자리를 채운 실제 설정은 로컬에만 두거나 `.gitignore`로 제외하세요.
- 값을 채우다 막히면, 로그를 그대로 복사해 AI에게 던지세요. **로그 없이 물으면 AI는 추측하고, 로그를 주면 추론합니다.** (6장)
