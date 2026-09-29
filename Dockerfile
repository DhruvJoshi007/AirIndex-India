FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir pandas numpy fastapi uvicorn
COPY . .
# build six months of demo history at image build time (~1 minute)
RUN python -m airindex.pipeline backfill
EXPOSE 8000
CMD ["uvicorn", "airindex.api:app", "--host", "0.0.0.0", "--port", "8000"]
