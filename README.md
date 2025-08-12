# Loyalty Bot — проект Телеграм бота для карты лояльности клентов бизнеса на YCLIENTS

---

## Краткое описание
Проект представляет собой backend на FastAPI с интеграцией Telegram-бота и фоновыми задачами. Основной функционал:

1. Сервис синхронизации - фоновые задачи (APScheduler) для синхронизации записей из внешней системы YCLIENTS и логики начисления/учёта баллов. Функции: `sync_records`, `notify_new_bonuses`. Хранение баллов в базе данных.
2. Telegram-бот - хэндлеры для взаимодействия с пользователями и администрацией: пользовательские команды (узнать баланс, привязать телефон и т.п.) и админ-функциональность (ручное начисление/списание баллов по номеру телефона).

Из внешней системы собираются все оплаченные записи. По конкретной бизнес-логике, реализованной в коде, для каждой оплаченной записи считается начисление баллов - 1% от суммы оплаты. Результат записывается в таблицу `bonuslog` и при необходимости отправляется уведомление клиенту в Telegram, если запись ещё не была уведомлена.

---

## Что включено в репозиторий
- `app/` - исходники приложения (models, db, bot, tasks, config).  
- `alembic/` и `alembic.ini` - миграции базы данных.  
- `.env.example` - шаблон переменных окружения - только для разработки и справки.  
- `requirements.txt` или `pyproject.toml` - зависимости.  
- `Dockerfile`, `docker-compose.yml` - проект рассчитан на развёртывание через Docker и Docker Secrets.

---

## Переменные окружения и секреты
В проекте для продакшн-развёртывания применяется механизм Docker Secrets. Значения конфиденциальных параметров не должны попадать в репозиторий. В `.env.example` приведены имена переменных и формат для справки. В продакшн-сценарии необходимо создать соответствующие Docker Secrets и подключить их в `docker-compose.yml` или в стеке Docker Swarm.

Примеры имён секретов для создания (примерные обозначения):
- FATHERBOT_TOKEN
- YCLIENTS_USER_TOKEN
- YCLIENTS_PARTNER_TOKEN
- DATABASE_URL
- COMPANY_ID
- ADMINS_IDS
- YCLIENTS_BOOK_URL
- COMPANY_YMAPS_LINK
- SUPPORT_PHONE

Пример команды создания Docker Secret (заменить значение на реальное):
```bash
echo "значение_секрета" | docker secret create FATHERBOT_TOKEN -
echo "postgresql+asyncpg://user:password@db:5432/loyaltydb" | docker secret create DATABASE_URL -
```

---

## Запуск и деплой - через Docker
Ниже приведена инструкция по развёртыванию приложения на выделенном сервере Ubuntu 24.04 с использованием Docker и Docker Compose.Предполагается, что nginx и certbot будут использоваться как обратный прокси и для получения SSL-сертификата.

### 1. Подготовка сервера
- Установить обновления и требуемые пакеты:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx
```

- Убедиться, что служба Docker запущена:
```bash
sudo systemctl enable --now docker
```

### 2. Клонирование репозитория и подготовка
```bash
cd /srv
git clone <your-repo-url>.git app-loyalty
cd app-loyalty
```

### 3. Создание Docker Secrets
Создать все необходимые секреты. Пример (на сервере выполнить для каждого секретного значения):
```bash
# Telegram bot token
echo "PASTE_FATHERBOT_TOKEN_HERE" | sudo docker secret create FATHERBOT_TOKEN -

# YCLIENTS tokens
echo "PASTE_YCLIENTS_USER_TOKEN_HERE" | sudo docker secret create YCLIENTS_USER_TOKEN -
echo "PASTE_YCLIENTS_PARTNER_TOKEN_HERE" | sudo docker secret create YCLIENTS_PARTNER_TOKEN -

# DATABASE_URL - можно хранить полную строку подключения
echo "postgresql+asyncpg://dbuser:dbpass@db:5432/loyaltydb" | sudo docker secret create DATABASE_URL -

# Остальные секреты
echo "1234567" | sudo docker secret create COMPANY_ID -
echo "111111111,222222222" | sudo docker secret create ADMINS_IDS -
echo "https://n1234567.yclients.com" | sudo docker secret create YCLIENTS_BOOK_URL -
echo "+79990000000" | sudo docker secret create SUPPORT_PHONE -
```

Значения заменить на реальные. Никогда не коммитить реальные значения в репозиторий.

### 4. Настройка Docker Compose
В `docker-compose.yml` ожидается, что сервис приложения использует Docker Secrets. 
### 5. Запуск контейнеров
```bash
# Собрать и запустить контейнеры
sudo docker compose up -d --build
# Проверить статус
sudo docker compose ps
# Просмотреть логи приложения
sudo docker compose logs -f web
```

### 6. Применение миграций
Миграции управляются Alembic. Применение миграций внутри контейнера:
```bash
# Вызвать команду alembic в работающем контейнере
sudo docker compose exec web alembic upgrade head
```
---

## 7. Настройка nginx и получение SSL сертификата (certbot)
- Привести nginx в состояние проксирования на локальный порт приложения 8000.
- Пример конфигурации `/etc/nginx/sites-available/loyalty`:
```nginx
server {
    listen 80;
    server_name example.com www.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

- Активировать сайт и перезагрузить nginx:
```bash
sudo ln -s /etc/nginx/sites-available/loyalty /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

- Получить SSL сертификат через certbot:
```bash
sudo certbot --nginx -d example.com -d www.example.com
```

После успешной выдачи сертификата certbot обновит nginx-конфигурацию для HTTPS.

---

## Функциональные детали
- Сбор оплаченных записей происходит в задачах синхронизации. Для каждой записи в коде определяется сумма оплаты и дата. Если запись помечена как оплаченная и ещё не была обработана, формируется запись в таблице `bonuslog` с вычислением баллов по правилу - 1% от суммы оплаты.
- При формировании записи в `bonuslog` сохраняются поля: `record_id`, `client_id`, `points`, `awarded_at`, `is_telegram_notified`. Если `is_telegram_notified` равно false, в задаче уведомлений формируется отправка сообщения в Telegram и флаг обновляется.
- Реализована защита от дублирования начислений - в `bonuslog` присутствует ограничение по `record_id`.
