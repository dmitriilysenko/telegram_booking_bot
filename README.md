# Telegram Booking Bot

[![Version](https://img.shields.io/github/v/tag/dmitriilysenko/telegram_booking_bot?label=version&sort=semver)](https://github.com/dmitriilysenko/telegram_booking_bot/tags)
[![Deploy](https://github.com/dmitriilysenko/telegram_booking_bot/actions/workflows/main.yml/badge.svg)](https://github.com/dmitriilysenko/telegram_booking_bot/actions/workflows/main.yml)

Бот для регистрации и записи на занятия по стрельбе: обычная запись по слотам и отдельный airsoft-формат.
Django + PostgreSQL + pyTelegramBotAPI + APScheduler. Запуск в Docker, деплой через GitHub Actions.

---

## Возможности

- 📝 Регистрация пользователей через `/start`, уведомление админов о новом участнике.
- 📅 Запись на занятия по слотам (расписание на текущую неделю).
- 🔒 Ограничения: 1 запись в день, 3 в неделю, запись открывается в понедельник в 09:00.
- ❌ Отмена записи, «Мои записи», профиль, отзывы.
- 🎯 Airsoft: тренировки отдельно для парней и девушек, подтверждение участия, статус тренировки у тренера.
- ⏰ Напоминания в группу за 30 минут до занятия, ежедневное расписание в 17:00.
- 🧹 Автоматическое гашение прошедших записей (`is_active=False`).
- 🛠 Админка Django для управления пользователями, записями, airsoft.

---

## Стек

- Python 3.12
- Django 5.x
- PostgreSQL 16
- pyTelegramBotAPI (telebot)
- django-apscheduler
- Gunicorn (WSGI)
- Nginx (gateway)
- Docker / Docker Compose
- GitHub Actions (CI/CD)

---

## Архитектура (production)

```
                ┌──────────────┐
   Telegram ───►│     bot      │  python manage.py runbot
                └──────┬───────┘
                       │
                ┌──────▼───────┐      ┌──────────────┐
   HTTP    ────►│   gateway    │─────►│   backend    │  gunicorn (Django)
   (8080)       │   (nginx)    │      └──────┬───────┘
                └──────────────┘             │
                       │              ┌──────▼───────┐
                       │              │   migrate    │  python manage.py migrate
                       │              └──────┬───────┘
                       │                     │
                       │              ┌──────▼───────┐
                       └─────────────►│      db      │  PostgreSQL 16
                                      └──────────────┘
```

- **bot** — polling Telegram, APScheduler (напоминания, расписание, airsoft, гашение прошедших).
- **backend** — Django + Gunicorn, отдаёт админку через nginx.
- **migrate** — разовый контейнер, применяет миграции при каждом деплое.
- **gateway** — nginx, проксирует на backend, раздаёт `staticfiles`.
- **db** — PostgreSQL с healthcheck.

---

## Быстрый старт (production / Docker)

```bash
git clone https://github.com/dmitriilysenko/telegram_booking_bot.git
cd telegram_booking_bot

cp .env.example .env
# заполни .env: SECRET_KEY, BOT_TOKEN, GROUP_CHAT_ID, BOT_LINK,
# POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, DOCKER_LOGIN, SERVER_NAME

docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml exec -T backend \
    python manage.py collectstatic --noinput
docker compose -f docker-compose.production.yml exec -T backend \
    python manage.py createsuperuser
```

Админка: `http://bot-admin.hopto.org:8080/admin/`

---

## Локальный запуск (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # заполни переменные
python manage.py migrate
python manage.py createsuperuser
python manage.py runbot
```

---

## Переменные окружения

| Переменная | Обязательна | Описание                                          |
|---|---|---------------------------------------------------|
| `SECRET_KEY` | да | Django secret key                                 |
| `DEBUG` | нет | `True` / `False` (по умолчанию `False`)           |
| `ALLOWED_HOSTS` | нет | через запятую, по умолчанию `localhost,127.0.0.1` |
| `SERVER_NAME` | да (prod) | домен для nginx (`server_name`)                   |
| `POSTGRES_DB` | да | имя БД                                            |
| `POSTGRES_USER` | да | пользователь БД                                   |
| `POSTGRES_PASSWORD` | да | пароль БД                                         |
| `DB_HOST` | нет | по умолчанию `db`                                 |
| `DB_PORT` | нет | по умолчанию `5432`                               |
| `BOT_TOKEN` | да | токен Telegram-бота                               |
| `BOT_LINK` | да | ссылка на бота (`https://t.me/SavelyMasterBot`)   |
| `GROUP_CHAT_ID` | да | ID группы для уведомлений                         |
| `TEST_GROUP_CHAT_ID` | нет | тестовая группа (fallback)                        |
| `DOCKER_LOGIN` | да (prod) | Docker Hub login, для тега образа                 |

Секреты в production задаются через GitHub Secrets и подставляются в `.env` на сервере шагом `deploy` (см. workflow).

---

## Структура проекта

```
.
├── bot_app/
│   ├── admin.py                # админка
│   ├── config.py               # слоты, лимиты, дни недели
│   ├── core.py                 # bot, logger, middleware (FSM reset)
│   ├── models.py               # User, Booking, Review, AirsoftTraining, AirsoftConfirmation
│   ├── scheduler.py            # APScheduler: напоминания, расписание, airsoft, гашение
│   ├── keyboards.py            # inline-клавиатуры
│   ├── bot_logic.py            # run_bot()
│   ├── exceptions.py           # validate_bot_settings()
│   ├── handlers/
│   │   ├── commands.py         # /start, /schedule, /book, /my_bookings, /cancel, /main, /profile, /reviews
│   │   ├── callbacks.py        # запись, отмена, airsoft, отзыв, профиль, регистрация
│   │   └── navigation.py       # nav_* callback'и + echo_all
│   ├── services/
│   │   ├── schedule.py         # расписание, слоты
│   │   ├── booking.py          # лимиты, уведомления
│   │   └── airsoft.py          # airsoft-логика
│   └── management/commands/
│       └── runbot.py           # команда запуска бота
├── telegram_booking_bot/       # Django project (settings, urls, wsgi)
├── nginx.conf
├── Dockerfile
├── docker-compose.yml          # локальная разработка
├── docker-compose.production.yml
├── requirements.txt
├── .env.example
└── .github/workflows/
    ├── main.yml                # build → deploy → notify
    └── release.yml             # bump version → tag
```

---

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Регистрация / приветствие |
| `/schedule` | Расписание на текущую неделю |
| `/book` | Записаться на занятие |
| `/my_bookings` | Мои записи |
| `/cancel` | Отменить последнюю запись |
| `/profile` | Личный кабинет |
| `/reviews` | Последние отзывы (только админ) |
| `/main` | Справка по командам |

---

## CI/CD

Workflow `.github/workflows/main.yml` при push в `main`:

1. **build_and_push** — собирает Docker-образ, пушит в Docker Hub с тегом `latest`.
2. **deploy** — копирует `docker-compose.production.yml` и `nginx.conf` на сервер по SCP, обновляет `.env` из secrets, делает `pull` + `up -d` + `collectstatic`.
3. **send_message** — уведомление в Telegram об успешном деплое.

Workflow `.github/workflows/release.yml` при push в `main` поднимает patch-версию, ставит git-тег `vX.Y.Z` и пушит его. Версия отображается бейджем в шапке README.

### Секреты репозитория

| Секрет | Назначение |
|---|---|
| `DOCKER_LOGIN` / `DOCKER_PASSWORD` | Docker Hub |
| `HOST` / `USER` / `SSH_KEY` | SSH-доступ к серверу |
| `DOMAIN` | домен для `ALLOWED_HOSTS` и nginx |
| `SECRET_KEY`, `BOT_TOKEN`, `GROUP_CHAT_ID`, `TEST_GROUP_CHAT_ID`, `BOT_LINK` | конфиг бота |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | конфиг БД |
| `TELEGRAM_TO` | chat_id для уведомлений о деплое |

---

## Релизы и версионирование

Версия хранится в **git-теге** (`v1.0.0`, `v1.0.1`, ...). Workflow `release.yml` автоматически:

1. Берёт последний тег.
2. Поднимает **patch** (`v1.0.0` → `v1.0.1`).
3. Ставит тег и пушит его.

Если нужен **minor** / **major** — пушь тег вручную:

```bash
git tag v1.1.0
git push origin v1.1.0
```

## Автор

dmitriilys / Lysenko D. P.