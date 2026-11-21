import argparse
import hashlib
import json
import re
import secrets
import sqlite3
import time
import webbrowser
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from database import CATEGORIES, ROLES, connect, initialize, log_event, save_version, verify_password


ROOT = Path(__file__).resolve().parent
SESSION_SECONDS = 8 * 3600
COOKIE = 'knowledge_session'
STATIC = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css'), '/brand.png': ('brand.png', 'image/png')}
ARTICLE_FIELDS = '''a.id, a.title, a.category, a.keywords, a.body, a.version, a.archived,
                    a.updated_at, u.name AS author FROM articles a JOIN users u ON u.id = a.author_id'''


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def required_text(data, key, label, limit, optional=False, trim=True):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ApiError(400, f'Поле «{label}» має містити текст.')
    if trim:
        value = value.strip()
    if not optional and not value:
        raise ApiError(400, f'Заповни поле «{label}».')
    if len(value) > limit:
        raise ApiError(400, f'Поле «{label}» має містити до {limit} символів.')
    return value


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session_cookie(token, max_age):
    return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}'


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, content_type='application/json', cookie=None):
        if content_type == 'application/json':
            payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if content_type.startswith('text/') or content_type == 'application/json':
            content_type += '; charset=utf-8'
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(payload)

    def session_token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return cookie[COOKIE].value if COOKIE in cookie else ''
        except CookieError:
            return ''

    def request_data(self):
        if self.headers.get_content_type() != 'application/json':
            raise ApiError(415, 'Запит має бути у форматі JSON.')
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 128_000:
                raise ApiError(400, 'Некоректний розмір запиту.')
            data = json.loads(self.rfile.read(size).decode('utf-8'))
            if isinstance(data, dict):
                return data
        except (UnicodeError, ValueError):
            pass
        raise ApiError(400, 'Некоректний формат запиту.')

    def handle_request(self):
        try:
            url = urlsplit(self.path)
            path = url.path
            host = self.headers.get('Host')
            if host not in self.server.allowed_hosts:
                raise ApiError(403, 'Ця адреса недоступна.')
            if self.command in ('POST', 'PATCH'):
                origin = self.headers.get('Origin')
                if origin and origin != f'http://{host}':
                    raise ApiError(403, 'Запит з іншого сайту відхилено.')
            if self.command == 'GET' and (path in STATIC or re.fullmatch(r'/instructions/\d+', path)):
                file, content_type = STATIC.get(path, STATIC['/'])
                self.respond(200, (ROOT / 'public' / file).read_bytes(), content_type)
                return
            if not path.startswith('/api/'):
                raise ApiError(404, 'Сторінку не знайдено.')
            data = self.request_data() if self.command in ('POST', 'PATCH') else {}
            with connect(self.server.database_path) as db:
                if self.command in ('POST', 'PATCH'):
                    db.execute('BEGIN IMMEDIATE')
                status, payload, cookie = self.dispatch(db, path, parse_qs(url.query), data)
            self.respond(status, payload, cookie=cookie)
        except ApiError as error:
            self.respond(error.status, {'error': error.message})
        except sqlite3.Error:
            self.log_error('Database operation failed')
            self.respond(503, {'error': 'База даних тимчасово недоступна. Спробуй ще раз.'})

    do_GET = handle_request
    do_POST = handle_request
    do_PATCH = handle_request

    def dispatch(self, db, path, query, data):
        method = self.command
        session = self.session_token()
        if path == '/api/login' and method == 'POST':
            return self.login(db, data, session)

        user = db.execute('''SELECT u.id, u.email, u.name, u.role FROM users u
                             JOIN sessions s ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ?''',
                          (token_hash(session), int(time.time()))).fetchone()
        if not user:
            raise ApiError(401, 'Увійди, щоб отримати доступ.')
        can_edit = user['role'] in ('admin', 'editor')

        if path == '/api/logout' and method == 'POST':
            db.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash(session),))
            return 200, {'ok': True}, session_cookie('', 0)
        if path == '/api/session' and method == 'GET':
            return 200, {'user': dict(user), 'categories': CATEGORIES}, None
        if path == '/api/articles':
            if method == 'GET':
                archived = query.get('archived', ['0'])[0] == '1'
                if archived and not can_edit:
                    raise ApiError(403, 'Архів доступний редактору й адміністратору.')
                return 200, self.list_articles(db, query, archived), None
            if method == 'POST':
                self.require_editor(can_edit)
                fields = self.article_fields(data)
                row = db.execute('''INSERT INTO articles (title, category, keywords, body, author_id)
                                    VALUES (?, ?, ?, ?, ?)''', (*fields, user['id']))
                save_version(db, row.lastrowid, user['id'])
                return 201, self.get_article(db, row.lastrowid, can_edit), None

        article_route = re.fullmatch(r'/api/articles/(\d{1,15})(?:/(versions|archive|reports))?', path)
        if article_route:
            article_id, action = article_route.groups()
            article_id = int(article_id)
            article = self.get_article(db, article_id, can_edit)
            result = self.article_action(db, article_id, action, article, user, can_edit, data)
            if result:
                return result

        if path == '/api/reports' and method == 'GET':
            self.require_editor(can_edit)
            rows = db.execute('''SELECT r.id, r.article_id, a.title, r.message, r.created_at, r.resolved,
                                 u.name FROM reports r JOIN articles a ON a.id = r.article_id
                                 JOIN users u ON u.id = r.user_id ORDER BY r.resolved, r.id DESC''')
            return 200, [dict(row) for row in rows], None
        report_route = re.fullmatch(r'/api/reports/(\d{1,15})', path)
        if report_route and method == 'PATCH':
            self.require_editor(can_edit)
            row = db.execute('UPDATE reports SET resolved = 1 WHERE id = ?', (int(report_route[1]),))
            if not row.rowcount:
                raise ApiError(404, 'Повідомлення не знайдено.')
            return 200, {'ok': True}, None

        user_route = re.fullmatch(r'/api/users/(\d{1,15})', path)
        if path == '/api/users' or user_route:
            if user['role'] != 'admin':
                raise ApiError(403, 'Ця дія доступна адміністратору.')
            if path == '/api/users' and method == 'GET':
                rows = db.execute('SELECT id, name, email, role FROM users ORDER BY id')
                return 200, [dict(row) for row in rows], None
            if user_route and method == 'PATCH':
                return self.change_role(db, int(user_route[1]), user, data)
        raise ApiError(404, 'Ресурс не знайдено.')

    @staticmethod
    def login(db, data, old_token):
        email = required_text(data, 'email', 'Електронна пошта', 254).lower()
        password = required_text(data, 'password', 'Пароль', 128, trim=False)
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if not verify_password(password, user):
            log_event(db, 'login_failed')
            return 401, {'error': 'Неправильна пошта або пароль'}, None
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires <= ? OR token_hash = ?', (now, token_hash(old_token)))
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (token_hash(token), user['id'], now + SESSION_SECONDS))
        log_event(db, 'login_ok', user['id'])
        public_user = {key: user[key] for key in ('id', 'email', 'name', 'role')}
        return 200, {'user': public_user, 'categories': CATEGORIES}, session_cookie(token, SESSION_SECONDS)

    @staticmethod
    def require_editor(can_edit):
        if not can_edit:
            raise ApiError(403, 'Ця дія доступна редактору й адміністратору.')

    @staticmethod
    def get_article(db, article_id, can_edit):
        row = db.execute(f'SELECT {ARTICLE_FIELDS} WHERE a.id = ?', (article_id,)).fetchone()
        if not row or (row['archived'] and not can_edit):
            raise ApiError(404, 'Інструкцію не знайдено.')
        return dict(row)

    @staticmethod
    def list_articles(db, query, archived):
        category = query.get('category', [''])[0]
        terms = query.get('q', [''])[0].casefold().split()
        rows = db.execute(f'''SELECT {ARTICLE_FIELDS} WHERE a.archived = ? AND (? = '' OR a.category = ?)
                              ORDER BY a.updated_at DESC, a.id DESC''', (int(archived), category, category))
        result = []
        for row in rows:
            haystack = ' '.join(row[key] for key in ('title', 'keywords', 'body')).casefold()
            if all(term in haystack for term in terms):
                article = dict(row)
                article['excerpt'] = ' '.join(article.pop('body').split())[:170]
                result.append(article)
        return result

    @staticmethod
    def article_fields(data):
        title = required_text(data, 'title', 'Назва', 140)
        body = required_text(data, 'body', 'Текст інструкції', 15_000)
        category = data.get('category') or CATEGORIES[0]
        if category not in CATEGORIES:
            raise ApiError(400, 'Обери категорію зі списку.')
        keywords = required_text(data, 'keywords', 'Ключові слова', 240, optional=True)
        return title, category, keywords, body

    def article_action(self, db, article_id, action, article, user, can_edit, data):
        method = self.command
        if action is None and method == 'GET':
            return 200, article, None
        if action is None and method == 'PATCH':
            self.require_editor(can_edit)
            if article['archived']:
                raise ApiError(409, 'Спочатку поверни інструкцію з архіву.')
            if type(data.get('version')) is not int or data['version'] != article['version']:
                raise ApiError(409, 'Інструкцію вже оновлено. Відкрий її знову перед редагуванням.')
            fields = self.article_fields(data)
            db.execute('''UPDATE articles SET title = ?, category = ?, keywords = ?, body = ?,
                          version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
                       (*fields, article_id))
            save_version(db, article_id, user['id'])
            return 200, self.get_article(db, article_id, can_edit), None
        if action == 'versions' and method == 'GET':
            rows = db.execute('''SELECT v.version, v.title, v.category, v.keywords, v.body, v.created_at, u.name
                                 FROM versions v JOIN users u ON v.user_id = u.id
                                 WHERE v.article_id = ? ORDER BY v.version DESC''', (article_id,))
            return 200, [dict(row) for row in rows], None
        if action == 'archive' and method == 'PATCH':
            self.require_editor(can_edit)
            archived = data.get('archived')
            if type(archived) is not bool:
                raise ApiError(400, 'Вкажи стан архівування.')
            db.execute('UPDATE articles SET archived = ? WHERE id = ?', (int(archived), article_id))
            return 200, self.get_article(db, article_id, can_edit), None
        if action == 'reports' and method == 'POST':
            if article['archived']:
                raise ApiError(409, 'Інструкція перебуває в архіві.')
            message = required_text(data, 'message', 'Опис неточності', 2000)
            db.execute('INSERT INTO reports (article_id, user_id, message) VALUES (?, ?, ?)',
                       (article_id, user['id'], message))
            return 201, {'ok': True}, None
        return None

    @staticmethod
    def change_role(db, user_id, administrator, data):
        if administrator['id'] == user_id:
            raise ApiError(400, 'Змінити власну роль тут неможливо.')
        role = data.get('role')
        if role not in ROLES:
            raise ApiError(400, 'Обери доступну роль.')
        row = db.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        if not row.rowcount:
            raise ApiError(404, 'Обліковий запис не знайдено.')
        return 200, {'ok': True}, None


def create_server(port, database_path):
    initialize(database_path)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.database_path = database_path
    server.allowed_hosts = {f'{address}:{server.server_port}' for address in ('127.0.0.1', 'localhost')}
    return server


def main():
    parser = argparse.ArgumentParser(description='Локальна демоверсія бази знань')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'knowledge.sqlite3')
    parser.add_argument('--open', action='store_true', help='Відкрити демо у браузері')
    args = parser.parse_args()
    with create_server(args.port, args.db) as server:
        url = f'http://127.0.0.1:{server.server_port}'
        print(f'База знань працює: {url} (Ctrl+C — зупинити)', flush=True)
        if args.open:
            Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nСервер зупинено.')


if __name__ == '__main__':
    main()
