# 20장. 새벽 3시에도 돌아가는가 — 운영

만드는 데 반년, 돌리는 데 남은 평생. 이 폴더는 그 "남은 평생" 쪽이다.

## 파일

| 파일 | 역할 |
|---|---|
| `systemd/rag-home.service` | 규칙대로 쓴 앱 서비스. `Type=simple` · `ExecStop` 없음 · 되살림에 제동 · 메모리 울타리 |
| `systemd/rag-reranker.service` | 늘 떠 있어야 하는 것 (`Restart=always`) |
| `systemd/rag-gateway.service` | 13장 게이트웨이 |
| `systemd/BAD-multi-app.service.example` | **이렇게 쓰지 마라.** 열두 번의 사고를 낸 실제 파일과 그 이유 셋 |
| `logrotate/guardian` | 파수꾼 로그를 주마다 자른다 |
| `journald.conf.example` | 시스템 로그를 얼마나 남길지 직접 정한다 |
| `zombie_check.sh` | 좀비를 찾아내고 죽이는 다섯 단계. 기본은 보기만 한다 |
| `weekly_check.sh` | 일주일에 한 번 이것만 보면 된다. 핵심은 재시작 횟수 |
| `backup_db.sh` | 없다고 확인한 그 백업. 다른 디스크가 아니면 멈춘다 |
| `restore_check.sh` | 되살려 보지 않은 백업은 파일일 뿐이다. 임시 DB에 되살려 세어 본다 |
| `guardian.cron.example` | 파수꾼 크론 본보기. 중복 한 줄이 만든 사고를 주석으로 |

## 해보기 (기계를 건드리지 않고)

```bash
./zombie_check.sh                       # 진짜 좀비(Z)가 있는지만 본다
./zombie_check.sh --port 8501           # 그 포트를 쥔 것이 서비스 소속인지 고아인지
./weekly_check.sh                       # 서비스들의 체온 — 재시작 횟수
./backup_db.sh --dry-run                # 무엇을 뜰지만 보여 준다
```

`zombie_check.sh`는 `--kill`을 붙이지 않으면 아무것도 죽이지 않는다. `backup_db.sh`는 백업 폴더가 원본과 같은 디스크면 아예 멈춘다.

## 서비스 파일을 고칠 때

```bash
systemd-analyze verify systemd/rag-home.service      # 문법 검사
sudo cp systemd/rag-home.service /etc/systemd/system/
sudo systemctl daemon-reload                          # 이 줄을 빠뜨리면 옛 설정으로 돈다
sudo systemctl enable --now rag-home
systemctl status rag-home
```

## 여덟 가지 규칙 (본문 요약)

1. 서비스 하나에 프로세스 하나. `Type=simple`.
2. `ExecStop`을 쓰지 마라. systemd가 제어 그룹째 죽인다.
3. 재시작 정책은 성격으로. 늘 떠 있을 것은 `always`, 자주 고치는 앱은 `on-failure`.
4. 되살림에 제동을 걸어라. `StartLimitBurst`.
5. `After`(순서) · `Wants`(같이 뜨되 독립) · `Requires`(함께 죽음)를 구분하라.
6. 자원에 울타리를. 다만 **GPU 메모리는 systemd가 못 막는다** — 코드 안에서 막아라.
7. 로그가 얼마나 남는지 직접 정하라. 기본값에 맡겨 7월 기록을 잃었다.
8. 고쳤으면 검사 → `daemon-reload` → 재시작. 가운데를 빠뜨리면 고쳤다고 믿는 것과 고쳐진 것이 달라진다.

## 정직하게

- 이 폴더의 서비스 파일들은 **고친 형태**다. 실제 운영 중인 파일은 아직 `BAD-multi-app.service.example` 쪽에 가깝다. 열두 번 되살아나면서도 서비스는 살아 있었고, 급한 불이 아니었다. 운영의 흠은 대개 이렇게 산다.
- `backup_db.sh`와 `restore_check.sh`는 **이 책을 쓰면서 만든 것**이다. 확인해 보니 실제 시스템에는 자동 백업이 없었다. 넉 달 전에 손으로 뜬 244GB 하나가 원본과 같은 디스크에 있었을 뿐이다.
- `logrotate/guardian`은 실제로 넣어서 확인했다. 25MB가 잘리고 본 파일이 0바이트가 되는 것까지 봤다.
- 표에 적은 재시작 횟수와 날짜는 실제 기계에서 읽은 값이다. 짐작한 숫자는 없다.

> 📖 본문 — 20장. 새벽 3시에도 돌아가는가
