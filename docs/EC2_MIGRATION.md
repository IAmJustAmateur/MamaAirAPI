# Тестовый перенос PostgreSQL между EC2

Источник — действующий production `api.mamaair.work`. Приёмник — новый EC2
`api-new.mamaair.work`. Выполняйте этот порядок после согласования тестового
переноса. На источнике нужны только диагностические запросы и чтение для
резервного копирования. Переключение в этом сценарии касается только нового EC2.

## 1. Подготовить доступ и проверить обе базы

Настройте SSH-алиасы `mamaair-api-prod` и `mamaair-api-dev` для старого
и нового EC2 соответственно. Сверьте отпечатки SSH host keys по доверенному
каналу и идентификаторы инстансов и AWS-аккаунтов по инвентарю. Для каждого шага
явно проверяйте, к какому EC2 подключена сессия. На обоих серверах откройте Bash
в корне того же checkout, из которого запущен Compose-проект. Если при
развёртывании задавали имя проекта через `-p` или `COMPOSE_PROJECT_NAME`,
экспортируйте то же имя как `COMPOSE_PROJECT_NAME` в этой сессии,
чтобы и команды Compose, и скрипты использовали один проект.
Имя можно получить из метки уже запущенного контейнера Compose:

```bash
project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' agent_api_db)" &&
  test -n "$project" && export COMPOSE_PROJECT_NAME="$project"
```

На обоих EC2 выполните команды ниже. Держите каталог резервных копий
вне checkout на зашифрованном диске. Функции пригодятся в следующих шагах.

```bash
umask 077
set -o pipefail
BACKUP_DIR="$HOME/mamaair-db-backups"
install -d -m 700 "$BACKUP_DIR"

compose() {
  docker compose --env-file "$PWD/.env" -f "$PWD/deployment/docker-compose.yml" "$@"
}

db_psql() {
  local database="$1"
  shift
  compose exec -T db sh -ec '
    database=${1:-$POSTGRES_DB}
    shift
    export PGPASSWORD="$POSTGRES_PASSWORD"
    export PGOPTIONS="-c default_transaction_read_only=on"
    exec psql -X -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 \
      -U "$POSTGRES_USER" -d "$database" "$@"
  ' sh "$database" "$@"
}

compose ps
df -h "$BACKUP_DIR"
db_psql '' <<'SQL'
SELECT current_database() AS database,
       current_setting('server_version') AS server_version,
       current_setting('server_version_num') AS server_version_num,
       pg_size_pretty(pg_database_size(current_database())) AS database_size,
       current_setting('server_encoding') AS encoding,
       current_setting('lc_collate') AS collation,
       current_setting('lc_ctype') AS character_classification;
SELECT extname, extversion FROM pg_extension ORDER BY extname;
SQL
compose exec -T db pg_dump --version
compose exec -T db pg_restore --version
compose exec -T web python manage.py showmigrations --plan
compose exec -T web python manage.py migrate --plan
```

Compose использует `postgres:15` и передаёт `DB_NAME`, `DB_USER`,
`DB_PASSWORD` в `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
Скрипты используют клиентские утилиты из контейнера `db`. Для репетиции
предпочтительно совпадение major-версий. Major-версия целевого сервера
должна быть не ниже версий исходного сервера и `pg_dump`. Сверьте кодировку,
локали и доступность расширений. Восстановление создаёт базу из целевого
`template0`, поэтому на приёмнике проверьте и его параметры.

```bash
db_psql '' -c "SELECT datname, pg_encoding_to_char(encoding) AS encoding, datcollate, datctype
               FROM pg_database WHERE datname = 'template0';"
compose exec -T db df -h /var/lib/postgresql/data
```

Сохраните вывод планов миграций. В этой ветке миграции `api` доходят
до `0056_accountfilecleanup`, а `recommendations` — до
`0009_recommendationrule_recommendation_mental`. На EC2 ориентируйтесь на версии
кода в фактически запущенных образах. Проверьте запас места под исходную
базу нового EC2, восстановленную базу с индексами и WAL и оба архива.

## 2. Изолировать новый EC2 перед получением копии

- Разрешите SSH только операторам через утверждённый VPN, bastion или список IP.
  Закройте публичный вход на 80/443 и 5432 во всех применимых security groups.
  Для HTTPS-проверок ниже используется SSH-туннель до существующего Caddy.
  С отдельной машины вне разрешённой сети проверьте, что сайт недоступен.
- На время работы с копией запретите исходящие соединения контейнеров приложения
  к внешним сервисам на сетевом уровне. Правило должно распространяться на Docker
  и IPv4/IPv6, сохранять доступ к локальной БД и проверяться из тестового
  контейнера до запуска на копии. В частности, заблокируйте SMTP, Google/Firebase
  и OpenWeatherMap. Некоторые функции погоды передают координаты даже при
  пустом `OWM_API_KEY`.
- Ограничьте доступ к SSH, Docker, PostgreSQL, EBS и снимкам теми операторами,
  которым он нужен. Проверьте правила обработки данных и доступ к KMS
  в обоих AWS-аккаунтах. Архив, содержимое БД, WAL и снимки могут содержать ПДн,
  сведения о беременностях и симптомах, геолокацию, хеши паролей, токены
  и данные аудита. Храните их на зашифрованных дисках EBS в приватном каталоге
  с правами `0700` и файлами `0600`. SHA-256 проверяет целостность, а шифрование
  при передаче обеспечивает SSH.
- На новом EC2 остановите `celery_worker`, который обслуживает очередь `email`,
  и `account_cleanup`, который повторяет удаление файлов. Запишите исходное
  состояние сервисов. Приостановите внешние cron/systemd-задачи или отдельно
  развернутые воркеры, если они обращаются к тестовой среде.
- Используйте отдельный `SECRET_KEY` тестового приложения, синтетическую учётную
  запись и синтетические данные для функциональных проверок. Приватные
  координатные ключи для проверки расшифровки передавайте отдельно через
  утверждённое хранилище секретов. Не копируйте production `.env`, SMTP/Firebase
  credentials или media. В PostgreSQL хранятся ссылки на файлы, а содержимое
  `media_volume` переносится отдельно.
- Выводите агрегаты и статусы. Не сохраняйте строки таблиц, координаты,
  токены, тела ответов API и содержимое писем в чатах, Git или журналах.
  Зафиксируйте срок хранения и ответственного за ручное удаление тестовой копии,
  ключей, архивов и связанных снимков после согласования.

На новом EC2:

```bash
compose ps -a
compose stop celery_worker account_cleanup
compose ps -a celery_worker account_cleanup
```

## 3. Снять дамп на старом EC2 и передать по SSH

На старом EC2 из корня репозитория:

```bash
archive="$(bash scripts/backup_db.sh --output-dir "$BACKUP_DIR")" &&
  stat -c '%a %s %n' "$archive" "$archive.sha256" &&
  basename "$archive"
```

`pg_dump` записывает согласованный снимок в custom format при работающем
приложении. Скрипт выводит путь готового архива в stdout. Для передачи
нужны сам `.dump` и соседний `.dump.sha256`. Каталог по умолчанию
`$HOME/mamaair-db-backups`. Если нужны контрольные количества строк,
снимите их на источнике по шагу 5 сразу после создания архива.

Из Bash на компьютере оператора подставьте фактические абсолютные пути
каталогов на серверах и имя файла, выведенное предыдущей командой.
`scp -3` передаёт содержимое через клиент SSH без промежуточной записи на
локальный диск. Ключи SSH остаются на компьютере оператора.
[Документация OpenSSH](https://man.openbsd.org/scp#3)

```bash
SOURCE_DIR=/home/ec2-user/mamaair-db-backups
TARGET_DIR=/home/ec2-user/mamaair-db-backups
DUMP_NAME=postgresql-YYYYMMDDTHHMMSSZ-XXXXXXXX.dump

scp -3 -p -o StrictHostKeyChecking=yes \
  "mamaair-api-prod:$SOURCE_DIR/$DUMP_NAME" \
  "mamaair-api-prod:$SOURCE_DIR/$DUMP_NAME.sha256" \
  "mamaair-api-dev:$TARGET_DIR/"
```

На новом EC2 подставьте то же имя и проверьте полученные файлы.

```bash
DUMP_NAME=postgresql-YYYYMMDDTHHMMSSZ-XXXXXXXX.dump
archive="$BACKUP_DIR/$DUMP_NAME"
chmod 600 "$archive" "$archive.sha256" &&
  (cd "$BACKUP_DIR" && sha256sum --check --strict "$DUMP_NAME.sha256")
```

Продолжайте после `OK` и нулевого кода выхода. При прерванной передаче
повторите передачу обоих файлов и проверку.

## 4. Сохранить базу нового EC2 и восстановить отдельную копию

На новом EC2 запишите имя текущей базы `web` и убедитесь, что оно совпадает
с базой, из которой скрипт сделает backup. При расхождении выясните, какая
конфигурация используется работающим приложением, перед резервным копированием.

```bash
PREVIOUS_DB="$(compose exec -T web sh -ec 'printf "%s\n" "$DB_NAME"')"
CURRENT_DB="$(db_psql '' -Atc 'SELECT current_database()')"
test -n "$PREVIOUS_DB" && test "$PREVIOUS_DB" = "$CURRENT_DB" &&
  printf 'Previous application database: %s\n' "$PREVIOUS_DB" &&
  bash scripts/backup_db.sh --output-dir "$BACKUP_DIR"
```

Сохраните путь полученного архива предыдущей базы. В отдельно проверенной
SSH-сессии на новом EC2 запишите полный ID его контейнера PostgreSQL.

```bash
compose ps --status running --quiet db
```

В сессии восстановления подставьте записанный ID. Используйте новое имя
базы для каждой репетиции. Сохраните имя прежней и новой баз для проверки
и возврата.

```bash
EXPECTED_DB_CONTAINER=REPLACE_WITH_RECORDED_FULL_DOCKER_CONTAINER_ID
RESTORED_DB="mamaair_restore_$(date -u +%Y%m%d_%H%M%S)"

bash scripts/restore_db.sh "$archive" --database "$RESTORED_DB" \
  --confirm-container "$EXPECTED_DB_CONTAINER"
```

Скрипт сверяет ID, SHA-256 и читаемость архива, проверяет версии и создаёт
новую базу. Существующие базы защищены, включая активную `POSTGRES_DB`.
Владельцы и ACL источника пропускаются, объекты создаются ролью целевого
PostgreSQL. Восстановление транзакционное. При ошибке может остаться пустая
созданная база. После диагностики используйте свежее имя для новой попытки.
Скрипт не переключает приложение и не запускает миграции.

## 5. Сверить количество записей и целостность до миграций

Определите эту функцию в обеих сессиях. Она выводит только метки таблиц
и количества, включая таблицы пользователей, перемещений, симптомов и
`django_migrations`. На production выполняйте полные подсчёты при приемлемой
нагрузке.

```bash
row_counts() {
  db_psql "$1" -Atq -F $'\t' <<'SQL'
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT format('SELECT %L, count(*) FROM %I.%I;', tablename, schemaname, tablename)
FROM pg_catalog.pg_tables
WHERE schemaname = 'public'
ORDER BY tablename COLLATE "C"
\gexec
COMMIT;
SQL
}
```

На старом EC2 запишите контрольные значения как можно ближе к моменту дампа.
Если шаг уже пройден, сохраните серверное время контрольного замера и
учтите разницу со временем архива.

```bash
date -u
row_counts '' >"$BACKUP_DIR/source-counts.tsv"
```

На компьютере оператора используйте те же `SOURCE_DIR` и `TARGET_DIR`:

```bash
scp -3 -p -o StrictHostKeyChecking=yes \
  "mamaair-api-prod:$SOURCE_DIR/source-counts.tsv" "mamaair-api-dev:$TARGET_DIR/"
```

На новом EC2 до `migrate` и до тестовых записей:

```bash
row_counts "$RESTORED_DB" >"$BACKUP_DIR/restored-counts.tsv"
diff -u "$BACKUP_DIR/source-counts.tsv" "$BACKUP_DIR/restored-counts.tsv"
```

Подсчёт на работающем production использует отдельный снимок, поэтому
параллельные изменения дают допустимые расхождения. Сопоставьте их с
временем дампа и активностью приложения, а различия в наборе таблиц и
необъяснимые расхождения разберите до переключения. Сверьте список
ограничений без валидации и количество записей без связанного пользователя.
На старом EC2 задайте `CHECK_DB=''`, а на новом
`CHECK_DB="${RESTORED_DB:?Set RESTORED_DB}"`. Затем выполните одинаковый SQL.

```bash
db_psql "${CHECK_DB?Set CHECK_DB for this EC2}" <<'SQL'
SELECT c.conrelid::regclass AS relation, c.conname
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname = 'public' AND c.contype = 'f' AND NOT c.convalidated
ORDER BY 1, 2;
SELECT 'movements' AS relation, count(*) AS orphan_rows
FROM public.movements m LEFT JOIN public.api_user u ON u.myuser_ptr_id = m.user_id
WHERE u.myuser_ptr_id IS NULL
UNION ALL
SELECT 'api_airexposurelog', count(*)
FROM public.api_airexposurelog e
LEFT JOIN public.api_user u ON u.myuser_ptr_id = e.user_id
WHERE u.myuser_ptr_id IS NULL;
SQL
```

Для этих двух связей ожидается `orphan_rows = 0`. Если сравниваемая версия
схемы старше и таблицы отсутствуют, сверьте `showmigrations --plan` и
адаптируйте SQL к общей версии исходной и восстановленной схем.

## 6. Проверить миграции и координаты в отдельном процессе

На новом EC2 создайте локальный Compose overlay вне checkout. Штатный
`deployment/entrypoint.sh` запускает `migrate` при `DJANGO_ENV=production`
или `staging`. Overlay запускает Gunicorn напрямую и оставляет миграции
отдельной командой оператора. `production` вместе с `DEBUG=false` закрывает
дополнительные debug-маршруты, которые доступны в режиме `staging`.

```bash
set +x
TRIAL_COMPOSE="$BACKUP_DIR/trial.compose.yml"
export TRIAL_COORDINATE_ENV="$BACKUP_DIR/trial.coordinate.env"
export TRIAL_FIREBASE_PLACEHOLDER="$BACKUP_DIR/trial.firebase-disabled.json"
export TRIAL_DB_NAME="$RESTORED_DB"

TRIAL_SECRET_FILE="$BACKUP_DIR/trial.secret"
if [ ! -s "$TRIAL_SECRET_FILE" ]; then
  openssl rand -hex 48 >"$TRIAL_SECRET_FILE"
fi
export TRIAL_DJANGO_SECRET_KEY="$(cat "$TRIAL_SECRET_FILE")"
touch "$TRIAL_COORDINATE_ENV"
printf '{}\n' >"$TRIAL_FIREBASE_PLACEHOLDER"
chmod 600 "$TRIAL_SECRET_FILE" "$TRIAL_COORDINATE_ENV" "$TRIAL_FIREBASE_PLACEHOLDER"

cat >"$TRIAL_COMPOSE" <<'YAML'
services:
  web:
    command: ["gunicorn", "agent_api.wsgi:application", "--bind", "0.0.0.0:8000"]
    env_file:
      - ${TRIAL_COORDINATE_ENV:?Set TRIAL_COORDINATE_ENV}
    volumes:
      - ${TRIAL_FIREBASE_PLACEHOLDER:?Set TRIAL_FIREBASE_PLACEHOLDER}:/run/secrets/firebase_service_account.json:ro
    environment:
      DB_NAME: ${TRIAL_DB_NAME:?Set TRIAL_DB_NAME}
      DJANGO_ENV: production
      DEBUG: "false"
      SECRET_KEY: ${TRIAL_DJANGO_SECRET_KEY:?Set TRIAL_DJANGO_SECRET_KEY}
      DJANGO_SECRET_KEY: ${TRIAL_DJANGO_SECRET_KEY:?Set TRIAL_DJANGO_SECRET_KEY}
      AUTH_PUBLIC_URL: https://api-new.mamaair.work
      EMAIL_BACKEND: django.core.mail.backends.dummy.EmailBackend
      EMAIL_HOST_USER: ""
      EMAIL_HOST_PASSWORD: ""
      CELERY_BROKER_URL: memory://
      AUTH_REDIS_CACHE_URL: ""
      FIREBASE_CREDENTIALS: ""
      GOOGLE_ALLOWED_AUDS: ""
      DELETION_GOOGLE_CLIENT_ID: ""
      DELETION_FIREBASE_API_KEY: ""
      DELETION_FIREBASE_AUTH_DOMAIN: ""
      DELETION_FIREBASE_PROJECT_ID: ""
      DELETION_FIREBASE_APP_ID: ""
      OWM_API_KEY: ""
      AUDIT_LOG_ENABLED: "false"
YAML

trial() {
  compose -f "$TRIAL_COMPOSE" "$@"
}
```

Через защищённый канал заполните `trial.coordinate.env` значениями
`MOVEMENT_COORDINATE_KEYS`, `MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION` и, при
отличии от значения по умолчанию, `MOVEMENT_H3_RESOLUTION`. В карте AES-ключей
нужны все версии, используемые зашифрованными записями, и активная версия.
Файл имеет формат Compose env-файла. Для JSON-карты в нём можно использовать
одинарные кавычки вокруг целого JSON. Для проверки Compose используйте
`config --quiet`, поскольку полный вывод содержит секреты.

Проверьте настроенную блокировку исходящих соединений из одноразового
контейнера приложения. Проверка открывает только TCP-соединение и не передаёт
данные. Если какое-либо соединение удалось, исправьте правила до запуска.

```bash
trial config --quiet &&
  trial run --rm --no-deps -T web python - <<'PY'
import socket

for host, port in [
    ("smtp.gmail.com", 587),
    ("accounts.google.com", 443),
    ("identitytoolkit.googleapis.com", 443),
    ("api.openweathermap.org", 80),
    ("api.openweathermap.org", 443),
]:
    try:
        with socket.create_connection((host, port), timeout=3):
            raise SystemExit(f"Unexpected outbound connectivity to {host}:{port}")
    except OSError:
        print(f"Outbound connection unavailable to {host}:{port}")
PY
```

Сначала подтвердите подключение к `RESTORED_DB` и изучите план:

```bash
trial_manage() {
  trial run --rm --no-deps -T web python manage.py "$@"
}

trial config --quiet &&
  trial_manage shell --no-imports -c \
    'from django.db import connection; c = connection.cursor(); c.execute("SELECT current_database()"); print(c.fetchone()[0])' &&
  trial_manage showmigrations --plan &&
  trial_manage migrate --plan
```

В выводе должно быть имя `RESTORED_DB`. Оцените операции и совместимость
образа. При наличии одобренных миграций выполните их явно, затем проверьте
применение. Для уже актуальной схемы достаточно проверок.

```bash
trial_manage migrate --noinput
trial_manage showmigrations --plan &&
  trial_manage migrate --check
```

Миграция `0047_movement_location_security` добавляет поля для AES-256-GCM
и H3. Она не шифрует исторические записи. `backfill_movement_locations`
изменяет данные и требует отдельного решения. Открытые поля координат
в `movements` и `api_airexposurelog`, а также H3-ячейки, учитывайте как
чувствительные данные независимо от результатов проверки.

Проверьте аутентификацию и расшифровку выборки для каждой версии ключа без
вывода координат или идентификаторов пользователей:

```bash
trial_manage shell --no-imports <<'PY'
from django.db.models import Count
from api.models import Movement
from api.services.coordinate_encryption import CoordinateEncryptionError, decrypt_coordinates

encrypted = Movement.objects.filter(coordinates_encrypted__isnull=False)
print("Movement rows without ciphertext:", Movement.objects.count() - encrypted.count())
if encrypted.filter(coordinates_key_version__isnull=True).exists():
    raise SystemExit("Encrypted movements with missing key versions")
if not encrypted.exists():
    raise SystemExit("No encrypted movements available to verify")

versions = encrypted.values("coordinates_key_version").annotate(total=Count("pk"))
for group in versions.order_by("coordinates_key_version"):
    version = group["coordinates_key_version"]
    sample = encrypted.filter(coordinates_key_version=version).order_by("pk")
    checked = 0
    for ciphertext in sample.values_list("coordinates_encrypted", flat=True)[:20]:
        try:
            decrypt_coordinates(ciphertext, version)
        except CoordinateEncryptionError:
            raise SystemExit(f"Coordinate validation failed for key version {version}") from None
        checked += 1
    print(f"Key version {version}: checked {checked} of {group['total']} rows")
PY
```

Отсутствие зашифрованных строк означает, что проверку расшифровки нельзя
подтвердить по этому архиву. Разберите неожиданные ошибки до запуска `web`.

## 7. Переключить новый web и проверить API

Сохраняйте сетевые ограничения и остановленные фоновые сервисы. Запустите
только `web` с overlay. `--no-deps` оставляет `db`, Redis и Caddy без
пересоздания. Наличие действующего сертификата Caddy проверьте заранее,
поскольку выпуск или обновление публичного сертификата требует внешней сети.

```bash
trial up -d --no-deps --force-recreate --wait web &&
  trial ps -a
trial exec -T web python manage.py shell --no-imports -c \
  'from django.db import connection; c = connection.cursor(); c.execute("SELECT current_database()"); print(c.fetchone()[0])'
trial exec -T web python manage.py migrate --check
```

Проверьте, что подключена `RESTORED_DB`, а `celery_worker` и
`account_cleanup` остановлены. С компьютера оператора откройте туннель.
Во второй локальной сессии проверьте TLS, открытый маршрут и требование
аутентификации, сохраняя исходное доменное имя для TLS и HTTP.

```bash
ssh -o ExitOnForwardFailure=yes -N -L 127.0.0.1:8443:127.0.0.1:443 mamaair-api-dev
```

```bash
curl -fsS --max-time 15 --noproxy '*' --connect-to api-new.mamaair.work:443:127.0.0.1:8443 \
  https://api-new.mamaair.work/api/meta/choices/ -o /dev/null
test "$(curl -sS --max-time 15 --noproxy '*' --connect-to api-new.mamaair.work:443:127.0.0.1:8443 \
  https://api-new.mamaair.work/api/profile/ -o /dev/null -w '%{http_code}')" = 401
```

На новом EC2 проверьте вход по паролю, профиль и чтение каталога задач
через HTTP. Тест создаёт только синтетическую учётную запись в копии и
удаляет её после проверки. Пароль, JWT и тела ответов остаются в процессе
теста.

```bash
trial exec -T web python manage.py shell --no-imports <<'PY'
import json
import os
from secrets import token_urlsafe
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection

database = os.environ["DB_NAME"]
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database()")
    if cursor.fetchone()[0] != database or not database.startswith("mamaair_restore_"):
        raise SystemExit("Smoke test requires the restored test database")

opener = build_opener(ProxyHandler({}))

def request(path, *, payload=None, access=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    body = json.dumps(payload).encode() if payload is not None else None
    if access:
        headers["Authorization"] = f"Bearer {access}"
    message = Request(f"http://127.0.0.1:8000{path}", data=body, headers=headers)
    with opener.open(message, timeout=10) as response:
        return json.load(response)

email = f"migration-{uuid4().hex}@example.invalid"
password = token_urlsafe(32)
user = get_user_model().objects.create_user(email=email, password=password, email_verification_pending=False)
try:
    access = request("/api/auth/email/login/", payload={"email": email, "password": password})["access"]
    if request("/api/profile/", access=access)["email"] != email:
        raise SystemExit("Unexpected profile")
    if not isinstance(request("/api/daily-tasks/", access=access), list):
        raise SystemExit("Unexpected daily task response")
    print("Email login, authenticated profile and daily tasks passed")
finally:
    user.delete()
PY
```

Google/Firebase, SMTP, прогноз погоды и загрузку маршрутов проверяйте
отдельно с синтетической базой. `scripts/test_server_api.py` выполняет
широкий набор записей и может вызывать внешние интеграции.

## 8. Вернуть новый EC2 к прежней базе

Оставьте ограничения доступа и внешних вызовов. В той же сессии подставьте
ранее записанное имя `PREVIOUS_DB`, если переменная была потеряна.
Для быстрого возврата сохраните защиту overlay и измените только базу `web`.

```bash
export TRIAL_DB_NAME="$PREVIOUS_DB"
trial_manage migrate --check &&
  trial up -d --no-deps --force-recreate --wait web &&
  trial exec -T web python manage.py shell --no-imports -c \
    'from django.db import connection; c = connection.cursor(); c.execute("SELECT current_database()"); print(c.fetchone()[0])'
```

Убедитесь, что подключена `PREVIOUS_DB` и проходит HTTPS-проверка
`/api/meta/choices/`. Дамп предыдущей базы нужен на случай её недоступности,
а обычный возврат переключает приложение на существующую базу. Копию и
архивы сохраните до решения об их безопасном удалении.

Для возврата обычной конфигурации убедитесь, что базовый Compose по-прежнему
настроен на `PREVIOUS_DB`, проверьте миграции этой базы и пересоздайте только
`web` из базовой конфигурации. Штатный entrypoint проверит и выполнит свой
обычный startup. Восстановите исходное состояние фоновых сервисов и сетевых
правил только после подтверждения, что ни один сервис не обращается к
тестовой копии. Пример для изначально запущенных обоих воркеров:

```bash
compose config --quiet &&
  configured_db="$(compose run --rm --no-deps -T web sh -ec 'printf "%s\n" "$DB_NAME"')" &&
  test -n "$PREVIOUS_DB" && test "$configured_db" = "$PREVIOUS_DB" &&
  compose run --rm --no-deps -T web python manage.py migrate --check &&
  compose up -d --no-deps --force-recreate --wait web &&
  compose up -d --no-deps celery_worker account_cleanup
```

Проверьте имя базы в новом `web`, здоровье сервисов и прежний API.
Не удаляйте Docker volumes при переключении или возврате.
