import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function browser(storage = new Map()) {
  const session = new Map();
  const api = data => ({
    getItem:key => data.get(key) ?? null,
    setItem:(key,value) => data.set(key,String(value)),
    removeItem:key => data.delete(key),
  });
  const context = vm.createContext({localStorage:api(storage), sessionStorage:api(session), URL});
  vm.runInContext(readFileSync(new URL('./dist/demo-data.js', import.meta.url), 'utf8'), context);
  vm.runInContext(readFileSync(new URL('./public/demo-runtime.js', import.meta.url), 'utf8'), context);
  return context.TechnoDemo.request;
}
const login = (request, role) => request('/login','POST',{email:role+'@demo.test',password:'Demo2026!'});

test('Public demo applies roles and keeps each visitor’s changes in their own browser', async () => {
  const storage = new Map();
  const first = browser(storage), other = browser();
  await assert.rejects(()=>first('/session'),{status:401});
  await login(first,'reader');
  const input = {title:'Тестова інструкція',body:'Перевірка друку',category:'Обладнання',device:'printer'};
  await assert.rejects(()=>first('/articles','POST',input),{status:403});
  await login(first,'editor');
  const saved = await first('/articles','POST',input);
  const reopened = browser(storage);
  await login(reopened,'reader');
  assert.equal((await reopened('/articles/'+saved.id)).title,input.title);
  await login(other,'reader');
  await assert.rejects(()=>other('/articles/'+saved.id),{status:404});
});

test('Public model matching, version history and archive work together', async () => {
  const request = browser();
  await login(request,'editor');
  const issue = {device:'printer',model:'PR-80',symptom:'Принтер не друкує'};
  const saved = await request('/articles','POST',{title:'Друк PR-80',body:'Перевір папір і друк.',
    category:'Обладнання',device:'printer',model:'PR-80',symptoms:'не друкує'});
  assert.equal((await request('/diagnose','POST',issue)).matches[0].id,saved.id);
  assert.equal((await request('/diagnose','POST',{...issue,model:'PR-99'})).matches.some(a=>a.id===saved.id),false);
  const edited = await request('/articles/'+saved.id,'PATCH',{...saved,body:'Оновлений друк'});
  assert.equal(edited.version,2);
  await assert.rejects(()=>request('/articles/'+saved.id,'PATCH',saved),{status:409});
  assert.equal((await request('/articles/'+saved.id+'/versions'))[1].body,saved.body);
  await request('/articles/'+saved.id+'/archive','PATCH',{archived:true});
  assert.equal((await request('/diagnose','POST',issue)).matches.some(a=>a.id===saved.id),false);
  await login(request,'reader');
  await assert.rejects(()=>request('/articles/'+saved.id),{status:404});
});

test('Reader reports and admin role changes are local to the demo', async () => {
  const request = browser();
  await login(request,'reader');
  await request('/articles/1/reports','POST',{message:'Уточнити крок'});
  await assert.rejects(()=>request('/reports'),{status:403});
  await login(request,'editor');
  const reports = await request('/reports');
  assert.equal(reports[0].message,'Уточнити крок');
  await request('/reports/'+reports[0].id,'PATCH');
  assert.equal((await request('/reports'))[0].resolved,1);
  await login(request,'admin');
  const users = await request('/users');
  const editor = users.find(user=>user.email==='editor@demo.test');
  await request('/users/'+editor.id,'PATCH',{role:'reader'});
  await login(request,'editor');
  await assert.rejects(()=>request('/articles','POST',{}),{status:403});
});
