const icons = {
  book: '<path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1zM12 6v14"/>',
  file: '<path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6"/>',
  search: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  network: '<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M6 16v-4h12v4"/>',
  hardware: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4m-4 0h8"/>',
  program: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18m-13 5 2 2 4-4"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9m-9 4h4"/>',
  flag: '<path d="M5 21V4m0 1c5-4 9 4 15 0v10c-6 4-10-4-15 0"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2m1-15a3 3 0 0 1 0 6m2 3c2 .6 3 2 3 4v2"/>',
  logout: '<path d="M11 4H5v16h6m4-12 4 4-4 4m-6-4h10"/>',
  edit: '<path d="m4 20 4-1 12-12-3-3L5 16zm10-13 3 3"/>',
  history: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
};
const roles = { admin: 'Адміністратор', editor: 'Редактор', reader: 'Читач' };
const categoryStyles = {
  'Обладнання': ['hardware', ''],
  'Мережі': ['network', 'network'],
  'Програми': ['program', 'program'],
};
const app = document.querySelector('#app');
const dialog = document.querySelector('#dialog');
const notice = document.querySelector('#notice');
let currentUser = null;
let categories = [];
let page = 'articles';
let search = '';
let category = '';
let renderId = 0;
let listId = 0;
let searchTimer;
let noticeTimer;

function escapeText(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function icon(name) {
  return '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + icons[name] + '</svg>';
}

const brand = '<div class="brand"><img class="brand-mark" src="/brand.png" width="44" height="44" alt="">' +
  '<div class="brand-text"><span class="brand-name">ТехноСервіс</span><span class="brand-product">База знань</span></div></div>';
const canEdit = () => ['admin', 'editor'].includes(currentUser?.role);

function formatDate(value) {
  return new Intl.DateTimeFormat('uk-UA', { dateStyle: 'medium' })
    .format(new Date(value.replace(' ', 'T') + 'Z'));
}

async function request(path, method = 'GET', data = {}) {
  const options = method === 'GET' ? {} : {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  };
  let response;
  try {
    response = await fetch('/api' + path, options);
  } catch {
    throw new Error('Не вдалося зв’язатися із сервером. Перевір, чи його запущено.');
  }
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error);
    error.status = response.status;
    if (response.status === 401 && path !== '/login' && currentUser) {
      currentUser = null;
      closeDialog();
      renderLogin();
      notify('Увійди знову, щоб продовжити.');
    }
    throw error;
  }
  return payload;
}

function notify(message) {
  clearTimeout(noticeTimer);
  notice.textContent = message;
  noticeTimer = setTimeout(() => { notice.textContent = ''; }, 4500);
}

function errorBox(element, error) {
  element.textContent = error.message;
  element.hidden = false;
}

function renderLogin() {
  renderId++;
  app.innerHTML =
    '<main class="login"><section class="login-side">' + brand +
    '<div><h1>Корпоративна база знань</h1><p>Технічні інструкції для щоденної роботи з обладнанням, мережею та програмами.</p></div>' +
    '<small>Локальна демонстрація кваліфікаційної роботи</small></section>' +
    '<section class="login-main"><div class="login-card"><h2>Вхід до бази знань</h2>' +
    '<p class="muted">Увійди під обліковим записом працівника.</p>' +
    '<form class="fields" id="login-form"><label class="field">Електронна пошта<input name="email" type="email" autocomplete="username" placeholder="editor@demo.test" maxlength="254" required></label>' +
    '<label class="field">Пароль<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>' +
    '<p class="error" role="alert" hidden></p><button class="button primary" type="submit">Увійти</button></form>' +
    '<div class="login-demo"><p>Заповнити форму демонстраційними даними</p><div class="row">' +
    Object.entries(roles).map(([role, name]) => '<button class="button" data-demo="' + role + '">' + name + '</button>').join('') +
    '</div></div></div></section></main>';
  const form = app.querySelector('form');
  app.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => {
    form.elements.email.value = button.dataset.demo + '@demo.test';
    form.elements.password.value = 'Demo2026!';
    form.querySelector('[type=submit]').focus();
  }));
  bindForm(form, async data => {
    const session = await request('/login', 'POST', data);
    setSession(session);
    search = '';
    category = '';
    await renderLocation();
  });
}

function setSession(session) {
  currentUser = session.user;
  categories = session.categories;
}

function bindForm(form, onSubmit) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    const error = form.querySelector('.error');
    button.disabled = true;
    error.hidden = true;
    try {
      await onSubmit(Object.fromEntries(new FormData(form)));
    } catch (failure) {
      errorBox(error, failure);
    } finally {
      button.disabled = false;
    }
  });
}

function navButton(target, label, symbol) {
  const active = page === target || (target === 'articles' && page === 'detail');
  return '<button class="nav-button" data-page="' + target + '"' + (active ? ' aria-current="page"' : '') + '>' + icon(symbol) + label + '</button>';
}

function renderShell(label, contents, options = {}) {
  app.innerHTML = '<div class="shell"><aside class="sidebar">' + brand +
    '<nav aria-label="Розділи бази знань">' + navButton('articles', 'Інструкції', 'book') +
    (canEdit() ? navButton('archive', 'Архів', 'archive') + navButton('reports', 'Неточності', 'flag') : '') +
    (currentUser.role === 'admin' ? navButton('users', 'Користувачі', 'users') : '') +
    '</nav><div class="sidebar-account"><span class="avatar" aria-hidden="true">' + escapeText(currentUser.name[0]) + '</span>' +
    '<span class="account-text"><strong>' + escapeText(currentUser.name) + '</strong><small>' + roles[currentUser.role] + '</small></span>' +
    '<button class="button subtle icon-button" id="logout" type="button" aria-label="Вийти" title="Вийти">' + icon('logout') + '</button></div></aside>' +
    '<div class="workspace"><header class="topbar"><div class="breadcrumbs"><span>База знань</span><span aria-hidden="true">/</span><span>' + label + '</span></div>' +
    (options.create ? '<button class="button primary" id="create" type="button">' + icon('plus') + 'Створити інструкцію</button>' : '') +
    '</header><main class="content" id="content">' + contents + '</main></div></div>';
  app.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
    if (location.pathname !== '/' || page !== button.dataset.page) openPage(button.dataset.page);
  }));
  app.querySelector('#logout').addEventListener('click', async () => {
    try {
      await request('/logout', 'POST');
      currentUser = null;
      history.replaceState({}, '', '/');
      renderLogin();
    } catch (error) {
      notify(error.message);
    }
  });
  app.querySelector('#create')?.addEventListener('click', () => articleForm());
}

function go(path, state = {}) {
  if (location.pathname !== path || history.state?.section !== state.section) {
    history.pushState(state, '', path);
  }
  renderLocation();
}

function openPage(target, preserveFilters = false) {
  if (!preserveFilters) {
    search = '';
    category = '';
  }
  go('/', { section: target });
}

async function renderLocation() {
  const id = ++renderId;
  clearTimeout(searchTimer);
  if (!currentUser) return;
  const match = /^\/instructions\/(\d+)$/.exec(location.pathname);
  if (match) {
    await renderDetail(match[1], id);
    return;
  }
  const target = history.state?.section;
  if (target === 'reports' && canEdit()) await renderReports(id);
  else if (target === 'users' && currentUser.role === 'admin') await renderUsers(id);
  else renderLibrary(target === 'archive' && canEdit());
}

function renderLibrary(archived) {
  page = archived ? 'archive' : 'articles';
  const label = archived ? 'Архів' : 'Інструкції';
  const intro = archived ? '<h1 class="section-title">Архів інструкцій</h1>' : '<h1>Корпоративна база знань</h1><p>Знайди потрібну технічну інструкцію або робочий порядок дій.</p>';
  const filters = ['', ...categories].map(value =>
    '<button type="button" class="filter" data-category="' + escapeText(value) + '" aria-pressed="' + (category === value) + '">' + escapeText(value || 'Усі категорії') + '</button>'
  ).join('');
  renderShell(label,
    '<section class="' + (archived ? 'section-head' : 'hero') + '">' + intro +
    (archived ? '' : '<div class="hero-art" aria-hidden="true"><span></span><span></span><span>' + icon('file') + '</span></div>') +
    '<label class="searchbox">' + icon('search') + '<span class="visually-hidden">Пошук інструкцій</span><input type="search" id="search" value="' + escapeText(search) + '" placeholder="Пошук за назвою або ключовими словами" maxlength="150"></label></section>' +
    '<div class="toolbar"><div><h2>' + (archived ? 'Архівовані матеріали' : 'Інструкції') + '</h2><p class="count" id="count" aria-live="polite"></p></div><div class="filter-row" aria-label="Категорії">' + filters + '</div></div>' +
    '<div id="results" aria-busy="true"><p class="empty">Завантаження інструкцій…</p></div>',
    { create: !archived && canEdit() });
  app.querySelector('#search').addEventListener('input', event => {
    search = event.target.value;
    listId++;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => updateList(archived), 150);
  });
  app.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    category = button.dataset.category;
    app.querySelectorAll('[data-category]').forEach(filter => filter.setAttribute('aria-pressed', String(filter === button)));
    clearTimeout(searchTimer);
    updateList(archived);
  }));
  updateList(archived);
}

async function updateList(archived) {
  const results = app.querySelector('#results');
  const count = app.querySelector('#count');
  const query = new URLSearchParams({ q: search, category, archived: archived ? '1' : '0' });
  const id = ++listId;
  results.setAttribute('aria-busy', 'true');
  try {
    const articles = await request('/articles?' + query);
    if (!results.isConnected || id !== listId) return;
    count.textContent = 'Знайдено: ' + articles.length;
    results.innerHTML = articles.length ? '<div class="cards">' + articles.map(renderCard).join('') + '</div>' :
      '<p class="empty">' + (search.trim() || category ? 'За вашим запитом нічого не знайдено' :
        archived ? 'В архіві поки немає інструкцій.' : 'Інструкцій поки немає.') + '</p>';
  } catch (error) {
    if (results.isConnected && id === listId) results.innerHTML = '<p class="error" role="alert">' + escapeText(error.message) + '</p>';
  } finally {
    if (results.isConnected && id === listId) results.setAttribute('aria-busy', 'false');
  }
}

function renderCard(article) {
  const [symbol, tone] = categoryStyles[article.category] || ['file', ''];
  return '<a class="article-card" data-article href="/instructions/' + article.id + '">' +
    '<div class="card-top"><span class="tile-icon ' + tone + '">' + icon(symbol) + '</span><span class="chip">' + escapeText(article.category) + '</span></div>' +
    '<h3>' + escapeText(article.title) + '</h3><p>' + escapeText(article.excerpt) + '</p>' +
    '<div class="card-bottom">Оновлено ' + formatDate(article.updated_at) + '</div></a>';
}

async function renderDetail(articleId, id) {
  page = 'detail';
  renderShell('Інструкція', '<p class="empty">Завантаження інструкції…</p>');
  try {
    const article = await request('/articles/' + articleId);
    if (id !== renderId) return;
    const content = app.querySelector('#content');
    content.innerHTML = '<article class="detail"><button id="back" type="button" class="button">До списку інструкцій</button><header class="section-head">' +
      '<div class="row"><span class="chip">' + escapeText(article.category) + '</span><span class="chip">Версія ' + article.version + '</span>' +
      (article.archived ? '<span class="chip">В архіві</span>' : '') + '</div><h1>' + escapeText(article.title) + '</h1>' +
      '<p class="muted">Оновлено ' + formatDate(article.updated_at) + ' · ' + escapeText(article.author) + '</p></header>' +
      '<div class="panel article-body">' + escapeText(article.body) + '</div><div class="row detail-actions">' +
      '<button class="button" data-action="history">' + icon('history') + 'Історія версій</button>' +
      (!article.archived ? '<button class="button" data-action="report">' + icon('flag') + 'Повідомити про неточність</button>' : '') +
      (canEdit() && !article.archived ? '<button class="button" data-action="edit">' + icon('edit') + 'Редагувати</button>' : '') +
      (canEdit() ? '<button class="button" data-action="archive">' + icon('archive') + (article.archived ? 'Повернути з архіву' : 'Архівувати') + '</button>' : '') +
      '</div></article>';
    content.querySelector('#back').addEventListener('click', () => openPage(article.archived ? 'archive' : 'articles', true));
    content.querySelector('[data-action=edit]')?.addEventListener('click', () => articleForm(article));
    content.querySelector('[data-action=report]')?.addEventListener('click', () => reportForm(article));
    content.querySelector('[data-action=history]').addEventListener('click', () => showVersions(article.id));
    content.querySelector('[data-action=archive]')?.addEventListener('click', () => archiveForm(article));
  } catch (error) {
    if (id !== renderId) return;
    app.querySelector('#content').innerHTML = '<p class="error" role="alert">' + escapeText(error.message) + '</p><button class="button" id="back">До списку інструкцій</button>';
    app.querySelector('#back').addEventListener('click', () => openPage('articles'));
  }
}

function openDialog(title, body) {
  dialog.innerHTML = '<header class="dialog-head"><h2 id="dialog-title">' + escapeText(title) + '</h2><button type="button" class="button subtle icon-button" aria-label="Закрити" data-close>' + icon('close') + '</button></header>' + body;
  dialog.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', closeDialog));
  if (!dialog.open) dialog.showModal();
}

function closeDialog() {
  if (dialog.open) dialog.close();
}

function modalForm(title, body, submit, handler) {
  openDialog(title, '<form><div class="fields">' + body + '</div><p class="error" role="alert" hidden></p>' +
    '<div class="row dialog-actions"><button type="button" class="button" data-close>Скасувати</button><button type="submit" class="button primary">' + submit + '</button></div></form>');
  bindForm(dialog.querySelector('form'), handler);
}

function articleForm(article = {}) {
  const updating = Boolean(article.id);
  modalForm(updating ? 'Редагувати інструкцію' : 'Створити інструкцію',
    '<label class="field">Назва<input name="title" value="' + escapeText(article.title) + '" required maxlength="140"></label>' +
    '<label class="field">Категорія<select name="category">' + categories.map(value =>
      '<option' + (article.category === value ? ' selected' : '') + '>' + escapeText(value) + '</option>').join('') + '</select></label>' +
    '<label class="field">Ключові слова<input name="keywords" value="' + escapeText(article.keywords) + '" placeholder="Через кому" maxlength="240"></label>' +
    '<label class="field">Текст інструкції<textarea name="body" rows="8" required maxlength="15000">' + escapeText(article.body) + '</textarea></label>',
    'Зберегти', async data => {
      if (updating) data.version = article.version;
      const saved = await request(updating ? '/articles/' + article.id : '/articles', updating ? 'PATCH' : 'POST', data);
      closeDialog();
      notify('Інструкцію збережено');
      if (updating) go('/instructions/' + saved.id);
      else {
        search = '';
        category = '';
        await renderLocation();
      }
    });
  dialog.querySelector('[name=title]').focus();
}

function reportForm(article) {
  modalForm('Повідомити про неточність',
    '<label class="field">Опис неточності<textarea name="message" required maxlength="2000" placeholder="Який крок або фрагмент тексту потрібно уточнити?"></textarea></label>',
    'Надіслати', async data => {
      await request('/articles/' + article.id + '/reports', 'POST', data);
      closeDialog();
      notify('Повідомлення надіслано');
    });
}

function archiveForm(article) {
  const restoring = Boolean(article.archived);
  modalForm(restoring ? 'Повернути з архіву' : 'Архівувати інструкцію',
    '<p>' + (restoring ? 'Інструкція знову з’явиться в загальному списку.' : 'Інструкція зникне із загального списку й залишиться в архіві.') + '</p>',
    restoring ? 'Повернути' : 'Архівувати', async () => {
      await request('/articles/' + article.id + '/archive', 'PATCH', { archived: !restoring });
      closeDialog();
      notify(restoring ? 'Інструкцію повернуто з архіву' : 'Інструкцію архівовано');
      openPage(restoring ? 'articles' : 'archive');
    });
}

async function showVersions(articleId) {
  openDialog('Історія версій', '<p class="muted" id="version-list">Завантаження…</p>');
  const loading = dialog.querySelector('#version-list');
  try {
    const versions = await request('/articles/' + articleId + '/versions');
    if (!loading.isConnected || !dialog.open) return;
    loading.outerHTML = '<div>' + versions.map(version => '<details class="version"><summary>Версія ' +
      version.version + ' · ' + formatDate(version.created_at) + ' · ' + escapeText(version.name) + '</summary>' +
      '<div class="article-body"><strong>' + escapeText(version.title) + '</strong><p>' + escapeText(version.body) + '</p></div></details>').join('') + '</div>';
  } catch (error) {
    if (loading.isConnected) errorBox(loading, error);
  }
}

async function renderReports(id) {
  page = 'reports';
  renderShell('Неточності', '<header class="section-head"><h1 class="section-title">Повідомлення про неточності</h1></header><div class="list" id="rows"></div>');
  const rows = app.querySelector('#rows');
  try {
    const items = await request('/reports');
    if (id !== renderId) return;
    rows.innerHTML = items.length ? items.map(item => '<section class="panel list-item"><div class="stack"><a data-article href="/instructions/' + item.article_id + '">' +
      escapeText(item.title) + '</a><p class="article-body">' + escapeText(item.message) + '</p><small>' + escapeText(item.name) + ' · ' + formatDate(item.created_at) +
      '</small></div>' + (item.resolved ? '<span class="chip">Опрацьовано</span>' :
        '<button class="button" data-resolve="' + item.id + '">Позначити опрацьованим</button>') + '</section>').join('') :
      '<p class="empty">Повідомлень поки немає.</p>';
    rows.querySelectorAll('[data-resolve]').forEach(button => button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await request('/reports/' + button.dataset.resolve, 'PATCH');
        if (id === renderId) renderLocation();
      } catch (error) {
        notify(error.message);
      } finally {
        button.disabled = false;
      }
    }));
  } catch (error) {
    if (id === renderId) errorBox(rows, error);
  }
}

async function renderUsers(id) {
  page = 'users';
  renderShell('Користувачі', '<header class="section-head"><h1 class="section-title">Права користувачів</h1><p class="muted">Ролі демонстраційних облікових записів</p></header><div class="list" id="rows"></div>');
  const rows = app.querySelector('#rows');
  try {
    const users = await request('/users');
    if (id !== renderId) return;
    rows.innerHTML = users.map(user => '<section class="panel list-item"><div class="stack"><strong>' +
      escapeText(user.email) + '</strong><small>' + roles[user.role] + '</small></div>' +
      (user.id === currentUser.id ? '<span class="chip">Твій обліковий запис</span>' :
        '<button class="button" data-user="' + user.id + '">Змінити роль</button>') + '</section>').join('');
    rows.querySelectorAll('[data-user]').forEach(button => button.addEventListener('click', () => {
      const user = users.find(record => record.id === Number(button.dataset.user));
      modalForm('Змінити роль',
        '<p>' + escapeText(user.email) + '</p><label class="field">Роль<select name="role">' +
        Object.entries(roles).map(([role, name]) => '<option value="' + role + '"' + (role === user.role ? ' selected' : '') + '>' + name + '</option>').join('') + '</select></label>',
        'Зберегти роль', async data => {
          await request('/users/' + user.id, 'PATCH', data);
          closeDialog();
          notify('Роль оновлено');
          await renderLocation();
        });
    }));
  } catch (error) {
    if (id === renderId) errorBox(rows, error);
  }
}

app.addEventListener('click', event => {
  const link = event.target.closest('a[data-article]');
  if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    go(link.pathname);
  }
});
window.addEventListener('popstate', () => {
  closeDialog();
  renderLocation();
});

async function start() {
  try {
    setSession(await request('/session'));
    await renderLocation();
  } catch (error) {
    renderLogin();
    if (error.status !== 401) notify(error.message);
  }
}

start();
