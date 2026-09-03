#!/usr/bin/env python3
"""
daily_brief.py — 조용하지 않은 파수꾼 (21장)

    python daily_brief.py --lat 35.38 --lon 127.03 --place "담양 용면"
    python daily_brief.py --fake

이 파수꾼만 규칙이 반대다. **아무 일이 없어도 말한다.**

앞의 파수꾼들이 침묵하는 이유는 "들어도 달라질 것이 없어서"였다.
그런데 아침의 "오늘 비 3mm"는 들어야 하루가 달라진다. 밭에 물을 줄지가 거기 걸린다.
침묵해야 하는 것은 변화가 없을 때가 아니라, 들어도 행동이 달라지지 않을 때다.

농사에 필요한 것은 확률이 아니라 양이다. 30퍼센트보다 3밀리미터가 쓸모 있다.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import send   # noqa: E402

API = "https://api.open-meteo.com/v1/forecast"
LLM = os.getenv("LLM_URL", "http://localhost:4000/v1/chat/completions")
MODEL = os.getenv("LLM_MODEL", "qwen")

# 과장하지 말라는 마지막 문장을 여러 번 고쳐 썼다.
# 처음에는 모델이 "오늘은 완벽한 하루입니다!" 같은 말을 했고, 사흘이면 지겨워진다.
COMMENT_SYS = ("당신은 산골 마을에 사는 사람에게 오늘 날씨를 전하는 역할입니다. "
               "주어진 수치를 바탕으로 오늘 하루가 어떤 날일지 두세 문장으로 말해 주세요. "
               "수치를 그대로 나열하지 말고, 밖에 나가기 좋은지 창을 열어둘 만한지 같은 "
               "생활 감각으로 풀어 주세요. 마크다운 기호나 목록은 쓰지 말고 "
               "평범한 문장으로만 쓰세요. 과장하지 말고 담담하게 쓰세요.")


def forecast(lat, lon, fake=False):
    if fake:
        return {"hi": 27.4, "lo": 18.1, "rain": 3.2, "prob": 70, "uv": 5.1,
                "sunrise": "06:12", "sunset": "18:54"}
    import requests
    r = requests.get(API, params={
        "latitude": lat, "longitude": lon, "timezone": "Asia/Seoul", "forecast_days": 1,
        "daily": ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
                  "precipitation_probability_max,uv_index_max,sunrise,sunset")}, timeout=30)
    r.raise_for_status()
    d = r.json()["daily"]
    return {"hi": d["temperature_2m_max"][0], "lo": d["temperature_2m_min"][0],
            "rain": d["precipitation_sum"][0], "prob": d["precipitation_probability_max"][0],
            "uv": d["uv_index_max"][0], "sunrise": d["sunrise"][0][11:16], "sunset": d["sunset"][0][11:16]}


def comment(facts, fake=False):
    if fake:
        return "비가 조금 내리겠습니다. 밭일은 오전에 마치는 편이 낫겠고, 물은 오늘 주지 않아도 되겠습니다."
    import requests
    try:
        r = requests.post(LLM, json={"model": MODEL,
                                     "messages": [{"role": "system", "content": COMMENT_SYS},
                                                  {"role": "user", "content": facts}],
                                     "max_tokens": 500, "temperature": 0.7,
                                     "chat_template_kwargs": {"enable_thinking": False}}, timeout=180)
        r.raise_for_status()
        m = r.json()["choices"][0]["message"]
        return (m.get("content") or m.get("reasoning_content") or "").strip()
    except Exception as e:
        print("코멘트 실패:", e, file=sys.stderr)
        return ""          # 코멘트가 없어도 날씨는 보낸다


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, default=35.38)
    ap.add_argument("--lon", type=float, default=127.03)
    ap.add_argument("--place", default="담양 용면")
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()

    f = forecast(a.lat, a.lon, a.fake)
    facts = (f"{a.place} · 최고 {f['hi']}도 최저 {f['lo']}도 · "
             f"강수량 {f['rain']}mm(확률 {f['prob']}%) · 자외선 {f['uv']} · "
             f"일출 {f['sunrise']} 일몰 {f['sunset']}")

    lines = [f"🌤 {a.place} 오늘",
             f"\n기온  {f['lo']} ~ {f['hi']}도",
             f"비    {f['rain']}mm  (확률 {f['prob']}%)",     # 확률보다 양을 앞에
             f"자외선 {f['uv']}",
             f"해   {f['sunrise']} ~ {f['sunset']}"]
    c = comment(facts, a.fake)
    if c:
        lines.append("\n" + c)
    send("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
