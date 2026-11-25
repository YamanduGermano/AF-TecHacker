"""Registros, exportação independente, redação de credenciais e rascunho do relatório."""
import io
import json
import os
import zipfile

from conftest import proposta


def ciclo(plat, sid):
    plat.investigar(sid, proposta())
    a = plat.estado(sid)["acao_pendente"]
    plat.ollama.respostas.append(json.dumps({"tipo": "mensagem", "texto": "A resposta parece conter a página inicial."}))
    assert plat.c.post(f"/api/acoes/{a['id']}/decisao", json={"decisao": "autorizar"}).status_code == 200
    return a["id"]


def ler_zip(resp):
    assert resp.status_code == 200, resp.text
    return zipfile.ZipFile(io.BytesIO(resp.content))


def test_estrutura_de_arquivos_da_sessao_e_eventos_encadeados(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    aid = ciclo(plat, sid)
    base = plat.arm.dir_sessao(sid)
    assert {p.name for p in base.iterdir()} >= {"plano-inicial.md", "eventos.jsonl", "chat.jsonl", "evidencias", "resultados-ferramentas"}
    linhas = [json.loads(l) for l in (base / "eventos.jsonl").read_text().splitlines()]
    assert linhas[0]["anterior_id"] is None and all(linhas[i]["anterior_id"] == linhas[i - 1]["id"] for i in range(1, len(linhas)))
    for e in linhas:
        assert e["sessao_id"] == sid and e["ts"] and e["objetivo"] and e["tipo"]
    assert {r.name for r in (base / "resultados-ferramentas").iterdir()} == {f"{aid}.stdout", f"{aid}.stderr"}
    ex = [e for e in linhas if e["tipo"] == "acao_executada"][0]["dados"]
    assert ex["chamada_efetiva"][-1].startswith("http://192.168.1.50:3000/") and ex["codigo_saida"] == 0 and len(ex["stdout_sha256"]) == 64
    assert ex["hashes"]["modelo_digest"] and {"acao_proposta", "acao_decidida", "consulta_modelo", "plano_salvo", "sessao_criada"} <= {e["tipo"] for e in linhas}
    # consultas ao modelo guardam prompt e resposta para a análise crítica
    cons = [json.loads(l) for l in (base / "consultas-modelo.jsonl").read_text().splitlines()]
    assert cons[0]["modelo_id"] == "modelo-teste:1b" and cons[0]["mensagens"][0]["role"] == "system" and cons[0]["resposta"]


def test_exportacoes_independentes_e_credenciais_ocultas(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    aid = ciclo(plat, sid)
    plat.c.post(f"/api/sessoes/{sid}/evidencias", json={"acao_id": aid, "nota": "página inicial servida"})
    chat = plat.c.get(f"/api/sessoes/{sid}/exportar/chat")
    assert chat.status_code == 200 and "attachment" in chat.headers["content-disposition"] and "token=segredo123" not in chat.text
    ev = plat.c.get(f"/api/sessoes/{sid}/exportar/eventos")
    assert "segredo123" not in ev.text and "acao_executada" in ev.text
    for texto in (chat.text, ev.text):  # a ocultação não pode quebrar o JSON das linhas exportadas
        assert all(isinstance(json.loads(l), dict) for l in texto.splitlines())
    res = ler_zip(plat.c.get(f"/api/sessoes/{sid}/exportar/resultados"))
    nomes = res.namelist()
    assert f"resultados-ferramentas/{aid}.stdout" in nomes and "MANIFESTO-HASHES.json" in nomes
    stdout = res.read(f"resultados-ferramentas/{aid}.stdout").decode()
    assert "segredo123" not in stdout and "[REDIGIDO]" in stdout and "OWASP Juice Shop" in stdout
    man = {a["arquivo"]: a for a in json.loads(res.read("MANIFESTO-HASHES.json"))["arquivos"]}
    m = man[f"resultados-ferramentas/{aid}.stdout"]
    import hashlib
    assert m["sha256"] == hashlib.sha256(stdout.encode()).hexdigest() and m["credenciais_ocultadas"] is True
    original = plat.arm.resultados(sid)[0]
    assert m["sha256_original"] == original["sha256"]  # a verificação contra o bruto íntegro continua possível
    arq = ler_zip(plat.c.get(f"/api/sessoes/{sid}/exportar/arquivos"))
    assert {"plano-inicial.md", "eventos.jsonl", "chat.jsonl", "evidencias/EV-001.json"} <= set(arq.namelist())
    assert not any(n.startswith("resultados-ferramentas/") for n in arq.namelist())  # exportação independente
    assert plat.c.get(f"/api/sessoes/{sid}/exportar/relatorio").status_code == 200
    assert plat.c.get(f"/api/sessoes/{sid}/exportar/inexistente").status_code == 404
    # o registro interno preserva o bruto
    assert "token=segredo123" in plat.arm.ler_resultado(original["id"])[1].decode()


def test_exportacao_so_inclui_arquivos_da_propria_sessao_e_ignora_links_simbolicos(plat, tmp_path):
    plat.ferramenta_pronta()
    s1 = plat.sessao()
    ciclo(plat, s1)
    s2 = plat.sessao()
    segredo = tmp_path / "segredo.txt"
    segredo.write_text("conteúdo fora da sessão")
    base1 = plat.arm.dir_sessao(s1)
    os.symlink(segredo, base1 / "resultados-ferramentas" / "link.txt")
    os.symlink(plat.arm.dir_sessao(s2), base1 / "evidencias" / "outra-sessao")
    z = ler_zip(plat.c.get(f"/api/sessoes/{s1}/exportar/completo"))
    assert not any("link.txt" in n or "outra-sessao" in n or s2 in n for n in z.namelist())
    assert b"conteudo fora" not in b"".join(z.read(n) for n in z.namelist())
    assert plat.c.get("/api/sessoes/../../etc/passwd/exportar/chat").status_code in (404, 422)


def test_exportacao_funciona_com_investigacao_sem_conclusao(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    plat.investigar(sid, proposta())  # termina sem ação executada nem conclusão
    for item in ("chat", "eventos", "arquivos", "resultados", "relatorio", "completo"):
        assert plat.c.get(f"/api/sessoes/{sid}/exportar/{item}").status_code == 200, item


def test_resultado_bruto_e_imutavel(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    aid = ciclo(plat, sid)
    import pytest
    with pytest.raises(FileExistsError):
        plat.arm.salvar_resultado(sid, aid, "stdout", b"sobrescrita")
    with pytest.raises(ValueError):
        plat.arm.salvar_resultado(sid, aid, "../escape", b"x")


# ---------------- relatório ---------------- #
def test_relatorio_vazio_marca_pendencias_sem_inventar(plat):
    sid = plat.sessao(plano=False, modelo=False)
    r = plat.c.get(f"/api/sessoes/{sid}/relatorio").json()
    assert r["existe"] is False
    t = r["conteudo"]
    assert t.count("[PENDENTE]") >= 10 and "Investigação 1" in t and "Investigação 3" in t
    assert "ainda não realizada" in t and "nenhuma execução registrada" in t and "não constitui evidência" in t
    assert "vulnerab" not in t.lower().replace("vulnerabilidade sem", "")


def test_relatorio_cita_registros_e_so_inclui_conclusao_com_evidencia(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    aid = ciclo(plat, sid)
    plat.c.post(f"/api/sessoes/{sid}/investigacoes/1/encerrar", json={"conclusao": "A busca devolve a página inicial", "limites": "uma única requisição"})
    t = plat.c.get(f"/api/sessoes/{sid}/relatorio").json()["conteudo"]
    assert "modelo-teste:1b" in t and aid in t and "autorizada sem alterações" in t and "http-client" in t
    assert "A busca devolve a página inicial" not in t and "nenhuma evidência registrada" in t  # conclusão retida sem evidência
    assert "Catálogo de produtos e busca" in t  # plano humano v1
    plat.c.post(f"/api/sessoes/{sid}/evidencias", json={"acao_id": aid, "nota": "HTTP 200 com o título do aplicativo"})
    t2 = plat.c.get(f"/api/sessoes/{sid}/relatorio").json()["conteudo"]
    assert "A busca devolve a página inicial" in t2 and "EV-001" in t2 and "segredo123" not in t2


def test_relatorio_gerado_nao_sobrescreve_edicao_do_grupo(plat):
    sid = plat.sessao(plano=False, modelo=False)
    assert plat.c.post(f"/api/sessoes/{sid}/relatorio/gerar").status_code == 200
    assert plat.c.put(f"/api/sessoes/{sid}/relatorio", json={"conteudo": "# Versão editada pelo grupo"}).status_code == 200
    r = plat.c.post(f"/api/sessoes/{sid}/relatorio/gerar")
    assert r.status_code == 409 and r.json()["codigo"] == "relatorio_existente"
    assert plat.c.get(f"/api/sessoes/{sid}/relatorio").json()["conteudo"] == "# Versão editada pelo grupo"
    assert plat.c.post(f"/api/sessoes/{sid}/relatorio/gerar?sobrescrever=true").status_code == 200
    assert any(p.name.startswith("relatorio.bak-") for p in plat.arm.dir_sessao(sid).iterdir())
