/* Interface do agente supervisionado — JavaScript puro, sem dependências externas.
 * Todo dado dinâmico entra no DOM por textContent/createElement (nunca innerHTML): a CSP do nginx não permite scripts inline.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const API = "/api";
const S = { estado: null, sid: null, sessao: null, chat: [], chatSeq: 0, acoes: [], eventosN: -1, sig: {}, planoSujo: false, planoVersao: null,
            ocupado: false, varreduraId: null, novaSessao: false };

// ------------------------------------------------------------------ utilidades de DOM
function el(tag, attrs, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "texto") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, "");
    else n.setAttribute(k, String(v));
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) n.append(f.nodeType ? f : document.createTextNode(String(f)));
  return n;
}
const limpar = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };
const badge = (t) => el("span", { class: "badge " + String(t || "").replace(/[^a-z_]/gi, ""), texto: String(t ?? "—").replace(/_/g, " ") });
const curto = (h, n = 12) => (h ? String(h).slice(0, n) + (String(h).length > n ? "…" : "") : "—");
const json = (o) => JSON.stringify(o, null, 2);
const hora = (ts) => { try { return new Date(ts).toLocaleString("pt-BR"); } catch { return ts || ""; } };
const kv = (pares) => el("div", { class: "kv" }, pares.flatMap(([k, v]) => [el("b", { texto: k }), el("div", {}, v ?? "—")]));
const lista = (itens) => el("ul", {}, itens.map((i) => el("li", { texto: i })));

function aviso(msg, tipo) {
  const a = $("aviso");
  if (!msg) { a.hidden = true; return; }
  a.className = tipo || ""; a.textContent = msg; a.hidden = false;
  if (tipo === "ok") setTimeout(() => { if (a.textContent === msg) a.hidden = true; }, 6000);
}

function operador() {
  const bruto = ($("operador").value || "").normalize("NFD").replace(/[̀-ͯ]/g, "");
  return bruto.replace(/[^\w .@-]/g, "").slice(0, 60).trim();
}

async function api(metodo, caminho, corpo) {
  const cab = { "X-Operador": operador() || "operador" };
  if (corpo !== undefined) cab["Content-Type"] = "application/json";
  let r;
  try { r = await fetch(API + caminho, { method: metodo, headers: cab, body: corpo === undefined ? undefined : JSON.stringify(corpo) }); }
  catch (e) { throw { codigo: "rede", mensagem: "sem conexão com a API do agente" }; }
  let dados = null;
  try { dados = await r.json(); } catch { /* corpo vazio */ }
  if (!r.ok) {
    if (dados && dados.codigo) throw dados;
    if (dados && Array.isArray(dados.detail)) throw { codigo: "requisicao_invalida", mensagem: dados.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ") };
    throw { codigo: "http_" + r.status, mensagem: `erro HTTP ${r.status}` };
  }
  return dados;
}
async function acao(fn, okMsg) {
  try { const r = await fn(); if (okMsg) aviso(okMsg, "ok"); return r; }
  catch (e) { aviso(`${e.mensagem || e}${e.codigo ? ` (${e.codigo})` : ""}`, "erro"); return null; }
}

// ------------------------------------------------------------------ diálogo genérico
function dialogo({ titulo, corpo = [], campos = [], okTexto = "Confirmar", perigo = false }) {
  return new Promise((resolve) => {
    const dlg = $("dialogo"), area = limpar($("dialogo-corpo")), ok = $("dialogo-ok"), cancelar = $("dialogo-cancelar");
    const refs = {};
    area.append(el("h2", { texto: titulo }), ...corpo);
    for (const c of campos) {
      let ctl;
      if (c.tipo === "textarea") ctl = el("textarea", { rows: c.linhas || 3, maxlength: c.max || 4000 });
      else if (c.tipo === "checkbox") ctl = el("input", { type: "checkbox" });
      else if (c.tipo === "select") ctl = el("select", {}, c.opcoes.map((o) => el("option", { value: o, texto: o })));
      else ctl = el("input", { type: "text", maxlength: c.max || 300 });
      if (c.tipo === "checkbox") ctl.checked = !!c.valor; else if (c.valor !== undefined) ctl.value = c.valor;
      refs[c.id] = ctl;
      area.append(el("label", { class: c.tipo === "checkbox" ? "check" : "" }, c.tipo === "checkbox" ? [ctl, c.rotulo] : [c.rotulo, ctl]));
    }
    ok.textContent = okTexto; ok.className = perigo ? "perigo" : "primario";
    const fechar = (v) => { ok.onclick = cancelar.onclick = dlg.onclose = null; if (dlg.open) dlg.close(); resolve(v); };
    ok.onclick = () => {
      const v = {};
      for (const c of campos) {
        v[c.id] = c.tipo === "checkbox" ? refs[c.id].checked : refs[c.id].value.trim();
        if (c.obrigatorio && !v[c.id]) { refs[c.id].focus(); aviso(`Preencha: ${c.rotulo}`, "erro"); return; }
      }
      fechar(v);
    };
    cancelar.onclick = () => fechar(null);
    dlg.onclose = () => fechar(null);
    dlg.showModal();
  });
}

// ------------------------------------------------------------------ renderização com assinatura (evita perder foco/digitação)
function seMudou(chave, assinatura, fn) {
  const s = typeof assinatura === "string" ? assinatura : JSON.stringify(assinatura);
  if (S.sig[chave] === s) return;
  S.sig[chave] = s; fn();
}

// ------------------------------------------------------------------ painel de recursos
function renderTopo() {
  const e = S.estado;
  const c1 = $("chip-ollama"), c2 = $("chip-executor");
  c1.textContent = e.ollama_acessivel ? "Ollama ok" : "Ollama inacessível"; c1.className = "chip " + (e.ollama_acessivel ? "ok" : "bad");
  c2.textContent = e.executor_acessivel ? "Executor ok" : "Executor inacessível"; c2.className = "chip " + (e.executor_acessivel ? "ok" : "bad");
}

function renderVarredura() {
  const v = S.estado.ultima_varredura, alvo = $("varredura");
  seMudou("varredura", v, () => {
    limpar(alvo);
    if (!v) { alvo.textContent = "Nenhuma varredura concluída ainda."; return; }
    const emAndamento = v.estado === "em_andamento";
    alvo.append(el("div", {}, badge(v.estado), ` iniciada ${hora(v.iniciada_em)}`, v.concluida_em ? ` · concluída ${hora(v.concluida_em)}` : ""));
    if (emAndamento) alvo.append(el("progress", { max: 100, value: v.progresso || 0 }));
    alvo.append(el("div", { class: "discreto" }, (v.etapas || []).map((x) => `${x.nome}: ${x.estado} (${x.itens})`).join(" · ")));
    for (const [rot, o] of [["Novos", v.novos], ["Alterados", v.alterados], ["Removidos", v.removidos]]) {
      const m = (o && o.modelos) || [], f = (o && o.ferramentas) || [];
      alvo.append(el("div", {}, el("b", { texto: rot + ": " }), m.length || f.length ? `modelos [${m.join(", ")}] · ferramentas [${f.join(", ")}]` : "nenhum"));
    }
    if ((v.avisos || []).length) alvo.append(el("div", { class: "aviso-doc" }, lista(v.avisos)));
    if ((v.erros || []).length) alvo.append(el("div", { class: "aviso-doc" }, lista(v.erros.map((x) => (typeof x === "string" ? x : json(x))))));
  });
}

function modelosDisponiveis() { return (S.estado.modelos || []).filter((m) => m.tipo === "registrado" && m.estado === "disponivel"); }

function renderModelos() {
  const e = S.estado, tb = $("tabela-modelos").querySelector("tbody"), vz = $("modelos-vazio");
  seMudou("modelos", { m: e.modelos, a: e.modelo_ativo, s: e.sem_modelos, i: e.instrucoes.modelos }, () => {
    vz.hidden = !e.sem_modelos; limpar(vz);
    if (e.sem_modelos) vz.append(el("b", { texto: "Nenhum modelo disponível." }), lista(e.instrucoes.modelos));
    limpar(tb);
    for (const m of e.modelos) {
      const btns = [];
      if (m.tipo === "registrado" && m.estado === "disponivel")
        btns.push(m.id === e.modelo_ativo ? el("b", { texto: "ativo" }) : el("button", { texto: "Selecionar", onclick: () => selecionarModelo(m.id) }));
      if (m.tipo === "candidato") btns.push(el("button", { texto: "Importar", onclick: () => importarModelo(m) }));
      tb.append(el("tr", {}, el("td", {}, m.id, el("div", { class: "discreto", texto: m.tipo === "candidato" ? "GGUF em modelos/importar" : "registrado no Ollama" })),
        el("td", {}, badge(m.estado), m.erro ? el("div", { class: "aviso-doc", texto: m.erro }) : null), el("td", { class: "discreto", texto: curto(m.versao) }), el("td", {}, btns)));
    }
  });
}
async function selecionarModelo(id) {
  if (await acao(() => api("POST", "/modelos/selecionar", { modelo_id: id }), `Modelo ${id} selecionado para novas sessões.`)) await atualizarEstado();
}
async function importarModelo(m) {
  const base = m.id.replace(/\.gguf$/i, "").toLowerCase().replace(/[^a-z0-9._-]/g, "-").slice(0, 60);
  const v = await dialogo({ titulo: "Importar modelo GGUF", okTexto: "Importar",
    corpo: [el("p", { texto: `Arquivo: ${m.id} (${m.tamanho} bytes). O arquivo e o Modelfile são validados (assinatura GGUF; FROM apontando para o mesmo arquivo) e registrados no Ollama.` })],
    campos: [{ id: "nome", rotulo: "Nome do modelo no Ollama", valor: base, obrigatorio: true, max: 64 }] });
  if (!v) return;
  aviso("Importando… pode levar alguns minutos.");
  if (await acao(() => api("POST", "/modelos/importar", { arquivo: m.id, nome: v.nome }), `Modelo ${v.nome} importado.`)) await atualizarEstado();
}

function renderFerramentas() {
  const e = S.estado, alvo = $("lista-ferramentas"), vz = $("ferramentas-vazio");
  seMudou("ferramentas", { f: e.ferramentas, s: e.sem_ferramentas, i: e.instrucoes.ferramentas }, () => {
    vz.hidden = !e.sem_ferramentas; limpar(vz);
    if (e.sem_ferramentas) vz.append(el("b", { texto: e.ferramentas.length ? "Nenhuma ferramenta habilitada." : "Nenhuma ferramenta detectada." }), lista(e.instrucoes.ferramentas));
    limpar(alvo);
    for (const f of e.ferramentas) {
      const b = [el("button", { texto: "Revisar", onclick: () => revisarFerramenta(f.id) })];
      if (f.status === "habilitada") b.push(el("button", { texto: "Desabilitar", onclick: () => desabilitar(f.id) }));
      alvo.append(el("div", { class: "painel" },
        el("div", {}, el("b", { texto: f.id }), " ", badge(f.status), f.perfil ? el("span", { class: "discreto", texto: ` · ${f.perfil}` }) : null),
        f.descricao ? el("div", { class: "discreto", texto: f.descricao }) : null,
        el("div", { class: "discreto", texto: `manifesto ${curto(f.manifesto_sha256)} · executável ${curto(f.executavel_sha256)} · doc ${curto(f.doc_sha256)}` }),
        (f.erros || []).length ? el("div", { class: "aviso-doc" }, lista(f.erros)) : null,
        (f.avisos || []).length ? el("div", { class: /SEM DOC/.test(f.avisos.join()) ? "aviso-doc" : "discreto" }, lista(f.avisos)) : null,
        el("div", { class: "linha" }, b)));
    }
  });
}
async function revisarFerramenta(id) {
  const f = await acao(() => api("GET", `/ferramentas/${encodeURIComponent(id)}`));
  if (!f) return;
  const podeHabilitar = ["pendente_habilitacao", "suspensa_alterada"].includes(f.status);
  const corpo = [
    kv([["Status", badge(f.status)], ["Perfil", f.perfil], ["Hash do manifesto", f.manifesto_sha256], ["Hash do executável", f.executavel_sha256], ["Hash da documentação", f.doc_sha256]]),
    (f.erros || []).length ? el("div", { class: "aviso-doc" }, lista(f.erros)) : null,
    (f.avisos || []).length ? el("div", { class: "discreto" }, lista(f.avisos)) : null,
    el("h3", { texto: "Manifesto" }), el("pre", { texto: json(f.manifesto) }),
    el("h3", { texto: "Documentação" }), el("pre", { texto: f.documentacao_texto || "(sem documentação)" }),
    el("p", { class: "discreto", texto: "Habilitar registra os hashes acima. Qualquer mudança posterior no manifesto, na documentação ou no executável suspende a ferramenta até nova revisão." }),
  ];
  const v = await dialogo({ titulo: `Revisar ferramenta ${id}`, corpo, okTexto: podeHabilitar ? "Habilitar" : "Fechar",
    campos: podeHabilitar ? [{ id: "justificativa", rotulo: "Justificativa da habilitação (opcional)", tipo: "textarea", linhas: 2, max: 1000 }] : [] });
  if (v && podeHabilitar) {
    if (await acao(() => api("POST", `/ferramentas/${encodeURIComponent(id)}/habilitar`, { manifesto_sha256: f.manifesto_sha256, justificativa: v.justificativa || null }), `Ferramenta ${id} habilitada.`)) await atualizarEstado();
  }
}
async function desabilitar(id) {
  if (await acao(() => api("POST", `/ferramentas/${encodeURIComponent(id)}/desabilitar`), `Ferramenta ${id} desabilitada.`)) await atualizarEstado();
}

function renderEgress() {
  const g = S.estado.egress, alvo = $("egress");
  seMudou("egress", g, () => {
    limpar(alvo);
    if (!g) { alvo.textContent = "Nunca verificada."; return; }
    alvo.append(el("div", {}, badge(g.ok ? "disponivel" : "bloqueada"), ` ${g.ok ? "nenhum destino proibido foi alcançado" : "ATENÇÃO: destino proibido alcançado"} · ${hora(g.em)}`),
      el("table", {}, el("tbody", {}, (g.resultados || []).map((r) => el("tr", {}, el("td", { texto: `${r.ip}:${r.porta}` }), el("td", { texto: r.rotulo }), el("td", { texto: r.alcancou ? "alcançou" : "bloqueado/sem resposta" }))))),
      el("div", { class: "discreto", texto: g.aviso }));
  });
}

// ------------------------------------------------------------------ sessões
function renderSessoes() {
  const e = S.estado, ul = $("lista-sessoes");
  seMudou("sessoes", { s: e.sessoes, a: S.sid }, () => {
    limpar(ul);
    if (!e.sessoes.length) ul.append(el("li", { class: "discreto", texto: "Nenhuma sessão." }));
    for (const s of e.sessoes) ul.append(el("li", { class: s.id === S.sid ? "ativa" : "", onclick: () => abrirSessao(s.id) },
      el("b", { texto: s.nome }), el("div", { class: "discreto" }, badge(s.fase), " ", badge(s.estado), ` ${hora(s.criado_em)}`)));
  });
}

function renderGuia() {
  const e = S.estado, g = limpar($("guia"));
  g.append(lista([
    `Modelo: ${e.sem_modelos ? "nenhum disponível — veja o painel «Modelos»" : `${modelosDisponiveis().length} disponível(is); ativo: ${e.modelo_ativo || "nenhum selecionado"}`}`,
    `Ferramentas: ${e.sem_ferramentas ? "nenhuma habilitada — veja o painel «Ferramentas»" : `${e.ferramentas.filter((f) => f.utilizavel).length} habilitada(s)`}`,
    `Limites: até ${e.limites.max_passos} passos por investigação, ${e.limites.max_chamadas_minuto} chamadas/min, métodos ${e.limites.metodos_permitidos.join("/")}.`,
    "Fluxo: validar alvo → criar sessão → plano humano → consultar modelo → decidir cada ação → registrar evidências → relatório.",
  ]));
}

function mostrarNovaSessao(sim) {
  S.novaSessao = sim;
  $("nova-sessao").hidden = !sim;
  atualizarVisibilidade();
}
function atualizarVisibilidade() {
  $("inicio").hidden = !!S.sid || S.novaSessao;
  $("sessao").hidden = !S.sid || S.novaSessao;
}
function modoSelecionado() { return document.querySelector('input[name="modo"]:checked').value; }
function lerPortas(txt) {
  const itens = txt.split(",").map((x) => x.trim()).filter(Boolean), ports = itens.map(Number);
  if (ports.some((p) => !Number.isInteger(p) || p < 1 || p > 65535)) throw { mensagem: "portas adicionais inválidas (use números de 1 a 65535 separados por vírgula)" };
  return ports;
}
function corpoAlvo() {
  const modo = modoSelecionado();
  return { modo, url: modo === "local" ? null : $("ns-url").value.trim() || null, confirmou_autorizacao: modo === "local" ? true : $("ns-confirma").checked,
           portas_autorizadas_extra: modo === "local" ? [] : lerPortas($("ns-portas").value) };
}
function prever(r) {
  const e = r.escopo, s = r.sondagem || {};
  return ["URL normalizada: " + e.url_base, `Host: ${e.host}`, `IP efetivo (fixado para a sessão): ${e.ip_efetivo}   IPs autorizados: ${(e.ips_autorizados || []).join(", ")}`,
    `Porta: ${e.porta}   Portas autorizadas p/ varredura: ${(e.portas_autorizadas || []).join(", ")}`,
    `Conectividade (a partir do executor): ${s.alcancavel === null || s.alcancavel === undefined ? "não verificada" : s.alcancavel ? "alcançável" : "INACESSÍVEL — " + (s.erro || "")}`,
    s.assinatura_juice_shop === undefined || s.assinatura_juice_shop === null ? "" : `Assinatura OWASP Juice Shop: ${s.assinatura_juice_shop ? "sim" : "NÃO"}`,
    "Escopo: somente este host/IP/porta (e as portas adicionais acima, apenas para varredura).",
    ...(r.avisos || []).map((a) => "AVISO: " + a)].filter(Boolean).join("\n");
}
async function validarAlvo() {
  let corpo; try { corpo = corpoAlvo(); } catch (e) { aviso(e.mensagem, "erro"); return null; }
  const r = await acao(() => api("POST", "/alvo/validar", corpo));
  const pre = $("ns-resultado"); pre.hidden = !r; if (r) pre.textContent = prever(r);
  return r;
}
async function criarSessao() {
  let corpo; try { corpo = corpoAlvo(); } catch (e) { aviso(e.mensagem, "erro"); return; }
  const r = await acao(() => api("POST", "/sessoes", { ...corpo, nome: $("ns-nome").value.trim(), objetivo: $("ns-objetivo").value.trim(), modelo_id: null }), "Sessão criada.");
  if (r) { mostrarNovaSessao(false); await atualizarEstado(); abrirSessao(r.sessao.id); }
}

// ------------------------------------------------------------------ sessão aberta
function abrirSessao(id) {
  S.sid = id; S.sessao = null; S.chat = []; S.chatSeq = 0; S.acoes = []; S.eventosN = -1; S.planoSujo = false; S.planoVersao = null;
  for (const k of ["cab", "faltas", "plano", "sug", "inv", "acao", "acoes", "chat", "linha", "sessoes"]) delete S.sig[k];
  limpar($("chat")); $("saida-acao").hidden = true; mostrarNovaSessao(false); atualizarVisibilidade();
  acao(() => api("GET", `/sessoes/${id}/relatorio`)).then((r) => { if (r) $("relatorio").value = r.conteudo; });
  atualizarSessao();
}

function renderCabecalho() {
  const d = S.sessao, s = d.sessao, e = s.escopo, alvo = $("cabecalho-sessao"), disp = modelosDisponiveis().map((m) => m.id);
  const ocupada = ["modelo_pensando", "executando"].includes(s.fase), ativa = s.estado === "ativa";
  seMudou("cab", { s, disp, ocupada, d: S.estado.modelo_ativo }, () => {
    limpar(alvo);
    const sel = el("select", {}, [el("option", { value: "", texto: s.modelo_id ? "— trocar de modelo —" : "— selecionar modelo —" }), ...disp.map((m) => el("option", { value: m, texto: m }))]);
    const exp = ["chat", "eventos", "arquivos", "resultados", "relatorio", "completo"].map((i) => el("a", { href: `${API}/sessoes/${S.sid}/exportar/${i}`, download: "", class: "chip", texto: `⬇ ${i}` }));
    alvo.append(
      el("h2", {}, s.nome, " ", badge(s.fase), " ", badge(s.estado)),
      el("div", { class: "discreto", texto: s.objetivo }),
      kv([["Alvo", `${e.url_base} (IP ${e.ip_efetivo}, porta ${e.porta})`], ["Portas p/ varredura", (e.portas_autorizadas || []).join(", ")], ["Modo", s.modo],
          ["Modelo da sessão", s.modelo_id ? `${s.modelo_id} (versão ${curto(s.modelo_digest)})` : "nenhum"], ["Último reset do alvo", s.ultimo_reset_em ? hora(s.ultimo_reset_em) : "nunca nesta sessão"],
          ["Aviso", s.aviso]]),
      el("div", { class: "linha" }, sel, el("button", { texto: "Aplicar modelo", disabled: !ativa || ocupada, onclick: () => trocarModelo(sel.value) })),
      el("div", { class: "linha" },
        el("button", { texto: "Restaurar alvo", disabled: !ativa || ocupada, onclick: resetarAlvo }),
        el("button", { texto: "Redefinir escopo", disabled: !ativa || ocupada, onclick: redefinirEscopo }),
        el("button", { class: "perigo", texto: "Interromper sessão", disabled: !ativa, onclick: interromper })),
      el("div", { class: "linha" }, el("span", { class: "discreto", texto: "Exportar:" }), exp));
  });
}
async function trocarModelo(id) {
  if (!id) { aviso("Escolha um modelo na lista.", "erro"); return; }
  const chamar = (rein) => api("POST", `/sessoes/${S.sid}/modelo`, { modelo_id: id, reiniciar_contexto: rein });
  try { await chamar(false); aviso(`Modelo da sessão: ${id}.`, "ok"); }
  catch (e) {
    if (e.codigo !== "confirmacao_necessaria") { aviso(e.mensagem || String(e), "erro"); return; }
    const v = await dialogo({ titulo: "Trocar de modelo", okTexto: "Trocar e reiniciar contexto", perigo: true,
      corpo: [el("p", { texto: e.mensagem }), el("p", { texto: "O histórico continua nos registros e na exportação, mas o novo modelo começa sem o contexto anterior. A troca fica registrada com a versão de cada modelo." })] });
    if (!v) return;
    await acao(() => chamar(true), `Modelo trocado para ${id}; contexto reiniciado.`);
  }
  atualizarSessao();
}
async function resetarAlvo() {
  const local = S.sessao.sessao.modo === "local";
  const v = await dialogo({ titulo: "Restaurar o alvo a um estado conhecido", okTexto: "Restaurar", perigo: true,
    corpo: [el("p", { texto: local ? "O contêiner do Juice Shop local será reiniciado e todos os dados criados nos testes serão descartados. A plataforma só reinicia esse contêiner." :
      "No modo LAN a plataforma não reinicia o computador do alvo. Execute o procedimento de restauração lá (por exemplo, reiniciar o contêiner do Juice Shop) e descreva-o abaixo; ele fica registrado." })],
    campos: [...(local ? [] : [{ id: "procedimento", rotulo: "Procedimento executado", tipo: "textarea", obrigatorio: true, max: 2000 }]),
             { id: "confirmacao", rotulo: local ? "Confirmo a restauração do alvo local" : "Confirmo que executei o procedimento acima", tipo: "checkbox", obrigatorio: true }] });
  if (!v) return;
  aviso("Restaurando o alvo e verificando disponibilidade…");
  await acao(() => api("POST", `/sessoes/${S.sid}/reset`, { confirmacao: v.confirmacao, procedimento: local ? null : v.procedimento }), "Alvo restaurado e verificado.");
  atualizarSessao();
}
async function redefinirEscopo() {
  const s = S.sessao.sessao, local = s.modo === "local";
  const v = await dialogo({ titulo: "Redefinir escopo", okTexto: "Redefinir",
    corpo: [el("p", { texto: `Escopo atual: ${s.escopo.url_base}. A redefinição cancela a ação pendente, é validada de novo e fica registrada com a justificativa.` })],
    campos: [...(local ? [] : [{ id: "url", rotulo: "Nova URL completa", valor: s.escopo.url_informada, obrigatorio: true },
                               { id: "portas", rotulo: "Portas adicionais p/ varredura (vírgula)", valor: "" },
                               { id: "conf", rotulo: "Confirmo que o novo destino é uma instância autorizada", tipo: "checkbox", obrigatorio: true }]),
             { id: "just", rotulo: "Justificativa", tipo: "textarea", obrigatorio: true, max: 1000 }] });
  if (!v) return;
  let portas; try { portas = local ? [] : lerPortas(v.portas); } catch (e) { aviso(e.mensagem, "erro"); return; }
  await acao(() => api("POST", `/sessoes/${S.sid}/escopo`, { modo: s.modo, url: local ? null : v.url, confirmou_autorizacao: local ? true : v.conf, portas_autorizadas_extra: portas, justificativa: v.just }), "Escopo redefinido.");
  atualizarSessao();
}
async function interromper() {
  const v = await dialogo({ titulo: "Interromper sessão", okTexto: "Interromper", perigo: true, corpo: [el("p", { texto: "A sessão deixa de aceitar consultas e execuções. Os registros continuam disponíveis para exportação." })],
    campos: [{ id: "motivo", rotulo: "Motivo (opcional)", max: 500 }] });
  if (v) { await acao(() => api("POST", `/sessoes/${S.sid}/interromper`, { motivo: v.motivo || null }), "Sessão interrompida."); atualizarSessao(); }
}

function renderFaltas() {
  const f = S.sessao.faltas, a = $("faltas");
  seMudou("faltas", f, () => { a.hidden = !f.length; limpar(a); if (f.length) a.append(el("h2", { texto: "Pendências para começar" }), lista(f)); });
}

const CAMPOS_PLANO = [["aspectos", "Aspectos a investigar"], ["hipoteses", "Hipóteses iniciais"], ["estrategia", "Estratégia de investigação"], ["ferramentas", "Ferramentas pretendidas"], ["evidencias_esperadas", "Evidências esperadas"]];
function renderPlano() {
  const p = S.sessao.plano, form = $("plano-form");
  if (!form.firstChild) {
    for (const [k, r] of CAMPOS_PLANO) form.append(el("label", {}, r, el("textarea", { id: "plano-" + k, rows: 3, maxlength: 4000, oninput: () => { S.planoSujo = true; } })));
  }
  const versao = p ? p.versao : 0;
  if (S.planoVersao !== versao && !S.planoSujo) {
    for (const [k] of CAMPOS_PLANO) $("plano-" + k).value = (p && p.conteudo[k]) || "";
    S.planoVersao = versao;
  }
  $("plano-info").textContent = p ? `Plano v${p.versao} salvo em ${hora(p.criado_em)}. Cada alteração gera uma nova versão; a anterior é preservada.` : "Nenhum plano salvo. O modelo só é consultado depois que o plano é salvo.";
  const s = S.sessao.sessao, ativa = s.estado === "ativa", ocupada = ["modelo_pensando", "executando"].includes(s.fase);
  $("btn-plano").disabled = !ativa;
  $("btn-consultar").disabled = !ativa || ocupada || !p || !s.modelo_id;
}
async function salvarPlano() {
  const c = {}; for (const [k] of CAMPOS_PLANO) c[k] = $("plano-" + k).value.trim();
  if (await acao(() => api("POST", `/sessoes/${S.sid}/plano`, c), "Plano salvo.")) { S.planoSujo = false; atualizarSessao(); }
}
async function consultarPlano() {
  if (S.planoSujo) { aviso("Há alterações não salvas no plano: salve antes de consultar o modelo.", "erro"); return; }
  if (await acao(() => api("POST", `/sessoes/${S.sid}/iniciar`), "Modelo consultado para revisar o plano.")) atualizarSessao();
}

function renderSugestoes() {
  const sug = S.sessao.sugestoes, alvo = $("sugestoes"), ativa = S.sessao.sessao.estado === "ativa";
  seMudou("sug", sug.map((g) => [g.id, g.estado]), () => {
    limpar(alvo); alvo.className = sug.length ? "" : "vazio";
    if (!sug.length) { alvo.textContent = "Nenhuma ainda."; return; }
    for (const g of sug) {
      const caixa = el("div", { class: "painel" }, el("div", {}, badge(g.estado), g.item ? el("span", { class: "discreto", texto: ` · item: ${g.item}` }) : null),
        el("p", { texto: g.texto }), el("div", { class: "discreto", texto: "Afirmação do modelo — não é evidência. Decida e justifique." }));
      if (g.estado === "pendente" && ativa) {
        const just = el("textarea", { rows: 2, placeholder: "Justificativa técnica (obrigatória)", maxlength: 2000 }), alt = el("textarea", { rows: 2, placeholder: "Texto alterado (para «Aceitar com alteração»)", maxlength: 2000 });
        const dec = (d) => async () => { if (await acao(() => api("POST", `/sessoes/${S.sid}/sugestoes/${g.id}/decisao`, { decisao: d, justificativa: just.value.trim(), texto_alterado: d === "alterada" ? alt.value.trim() : null }), "Decisão registrada.")) atualizarSessao(); };
        caixa.append(just, alt, el("div", { class: "linha" }, el("button", { texto: "Aceitar", onclick: dec("aceita") }), el("button", { texto: "Aceitar com alteração", onclick: dec("alterada") }), el("button", { texto: "Rejeitar", onclick: dec("rejeitada") })));
      } else {
        caixa.append(el("div", { class: "discreto", texto: `${g.operador || ""} ${g.decidido_em ? hora(g.decidido_em) : ""} — ${g.justificativa || ""}` }), g.texto_alterado ? el("div", {}, el("b", { texto: "Texto final: " }), g.texto_alterado) : null);
      }
      alvo.append(caixa);
    }
  });
}

function renderInvestigacoes() {
  const d = S.sessao, invs = d.investigacoes, alvo = $("investigacoes"), ativa = d.sessao.estado === "ativa";
  seMudou("inv", { i: invs.map((x) => [x.id, x.estado]), p: d.passos_usados, a: ativa }, () => {
    limpar(alvo);
    for (let n = 1; n <= 3; n++) {
      const inv = invs.find((x) => x.numero === n);
      if (!inv) { alvo.append(el("div", { class: "discreto", texto: `Investigação ${n}: não iniciada.` })); continue; }
      const aberta = ["ativa", "limite_passos"].includes(inv.estado), cartao = el("div", { class: "painel" },
        el("div", {}, el("b", { texto: `Investigação ${n} — ${inv.titulo} ` }), badge(inv.estado)),
        el("div", { class: "discreto", texto: `Hipótese: ${inv.hipotese || "—"} · Estratégia: ${inv.estrategia || "—"}` }));
      if (aberta) {
        const usados = inv.id === (d.investigacao_ativa || {}).id ? d.passos_usados : 0;
        cartao.append(el("div", { texto: `Passos: ${usados}/${d.passos_max}` }), el("div", { class: "passos" }, el("div", { style: `width:${Math.min(100, (usados / d.passos_max) * 100)}%` })));
        const conc = el("textarea", { rows: 2, placeholder: "Conclusão do grupo (opcional; só entra no relatório se houver evidência registrada)", maxlength: 4000 });
        const lim = el("textarea", { rows: 2, placeholder: "Limites e ressalvas (opcional)", maxlength: 4000 });
        cartao.append(conc, lim, el("button", { texto: "Encerrar investigação", disabled: !ativa, onclick: async () => {
          if (await acao(() => api("POST", `/sessoes/${S.sid}/investigacoes/${n}/encerrar`, { conclusao: conc.value.trim(), limites: lim.value.trim() }), `Investigação ${n} encerrada.`)) atualizarSessao(); } }));
      } else {
        cartao.append(el("div", { class: "discreto", texto: `Conclusão: ${inv.conclusao || "—"} · Limites: ${inv.limites_texto || "—"}` }));
      }
      alvo.append(cartao);
    }
    $("form-investigacao").hidden = invs.length >= 3 || !ativa;
  });
}
async function iniciarInvestigacao() {
  const r = await acao(() => api("POST", `/sessoes/${S.sid}/investigacoes`, { titulo: $("inv-titulo").value.trim(), hipotese: $("inv-hipotese").value.trim(), estrategia: $("inv-estrategia").value.trim() }), "Investigação iniciada.");
  if (r) { for (const i of ["inv-titulo", "inv-hipotese", "inv-estrategia"]) $(i).value = ""; $("form-investigacao").open = false; atualizarSessao(); }
}

function renderAcaoPendente() {
  const d = S.sessao, a = d.acao_pendente, alvo = $("painel-acao"), s = d.sessao;
  const chave = a ? [a.id, a.estado] : null;
  seMudou("acao", { chave, ativa: s.estado }, () => {
    limpar(alvo); alvo.className = "painel";
    alvo.hidden = !a || !["pendente", "executando"].includes(a.estado);
    if (alvo.hidden) return;
    alvo.classList.add("acao");
    const n = a.acao || {}, al = n.alvo || {}, pr = a.proposta || {};
    alvo.append(el("h2", { texto: a.estado === "pendente" ? "Ação aguardando a sua decisão" : "Ação em execução…" }));
    alvo.append(kv([["Ação", a.id], ["Ferramenta", `${a.ferramenta_id} (${n.perfil || "?"})`], ["Chamada", n.resumo_legivel],
      ["Alvo efetivo", al.host ? `${al.esquema}://${al.host} → IP ${al.ip}, porta ${al.porta}${al.caminho_base || ""}` : "—"],
      ["Parâmetros normalizados", el("pre", { texto: json(a.parametros_efetivos) })],
      ["Justificativa do modelo", el("div", {}, pr.justificativa || "—", el("div", { class: "discreto", texto: "afirmação do modelo — não é evidência" }))],
      ["Hipótese do modelo", pr.hipotese], ["Verificações de política", (n.verificacoes || []).length ? lista(n.verificacoes) : "—"],
      ["Avisos", (n.avisos || []).length ? lista(n.avisos) : "—"], ["Hashes registrados", `manifesto ${curto((a.hashes || {}).manifesto_sha256)} · executável ${curto((a.hashes || {}).executavel_sha256)} · modelo ${curto((a.hashes || {}).modelo_digest)}`]]));
    if (a.estado !== "pendente") return;
    const ed = el("textarea", { rows: 8, spellcheck: "false", hidden: true }), editando = { v: false };
    ed.value = json(a.parametros_efetivos);
    const just = el("textarea", { rows: 2, placeholder: "Justificativa (obrigatória para editar ou rejeitar)", maxlength: 2000 });
    const decidir = (d2, extra) => async () => {
      if (await acao(() => api("POST", `/acoes/${a.id}/decisao`, { decisao: d2, justificativa: just.value.trim() || null, ...extra() }), d2 === "rejeitar" ? "Ação rejeitada (nada foi executado)." : "Decisão registrada.")) atualizarSessao();
    };
    alvo.append(el("p", { class: "discreto", texto: "A política é aplicada de novo imediatamente antes da execução, inclusive depois de edições. Credenciais mascaradas na tela são restauradas pelo servidor." }),
      ed, just, el("div", { class: "linha" },
        el("button", { class: "primario", texto: "Autorizar", disabled: s.estado !== "ativa", onclick: decidir("autorizar", () => ({})) }),
        el("button", { texto: "Editar e autorizar", disabled: s.estado !== "ativa", onclick: () => {
          if (!editando.v) { editando.v = true; ed.hidden = false; aviso("Edite os parâmetros no quadro e clique em «Editar e autorizar» de novo."); return; }
          let p; try { p = JSON.parse(ed.value); } catch { aviso("JSON de parâmetros inválido.", "erro"); return; }
          decidir("editar_autorizar", () => ({ parametros_editados: p }))();
        } }),
        el("button", { class: "perigo", texto: "Rejeitar", disabled: s.estado !== "ativa", onclick: decidir("rejeitar", () => ({})) })));
  });
}

// ------------------------------------------------------------------ chat
function catMsg(m, anterior) {
  let corpo = m.conteudo, cat = "conversa", rotulo = m.papel, extra = "";
  if (m.papel === "humano") { cat = "conversa"; rotulo = `Você${m.meta && m.meta.operador ? " (" + m.meta.operador + ")" : ""}`; }
  else if (m.papel === "sistema") { cat = "sistema"; rotulo = "Sistema"; }
  else if (m.papel === "ferramenta") { cat = "saida"; rotulo = "Saída da ferramenta (dado bruto)"; }
  else if (m.papel === "modelo") {
    let o = null; try { o = JSON.parse(m.conteudo); } catch { /* texto livre */ }
    if (o && o.tipo === "proposta") { cat = "proposta"; rotulo = "Proposta do modelo"; corpo = `${o.ferramenta}\n${json(o.parametros)}\nJustificativa: ${o.justificativa}`; extra = m.acao_id ? ` · ação ${m.acao_id}` : ""; }
    else if (o && o.tipo === "mensagem") { corpo = o.texto; rotulo = anterior && anterior.papel === "ferramenta" ? "Interpretação do modelo (não é evidência)" : "Modelo"; if (rotulo.startsWith("Interp")) cat = "interpretacao"; }
    else if (o && o.tipo === "concluir") { corpo = o.texto; rotulo = "Conclusão do modelo (afirmação, não evidência)"; }
    else if (o && o.tipo === "revisao_plano") { corpo = (o.sugestoes || []).map((x) => `• ${x.texto}`).join("\n"); rotulo = "Revisão do plano pelo modelo"; }
    else rotulo = "Modelo (resposta fora do protocolo)";
  }
  return { cat, rotulo: rotulo + extra, corpo };
}
async function atualizarChat() {
  const r = await api("GET", `/sessoes/${S.sid}/chat?desde=${S.chatSeq}`);
  if (!r.mensagens.length) return;
  const caixa = $("chat"), perto = caixa.scrollHeight - caixa.scrollTop - caixa.clientHeight < 80;
  for (const m of r.mensagens) {
    const anterior = S.chat[S.chat.length - 1], c = catMsg(m, anterior);
    S.chat.push(m); S.chatSeq = Math.max(S.chatSeq, m.seq);
    caixa.append(el("div", { class: `msg ${m.papel} cat-${c.cat}` }, el("span", { class: "quem", texto: `${c.rotulo} · ${hora(m.ts)}` }), c.corpo));
  }
  if (perto) caixa.scrollTop = caixa.scrollHeight;
}
function aplicarFiltrosChat() {
  const c = $("chat");
  for (const f of document.querySelectorAll("[data-filtro]")) c.classList.toggle("oculta-" + f.dataset.filtro, !f.checked);
}
async function enviarMensagem() {
  const t = $("chat-texto").value.trim(); if (!t) return;
  if (await acao(() => api("POST", `/sessoes/${S.sid}/mensagens`, { texto: t }))) { $("chat-texto").value = ""; atualizarSessao(); }
}

// ------------------------------------------------------------------ ações, evidências, linha do tempo, relatório
async function atualizarAcoes() {
  const r = await api("GET", `/sessoes/${S.sid}/acoes`);
  seMudou("acoes", { a: r.acoes.map((x) => [x.id, x.estado, x.decisao]), e: S.sessao.evidencias.length }, () => {
    const alvo = limpar($("acoes"));
    if (!r.acoes.length) alvo.append(el("div", { class: "discreto", texto: "Nenhuma ação proposta ainda." }));
    else alvo.append(el("table", {}, el("thead", {}, el("tr", {}, ["Ação", "Ferramenta", "Estado", "Decisão", "Chamada", ""].map((h) => el("th", { texto: h })))),
      el("tbody", {}, r.acoes.map((a) => el("tr", {}, el("td", { texto: a.id }), el("td", { texto: a.ferramenta_id }), el("td", {}, badge(a.estado)), el("td", { texto: a.decisao || "—" }),
        el("td", { class: "discreto", texto: (a.acao || {}).resumo_legivel || ((a.validacao || {}).erro || {}).mensagem || "—" }),
        el("td", {}, [el("button", { texto: "Saída", disabled: !(a.resultado_ids || []).length, onclick: () => verSaida(a) }), " ",
          el("button", { texto: "Nota posterior", onclick: () => notaPosterior(a) })]))))));
    const ev = S.sessao.evidencias;
    alvo.append(el("h3", { texto: "Evidências registradas" }), ev.length ? el("ul", {}, ev.map((e) => el("li", { texto: `${e.id} · ação ${e.acao_id || "—"} · ${e.nota}` }))) : el("div", { class: "discreto", texto: "Nenhuma. Abra a «Saída» de uma ação e registre a evidência que a sustenta." }));
  });
}
async function verSaida(a) {
  const r = await acao(() => api("GET", `/acoes/${a.id}/saida`)); if (!r) return;
  const pre = $("saida-acao"); pre.hidden = false; limpar(pre);
  pre.append(`# Saída da ação ${a.id} (credenciais mascaradas na tela; arquivos brutos preservados com hash)\n`);
  const botoes = [];
  for (const [nome, o] of Object.entries(r)) {
    pre.append(`\n--- ${nome}  sha256=${o.sha256}  ${o.tamanho} bytes${o.cortado ? "  (exibição cortada)" : ""} ---\n${o.texto}\n`);
    botoes.push(el("button", { texto: `Registrar evidência: ${nome}`, onclick: () => registrarEvidencia(a, o.id) }));
  }
  pre.after(...[]); let c = $("saida-botoes"); if (c) c.remove();
  c = el("div", { id: "saida-botoes", class: "linha" }, botoes); pre.after(c);
}
async function registrarEvidencia(a, rid) {
  const v = await dialogo({ titulo: "Registrar evidência", okTexto: "Registrar", corpo: [el("p", { texto: `Ação ${a.id}, resultado ${rid}. Descreva o que este resultado bruto demonstra — esta nota é do grupo, não do modelo.` })],
    campos: [{ id: "nota", rotulo: "O que a evidência demonstra", tipo: "textarea", obrigatorio: true, max: 2000 }] });
  if (v && await acao(() => api("POST", `/sessoes/${S.sid}/evidencias`, { acao_id: a.id, resultado_id: rid, nota: v.nota }), "Evidência registrada.")) atualizarSessao();
}
async function notaPosterior(a) {
  const v = await dialogo({ titulo: `Nota sobre a ação ${a.id}`, okTexto: "Registrar", corpo: [el("p", { texto: "Registre uma decisão ou observação posterior sobre esta ação. O registro original da decisão não é alterado." })],
    campos: [{ id: "texto", rotulo: "Nota", tipo: "textarea", obrigatorio: true }] });
  if (v) await acao(() => api("POST", `/acoes/${a.id}/nota`, { texto: v.texto }), "Nota registrada.");
}

async function atualizarLinhaTempo() {
  const r = await api("GET", `/sessoes/${S.sid}/eventos`), ev = r.eventos;
  const ultimo = ev.length ? ev[ev.length - 1].id : "";
  seMudou("linha", [ev.length, ultimo], () => {
    const alvo = limpar($("linha-tempo")), nomes = {};
    for (const i of S.sessao.investigacoes) nomes[i.id] = `Investigação ${i.numero} — ${i.titulo}`;
    const grupos = new Map();
    for (const e of ev) { const k = e.investigacao_id || "-"; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(e); }
    for (const [k, lst] of grupos) alvo.append(el("details", { class: "grupo-inv", open: k === "-" || null }, el("summary", { texto: `${k === "-" ? "Sessão (sem investigação)" : nomes[k] || k} · ${lst.length} eventos` }),
      lst.map((e) => el("details", { class: "evt" }, el("summary", {}, el("code", { texto: e.tipo }), ` ${hora(e.ts)}`), el("pre", { texto: json(e.dados) })))));
  });
}

async function relatorioGerar() {
  let r;
  try { r = await api("POST", `/sessoes/${S.sid}/relatorio/gerar`); }
  catch (e) {
    if (e.codigo !== "relatorio_existente") { aviso(e.mensagem, "erro"); return; }
    const v = await dialogo({ titulo: "Sobrescrever rascunho?", okTexto: "Sobrescrever", perigo: true, corpo: [el("p", { texto: "Já existe um relatório editado. O anterior é preservado como arquivo .bak na pasta da sessão." })] });
    if (!v) return;
    r = await acao(() => api("POST", `/sessoes/${S.sid}/relatorio/gerar?sobrescrever=true`));
  }
  if (r) { $("relatorio").value = r.conteudo; aviso("Rascunho gerado a partir dos registros.", "ok"); }
}
async function relatorioSalvar() { await acao(() => api("PUT", `/sessoes/${S.sid}/relatorio`, { conteudo: $("relatorio").value }), "Relatório salvo."); }

// ------------------------------------------------------------------ ciclo de atualização
async function atualizarEstado() {
  try {
    S.estado = await api("GET", "/estado");
    renderTopo(); renderVarredura(); renderModelos(); renderFerramentas(); renderEgress(); renderSessoes(); renderGuia();
    $("btn-varrer").disabled = (S.estado.ultima_varredura || {}).estado === "em_andamento";
  } catch (e) { $("chip-ollama").textContent = "API inacessível"; $("chip-ollama").className = "chip bad"; }
}
async function atualizarSessao() {
  if (!S.sid || S.ocupado) return;
  S.ocupado = true;
  try {
    S.sessao = await api("GET", `/sessoes/${S.sid}`);
    renderCabecalho(); renderFaltas(); renderPlano(); renderSugestoes(); renderInvestigacoes(); renderAcaoPendente();
    const f = S.sessao.sessao.fase;
    $("btn-enviar").disabled = S.sessao.sessao.estado !== "ativa";
    $("btn-iniciar-inv").disabled = S.sessao.sessao.estado !== "ativa";
    await Promise.all([atualizarChat(), atualizarAcoes(), atualizarLinhaTempo()]);
    if (f === "modelo_pensando") aviso("O modelo está pensando…");
    else if (f === "executando") aviso("Executando a ação autorizada…");
    else if ($("aviso").textContent.match(/pensando|Executando a ação/)) aviso(null);
  } catch (e) { if (e.codigo === "sessao_inexistente" || e.codigo === "http_404") { S.sid = null; atualizarVisibilidade(); } else aviso(e.mensagem || String(e), "erro"); }
  finally { S.ocupado = false; }
}
function ligar() {
  $("operador").value = (() => { try { return localStorage.getItem("operador") || ""; } catch { return ""; } })();
  $("operador").addEventListener("input", () => { try { localStorage.setItem("operador", operador()); } catch { /* sem armazenamento */ } });
  $("btn-varrer").onclick = async () => { if (await acao(() => api("POST", "/varreduras"))) { await atualizarEstado(); } };
  $("btn-egress").onclick = async () => {
    aviso("Verificando saída de rede do executor…");
    const r = await acao(() => api("POST", "/egress/verificar", { sessao_id: S.sid, destinos_extra: [] }));
    if (r) { aviso(`${r.ok ? "Nenhum destino proibido foi alcançado." : "ATENÇÃO: um destino proibido foi alcançado."} ${r.aviso}`, r.ok ? "ok" : "erro"); await atualizarEstado(); }
  };
  $("btn-nova-sessao").onclick = () => { S.sid = null; mostrarNovaSessao(true); };
  $("ns-cancelar").onclick = () => mostrarNovaSessao(false);
  $("ns-validar").onclick = validarAlvo; $("ns-criar").onclick = criarSessao;
  for (const r of document.querySelectorAll('input[name="modo"]')) r.addEventListener("change", () => {
    const local = modoSelecionado() === "local";
    for (const i of ["rotulo-url"]) $(i).hidden = local;
    $("ns-confirma").closest("label").hidden = local; $("ns-portas").closest("label").hidden = local;
  });
  $("btn-plano").onclick = salvarPlano; $("btn-consultar").onclick = consultarPlano;
  $("btn-iniciar-inv").onclick = iniciarInvestigacao; $("btn-enviar").onclick = enviarMensagem;
  $("chat-texto").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) enviarMensagem(); });
  $("btn-rel-gerar").onclick = relatorioGerar; $("btn-rel-salvar").onclick = relatorioSalvar;
  // filtros do chat
  const filtros = el("div", { class: "linha discreto" }, el("span", { texto: "Mostrar:" }),
    [["conversa", "conversa"], ["interpretacao", "interpretações"], ["proposta", "propostas"], ["saida", "saídas de ferramenta"], ["sistema", "sistema"]].map(([k, r]) =>
      el("label", { class: "check" }, el("input", { type: "checkbox", checked: true, "data-filtro": k, onchange: aplicarFiltrosChat }), r)));
  $("chat").before(filtros);
  const ciclo = async () => { await atualizarEstado(); await atualizarSessao(); const emVarredura = (S.estado && S.estado.ultima_varredura || {}).estado === "em_andamento";
    const f = S.sessao && S.sessao.sessao.fase; setTimeout(ciclo, emVarredura || ["modelo_pensando", "executando"].includes(f) ? 1500 : 4000); };
  ciclo();
}
document.addEventListener("DOMContentLoaded", ligar);
