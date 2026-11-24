'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Ícones locais: nenhuma fonte ou recurso externo.
const paths = {
 explore:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 chat:'<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9H13a8.5 8.5 0 0 1 8 8v.5Z"/>',
 logs:'<path d="m4 6 4 4-4 4m8 3h8"/>', report:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
 settings:'<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="m9 3 .6-1h4.8l.6 3 2 1 2.6-1 2.4 4-2 2v2l2 2-2.4 4L17 18l-2 1-.6 3H9.6L9 19l-2-1-2.6 1L2 15l2-2v-2L2 9l2.4-4L7 6l2-1Z"/>',
 shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
 plus:'<path d="M12 5v14M5 12h14"/>', expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>', close:'<path d="m6 6 12 12M6 18 18 6"/>',
 spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4"/>',
 folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
 target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
 cpu:'<rect x="5" y="5" width="14" height="14" rx="3"/><path d="M9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
 check:'<path d="m5 12 4 4L19 6"/>', circle:'<circle cx="12" cy="12" r="8"/>', book:'<path d="M12 5C8 2 3 3 3 3v16s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2v16Z"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>', refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', pause:'<path d="M8 5v14M16 5v14"/>', edit:'<path d="m15 5 4 4M4 20l4-1L20 7a3 3 0 0 0-4-4L4 15v5Z"/>',
 flask:'<path d="M9 3h6m-5 0v6L4 19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2L14 9V3M7 15h10"/>', info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.5"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.circle}</svg>`;
const date = value => value ? new Date(value).toLocaleString('pt-BR', {dateStyle:'short',timeStyle:'short'}) : 'Ainda não verificado';
const labels = {idle:'Pronta',thinking:'Modelo analisando',running:'Executando comando',stopping:'Interrompendo',paused:'Pausada',pending:'Aguardando revisão',completed:'Concluída',failed:'Falhou',rejected:'Rejeitada',suspended:'Suspensa',interrupted:'Interrompida',accepted:'Aceita',modified:'Modificada'};
const fieldLabels = {objective:'Objetivo',hypotheses:'Hipóteses',strategy:'Estratégia',tools:'Ferramentas previstas',evidence:'Evidências necessárias'};
const state = {token:'', resources:{models:[],tools:[]}, sessions:[], session:null, view:'explore', investigation:0, focus:false, offline:false};

// Comunicação com o backend e estado de apresentação.
const api = async (path, data) => {
 const response = await fetch('/api' + path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':state.token},body:JSON.stringify(data)});
 let body; try {body = await response.json();} catch {throw new Error('Backend local indisponível. Inicie a aplicação com python3 -m app.');}
 if (!response.ok) throw new Error(body.error || 'Não foi possível completar a operação.');
 return body;
};
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('visible'),5500);}
function badge(status){return `<span class="badge ${['idle','completed','accepted'].includes(status)?'green':['pending','thinking','running'].includes(status)?'orange':['failed','rejected','suspended'].includes(status)?'red':''}">${esc(labels[status]||status)}</span>`;}
function button(action,label,type='',extra=''){return `<button class="${type}" data-action="${action}" ${extra}>${label}</button>`;}
function runningControl(){return ['thinking','running','stopping'].includes(state.session?.status)?button('stop',icon('pause')+' Interromper','small danger'):'';}
function panel(id,title,ic,body,footer='',classes=''){
 return `<section class="panel ${classes}" id="${id}"><div class="panel-header"><div class="panel-heading">${icon(ic)}<h2>${title}</h2></div><div class="actions">${['chat-panel','synthesis-panel','logs-panel'].includes(id)?`<span data-running-control>${runningControl()}</span>`:''}${button('maximize',icon('expand'),'icon-button',`data-panel="${id}" aria-label="Maximizar ${title}"`)}</div></div>${body}${footer?`<div class="panel-footer">${footer}</div>`:''}</section>`;
}
function inv(){return state.session?.investigations[state.investigation];}
function currentPending(){return state.session?.proposals.find(p=>p.status==='pending');}
function blank(title,description,action='new',label='Criar sessão'){return `<div class="blank-view">${icon('folder')}<h2>${title}</h2><p>${description}</p>${button(action,label,'primary')}</div>`;}

// Estrutura principal e navegação.
let lastRenderContext=null;
function render(){
 const maximizedId=document.querySelector('.maximized')?.id;
 const chatBox=$('.chat-messages');
 const chatPosition=chatBox?.scrollTop||0;
 const atBottom=!chatBox||chatBox.scrollHeight-chatPosition-chatBox.clientHeight<100;
 const context=state.session?.id+'/'+state.investigation;
 const formValues=lastRenderContext===context?[...document.querySelectorAll('#chat-form textarea, #report-form textarea')].map(e=>({form:e.form.id,name:e.name,value:e.value})):[];
 lastRenderContext=context;
 const s=state.session;
 $('#navigation').innerHTML=[['explore','Explorações','explore'],['chat','Chat','chat'],['logs','Atividade','logs'],['report','Relatório','report']].map(([key,label,ic])=>`<button data-action="view" data-view="${key}" class="${state.view===key?'active':''}" ${state.view===key?'aria-current="page"':''}>${icon(ic)}${label}${key==='explore'?'<span class="count">3</span>':''}</button>`).join('');
 $('#session-list').innerHTML=state.sessions.length?state.sessions.map(item=>`<button data-action="session" data-id="${item.id}" class="${s?.id===item.id?'selected':''}">${esc(item.title)}<small>${esc(item.target)}</small></button>`).join(''):'<p class="session-empty">Suas investigações ficam<br>salvas aqui.</p>';
 $('#session-title').textContent=s?.title||'Nova exploração';
 const titles={explore:['PAINEL DE INVESTIGAÇÃO','Explorações','Transforme hipóteses em evidências. Um passo de cada vez.'],chat:['CONVERSA COM O MODELO','Chat','Contexto e perguntas para orientar a próxima análise.'],logs:['TRILHA DA INVESTIGAÇÃO','Atividade','Cada proposta, decisão e resultado, na ordem em que aconteceu.'],report:['DO LABORATÓRIO AO RELATÓRIO','Relatório','Um rascunho construído com o que foi realmente registrado.']};
 const [eye,title,description]=titles[state.view];
 $('#main').innerHTML=`${state.offline?'<div class="offline-banner">Prévia da interface. Para conectar seu Ollama e executar ferramentas, inicie o projeto na sua máquina.</div>':''}<div class="page-head"><div><div class="eyebrow">${eye}</div><h1>${title}</h1><p class="page-description">${description}</p></div><div class="actions">${s?button('exports',icon('download')+' Exportar','subtle'):button('settings',icon('settings')+' Configurar recursos','subtle')}${button('new',icon('plus')+' Nova sessão','primary')}${button('focus',icon('expand'),'icon-button','aria-label="Maximizar aba atual"')}</div></div>${s?metaStrip():''}${state.view==='explore'?exploreView():state.view==='chat'?chatView():state.view==='logs'?logsView():reportView()}${state.focus?button('focus','Sair da tela ampliada','focus-exit'):''}`;
 document.body.classList.toggle('focus-mode',state.focus);
 if(maximizedId)document.getElementById(maximizedId)?.classList.add('maximized');
 document.querySelectorAll('[data-icon]').forEach(e=>e.innerHTML=icon(e.dataset.icon));
 for(const value of formValues){const input=$('#'+value.form+' [name="'+value.name+'"]');if(input)input.value=value.value;}
 const newChat=$('.chat-messages');if(newChat)newChat.scrollTop=atBottom?newChat.scrollHeight:chatPosition;
}
function metaStrip(){const s=state.session;return `<div class="meta-strip"><span>${icon('target')} Alvo <b>${esc(s.target)}</b></span><span>${icon('cpu')} ${esc(s.model)}</span><span>${icon('logs')} ${s.actions}/${s.limits.max_actions} ações</span><span class="status" data-session-status>${badge(s.status)}${['thinking','running','stopping'].includes(s.status)?button('stop',icon('pause')+' Interromper','small danger'):''}</span></div>`;}
function explorationTabs(){return `<div class="investigations" role="tablist" aria-label="Investigações">${[0,1,2].map(i=>{const v=state.session?.investigations[i];return `<button role="tab" aria-selected="${state.investigation===i}" class="investigation ${state.investigation===i?'active':''}" data-action="investigation" data-index="${i}"><div class="card-top"><span class="icon-tile">${icon(i===0?'target':i===1?'flask':'folder')}</span><span class="badge ${v?.syntheses.length?'green':''}">${v?.conclusion?'Registrada':v?.syntheses.length?'Em exploração':'Não iniciada'}</span></div><strong>${esc(v?.title||'Investigação '+(i+1))}</strong><small>${v?.syntheses.length?v.syntheses.length+' síntese(s) registrada(s)':'Defina uma hipótese para começar'}</small></button>`;}).join('')}</div>`;}

// Painel de explorações, sínteses e revisão de comandos.
function exploreView(){
 const s=state.session,v=inv(),latest=v?.syntheses.at(-1),pending=currentPending();
 const synthesis=latest?`<div class="panel-body"><div class="synthesis-intro"><span class="badge green">Síntese do modelo</span><small>${date(latest.at)}</small></div><p class="prose">${esc(latest.synthesis)}</p>${latest.observations.length?`<h3 class="synthesis-label">Observações registradas</h3><ul class="synthesis-list">${latest.observations.map(o=>'<li>'+esc(o)+'</li>').join('')}</ul>`:''}${latest.next_question?`<div class="question-box"><strong>Questão em aberto</strong><br>${esc(latest.next_question)}</div>`:''}${latest.limitations.length?`<details><summary>Limitações desta análise (${latest.limitations.length})</summary><ul class="synthesis-list">${latest.limitations.map(l=>'<li>'+esc(l)+'</li>').join('')}</ul></details>`:''}${v.syntheses.length>1?`<details><summary>Ver ${v.syntheses.length-1} síntese(s) anterior(es)</summary>${v.syntheses.slice(0,-1).reverse().map(x=>`<div class="text-row"><div><small class="muted">${date(x.at)}</small><p class="prose">${esc(x.synthesis)}</p></div></div>`).join('')}</details>`:''}</div>`:`<div class="empty-synthesis"><div class="empty-art">${icon('spark')}</div><h2>${s?'O próximo passo começa com uma boa hipótese.':'Sua próxima descoberta começa aqui.'}</h2><p>${s?'Registre a hipótese e a estratégia da investigação. O modelo organizará sua análise neste espaço.':'Reúna o plano do grupo, as sínteses da IA e as evidências em um único lugar. Você decide cada próximo passo.'}</p>${button(s?'notes':'new',icon(s?'edit':'plus')+(s?' Preparar investigação':'Criar primeira sessão'),'primary')}<div class="guide-line"><span>Planejar</span><i></i><span>Investigar</span><i></i><span>Sintetizar</span></div></div>`;
 const footer=`<span>${icon('spark')} ${latest?'Análise da IA · valide com as evidências':'As sínteses aparecerão aqui após a análise'}</span>${s?button('ask','Solicitar análise','link-button'):''}`;
 const side=pending?approvalPanel(pending):panel('next-panel','Próximo passo','target',`<div class="panel-body"><div class="side-intro"><div class="icon-tile">${icon('book')}</div><div><h3>${s?'Investigação supervisionada':'Prepare seu laboratório'}</h3><p>${s?'O plano é seu ponto de partida.':'Tudo pronto antes da primeira análise.'}</p></div></div><div class="checklist">${checkRow(state.resources.models.length,'Conectar um modelo','Escolha um modelo do Ollama')}${checkRow(state.resources.tools.filter(t=>t.resolved).length>=2,'Disponibilizar ferramentas','Cadastre pelo menos dois comandos')}${checkRow(!!s,'Definir alvo e plano','Registre a estratégia do grupo')}</div>${button(s?'plan':'settings',s?'Consultar plano humano':'Abrir recursos','full subtle')}</div>`);
 const revision=s?.revisions.filter(r=>r.status==='pending').map(r=>`<div class="quiet-card"><div>${icon('edit')}</div><div><h3>Revisão de plano sugerida</h3><p>${esc(fieldLabels[r.field])}: ${esc(r.value)}</p>${button('revision','Revisar sugestão','link-button',`data-id="${r.id}"`)}</div></div>`).join('')||'';
 const recentError=s?.events.filter(e=>e.kind==='error'||e.kind==='suspended').at(-1);
 return `${explorationTabs()}${recentError?`<div class="error-box">${esc(recentError.message)} ${button('view','Ver atividade','link-button','data-view="logs"')}</div>`:''}<div class="grid"><div class="stack">${panel('synthesis-panel','Síntese da exploração','spark',`<div data-live-progress>${liveProgress()}</div>`+synthesis,footer)}<div class="under-grid">${panel('notes-panel','Registros do grupo','book',v?.hypothesis?`<div class="panel-body"><h3 class="synthesis-label">Hipótese</h3><p class="prose body-small">${esc(v.hypothesis)}</p><details><summary>Estratégia, conclusão e evidências</summary><p class="prose">${esc(v.strategy)}\n\nConclusão: ${esc(v.conclusion||'Pendente')}\n\nEvidências: ${esc(v.evidence||'Pendentes')}</p></details></div>`:'<div class="mini-empty"><strong>Comece com uma pergunta.</strong>Suas hipóteses e conclusões ficam separadas das sugestões da IA.</div>',s?button('notes',icon('edit')+' Editar registros','link-button'):'<span>Plano humano primeiro</span>')}${panel('files-panel','Evidências e arquivos','folder',s?.artifacts.length?`<div class="panel-body">${s.artifacts.slice(-3).reverse().map(a=>`<div class="text-row"><div>${button('view-file',esc(a.name),'link-button file-name',`data-id="${a.id}"`)}<p>${esc(a.origin)}</p></div></div>`).join('')}<details><summary>Todos os arquivos e hashes (${s.artifacts.length})</summary>${s.artifacts.map(a=>`<div class="text-row"><div>${button('view-file',esc(a.name),'link-button file-name',`data-id="${a.id}"`)}<p>ID: ${a.id}</p><code>SHA-256 ${a.sha256}</code></div></div>`).join('')}</details></div>`:'<div class="mini-empty"><strong>Rastreável desde a origem.</strong>Saídas e arquivos serão registrados com identificador e hash.</div>',s?button('exports',icon('download')+' Baixar arquivos','link-button'):'<span>Nenhuma evidência registrada</span>')}</div></div><div class="stack">${side}${revision}<div class="quiet-card">${icon('shield')}<div><h3>Você está no controle</h3><p>O modelo sugere. Você revisa, edita ou rejeita. Cada comando precisa de uma nova autorização.</p></div></div>${s?panel('restoration-panel','Estado do laboratório','refresh',`<div class="panel-body"><p class="body-small muted">${s.restorations.length?`${s.restorations.length} restauração(ões) registrada(s).`:'Nenhuma restauração registrada.'}</p>${s.restorations.length?`<details><summary>Ver procedimentos e confirmações</summary>${s.restorations.map(r=>`<p class="prose">${date(r.at)} · Investigação ${r.investigation+1} · ${esc(r.mode)}\n${esc(r.procedure)}\n${esc(r.confirmation)}</p>`).join('')}</details>`:''}</div>`,button('restore','Registrar restauração','link-button')):''}</div></div>`;
}
function checkRow(done,title,desc){return `<div class="check-row ${done?'done':''}">${icon(done?'check':'circle')}<div><strong>${title}</strong><small>${desc}</small></div></div>`;}
// One draft per proposal: edits survive polling and switching between chat and panels.
const proposalDrafts = new Map();
function proposalDraft(p) {
 const key=state.session.id+'/'+p.id;
 let d=proposalDrafts.get(key);
 if(!d || d.revision!==p.revision){d={tool:p.tool,command:p.command,reason:'',preview:p,revision:p.revision,loading:false,busy:false,sequence:0,error:''};proposalDrafts.set(key,d);}
 return d;
}
function approvalFeedback(d) {
 if(d.loading)return '<p class="muted body-small">Atualizando prévia do comando…</p>';
 if(d.error)return `<div class="error-box">${esc(d.error)}</div>`;
 const p=d.preview;
 return `<label>Comando final que será executado</label><pre class="command">${esc(p.command)}</pre><p class="body-small muted">Destino aparente: ${esc(p.destinations.apparent.join(', ')||'Não identificado; confira os argumentos.')}</p>${p.destinations.warnings.map(w=>`<div class="warning">${esc(w)}</div>`).join('')}${d.command!==currentProposal(p.id)?.command?'<p class="edited-label">Edição humana: o modelo será informado do comando efetivo.</p>':''}`;
}
function currentProposal(id){return state.session?.proposals.find(p=>p.id===id);}
function approvalRequest(p) {
 if(p.status!=='pending')return `<div class="request-decided">${badge(p.status)}${p.human_edited?'<span class="badge">Editado pelo usuário</span>':''}<pre class="command">${esc(p.command)}</pre><p class="body-small">${esc(p.decision?.reason||'Decisão registrada.')}</p></div>`;
 const d=proposalDraft(p);
 const tools=state.resources.tools.some(t=>t.name===p.tool)?state.resources.tools:[{name:p.tool,resolved:p.resolved},...state.resources.tools];
 return `<div class="approval-request" data-proposal-id="${p.id}">
  <span class="badge orange">Investigação ${p.investigation+1} · Aprovação pendente</span>
  <p class="body-small request-rationale">${esc(p.rationale)}</p>
  <label>Ferramenta<select data-proposal-field="tool" aria-label="Ferramenta permitida">${tools.map(t=>`<option value="${esc(t.name)}" ${d.tool===t.name?'selected':''} ${!t.resolved?'disabled':''}>${esc(t.name)}</option>`).join('')}</select></label>
  <label>Comando editável<textarea class="command-editor" data-proposal-field="command" aria-label="Comando editável" spellcheck="false" maxlength="24000">${esc(d.command)}</textarea></label>
  <div class="proposal-feedback" aria-live="polite">${approvalFeedback(d)}</div>
  <p class="body-small"><strong>Efeitos informados pelo modelo:</strong> ${esc(p.effects)}</p>
  <details><summary>Referência e limites</summary><p class="prose">${esc(p.destinations.notice)}</p><p class="prose">Referência: ${esc(p.documentation?.source||'Sem documentação útil')}\n${esc(p.documentation?.content||'')}</p><code class="tool-path">${esc(d.preview.resolved.path)} · SHA-256 ${esc(d.preview.resolved.sha256)}</code></details>
  <label class="reason-field">Observação (opcional)<input data-proposal-field="reason" value="${esc(d.reason)}" placeholder="Motivo da edição ou da rejeição"></label>
  <div class="actions"><button type="button" data-action="approve-proposal" data-id="${p.id}" class="primary" ${d.loading||d.error||d.busy?'disabled':''}>Aprovar</button><button type="button" data-action="reject-proposal" data-id="${p.id}" class="danger" ${d.busy?'disabled':''}>Rejeitar</button></div>
  <p class="approval-caption">Aprovar autoriza somente o comando final exibido acima.</p>
 </div>`;
}
function approvalPanel(p){return panel('approval-panel','Revisão necessária','shield',`<div class="panel-body">${approvalRequest(p)}</div>`,'Cada decisão também aparece no chat.','approval');}
function liveProgress() {
 const s=state.session,p=s?.model_progress;
 if(!s)return '';
 const active=['thinking','running','stopping'].includes(s.status);
 if(!active&&!['interrupted','failed'].includes(p?.status))return '';
 const running=s.status==='running';
 const fields=running?{}:(p?.fields||{});
 const title=running?'Comando em execução':s.status==='stopping'?'Interrompendo atividade':active?'Análise em andamento':p?.status==='failed'?'Análise não concluída':'Análise interrompida';
 return `<div class="live-card"><div class="live-heading"><div>${icon(running?'logs':'spark')} <strong>${title}</strong>${p?`<small>Investigação ${p.investigation+1} · ${date(p.updated_at)}</small>`:''}</div>${active?button('stop',icon('pause')+' Interromper','small danger'):''}</div>
 ${Object.keys(fields).length?Object.entries({progress_summary:'Direção da análise',synthesis:'Síntese em construção',rationale:'Justificativa da ação',tool:'Ferramenta considerada',effects:'Efeitos previstos'}).filter(([k])=>fields[k]).map(([k,label])=>`<div class="live-field"><span>${label}</span><p class="prose">${esc(fields[k])}</p></div>`).join(''):`<p class="body-small muted">${running?'Acompanhe o resultado no fluxo de atividade.':'Aguardando uma atualização do modelo. Você já pode interromper.'}</p>`}
 <p class="live-caption">Resumos de supervisão em tempo real · conteúdo parcial, ainda não validado</p></div>`;
}
function chatEntry(m) {
 let content=m.content;
 try{const parsed=JSON.parse(content);content=parsed.synthesis||parsed.progress_summary||content;}catch{}
 return `<article class="chat-message ${m.role}"><small>${m.role==='user'?(m.origin==='execution'?'Resultado enviado ao modelo':m.origin==='command_edit'?'Intervenção humana':'Grupo'):'Modelo · '+esc(state.session.model)} · ${date(m.at)}${m.discarded?' · resposta interrompida/incompleta':''}</small><div class="prose">${esc(content)}</div>${m.role==='assistant'?`<details><summary>Resposta pública completa</summary><pre>${esc(m.content)}</pre></details>`:''}</article>`;
}
function eventEntry(e) {
 const s=state.session,p=currentProposal(e.proposal_id);
 const fileId=e.artifact_id||(e.kind==='execution'?p?.result?.artifacts?.[0]:null);
 return `<article class="chat-log"><small>${date(e.at)} · Atividade</small><p>${icon(e.kind==='approved'?'check':e.kind==='rejected'?'close':'logs')} ${esc(e.message)}</p>${e.before?`<details><summary>Alteração do comando</summary><pre>Antes: ${esc(e.before)}\nDepois: ${esc(e.after)}</pre></details>`:''}${fileId?button('view-file','Abrir log / saída','link-button',`data-id="${fileId}"`):''}</article>`;
}

function chatView() {
 const s=state.session;
 if(!s)return panel('chat-panel','Conversa','chat',blank('Uma conversa com contexto','Crie uma sessão para conversar com o modelo do seu Ollama.'));
 const items=s.chat.filter(m=>m.investigation===state.investigation).map(m=>({at:m.at,html:chatEntry(m)}));
 for(const p of s.proposals.filter(p=>p.investigation===state.investigation))items.push({at:p.at,html:`<article class="chat-proposal"><div class="chat-proposal-heading">${icon('shield')} Pedido de aprovação <small>${date(p.at)}</small></div>${approvalRequest(p)}</article>`});
 const kinds=['model','approved','rejected','edited','execution','error','stop','interrupted','suspended','export'];
 for(const e of s.events){const i=e.investigation??currentProposal(e.proposal_id)?.investigation;if(kinds.includes(e.kind)&&(i===undefined||i===state.investigation))items.push({at:e.at,html:eventEntry(e)});}
 items.sort((a,b)=>a.at.localeCompare(b.at));
 return `${explorationTabs()}${panel('chat-panel','Conversa e execuções','chat',`<div class="chat-messages">${items.map(x=>x.html).join('')||'<div class="blank-view"><h2>O plano é o início da conversa.</h2><p>Pergunte sobre a hipótese ou solicite a primeira análise.</p></div>'}<div data-live-progress>${liveProgress()}</div></div><form id="chat-form" class="chat-compose"><textarea name="message" placeholder="Oriente a próxima análise…" aria-label="Mensagem para o modelo" required maxlength="12000"></textarea><button class="primary" type="submit">Enviar</button></form>`)}`;
}

function logsView(){const s=state.session;if(!s)return panel('logs-panel','Histórico','logs',blank('Uma trilha completa de decisões','Crie uma sessão para acompanhar o histórico.'));return panel('logs-panel','Histórico da sessão','logs',s.events.length?s.events.slice().reverse().map(e=>{const p=s.proposals.find(p=>p.id===e.proposal_id);return `<article class="log-row"><time>${date(e.at)}</time><div><p>${esc(e.message)}</p>${p?`<details><summary>${esc(p.tool)} · ${esc(labels[p.status]||p.status)} · Ver comando e saída</summary><pre class="command">${esc(p.command)}</pre><p>Decisão: ${esc(p.decision?.reason||'Pendente')}</p>${p.result?`<pre>stdout:\n${esc(p.result.stdout)}\n\nstderr:\n${esc(p.result.stderr)}\n\nCódigo: ${p.result.exit_code} · ${esc(p.result.reason)} · ${p.result.duration} s</pre>`:''}<details><summary>Registro completo, referências e edições</summary><pre>${esc(JSON.stringify(p,null,2))}</pre></details></details>`:''}${e.artifact_id?button('view-file','Abrir arquivo','link-button',`data-id="${e.artifact_id}"`):''}${e.investigation!==undefined?`<span class="badge">Investigação ${e.investigation+1}</span>`:''}</div></article>`;}).join(''):'<div class="mini-empty">Nenhuma atividade registrada.</div>',button('preview-export','Abrir logs.json','link-button','data-kind="logs"')+button('exports',icon('download')+' Exportar histórico','link-button'));}
function reportView(){const s=state.session;if(!s)return panel('report-panel','Rascunho acadêmico','report',blank('O relatório acompanha a investigação','Sínteses, intervenções humanas e evidências serão reunidas sem inventar resultados.'));return `<div class="grid"><div>${panel('report-panel','Conclusões e análise crítica','report',`<form id="report-form" class="panel-body report-editor"><p class="dialog-description">As três investigações, o plano inicial, as decisões e as evidências serão incluídos automaticamente no rascunho em Markdown.</p><div class="field"><label for="comparison">Plano humano × contribuições da IA</label><textarea id="comparison" name="comparison" placeholder="O que foi mantido, alterado ou rejeitado?">${esc(s.report_notes.comparison)}</textarea></div><div class="field"><label for="limitations">Limitações concretas</label><textarea id="limitations" name="limitations" placeholder="Registre pelo menos uma limitação observada nos testes.">${esc(s.report_notes.limitations)}</textarea></div><button class="primary" type="submit">Salvar análise</button></form>`)}</div><div class="stack">${panel('report-status','Prontidão do rascunho','report',`<div class="panel-body"><div class="checklist">${s.investigations.map((v,i)=>checkRow(!!v.conclusion,esc(v.title),v.conclusion?'Conclusão registrada':'Conclusão pendente')).join('')}${checkRow(!!s.report_notes.comparison,'Comparação crítica',s.report_notes.comparison?'Registrada':'Pendente')}${checkRow(!!s.report_notes.limitations,'Limitação concreta',s.report_notes.limitations?'Registrada':'Pendente')}</div><a class="primary button-link" href="/api/sessions/${s.id}/export/report">${icon('download')} Baixar rascunho .md</a></div>`)}<div class="quiet-card">${icon('info')}<div><h3>Revisão do grupo</h3><p>O rascunho marca lacunas como pendentes. O relatório final de 4 a 6 páginas e o vídeo de até 10 minutos serão produzidos pelo grupo.</p></div></div></div></div>`;}

// Janelas sob demanda e formulários.
function openDialog(title,body,footer=''){$('#dialog').classList.remove('wide-dialog');$('#dialog-content').innerHTML=`<div class="dialog-head"><h2>${title}</h2>${button('close',icon('close'),'icon-button','aria-label="Fechar janela"')}</div><div class="dialog-errors" role="alert"></div><div class="dialog-body">${body}</div>${footer?`<div class="dialog-footer">${footer}</div>`:''}`;if(!$('#dialog').open)$('#dialog').showModal();}
function field(name,label,value='',type='text',placeholder='',required=false){return `<div class="field"><label for="f-${name}">${label}</label>${type==='textarea'?`<textarea id="f-${name}" name="${name}" placeholder="${esc(placeholder)}" ${required?'required':''} maxlength="12000">${esc(value)}</textarea>`:`<input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${required?'required':''}>`}</div>`;}
function formFooter(id,label){return button('close','Cancelar','subtle')+`<button type="submit" form="${id}" class="primary">${label}</button>`;}
function newSession(){const r=state.resources;openDialog('Nova sessão',`<p class="dialog-description">Defina o laboratório e registre o plano do grupo antes de consultar o modelo.</p>${!r.models.length?'<div class="warning">Nenhum modelo disponível. Inicie o Ollama e atualize os recursos antes de criar a sessão.</div>':''}<form id="new-form">${field('title','Nome da sessão','','text','Ex.: Análise da aplicação Juice Shop',true)}<div class="fields-two">${field('target','URL do Juice Shop','','url','http://192.168.1.50:3000/',true)}<div class="field"><label for="f-model">Modelo instalado</label><select name="model" id="f-model" required><option value="">Selecione um modelo</option>${r.models.map(m=>`<option value="${esc(m.name)}">${esc(m.name)}</option>`).join('')}</select></div></div><label class="checkbox"><input type="checkbox" name="authorized" required>Confirmo que esta instância do OWASP Juice Shop está autorizada para os testes.</label><h3 class="section-label">Plano elaborado pelo grupo</h3>${Object.entries(fieldLabels).map(([k,label])=>field(k,label,'','textarea',({objective:'O que o grupo pretende investigar?',hypotheses:'Quais hipóteses serão verificadas?',strategy:'Como o grupo pretende conduzir os testes?',tools:'Quais comandos serão utilizados e por quê?',evidence:'Que registros serão necessários para sustentar as conclusões?'})[k],true)).join('')}<details><summary>Ferramentas disponíveis e limites da sessão</summary><p class="dialog-description">${r.tools.map(t=>esc(t.name)+(t.resolved?' · disponível':' · indisponível')).join('<br>')||'Nenhum comando cadastrado. Abra Recursos e configurações.'}</p><div class="fields-two">${field('timeout','Tempo máximo por ação (s)',30,'number')}${field('max_actions','Máximo de ações',30,'number')}</div>${field('output_limit','Limite de saída (bytes)',131072,'number')}<p class="body-small muted">O modelo fica fixo nesta sessão. Para trocar, crie outra sessão.</p></details></form>`,formFooter('new-form','Criar sessão'));}
function settings(){const r=state.resources;openDialog('Recursos e configurações',`<div class="resource-health"><div><strong>${r.models.length?'Ollama conectado':'Ollama não conectado'}</strong><p>Verificado: ${date(r.checked_at)}</p></div>${button('refresh',icon('refresh')+' Atualizar','small')}</div>${r.error?`<div class="warning">${esc(r.error)}</div>`:''}<h3 class="section-label">Modelos instalados</h3>${r.models.length?r.models.map(m=>`<div class="text-row"><div><strong>${esc(m.name)}</strong><p>${esc(m.details?.parameter_size||'Modelo local')}${m.size?' · '+(m.size/1e9).toFixed(1)+' GB':''}</p></div><span class="badge green">Disponível</span></div>`).join(''):'<p class="body-small muted">Inicie o Ollama e instale o modelo por conta própria. A aplicação não baixa modelos.</p>'}<h3 class="section-label">Comandos permitidos</h3><p class="dialog-description">Cadastre os nomes dos comandos instalados no seu sistema. Disponibilize pelo menos dois, incluindo um que interaja diretamente com o Juice Shop.</p>${r.tools.map(t=>`<div class="tool-card"><div class="tool-card-head"><strong>${esc(t.name)}</strong><span class="badge ${t.resolved?'green':'red'}">${t.resolved?'Disponível':'Não encontrado'}</span></div><code class="tool-path">${esc(t.resolved?.path||'Não encontrado no PATH')}</code><p>${esc(t.description)}</p>${!t.documentation?'<div class="warning">Sem instruções úteis. Consulte o manual ou autorize --help antes de usar.</div>':`<details><summary>Documentação · ${esc(t.documentation.source)}</summary><pre>${esc(t.documentation.content)}</pre><code class="tool-path">SHA-256 ${esc(t.documentation.sha256)}</code></details>`}<div class="actions">${button('manual','Atualizar manual','small',`data-name="${esc(t.name)}"`)}${button('help','Consultar --help','small',`data-name="${esc(t.name)}"`)}${button('remove-tool','Remover','small danger',`data-name="${esc(t.name)}"`)}</div></div>`).join('')}<form id="tool-form"><h3 class="section-label">Adicionar comando</h3><div class="fields-two">${field('name','Nome do comando','','text','Ex.: curl',true)}${field('description','Descrição','','text','Como esta ferramenta ajuda?')}</div><button type="submit" class="primary">Adicionar e consultar manual</button></form><details><summary>Funcionamento e limites</summary><p class="prose">Somente os nomes cadastrados são consultados no PATH. A atualização de recursos não executa esses comandos. A consulta a man é automática; --help exige aprovação específica.\n\nNão há isolamento de rede ou do sistema de arquivos. Revise todos os argumentos antes de aprovar.\n\nOllama: ${esc(r.ollama_url||'http://127.0.0.1:11434')}\nA aplicação não instala modelos, ferramentas ou o Juice Shop.</p></details>`);}
function notes(){if(!state.session)return newSession();const v=inv();openDialog('Registros da investigação',`<form id="notes-form"><p class="dialog-description">Hipóteses e conclusões do grupo ficam separadas das sínteses produzidas pela IA.</p>${field('title','Título',v.title,'text','',true)}${field('hypothesis','Hipótese',v.hypothesis,'textarea','Qual pergunta será verificada?',true)}${field('strategy','Estratégia',v.strategy,'textarea','Como verificar a hipótese?',true)}${field('conclusion','Conclusão do grupo',v.conclusion,'textarea','Preencha depois de interpretar as evidências.')}${field('evidence','Evidências e referências',v.evidence,'textarea','Cite os IDs dos arquivos e descreva o que sustentam.')}</form>`,formFooter('notes-form','Salvar registros'));}
function showPlan(){const s=state.session;openDialog('Plano humano',`<p class="dialog-description">Registrado antes da primeira interação com o modelo. O plano inicial permanece preservado.</p>${Object.entries(fieldLabels).map(([k,l])=>`<h3 class="section-label">${l}</h3><p class="prose">${esc(s.plan[k])}</p>${s.initial_plan[k]!==s.plan[k]?`<details><summary>Versão inicial</summary><p class="prose">${esc(s.initial_plan[k])}</p></details>`:''}`).join('')}<details><summary>Histórico de revisões (${s.revisions.length})</summary>${s.revisions.map(r=>`<div class="text-row"><div><strong>${esc(fieldLabels[r.field])} · ${esc(labels[r.status])}</strong><p>${esc(r.value)}</p><p>Motivo da IA: ${esc(r.reason)}</p><p>Decisão humana: ${esc(r.decision||'Pendente')}</p></div></div>`).join('')}</details>`);}
function exportsDialog(){const s=state.session;openDialog('Exportar sessão',`<p class="dialog-description">Baixe apenas o que precisa. O pacote completo inclui um manifesto de hashes SHA-256.</p>${[['chat','Chat completo','Mensagens originais em JSON'],['logs','Logs e saídas','Decisões, propostas e resultados em JSON'],['files','Arquivos da sessão','Pacote ZIP com registros, contextos e evidências'],['report','Rascunho editável','Relatório em Markdown com pendências destacadas']].map(([kind,title,desc])=>`<div class="text-row"><div><strong>${title}</strong><p>${desc}</p>${kind!=='files'?button('preview-export','Visualizar na página','link-button',`data-kind="${kind}"`):''}</div><a href="/api/sessions/${s.id}/export/${kind}" aria-label="Baixar ${title}">${icon('download')}</a></div>`).join('')}`);}
async function loadSession(id){state.session=await api('/sessions/'+id);state.investigation=0;localStorage.setItem('lab-session',id);render();}
async function loadBootstrap(){const data=await api('/bootstrap');state.token=data.token;state.resources=data.resources;state.sessions=data.sessions;}
async function sessionPost(action,data){state.session=await api('/sessions/'+state.session.id+'/'+action,data);const i=state.sessions.findIndex(s=>s.id===state.session.id);if(i>=0)state.sessions[i]={...state.sessions[i],...state.session};render();}

// Inline approval previews are validated by the backend, without executing anything.
function paintProposal(id) {
 const p=currentProposal(id); if(!p)return;
 const d=proposalDraft(p);
 document.querySelectorAll(`.approval-request[data-proposal-id="${id}"]`).forEach(root=>{
  $('.proposal-feedback',root).innerHTML=approvalFeedback(d);
  $('[data-action="approve-proposal"]',root).disabled=d.loading||!!d.error||d.busy;
  $('[data-action="reject-proposal"]',root).disabled=d.busy;
 });
}
function quoteArgument(value){return /^[a-zA-Z0-9_@%+=:,./-]+$/.test(value)?value:"'"+value.replace(/'/g,"'\"'\"'")+"'";}
function updateDraft(event) {
 const input=event.target.closest('[data-proposal-field]');if(!input)return;
 const root=input.closest('[data-proposal-id]'),p=currentProposal(root.dataset.proposalId);
 if(!p||p.status!=='pending')return;
 const d=proposalDraft(p),field=input.dataset.proposalField;
 d[field]=input.value;
 if(field==='reason')return;
 if(field==='tool'){
  d.command=[d.tool,...(d.preview?.args||p.args).map(quoteArgument)].join(' ');
  $('[data-proposal-field="command"]',root).value=d.command;
 }
 d.sequence++;const sequence=d.sequence,sid=state.session.id;
 d.loading=true;d.error='';clearTimeout(d.timer);paintProposal(p.id);
 d.timer=setTimeout(async()=>{
  try{
   const preview=await api('/sessions/'+sid+'/proposals/'+p.id+'/preview',{revision:p.revision,tool:d.tool,command:d.command});
   if(d.sequence!==sequence||state.session?.id!==sid)return;
   d.preview=preview;
  }catch(error){if(d.sequence===sequence)d.error=error.message;}
  finally{if(d.sequence===sequence){d.loading=false;if(state.session?.id===sid)paintProposal(p.id);}}
 },300);
}
document.addEventListener('input',updateDraft);
document.addEventListener('change',event=>{if(event.target.matches('[data-proposal-field="tool"]'))updateDraft(event);});
async function decideProposal(id,approve) {
 const p=currentProposal(id);if(!p||p.status!=='pending')throw new Error('Este pedido já foi decidido.');
 const d=proposalDraft(p);if(d.busy)return;
 if(approve&&(d.loading||d.error))throw new Error('Aguarde a prévia válida do comando.');
 d.busy=true;paintProposal(id);
 const data={revision:p.revision,reason:d.reason};
 if(approve)Object.assign(data,{confirmed:true,tool:d.tool,command:d.command,expected_command:d.preview.command,expected_resolved:d.preview.resolved});
 try{
  await sessionPost('proposals/'+id+'/'+(approve?'approve':'reject'),data);
  toast(approve?'Comando aprovado. Acompanhe a execução no chat.':'Proposta rejeitada e registrada no chat.');
 }catch(error){d.error=error.message;throw error;}
 finally{d.busy=false;paintProposal(id);}
}
function fileViewer(data,download) {
 let content=data.content;
 if(!data.truncated&&data.name.endsWith('.json')){try{content=JSON.stringify(JSON.parse(content),null,2);}catch{}}
 openDialog(esc(data.name),`<p class="dialog-description">${esc(data.origin)} · ${Number(data.bytes).toLocaleString('pt-BR')} bytes</p>${data.sha256?`<code class="tool-path">ID: ${esc(data.id)}<br>SHA-256: ${esc(data.sha256)}</code>`:''}${data.truncated?'<div class="warning">Prévia limitada. Baixe o arquivo para consultar o conteúdo completo.</div>':''}<pre class="file-preview">${esc(content)}</pre>`,`<a class="button-link primary" href="${download}">${icon('download')} Baixar arquivo</a>`);
 $('#dialog').classList.add('wide-dialog');
}
async function viewFile(id) {
 const base='/sessions/'+state.session.id+'/artifacts/'+id;
 const data=await api(base+'/view');
 fileViewer(data,'/api'+base);
}
async function viewExport(kind) {
 const base='/sessions/'+state.session.id;
 const data=await api(base+'/preview/'+kind);
 fileViewer(data,'/api'+base+'/export/'+kind);
}

// Ações explícitas da interface.
async function handleAction(el){const action=el.dataset.action;
 if(action==='close')return $('#dialog').close();
 if(action==='view'){state.view=el.dataset.view;return render();}
 if(action==='new')return newSession();
 if(action==='settings')return settings();
 if(action==='focus'){state.focus=!state.focus;return render();}
 if(action==='maximize'){const p=document.getElementById(el.dataset.panel);p.classList.toggle('maximized');el.setAttribute('aria-label',p.classList.contains('maximized')?'Restaurar painel':'Maximizar painel');return;}
 if(action==='investigation'){state.investigation=Number(el.dataset.index);return render();}
 if(action==='session')return loadSession(el.dataset.id);
 if(action==='notes')return notes();
 if(action==='plan')return showPlan();
 if(action==='exports')return exportsDialog();
 if(action==='ask'){await sessionPost('ask',{investigation:state.investigation});return toast('Análise solicitada. A síntese aparecerá no painel.');}
 if(action==='stop'){await sessionPost('stop',{});return toast('Interrupção solicitada. Nenhum novo comando será executado.');}
 if(action==='approve-proposal'||action==='reject-proposal')return decideProposal(el.dataset.id,action==='approve-proposal');
 if(action==='view-file')return viewFile(el.dataset.id);
 if(action==='preview-export')return viewExport(el.dataset.kind);
 if(action==='refresh'){state.resources=await api('/resources/refresh',{});render();settings();return toast('Recursos verificados.');}
 if(action==='manual'){state.resources=await api('/tools/manual',{name:el.dataset.name});render();return settings();}
 if(action==='remove-tool'){state.resources=await api('/tools/remove',{name:el.dataset.name});render();return settings();}
 if(action==='help'){const h=await api('/help/prepare',{name:el.dataset.name});return openDialog('Autorizar consulta --help',`<form id="help-form" data-id="${h.id}"><p class="dialog-description">Nem todo executável trata --help sem efeitos. Revise antes de continuar. Tempo máximo: 5 segundos.</p><pre class="command">${esc(h.command)}</pre><code class="tool-path">SHA-256 ${esc(h.resolved.sha256)}</code><label class="checkbox"><input type="checkbox" name="confirmed" required>Autorizo esta execução específica de --help.</label></form>`,formFooter('help-form','Autorizar consulta'));}
 if(action==='restore')return openDialog('Registrar restauração',`<form id="restore-form"><p class="dialog-description">Registre a restauração que o grupo já realizou. Este formulário não executa comandos nem reinicia o Juice Shop.</p><div class="field"><label for="restore-mode">Ambiente</label><select name="mode" id="restore-mode"><option value="LAN">LAN</option><option value="local">Local</option></select></div>${field('procedure','Procedimento realizado','','textarea','Como o estado foi restaurado?',true)}${field('confirmation','Estado conhecido confirmado','','textarea','Como o grupo verificou a restauração?',true)}<label class="checkbox"><input type="checkbox" name="confirmed" required>Confirmo que a restauração foi realizada e conferida.</label></form>`,formFooter('restore-form','Registrar restauração'));
 if(action==='revision'){const r=state.session.revisions.find(r=>r.id===el.dataset.id);return openDialog('Revisar sugestão ao plano',`<form id="revision-form" data-id="${r.id}"><p class="dialog-description">Campo: ${esc(fieldLabels[r.field])}</p><p class="prose">${esc(r.value)}</p><div class="info-box">Motivo do modelo: ${esc(r.reason)}</div><div class="field"><label for="revision-status">Sua decisão</label><select id="revision-status" name="status"><option value="accepted">Aceitar sugestão</option><option value="modified">Modificar sugestão</option><option value="rejected">Rejeitar sugestão</option></select></div>${field('value','Texto final (usado ao modificar)',r.value,'textarea')}${field('reason','Justificativa da decisão','','textarea','',true)}</form>`,formFooter('revision-form','Registrar decisão'));}
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-action]');if(!el)return;el.disabled=true;try{await handleAction(el);}catch(error){const box=$('.dialog-errors');if($('#dialog').open&&box)box.textContent=error.message;else toast(error.message);}finally{el.disabled=false;}});

// Envio dos formulários; execução depende da aprovação específica.
document.addEventListener('submit',async event=>{
 event.preventDefault();const form=event.target;const data=Object.fromEntries(new FormData(form));const submit=document.querySelector(`[form="${form.id}"]`)||$('button[type="submit"]',form);if(submit)submit.disabled=true;const errors=$('.dialog-errors');if(errors)errors.textContent='';
 try{
  if(form.id==='new-form'){const plan=Object.fromEntries(Object.keys(fieldLabels).map(k=>[k,data[k]]));state.session=await api('/sessions',{title:data.title,target:data.target,model:data.model,authorized:data.authorized==='on',plan,limits:{timeout:Number(data.timeout),output_limit:Number(data.output_limit),max_actions:Number(data.max_actions)}});state.investigation=0;state.view='explore';await loadBootstrap();localStorage.setItem('lab-session',state.session.id);$('#dialog').close();render();toast('Sessão criada. Prepare a primeira investigação.');}
  if(form.id==='tool-form'){state.resources=await api('/tools/add',data);render();settings();toast('Comando cadastrado e manual consultado.');}
  if(form.id==='notes-form'){await sessionPost('update',{...data,investigation:state.investigation});$('#dialog').close();toast('Registros salvos.');}
  if(form.id==='chat-form'){await sessionPost('ask',{message:data.message,investigation:state.investigation});$('#chat-form textarea').value='';toast('Mensagem enviada ao modelo.');}
  if(form.id==='report-form'){await sessionPost('update',{report_notes:data});toast('Análise salva no rascunho.');}
  if(form.id==='restore-form'){await sessionPost('restore',{...data,confirmed:data.confirmed==='on',investigation:state.investigation});$('#dialog').close();toast('Restauração registrada.');}
  if(form.id==='revision-form'){await sessionPost('revisions/'+form.dataset.id,data);$('#dialog').close();toast('Decisão registrada.');}
  if(form.id==='help-form'){await api('/help/'+form.dataset.id+'/approve',{confirmed:data.confirmed==='on'});await loadBootstrap();render();settings();toast('Consulta encerrada. Confira a documentação.');}
 }catch(error){if($('#dialog').open&&$('.dialog-errors'))$('.dialog-errors').textContent=error.message;else toast(error.message);}finally{if(submit)submit.disabled=false;}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){document.querySelectorAll('.maximized').forEach(p=>p.classList.remove('maximized'));if(state.focus&&!$('#dialog').open){state.focus=false;render();}}});

// Inicialização e atualização de sessões em andamento.
async function start(){try{await loadBootstrap();const saved=localStorage.getItem('lab-session');if(saved&&state.sessions.some(s=>s.id===saved))state.session=await api('/sessions/'+saved);else if(state.sessions.length)state.session=await api('/sessions/'+state.sessions[0].id);}catch{state.offline=true;}render();}
start();

let needsRender=false, polling=false;
setInterval(async()=>{
 if(!state.session||state.offline||polling)return;
 polling=true;
 const sid=state.session.id;
 try{
  const s=await api('/sessions/'+sid);
  if(state.session?.id!==sid)return;
  if(s.updated_at>state.session.updated_at||needsRender){
   if(s.updated_at>=state.session.updated_at)state.session=s;
   if($('#dialog').open||document.activeElement?.matches('textarea,input,select')){
    document.querySelectorAll('[data-live-progress]').forEach(el=>el.innerHTML=liveProgress());
    document.querySelectorAll('[data-running-control]').forEach(el=>el.innerHTML=runningControl());
    const status=$('[data-session-status]');
    if(status)status.innerHTML=badge(s.status)+(['thinking','running','stopping'].includes(s.status)?button('stop',icon('pause')+' Interromper','small danger'):'');
    needsRender=true;
   }else{render();needsRender=false;}
  }
 }catch(error){toast(error.message);}finally{polling=false;}
},650);
