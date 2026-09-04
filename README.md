# Webordo CRM

CRM-система для учёта клиентов и управления продажами: единая база клиентов,
распределение по менеджерам, Канбан-воронка, задачи, шаблоны сообщений и
переход в WhatsApp с готовым текстом, ручная массовая рассылка, импорт/экспорт
Excel и мобильная версия.

Реализован **Этап 1 (MVP)** из технического задания.

## Стек

- Python 3.13, Django 5.1
- PostgreSQL 16 (`psycopg` 3)
- Серверный рендеринг (Django templates) + ванильный JS
- `openpyxl` — импорт/экспорт Excel
- Конфигурация через `.env` (`python-dotenv`)

## Возможности (Этап 1)

| Модуль | Где |
|---|---|
| Авторизация и роли (администратор / руководитель / менеджер) | `apps/crm/models.py`, `access.py` |
| Dashboard со сводкой по клиентам, задачам, продажам | `/` |
| База клиентов: поиск, фильтры, сортировка, массовые действия | `/clients/` |
| Карточка клиента: история, комментарии, задачи, WhatsApp | `/clients/<id>/` |
| Канбан с drag & drop, автосменой стадии и записью в историю | `/kanban/` |
| Задачи: вкладки (просрочено / сегодня / ближайшие / выполнено) | `/tasks/` |
| Сообщение из задачи → подстановка данных → WhatsApp | `/tasks/<id>/message/` |
| Шаблоны сообщений с переменными `{имя} {телефон} {менеджер} {объект} {бюджет}` | `/templates/` |
| Ручная массовая рассылка (пошагово 1/N, отправка вручную) | `/broadcast/` |
| Импорт Excel: предпросмотр → сопоставление колонок → проверка дублей по телефону | `/import/` |
| Экспорт Excel (всё / по фильтру / выбранные) | `/clients/export/` |
| Глобальный поиск, уведомления | `/search/`, `/notifications/` |
| Админ-панель: пользователи, менеджеры, стадии | `/admin-panel/...` |
| Мобильная версия с нижним меню | адаптив во всех шаблонах |

Автоматическая отправка через WhatsApp **не выполняется** — CRM только готовит
текст и открывает `wa.me`; менеджер отправляет сам и вручную отмечает статус.
Схема БD подготовлена ко второму этапу (WhatsApp Business API): `Message`,
`WhatsAppAction`, `BroadcastBatch`, `Notification`, заготовки триггеров в
`views._do_stage_change`.

## Запуск

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # при необходимости поправить POSTGRES_*

docker compose up -d db       # либо локальный PostgreSQL:
                              #   CREATE ROLE webordo LOGIN PASSWORD 'webordo' CREATEDB;
                              #   CREATE DATABASE webordo_srm OWNER webordo;

python manage.py migrate
python manage.py seed_crm --demo-users --import apps/crm/fixtures/sample_clients.xlsx
python manage.py runserver
```

`seed_crm` создаёт стадии воронки, шаблоны сообщений и (с `--demo-users`)
демо-аккаунты:

| Логин | Пароль | Роль |
|---|---|---|
| `admin` | `webordo123` | администратор (+ Django-админка) |
| `head` | `webordo123` | руководитель |
| `amantur`, `aziza` | `webordo123` | менеджеры |

Свой суперпользователь: `python manage.py createsuperuser`.

## Импорт своей базы

`/import/` → загрузить `.xlsx` → проверить автосопоставление колонок →
выбрать стратегию для дублей (пропустить / обновить / создать) → импортировать.
Дубли определяются по нормализованному номеру телефона; при отсутствии
телефона — по имени. Повторная загрузка того же файла помечается
предупреждением (`ImportLog.file_hash`).

Тестовый эталон — `apps/crm/fixtures/sample_clients.xlsx` (лист «список»).

## Структура

```
config/               настройки проекта
apps/crm/
  models.py           User, Stage, Client, ClientHistory, Task, MessageTemplate,
                       Message, WhatsAppAction, BroadcastBatch, Comment,
                       Notification, ImportLog
  views.py            все экраны
  access.py           разграничение доступа по ролям
  forms.py            формы
  services/           excel_import.py, excel_export.py
  utils.py            нормализация телефонов, рендер шаблонов, история
  context_processors.py  счётчики в навигации
  management/commands/seed_crm.py
templates/crm/        шаблоны
static/crm/           app.css (дизайн-система), app.js
```
