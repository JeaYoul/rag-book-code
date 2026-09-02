# 파서 컨테이너 — "같은 이미지에서 갓 만든 새 배" 의 그 이미지 (14장)
#
# Spark 에서는 GPU 를 쓰기 위해 NVIDIA 의 PyTorch 컨테이너를 밑에 깔았다.
# 여기서는 원리만 보이도록 가벼운 파이썬 이미지를 쓴다. Docling 까지 쓰려면 밑줄을 바꿔라.
#   FROM nvcr.io/nvidia/pytorch:<검증한 태그>
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# 논문은 /papers 에, 패키지는 /packages 에 — 둘 다 볼륨 (run_parser.sh 의 -v)
# 죽으면 도커가 다시 띄우고, 이 명령이 처음부터 다시 돈다. 이어가기는 _DONE 이 한다.
CMD ["python", "phoenix_loop.py", "--papers", "/papers", "--packages", "/packages", "--exit-after", "80"]
