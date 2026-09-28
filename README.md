# Reminder Bot

Telegram-бот-напоминалка на `aiogram 3`. Понимает свободный текст, хранит напоминания в SQLite, восстанавливает незавершённые задачи после рестарта.

## Возможности

- Свободный ввод: `напомни через 30 минут позвонить маме`, `завтра в 15:00 встреча`
- Команды: `/remind`, `/list`, `/cancel`
- Хранение в SQLite через `aiosqlite` (без ORM — намеренно, см. ниже)
- Атомарная отправка через `UPDATE ... RETURNING` — нет race condition при misfire
- Восстановление pending-задач после перезапуска, включая просроченные

## Почему SQLite

Нагрузка — единичные записи на пользователя, конкурентных writers почти нет. SQLite + WAL закрывает этот профиль с запасом и убирает необходимость разворачивать Postgres и возиться с докерфайлом и тем более докер композом. Если проект вырастет — переход на Postgres в этом коде — замена `db.py`, интерфейс останется. Запросы идут безопасно - для данных используются Плейсхолдеры убирающие возможность SQL-иньекции

## Установка

```bash
git clone 
cd reminder-bot
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env
# впиши BOT_TOKEN от @BotFather
```

## Запуск

```bash
python -m app.bot
```

## Команды

| Команда | Что делает |
|---|---|
| `/start` | приветствие и подсказки |
| `/remind <текст>` | явно добавить напоминание |
| `/list` | список активных напоминаний |
| `/cancel <id>` | отменить напоминание по id |
| (свободный текст с «напомни», «через», «завтра» …) | авто-разбор |

## Схема БД

```sql
CREATE TABLE reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    remind_at  TEXT    NOT NULL,   -- ISO 8601 в UTC
    is_sent    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_reminders_pending ON reminders(is_sent, remind_at);
```

`remind_at` хранится строкой в UTC — это позволяет сравнивать его лексикографически через `WHERE remind_at > ?`, что для ISO 8601 корректно. Все конвертации в локальную зону — на уровне хендлеров.

## Интерфейс `app/db.py`

Модуль должен экспортировать:

| Функция | Возвращает |
|---|---|
| `init_db()` | создать схему, включить WAL |
| `add_reminder(user_id, text, remind_at) -> int` | id новой записи |
| `claim_for_sending(reminder_id) -> (user_id, text) \| None` | атомарно помечает `is_sent=1`, возвращает данные; `None`, если уже отправлено |
| `get_pending(now) -> list[tuple]` | строки `(id, user_id, text, remind_at_str)` для неотправленных с `remind_at > now` |
| `get_user_active(user_id, now) -> list[tuple]` | строки `(id, text, remind_at_str)` активных напоминаний пользователя |
| `delete_reminder(reminder_id, user_id) -> bool` | `True`, если удалено и принадлежит пользователю |

## Структура
Структура многопапочная и следует принципам SOLID:
```
.
├── app
│   ├── bot.py // высокоуровневый запуск Loop цикла бота
│   ├── config.py
│   ├── db.py // низкоуровневые запросы к БД(sqlite)
│   ├── handlers //  высокоуровневый обработчик запросов 
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── reminders.cpython-314.pyc
│   │   │   └── start.cpython-314.pyc
│   │   ├── reminders.py
│   │   └── start.py
│   ├── __init__.py
│   ├── __pycache__
│   │   ├── bot.cpython-314.pyc
│   │   ├── config.cpython-314.pyc
│   │   ├── db.cpython-314.pyc
│   │   └── __init__.cpython-314.pyc
│   └── services // низкоуровневое распределение задач
│       ├── __init__.py
│       ├── parser.py
│       ├── __pycache__
│       │   ├── __init__.cpython-314.pyc
│       │   ├── parser.cpython-314.pyc
│       │   └── scheduler.cpython-314.pyc
│       └── scheduler.py
├── README.md
├── reminders.db //база
└── requirements.txt

7 directories, 23 files
```

## Лицензия

MIT, проект  свободен
