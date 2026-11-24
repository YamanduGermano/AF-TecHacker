// Rendering smoke checks without a browser. Run with Node 18+ (optional).
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, {
    innerHTML: '', textContent: '', open: false,
    classList: {add(){}, remove(){}, toggle(){}},
    showModal(){this.open = true;}, close(){this.open = false;},
  });
  return nodes.get(selector);
};
const sandbox = {
  console, setTimeout: () => 0, clearTimeout(){}, setInterval(){},
  localStorage: {getItem(){return null;}, setItem(){}},
  document: {querySelector:s => s === '.maximized' ? null : node(s), querySelectorAll:() => [],
    getElementById:node, addEventListener(){}, body:node('body')},
  fetch:async () => ({ok:true, json:async () => ({token:'test', resources:{models:[],tools:[]}, sessions:[]})}),
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8'), sandbox);
setImmediate(() => {
  const evaluate = code => vm.runInContext(code, sandbox);
  assert(node('#main').innerHTML.includes('Sua próxima descoberta'));
  evaluate('settings()');
  assert(node('#dialog-content').innerHTML.includes('Ollama não conectado'));
  evaluate('newSession()');
  assert(node('#dialog-content').innerHTML.includes('Plano elaborado pelo grupo'));
  const unsafe = '<img src=x onerror=alert(1)>';
  sandbox.fixture = {
    id:'abc', title:unsafe, model:'local-model', target:'http://127.0.0.1:3000', status:'idle',
    actions:0, limits:{max_actions:30}, events:[], revisions:[], artifacts:[], restorations:[],
    report_notes:{comparison:'', limitations:''}, proposals:[],
    chat:[{role:'assistant', content:JSON.stringify({synthesis:unsafe}), investigation:0, at:new Date().toISOString()}],
    investigations:[0,1,2].map(i => ({title:`Investigação ${i+1}`, hypothesis:unsafe, strategy:'test', conclusion:'', evidence:'', syntheses:[{
      synthesis:unsafe, observations:[unsafe], limitations:['limitação'], next_question:unsafe, at:new Date().toISOString(),
    }]})),
    plan:{objective:unsafe, hypotheses:'test', strategy:'test', tools:'test', evidence:'test'},
    initial_plan:{objective:unsafe, hypotheses:'test', strategy:'test', tools:'test', evidence:'test'},
  };
  evaluate('state.session = fixture');
  for (const view of ['explore','chat','logs','report']) {
    evaluate(`state.view = '${view}'; render()`);
    assert(!node('#main').innerHTML.includes(unsafe), `${view}: unescaped content`);
  }
  evaluate('showPlan()');
  assert(!node('#dialog-content').innerHTML.includes(unsafe));
  assert(node('#dialog-content').innerHTML.includes('&lt;img'));
  evaluate('notes()');
  assert(!node('#dialog-content').innerHTML.includes(unsafe));
  console.log('UI smoke: estados inicial/preenchido, quatro abas, formulários e escape de conteúdo OK.');
});
