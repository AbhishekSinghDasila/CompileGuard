FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 g++ clang ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY compilerlab /app/compilerlab
COPY verifylab.py /app/verifylab.py
COPY configs /app/configs
COPY tests /app/tests
RUN python3 -m unittest discover -s tests -v
CMD ["python3", "verifylab.py", "campaign", "--matrix", "configs/host.json", "--count", "24", "--out", "/results/campaign"]
