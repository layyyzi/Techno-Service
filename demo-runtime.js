(() => {
  'use strict';
  const seed = globalThis.TechnoDemoSeed;
  const dataKey = 'techno-service-public-demo-v1';
  const sessionKey = 'techno-service-demo-user';
  const clone = value => JSON.parse(JSON.stringify(value));
  const fold = value => value.normalize('NFKC').toLocaleLowerCase('uk').replace(/[’ʼ]/g, "'");
  const now = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
  function fail(status, message) {
    const error = new Error(message);
    error.status = status;
    throw error;
  }
  function text(data, key, limit, optional = false) {
    const value = data[key] ?? '';
    if (typeof value !== 'string' || value.trim().length > limit) fail(400, 'Перевір довжину й формат поля.');
    if (!optional && !value.trim()) fail(400, 'Заповни обов’язкові поля.');
    return value.trim();
  }
  function fields(data, previous = {}) {
    const merged = {...previous, ...data};
    const category = merged.category || seed.categories[0];
    const device = merged.device || '';
    if (!seed.categories.includes(category) || (device && !seed.devices[device])) fail(400, 'Обери значення зі списку.');
    return {
      title:text(merged, 'title', 140), category, keywords:text(merged, 'keywords', 240, true),
      body:text(merged, 'body', 15000), device, model:text(merged, 'model', 160, true),
      symptoms:text(merged, 'symptoms', 500, true),
    };
  }
  function load() {
    try {
      const saved = localStorage.getItem(dataKey);
      if (!saved) return clone(seed.data);
      const parsed = JSON.parse(saved);
      if (parsed.schema !== 1) fail(409, 'Версія даних у браузері не підтримується.');
      return parsed;
    } catch (error) {
      if (error.status) throw error;
      fail(503, 'Браузер не може прочитати збережені дані демо.');
    }
  }
  function save(state) {
    try { localStorage.setItem(dataKey, JSON.stringify(state)); }
    catch { fail(503, 'Браузер не може зберегти зміни. Перевір доступ до локального сховища.'); }
  }
  function requireEditor(user) {
    if (!['editor', 'admin'].includes(user.role)) fail(403, 'Ця дія доступна редактору й адміністратору.');
  }
  function articleById(state, id, user) {
    const article = state.articles.find(item => item.id === Number(id));
    if (!article || (article.archived && user.role === 'reader')) fail(404, 'Інструкцію не знайдено.');
    return article;
  }
  function version(state, article, user) {
    state.versions[article.id] ??= [];
    state.versions[article.id].unshift({...clone(article), name:user.name, created_at:now()});
  }
  function recommendations(state, data) {
    if (!seed.devices[data.device]) fail(400, 'Обери тип обладнання.');
    const model = text(data, 'model', 160, true);
    const symptom = text(data, 'symptom', 1000);
    const terms = [...new Set((fold(symptom).match(/[\p{L}\p{N}_'-]+/gu) || [])
      .filter(word => word.length > 2 && !seed.stopWords.includes(word) && !seed.deviceTerms[data.device].includes(word)))];
    const matches = [];
    for (const article of state.articles) {
      if (article.archived) continue;
      const label = fold(article.title + ' ' + article.keywords);
      const inferred = Object.entries(seed.deviceTerms).filter(([, words]) => words.some(word => label.includes(word))).map(([key]) => key);
      if (article.device && article.device !== data.device) continue;
      if (!article.device && inferred.length && !inferred.includes(data.device)) continue;
      const category = {network:'Мережі', software:'Програми'}[data.device] || 'Обладнання';
      if (!article.device && !inferred.length && article.category !== category) continue;
      const models = article.model.split(',').map(value => fold(value.trim())).filter(Boolean);
      if (models.length && (!model || !models.includes(fold(model)))) continue;
      const haystack = fold([article.title, article.keywords, article.symptoms, article.body].join(' '));
      const found = terms.filter(term => (seed.synonyms.find(group => group.includes(term)) || [term]).some(word => haystack.includes(word)));
      if (!found.length) continue;
      const reasons = [
        'Тип обладнання — ' + seed.devices[data.device],
        'Збіг за описом — ' + found.join(', '),
        models.length ? 'Модель збігається — ' + model : 'Загальна інструкція — модель не обмежена автором',
      ];
      const {body, ...visible} = article;
      matches.push({score:found.length * 10 + (models.length ? 5 : 0),
        article:{...visible, excerpt:body.replace(/\s+/g, ' ').slice(0, 170), reasons, modelMatched:Boolean(models.length)}});
    }
    return matches.sort((a, b) => b.score - a.score || b.article.id - a.article.id).slice(0, 5).map(item => item.article);
  }
  async function request(path, method = 'GET', data = {}) {
    const url = new URL(path, 'https://demo.invalid');
    const route = url.pathname;
    const state = load();
    if (route === '/login' && method === 'POST') {
      const user = state.users.find(item => item.email === String(data.email).trim().toLowerCase());
      if (!user || data.password !== 'Demo2026!') fail(401, 'Неправильна пошта або пароль');
      sessionStorage.setItem(sessionKey, String(user.id));
      return {user:clone(user), categories:seed.categories, devices:seed.devices};
    }
    const user = state.users.find(item => String(item.id) === sessionStorage.getItem(sessionKey));
    if (!user) fail(401, 'Увійди, щоб отримати доступ.');
    if (route === '/session' && method === 'GET') return {user:clone(user), categories:seed.categories, devices:seed.devices};
    if (route === '/logout' && method === 'POST') {sessionStorage.removeItem(sessionKey); return {ok:true};}
    if (route === '/diagnose' && method === 'POST') return {matches:recommendations(state, data)};
    if (route === '/articles' && method === 'GET') {
      const archived = url.searchParams.get('archived') === '1';
      if (archived) requireEditor(user);
      const category = url.searchParams.get('category') || '';
      const terms = fold(url.searchParams.get('q') || '').split(/\s+/).filter(Boolean);
      return state.articles.filter(article => Boolean(article.archived) === archived && (!category || article.category === category))
        .filter(article => terms.every(term => fold([article.title, article.keywords, article.body].join(' ')).includes(term)))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id - a.id)
        .map(({body, ...article}) => ({...article, excerpt:body.replace(/\s+/g, ' ').slice(0, 170)}));
    }
    let result;
    if (route === '/articles' && method === 'POST') {
      requireEditor(user);
      const id = Math.max(0, ...state.articles.map(article => article.id)) + 1;
      const article = {...fields(data), id, author:user.name, version:1, archived:0, updated_at:now()};
      state.articles.push(article);
      version(state, article, user);
      result = article;
    }
    const articleRoute = /^\/articles\/(\d+)(?:\/(versions|archive|reports))?$/.exec(route);
    if (articleRoute) {
      const article = articleById(state, articleRoute[1], user);
      const action = articleRoute[2];
      if (!action && method === 'GET') return clone(article);
      if (action === 'versions' && method === 'GET') return clone(state.versions[article.id] || []);
      if (!action && method === 'PATCH') {
        requireEditor(user);
        if (article.archived || article.version !== data.version) fail(409, 'Відкрий актуальну інструкцію перед редагуванням.');
        Object.assign(article, fields(data, article), {version:article.version + 1, updated_at:now()});
        version(state, article, user);
        result = article;
      }
      if (action === 'archive' && method === 'PATCH') {
        requireEditor(user);
        if (typeof data.archived !== 'boolean') fail(400, 'Вкажи стан архівування.');
        article.archived = Number(data.archived);
        result = article;
      }
      if (action === 'reports' && method === 'POST') {
        if (article.archived) fail(409, 'Інструкція перебуває в архіві.');
        const id = Math.max(0, ...state.reports.map(item => item.id)) + 1;
        state.reports.push({id, article_id:article.id, title:article.title,
          message:text(data, 'message', 2000), name:user.name, created_at:now(), resolved:0});
        result = {ok:true};
      }
    }
    if (route === '/reports' && method === 'GET') {
      requireEditor(user);
      return state.reports.map(report => ({...report,
        title:state.articles.find(article => article.id === report.article_id)?.title || report.title}))
        .sort((a, b) => a.resolved - b.resolved || b.id - a.id);
    }
    const reportRoute = /^\/reports\/(\d+)$/.exec(route);
    if (reportRoute && method === 'PATCH') {
      requireEditor(user);
      const report = state.reports.find(item => item.id === Number(reportRoute[1]));
      if (!report) fail(404, 'Повідомлення не знайдено.');
      report.resolved = 1; result = {ok:true};
    }
    if (route === '/users' && method === 'GET') {
      if (user.role !== 'admin') fail(403, 'Ця дія доступна адміністратору.');
      return clone(state.users);
    }
    const userRoute = /^\/users\/(\d+)$/.exec(route);
    if (userRoute && method === 'PATCH') {
      if (user.role !== 'admin') fail(403, 'Ця дія доступна адміністратору.');
      const target = state.users.find(item => item.id === Number(userRoute[1]));
      if (!target) fail(404, 'Обліковий запис не знайдено.');
      if (target.id === user.id || !['admin', 'editor', 'reader'].includes(data.role)) fail(400, 'Перевір вибрану роль.');
      target.role = data.role; result = {ok:true};
    }
    if (result === undefined) fail(404, 'Ресурс не знайдено.');
    save(state);
    return clone(result);
  }
  globalThis.TechnoDemo = {request};
})();
