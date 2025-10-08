# This is a skeleton Dockerfile for deploying the MOEX bot.
# Note: Installing broker SDKs (e.g. tinkoff-investments) requires
# network access and appropriate credentials and therefore is not
# included here.  Add RUN instructions as needed.

FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir pandas matplotlib apscheduler requests pyyaml fastapi uvicorn scikit-learn plotly prometheus_client seaborn

# Expose port 8000 if running a web interface via FastAPI/Dash later
EXPOSE 8000

CMD ["python", "run_backtests.py"]