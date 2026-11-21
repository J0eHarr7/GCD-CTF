FROM python:3.12-slim

WORKDIR /srv/linas-blog

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY seed/ seed/
COPY wsgi.py .

ENV DATABASE_PATH=/tmp/linas_blog.sqlite3
EXPOSE 5000

# FLAG env var can be injected at deploy time by scoring infra; if unset,
# a random flag is generated at container start (see app/challenge/final_flag.py).
#
# Single worker on purpose: the DB file and the in-memory flag are both
# (re)initialized at process start, so multiple workers would each get
# their own SQLite file / flag and randomly disagree with each other.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "wsgi:app"]
