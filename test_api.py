import json
import unittest
from http.client import HTTPResponse
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urlencode

from database import DEMO_PASSWORD, connect, initialize
from server import Handler


class MemorySocket:
    def __init__(self, incoming):
        self.incoming = incoming
        self.outgoing = bytearray()

    def makefile(self, mode, *args):
        return BytesIO(self.incoming)

    def sendall(self, data):
        self.outgoing.extend(data)


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class KnowledgeBaseApiTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'test.sqlite3'
        initialize(self.path)

    def http(self, method, path, body=None, cookie=None):
        with self.response(method, path, body, cookie) as response:
            raw = response.read()
            data = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw
            return response.status, data, response.getheader('Set-Cookie', '')

    def response(self, method, path, body=None, cookie=None):
        payload = json.dumps(body).encode() if body is not None else b''
        host = '127.0.0.1:8000'
        headers = {'Host': host, 'Content-Type': 'application/json', 'Content-Length': len(payload)}
        if cookie:
            headers['Cookie'] = cookie
        request = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{key}: {value}\r\n' for key, value in headers.items())
        stream = MemorySocket((request + '\r\n').encode() + payload)
        settings = SimpleNamespace(database_path=self.path, allowed_hosts={host})
        QuietHandler(stream, ('127.0.0.1', 1025), settings)
        response = HTTPResponse(MemorySocket(stream.outgoing))
        response.begin()
        return response

    def login(self, role):
        status, data, cookie = self.http('POST', '/api/login', {'email': f'{role}@demo.test', 'password': DEMO_PASSWORD})
        self.assertEqual((status, data['user']['role']), (200, role))
        self.assertIn('HttpOnly', cookie)
        return cookie.split(';', 1)[0]

    def test_login_logout_and_direct_document(self):
        status, page, _ = self.http('GET', '/instructions/1')
        self.assertEqual(status, 200)
        self.assertNotIn('Налаштування принтера'.encode(), page)
        self.assertEqual(self.http('GET', '/api/articles/1')[0], 401)
        status, error, cookie = self.http('POST', '/api/login', {'email': 'reader@demo.test', 'password': 'wrong'})
        self.assertEqual((status, error['error'], cookie), (401, 'Неправильна пошта або пароль', ''))
        with connect(self.path) as db:
            event = db.execute('SELECT kind, user_id FROM audit_events').fetchone()
            self.assertEqual(tuple(event), ('login_failed', None))
        reader = self.login('reader')
        self.assertEqual(self.http('GET', '/api/articles/1', cookie=reader)[0], 200)
        self.assertEqual(self.http('POST', '/api/logout', {}, reader)[0], 200)
        self.assertEqual(self.http('GET', '/api/articles/1', cookie=reader)[0], 401)

    def test_brand_asset_is_available_before_login(self):
        with self.response('GET', '/brand.png') as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'image/png')
            self.assertEqual(response.read(8), b'\x89PNG\r\n\x1a\n')

    def test_create_persists_and_reader_cannot_write(self):
        editor = self.login('editor')
        reader = self.login('reader')
        content = {'title': 'Пробний друк', 'body': 'Перевірити пробну сторінку', 'category': 'Обладнання'}
        self.assertEqual(self.http('POST', '/api/articles', content)[0], 401)
        self.assertEqual(self.http('POST', '/api/articles', content, reader)[0], 403)
        self.assertEqual(self.http('POST', '/api/articles', {**content, 'title': ' '}, editor)[0], 400)
        status, article, _ = self.http('POST', '/api/articles', content, editor)
        self.assertEqual(status, 201)
        initialize(self.path)
        self.assertEqual(self.http('GET', f"/api/articles/{article['id']}", cookie=reader)[1]['title'], 'Пробний друк')

    def test_search_case_category_and_no_matches(self):
        reader = self.login('reader')
        for query in ('принтер', 'ПРИНТЕР', 'драйвер'):
            status, articles, _ = self.http('GET', '/api/articles?' + urlencode({'q': query}), cookie=reader)
            self.assertEqual(status, 200)
            self.assertEqual([item['title'] for item in articles], ['Налаштування принтера'])
        for query in ({'q': 'документ-якого-немає'}, {'q': 'ПРИНТЕР', 'category': 'Мережі'}):
            self.assertEqual(self.http('GET', '/api/articles?' + urlencode(query), cookie=reader)[1], [])

    def test_diagnostics_model_matching_and_server_permissions(self):
        reader = self.login('reader')
        editor = self.login('editor')
        issue = {'device': 'printer', 'model': 'PR-80', 'symptom': 'Принтер не друкує'}
        self.assertEqual(self.http('POST', '/api/diagnose', issue)[0], 401)
        self.assertEqual(self.http('POST', '/api/diagnose', {**issue, 'device': []}, reader)[0], 400)
        self.assertEqual(self.http('POST', '/api/diagnose', {**issue, 'symptom': ' '}, reader)[0], 400)
        article = {'title': 'Перевірка PR-80', 'body': 'Перевір папір. Виконай пробний друк.',
                   'category': 'Обладнання', 'device': 'printer', 'model': 'PR-80, PR-81',
                   'symptoms': 'не друкує, немає паперу'}
        self.assertEqual(self.http('POST', '/api/articles', article, reader)[0], 403)
        status, saved, _ = self.http('POST', '/api/articles', article, editor)
        self.assertEqual(status, 201)
        diagnose = lambda data: self.http('POST', '/api/diagnose', data, reader)[1]['matches']
        matches = diagnose(issue)
        self.assertEqual(matches[0]['id'], saved['id'])
        self.assertTrue(matches[0]['modelMatched'])
        self.assertTrue(any('Модель збігається' in reason for reason in matches[0]['reasons']))
        for model in ('', 'PR-99'):
            self.assertNotIn(saved['id'], [row['id'] for row in diagnose({**issue, 'model': model})])
        self.assertEqual(diagnose({**issue, 'symptom': 'зебра-невідома-помилка'}), [])
        self.assertNotIn(saved['id'], [row['id'] for row in diagnose({**issue, 'device': 'network'})])
        path = f"/api/articles/{saved['id']}"
        # Earlier clients can edit the text without sending the new applicability fields.
        change = {key: saved[key] for key in ('title', 'category', 'keywords', 'body', 'version')}
        revised = self.http('PATCH', path, change, editor)[1]
        self.assertEqual(revised['model'], 'PR-80, PR-81')
        revised['model'] = 'PR-90'
        self.assertEqual(self.http('PATCH', path, revised, editor)[0], 200)
        versions = self.http('GET', path + '/versions', cookie=reader)[1]
        self.assertEqual([row['model'] for row in versions], ['PR-90', 'PR-80, PR-81', 'PR-80, PR-81'])
        self.http('PATCH', path + '/archive', {'archived': True}, editor)
        archived_matches = self.http('POST', '/api/diagnose', {**issue, 'model': 'PR-90'}, editor)[1]['matches']
        self.assertNotIn(saved['id'], [row['id'] for row in archived_matches])

    def test_diagnostics_migration_keeps_existing_content_and_versions(self):
        with connect(self.path) as db:
            initial = [tuple(row) for row in db.execute('SELECT id, title, body FROM articles')]
            for table in ('articles', 'versions'):
                for column in ('device', 'model', 'symptoms'):
                    db.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
        initialize(self.path)
        initialize(self.path)
        with connect(self.path) as db:
            self.assertEqual(initial, [tuple(row) for row in db.execute('SELECT id, title, body FROM articles')])
            self.assertTrue(all(row['model'] == '' for row in db.execute('SELECT model FROM versions')))
        reader = self.login('reader')
        issue = {'device': 'printer', 'model': '', 'symptom': 'не друкує'}
        matches = self.http('POST', '/api/diagnose', issue, reader)[1]['matches']
        self.assertIn('Налаштування принтера', [row['title'] for row in matches])

    def test_versions_reports_archive_and_role_revocation(self):
        editor = self.login('editor')
        reader = self.login('reader')
        administrator = self.login('admin')
        path = '/api/articles/1'
        initial = self.http('GET', path, cookie=editor)[1]
        change = {**initial, 'body': 'Оновлений текст'}
        self.assertEqual(self.http('PATCH', path, change, reader)[0], 403)
        self.assertEqual(self.http('PATCH', path, change, editor)[1]['version'], 2)
        self.assertEqual(self.http('PATCH', path, change, editor)[0], 409)
        versions = self.http('GET', path + '/versions', cookie=reader)[1]
        self.assertEqual([version['body'] for version in versions], ['Оновлений текст', initial['body']])
        self.assertEqual(self.http('POST', path + '/reports', {'message': 'Уточнити другий крок'}, reader)[0], 201)
        self.assertEqual(self.http('GET', '/api/reports', cookie=reader)[0], 403)
        report = self.http('GET', '/api/reports', cookie=editor)[1][0]
        self.assertEqual(report['message'], 'Уточнити другий крок')
        self.assertEqual(self.http('PATCH', f"/api/reports/{report['id']}", {}, editor)[0], 200)
        self.assertEqual(self.http('PATCH', path + '/archive', {'archived': True}, editor)[0], 200)
        self.assertEqual(self.http('GET', path, cookie=reader)[0], 404)
        self.assertEqual(self.http('GET', '/api/articles?archived=1', cookie=reader)[0], 403)
        self.assertEqual(self.http('PATCH', path + '/archive', {'archived': False}, editor)[0], 200)
        users = self.http('GET', '/api/users', cookie=administrator)[1]
        editor_id = next(user['id'] for user in users if user['role'] == 'editor')
        self.assertEqual(self.http('PATCH', f'/api/users/{editor_id}', {'role': 'reader'}, administrator)[0], 200)
        self.assertEqual(self.http('PATCH', path, {**change, 'version': 2}, editor)[0], 403)
