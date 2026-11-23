import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager


CATEGORIES = ('Обладнання', 'Мережі', 'Програми')
DEVICES = {'printer': 'Принтер', 'network': 'Мережа', 'workstation': 'Комп’ютер і периферія', 'software': 'Робоча програма'}
ROLES = ('admin', 'editor', 'reader')
DEMO_PASSWORD = 'Demo2026!'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'reader')),
    salt BLOB NOT NULL, password_hash BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
    keywords TEXT NOT NULL, body TEXT NOT NULL, author_id INTEGER NOT NULL REFERENCES users(id),
    version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS versions (
    article_id INTEGER NOT NULL REFERENCES articles(id), version INTEGER NOT NULL,
    title TEXT NOT NULL, category TEXT NOT NULL, keywords TEXT NOT NULL, body TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (article_id, version)
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id),
    user_id INTEGER NOT NULL REFERENCES users(id), message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

DEMO_ARTICLES = (
    ('Налаштування принтера', 'Обладнання', 'принтер, друк, драйвер, Windows',
     'Під’єднай принтер до живлення та до комп’ютера або навчальної мережі.\n\n'
     '1. У Windows відкрий «Параметри» → «Bluetooth і пристрої» → «Принтери та сканери».\n'
     '2. Вибери «Додати пристрій» і знайди потрібний принтер.\n'
     '3. Відкрий властивості принтера та надрукуй пробну сторінку.\n\n'
     'Якщо принтер відсутній у списку, перевір підключення й передай у Service Desk модель пристрою та повідомлення Windows.'),
    ('Перевірка підключення до мережі', 'Мережі', 'Wi-Fi, Ethernet, інтернет, діагностика',
     'Визнач, чи проблема виникла на одному комп’ютері або на кількох.\n\n'
     '1. Перевір стан підключення у параметрах Windows.\n'
     '2. Для Ethernet перевір кабель. Для Wi-Fi звір назву обраної мережі.\n'
     '3. Запиши час збою й повідомлення, яке показує система.\n\nПід час звернення в підтримку додай ці спостереження до заявки.'),
    ('Створення заявки в Service Desk', 'Програми', 'Service Desk, підтримка, заявка',
     'Відкрий навчальний портал підтримки та створи нову заявку.\n\n'
     '1. Сформулюй проблему в одному реченні.\n'
     '2. Опиши, коли вона виникла і які дії її передували.\n'
     '3. За потреби додай знімок екрана без конфіденційних даних.\n\nЗбережи номер заявки для подальшого уточнення.'),
    ('Підготовка робочого місця', 'Обладнання', 'монітор, периферія, робоча станція',
     'Перевір комплектність обладнання та підключення живлення.\n\n'
     '1. Під’єднай монітор, клавіатуру й мишу.\n'
     '2. Увімкни комп’ютер і перевір зображення та звук.\n'
     '3. Повідом відповідального, якщо якогось пристрою бракує.'),
    ('Перевірка доступу до спільної папки', 'Мережі', 'спільна папка, файловий ресурс, доступ',
     'Підключись до дозволеної навчальної мережі та відкрий адресу папки, надану адміністратором.\n\n'
     'Якщо Windows повідомляє про відмову в доступі, надішли в підтримку назву ресурсу й опис роботи, для якої потрібен доступ.'),
    ('Оновлення робочої програми', 'Програми', 'оновлення, версія, програма',
     'Збережи відкриті документи та перевір поточну версію програми в меню «Довідка».\n\n'
     'Використовуй погоджене джерело оновлень. Після завершення відкрий програму і перевір, чи збереглися робочі параметри.'),
)


@contextmanager
def connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600_000)


def verify_password(password, user):
    salt = user['salt'] if user else bytes(16)
    expected = user['password_hash'] if user else bytes(32)
    matches = hmac.compare_digest(hash_password(password, salt), expected)
    return user is not None and matches


def log_event(db, kind, user_id=None):
    db.execute('INSERT INTO audit_events (kind, user_id) VALUES (?, ?)', (kind, user_id))


def save_version(db, article_id, user_id):
    db.execute('''INSERT INTO versions (article_id, version, title, category, keywords, body, user_id, device, model, symptoms)
                  SELECT id, version, title, category, keywords, body, ?, device, model, symptoms FROM articles WHERE id = ?''',
               (user_id, article_id))


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript(SCHEMA)
        db.execute('BEGIN IMMEDIATE')
        for table in ('articles', 'versions'):
            columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
            for field in ('device', 'model', 'symptoms'):
                if field not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        if db.execute('SELECT id FROM users LIMIT 1').fetchone():
            return
        for role, name in zip(ROLES, ('Адміністратор', 'Редактор', 'Читач')):
            salt = secrets.token_bytes(16)
            db.execute('INSERT INTO users (email, name, role, salt, password_hash) VALUES (?, ?, ?, ?, ?)',
                       (f'{role}@demo.test', name, role, salt, hash_password(DEMO_PASSWORD, salt)))
        editor_id = db.execute("SELECT id FROM users WHERE role = 'editor'").fetchone()['id']
        for article in DEMO_ARTICLES:
            row = db.execute('''INSERT INTO articles (title, category, keywords, body, author_id)
                                VALUES (?, ?, ?, ?, ?)''', (*article, editor_id))
            save_version(db, row.lastrowid, editor_id)
