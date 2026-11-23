import re
import unicodedata

from database import DEVICES


DEVICE_TERMS = {
    'printer': ('принтер', 'друк', 'print'),
    'network': ('мереж', 'wi-fi', 'ethernet', 'інтернет', 'роутер'),
    'workstation': ('комп', 'монітор', 'перифер', 'клавіатур', 'миша'),
    'software': ('програм', 'застосунк', 'оновлен'),
}
SYNONYMS = (
    ('друк', 'друкує', 'друкувати', 'printing', 'print'),
    ('мережа', 'мережі', 'мережу', 'мережевий', 'network'),
    ('пароль', 'пароля', 'вхід', 'входу', 'login'),
    ('підключення', 'підключити', 'підключитись', 'підключись'),
    ('оновлення', 'оновити', 'оновлюється', 'update'),
    ('папка', 'папки', 'папку', 'folder'),
    ('інтернет', 'інтернету', 'internet'),
    ('доступ', 'доступу', 'доступі', 'access'),
)
STOP_WORDS = {'не', 'ні', 'на', 'до', 'та', 'або', 'для', 'при', 'після', 'працює', 'працювати',
              'працюють', 'потрібно', 'немає', 'перестав', 'перестала', 'можу', 'чому', 'помилка', 'проблема'}


def normalize(value):
    return unicodedata.normalize('NFKC', value).casefold().replace('’', "'").replace('ʼ', "'")


def recommend(articles, device, model, symptom):
    terms = list(dict.fromkeys(
        word for word in re.findall(r"[\w'-]+", normalize(symptom))
        if len(word) > 2 and word not in STOP_WORDS and word not in DEVICE_TERMS[device]
    ))
    matches = []
    for article in articles:
        label_text = normalize(article['title'] + ' ' + article['keywords'])
        assigned = article['device']
        inferred = {key for key, words in DEVICE_TERMS.items() if any(word in label_text for word in words)}
        if assigned and assigned != device:
            continue
        if not assigned and inferred and device not in inferred:
            continue
        expected_category = {'network': 'Мережі', 'software': 'Програми'}.get(device, 'Обладнання')
        if not assigned and not inferred and article['category'] != expected_category:
            continue
        models = {normalize(value.strip()) for value in article['model'].split(',') if value.strip()}
        if models and (not model or normalize(model) not in models):
            continue
        haystack = normalize(' '.join(article[key] for key in ('title', 'keywords', 'symptoms', 'body')))
        found = []
        for term in terms:
            alternatives = next((group for group in SYNONYMS if term in group), (term,))
            if any(word in haystack for word in alternatives):
                found.append(term)
        if not found:
            continue
        reasons = ['Тип обладнання — ' + DEVICES[device], 'Збіг за описом — ' + ', '.join(found)]
        reasons.append('Модель збігається — ' + model if models else 'Загальна інструкція — модель не обмежена автором')
        result = {**article, 'reasons': reasons, 'modelMatched': bool(models)}
        result['excerpt'] = ' '.join(result.pop('body').split())[:170]
        matches.append((len(found) * 10 + int(bool(models)) * 5, result))
    matches.sort(key=lambda item: (-item[0], -item[1]['id']))
    return [article for _, article in matches[:5]]
