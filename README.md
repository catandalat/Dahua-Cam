# Dahua ANPR Operations System

Multi-gate ANPR operations platform for **Dahua DHI-ITC413** cameras.

## Stack

- Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Redis
- Event listener (HTTP Digest multipart attach)
- React + Vite dashboard

## Quick start

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

- API: http://localhost:8000/docs
- Dashboard: http://localhost:5173

### Local (without Docker for Python)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
# start postgres + redis via compose
docker compose -f infra/docker-compose.yml up -d postgres redis
export PYTHONPATH=packages:apps
uvicorn api.main:app --reload --port 8000
python -m listener.main
```

### Probe camera caps

```bash
probe-camera --host 192.168.1.108 --user admin --password '***' -o caps.json
```

### Extended camera ops (API)

- Snapshot / manual snap / strobe / speed-limit / unlicensed detection
- RTSP URL, device info, parking status (nếu firmware hỗ trợ)
- Flow by lane, jam events, vehicle registry (10.7 sync)

Dashboard thêm trang **Lưu lượng**, **Registry xe**, và panel điều khiển trên **Cameras**.

### Retention

```bash
anpr-retention --days 30
```

### Backfill media find

```bash
anpr-backfill --camera-id <uuid> --hours 2
```
