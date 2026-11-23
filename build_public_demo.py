"""Build a self-contained public demo using only the checked-in training records."""
import json
from pathlib import Path
from shutil import copy2

from database import CATEGORIES, DEVICES, DEMO_ARTICLES, ROLES
from diagnostics import DEVICE_TERMS, SYNONYMS, STOP_WORDS


def build(destination):
    root = Path(__file__).resolve().parent
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('app.js', 'style.css', 'brand.png', 'demo-runtime.js'):
        copy2(root / 'public' / name, destination / name)
    index = (root / 'public' / 'index.html').read_text(encoding='utf-8')
    index = index.replace('href="/', 'href="./').replace('src="/', 'src="./')
    index = index.replace('<script src="./app.js" defer></script>',
                          '<script src="./demo-data.js" defer></script>\n'
                          '  <script src="./demo-runtime.js" defer></script>\n'
                          '  <script src="./app.js" defer></script>')
    index = index.replace('</head>', '  <meta name="description" content="ТехноСервіс — публічна демонстрація корпоративної бази знань, підбору інструкцій і підготовки звернень.">\n</head>')
    (destination / 'index.html').write_text(index, encoding='utf-8')
    users = [dict(id=i, role=role, name=name, email=f'{role}@demo.test')
             for i, (role, name) in enumerate(zip(ROLES, ('Адміністратор', 'Редактор', 'Читач')), 1)]
    articles = []
    for number, (title, category, keywords, body) in enumerate(DEMO_ARTICLES, 1):
        articles.append(dict(id=number, title=title, category=category, keywords=keywords, body=body,
                             device='', model='', symptoms='', version=1, archived=0,
                             author='Редактор', updated_at='2026-11-24 09:00:00'))
    data = dict(schema=1, users=users, articles=articles, reports=[],
                versions={str(a['id']): [{**a, 'name': 'Редактор', 'created_at': a['updated_at']}] for a in articles})
    seed = dict(categories=CATEGORIES, devices=DEVICES, data=data, deviceTerms=DEVICE_TERMS,
                synonyms=SYNONYMS, stopWords=sorted(STOP_WORDS))
    (destination / 'demo-data.js').write_text('globalThis.TechnoDemoSeed = ' +
                                            json.dumps(seed, ensure_ascii=False) + ';\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'dist')
    print(build(parser.parse_args().output))
