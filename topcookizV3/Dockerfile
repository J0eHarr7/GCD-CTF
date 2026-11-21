FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLAG="GCDxGLORY{c00k13_j4r_1s_n3v3r_s4f3_fr0m_4_un10n_s3l3ct}"

EXPOSE 5000

# init_db() rebuilds a fresh DB on every container start
CMD ["sh", "-c", "python -c 'from app import init_db; init_db()' && python app.py"]
