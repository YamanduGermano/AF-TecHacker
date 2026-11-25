"""Rascunho editável do relatório técnico.

Preenche **apenas** o que existe nos registros. O que falta aparece como ``[PENDENTE]``; nada é inventado.
Conclusões de investigação só aparecem quando há evidência registrada que as sustente; afirmações do modelo
são sempre rotuladas como não sendo evidência.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .storage import Armazenamento, agora, redigir_texto

PEND = "**[PENDENTE]**"


def _linha(*c: Any) -> str:
    return "| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in c) + " |"


def gerar_rascunho(arm: Armazenamento, sessao_id: str) -> str:
    s = arm.sessao(sessao_id)
    assert s, "sessão inexistente"
    esc = s["escopo"]
    planos = arm.planos(sessao_id)
    sugestoes = arm.sugestoes(sessao_id)
    invs = arm.investigacoes(sessao_id)
    acoes = arm.acoes(sessao_id)
    evid = arm.evidencias(sessao_id)
    eventos = arm.eventos(sessao_id)
    consultas = arm.consultas(sessao_id)
    resultados = {r["id"]: r for r in arm.resultados(sessao_id)}

    L: list[str] = [
        f"# Relatório técnico — {s['nome']} (RASCUNHO EDITÁVEL)", "",
        f"> Gerado em {agora()} a partir dos registros da sessão `{s['id']}`. Campos {PEND} não têm registro correspondente "
        "e não foram preenchidos. **Uma afirmação do modelo não constitui evidência**; conclusões abaixo dependem de evidências "
        "registradas (IDs `EV-xxx`). Adapte este material ao relatório acadêmico de 4 a 6 páginas.", "",
        "## 1. Arquitetura e configuração efetivamente usada", "",
        f"- Modo do alvo: `{s['modo']}` — URL base: `{esc['url_base']}` — IP fixado: `{esc['ip_efetivo']}` — porta: `{esc['porta']}` "
        f"— portas autorizadas: `{esc['portas_autorizadas']}`",
        f"- Modelo da sessão: `{s['modelo_id'] or '—'}` (digest/versão `{(s['modelo_digest'] or '—')[:16]}`)",
    ]
    digests = sorted({(c["modelo_id"], (c["modelo_digest"] or "")[:16]) for c in consultas})
    L.append(f"- Modelos efetivamente consultados: {', '.join(f'`{m}` `{d}`' for m, d in digests) or PEND + ' (nenhuma consulta registrada)'}")
    usadas = {}
    for a in acoes:
        if a.get("hashes") and a["estado"] in ("executada", "erro_execucao"):
            usadas[a["ferramenta_id"]] = a["hashes"]
    if usadas:
        L.append("- Ferramentas efetivamente executadas (hashes SHA-256 registrados no momento da proposta):")
        for tid, h in usadas.items():
            L.append(f"  - `{tid}`: manifesto `{str(h['manifesto_sha256'])[:16]}…`, executável `{str(h['executavel_sha256'])[:16]}…`, "
                     f"documentação `{str(h.get('doc_sha256'))[:16]}…`")
    else:
        L.append(f"- Ferramentas efetivamente executadas: {PEND} (nenhuma execução registrada)")
    redef = [e for e in eventos if e["tipo"] == "escopo_redefinido"]
    resets = [e for e in eventos if e["tipo"] == "reset_alvo"]
    L.append(f"- Redefinições de escopo registradas: {len(redef)}")
    L.append(f"- Restaurações do alvo registradas: {len(resets)}"
             + ("" if resets else f" {PEND} (registre a restauração antes de cada investigação)"))
    egr = [e for e in eventos if e["tipo"] == "egress_verificado"]
    if egr:
        L.append(f"- Verificações de saída de rede (egress): {len(egr)} — última: "
                 f"{'sem destinos bloqueados alcançados' if egr[-1]['dados'].get('ok') else 'ATENÇÃO: destino bloqueado foi alcançado'} "
                 "(teste parcial; não prova ausência de outros caminhos)")
    L += ["", "## 2. Plano humano inicial e revisões do modelo", ""]
    if planos:
        p1 = planos[0]
        L += [f"Plano v1 salvo em {p1['criado_em']} (antes da primeira consulta ao modelo):", ""]
        for k, t in (("aspectos", "Aspectos"), ("hipoteses", "Hipóteses"), ("estrategia", "Estratégia"),
                     ("ferramentas", "Ferramentas"), ("evidencias_esperadas", "Evidências esperadas")):
            L.append(f"- **{t}:** {p1['conteudo'].get(k, '')}")
        if len(planos) > 1:
            L.append(f"- Versões posteriores do plano: {len(planos) - 1} (ver `plano-vN.md` na exportação).")
    else:
        L.append(f"{PEND} nenhum plano registrado.")
    L.append("")
    if sugestoes:
        L += ["Sugestões do modelo sobre o plano (cada uma decidida pelo grupo):", "", _linha("Sugestão do modelo", "Decisão", "Justificativa técnica"),
              _linha("---", "---", "---")]
        for g in sugestoes:
            L.append(_linha(g["texto"], g["estado"], g["justificativa"] or "—"))
    else:
        L.append(f"Sugestões do modelo sobre o plano: {PEND} nenhuma registrada.")

    L += ["", "## 3. Investigações", ""]
    por_inv: dict[str, list[dict]] = {}
    for a in acoes:
        por_inv.setdefault(a["investigacao_id"] or "-", []).append(a)
    for n in (1, 2, 3):
        inv = next((i for i in invs if i["numero"] == n), None)
        L.append(f"### Investigação {n}" + (f" — {inv['titulo']}" if inv else ""))
        if inv is None:
            L += ["", f"{PEND} Investigação {n} ainda não realizada.", ""]
            continue
        a_inv = por_inv.get(inv["id"], [])
        ev_inv = [e for e in evid if e["investigacao_id"] == inv["id"]]
        L += ["", f"- **Hipótese:** {inv['hipotese'] or PEND}", f"- **Estratégia:** {inv['estrategia'] or PEND}",
              f"- **Estado:** {inv['estado']} — passos registrados: {len(a_inv)}", ""]
        L += ["**Contribuições do agente (propostas — afirmações do modelo, não evidência):**", ""]
        L += [f"- `{a['id']}` `{a['ferramenta_id']}`: {a['proposta'].get('justificativa', '')}" for a in a_inv] or [f"- {PEND} sem propostas"]
        L += ["", "**Execução:**", "", _linha("Ação", "Estado", "Decisão", "Chamada", "Saída", "Resultado (SHA-256 stdout)"), _linha("---", "---", "---", "---", "---", "---")]
        for a in a_inv:
            ex = a.get("execucao") or {}
            L.append(_linha(a["id"], a["estado"], a.get("decisao") or "—",
                            (a.get("acao") or {}).get("resumo_legivel", "—"), ex.get("codigo_saida", "—"),
                            str(ex.get("stdout_sha256", "—"))[:16]))
        L += ["", "**Intervenção humana:**", ""]
        interv = []
        for a in a_inv:
            if a["estado"] == "rejeitada":
                interv.append(f"- `{a['id']}` REJEITADA: {a['justificativa']}")
            elif a.get("decisao") == "modificada":
                interv.append(f"- `{a['id']}` MODIFICADA ({a['justificativa']}): original `{a['parametros_originais']}` → efetivo `{a['parametros_efetivos']}`")
            elif a["estado"] == "bloqueada":
                interv.append(f"- `{a['id']}` BLOQUEADA pela política: {((a.get('validacao') or {}).get('erro') or {}).get('mensagem', '')}")
            elif a.get("decisao") == "autorizada":
                interv.append(f"- `{a['id']}` autorizada sem alterações")
        L += interv or [f"- {PEND} sem decisões registradas"]
        L += ["", "**Evidências desta investigação:** " + (", ".join(f"`{e['id']}`" for e in ev_inv) or f"{PEND} nenhuma"), ""]
        if inv.get("conclusao") and ev_inv:
            L += [f"**Conclusão (do grupo, sustentada pelas evidências acima):** {inv['conclusao']}", ""]
        elif inv.get("conclusao"):
            L += [f"**Conclusão:** {PEND} há uma conclusão escrita, mas **nenhuma evidência registrada** a sustenta; "
                  "ela não foi incluída. Registre as evidências ou revise a conclusão.", ""]
        else:
            L += [f"**Conclusão:** {PEND}", ""]
        L += [f"**Limites e ressalvas:** {inv.get('limites_texto') or PEND}", ""]

    L += ["## 4. Evidências", ""]
    if evid:
        L += [_linha("ID", "Ação", "Resultado bruto", "SHA-256", "O que demonstra (nota do grupo)"), _linha("---", "---", "---", "---", "---")]
        for e in evid:
            r = resultados.get(e["resultado_id"] or "", {})
            L.append(_linha(e["id"], e["acao_id"] or "—", r.get("arquivo", "—"), str(r.get("sha256", "—"))[:16], e["nota"]))
    else:
        L.append(f"{PEND} nenhuma evidência registrada.")

    c = Counter(a["estado"] for a in acoes)
    decisoes = Counter(a.get("decisao") for a in acoes if a.get("decisao"))
    invalidas = [e for e in eventos if e["tipo"] == "resposta_invalida"]
    L += ["", "## 5. Análise crítica da IA", "",
          f"{PEND} A análise (quando a IA ajudou, quando errou, quanto dependeu da correção humana) deve ser escrita pelo grupo.", "",
          "Dados registrados para apoiar a análise:", "",
          f"- Propostas do modelo: {len(acoes)} (estados: {dict(c)})", f"- Decisões do grupo: {dict(decisoes)}",
          f"- Respostas fora do protocolo JSON: {len(invalidas)}", f"- Consultas ao modelo: {len(consultas)}", "",
          "## 6. Erro ou limitação concreta da IA", "", f"{PEND} Descreva um erro/limitação concreto. Candidatos encontrados nos registros:", ""]
    cand = []
    for e in invalidas:
        cand.append(f"- `{e['id']}` resposta inválida do modelo: {e['dados'].get('erro')}")
    for a in acoes:
        if a["estado"] == "rejeitada":
            cand.append(f"- `{a['id']}` proposta rejeitada pelo grupo: {a['justificativa']}")
        if a["estado"] == "bloqueada":
            cand.append(f"- `{a['id']}` proposta bloqueada pela política: {((a.get('validacao') or {}).get('erro') or {}).get('mensagem', '')}")
        if a.get("decisao") == "modificada":
            cand.append(f"- `{a['id']}` proposta que precisou de edição humana: {a['justificativa']}")
    for g in sugestoes:
        if g["estado"] == "rejeitada":
            cand.append(f"- sugestão de plano rejeitada: «{g['texto']}» — {g['justificativa']}")
    L += cand or ["- (nenhum candidato registrado)"]
    L += ["", "## Anexos", "", "Logs completos para verificação: use a exportação **Arquivos da sessão** e **Resultados brutos** "
          "(ZIP com `MANIFESTO-HASHES.json`).", ""]
    return redigir_texto("\n".join(L))


def salvar_rascunho(arm: Armazenamento, sessao_id: str, sobrescrever: bool = False) -> tuple[str, bool]:
    texto = gerar_rascunho(arm, sessao_id)
    caminho = arm.dir_sessao(sessao_id) / "relatorio.md"
    if caminho.exists() and not sobrescrever:
        return texto, False
    if caminho.exists():
        caminho.replace(caminho.with_name(f"relatorio.bak-{agora().replace(':', '').replace('.', '')}.md"))
    caminho.write_text(texto, encoding="utf-8")
    return texto, True
