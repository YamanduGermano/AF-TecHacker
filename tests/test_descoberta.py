import json
"""Descoberta/validação de recursos: varredura sem executar nada, estados, habilitação e modelos."""
import json
import os

from conftest import GGUF_FALSO, FAKES


def scan(plat):
    r = plat.c.post("/api/varreduras")
    assert r.status_code == 200, r.text
    return r.json()


def status(plat, tid):
    return next(f["status"] for f in plat.desc.ferramentas() if f["id"] == tid and f["origem"] == "ferramentas")


def test_plataforma_sobe_vazia_e_orienta(plat):
    e = plat.c.get("/api/estado").json()
    assert e["sem_modelos"] is True and e["sem_ferramentas"] is True
    assert e["ferramentas"] == [] and e["instrucoes"]["modelos"] and e["instrucoes"]["ferramentas"]
    plat.ollama.modelos.clear()
    v = scan(plat)
    assert v["estado"] == "concluida" and not v["erros"]
    # alvo pode ser configurado e sessão criada mesmo sem modelo/ferramentas
    sid = plat.sessao(plano=True, modelo=False)
    s = plat.estado(sid)
    assert s["sessao"]["modelo_id"] is None and len(s["faltas"]) == 2
    for caminho, cod in (("iniciar", "sem_modelo"),):
        r = plat.c.post(f"/api/sessoes/{sid}/{caminho}")
        assert r.status_code == 409 and r.json()["codigo"] == cod


def test_varredura_detecta_novos_alterados_removidos_sem_executar(plat):
    pasta = plat.instalar_ferramenta()
    # executável que denuncia execução: cria um arquivo ao lado de si
    (pasta / "executavel").write_text('#!/bin/sh\ntouch "$(dirname "$0")/EXECUTOU"\n')
    v1 = scan(plat)
    assert v1["novos"]["ferramentas"] == ["http-client"] and v1["novos"]["modelos"] == ["registrado:modelo-teste:1b"]
    assert not (pasta / "EXECUTOU").exists()
    assert status(plat, "http-client") == "pendente_habilitacao"
    v2 = scan(plat)
    assert v2["novos"]["ferramentas"] == [] and v2["alterados"]["ferramentas"] == []
    m = json.loads((pasta / "manifest.json").read_text())
    m["versao"] = "1.0.1"
    (pasta / "manifest.json").write_text(json.dumps(m))
    assert scan(plat)["alterados"]["ferramentas"] == ["http-client"]
    import shutil
    shutil.rmtree(pasta)
    v4 = scan(plat)
    assert v4["removidos"]["ferramentas"] == ["http-client"]
    assert plat.arm.catalogo("ferramenta") == []  # some das opções
    assert not (pasta / "EXECUTOU").exists()


def test_varredura_mostra_progresso_horario_e_status_final(plat):
    v = scan(plat)
    assert v["iniciada_em"] and v["concluida_em"] and v["progresso"] == 100 and v["estado"].startswith("concluida")
    assert [e["nome"] for e in v["etapas"]] == ["modelos", "ferramentas"] and all(e["estado"] == "concluida" for e in v["etapas"])
    assert plat.c.get(f"/api/varreduras/{v['id']}").json()["id"] == v["id"]


def test_sem_documentacao_alerta_mesmo_desabilitada_e_impede_habilitar(plat):
    plat.instalar_ferramenta(doc=False)
    v = scan(plat)
    assert any("SEM DOCUMENTAÇÃO" in a for a in v["avisos"])
    assert status(plat, "http-client") == "sem_documentacao"
    f = plat.desc.ferramenta("http-client")
    r = plat.c.post("/api/ferramentas/http-client/habilitar", json={"manifesto_sha256": f["manifesto_sha256"]})
    assert r.status_code == 422 and r.json()["codigo"] == "nao_habilitavel"
    (plat.dados / "documentacoes" / "http-client.md").write_text("# doc\nagora existe\n")
    assert status(plat, "http-client") == "pendente_habilitacao"


def test_manifestos_invalidos(plat):
    plat.instalar_ferramenta("com-shell", manifesto_extra={"shell": True})
    plat.instalar_ferramenta("perfil-estranho", perfil="scanner_magico")
    plat.instalar_ferramenta("metodo-livre", politica={"metodos": ["GET", "POST", "DELETE"]})
    plat.instalar_ferramenta("destino-fixo", manifesto_extra={"destino": "10.0.0.5"})
    plat.instalar_ferramenta("timeout-enorme", manifesto_extra={"limites": {"timeout_s": 300}})
    plat.instalar_ferramenta("id-errado", manifesto_extra={"id": "outro-id"})
    sem_exe = plat.instalar_ferramenta("sem-exe")
    os.remove(sem_exe / "executavel")
    nao_exec = plat.instalar_ferramenta("nao-exec")
    os.chmod(nao_exec / "executavel", 0o644)
    (plat.dados / "ferramentas" / "lixo").mkdir()
    for tid in ("com-shell", "perfil-estranho", "metodo-livre", "destino-fixo", "timeout-enorme", "id-errado", "sem-exe", "nao-exec", "lixo"):
        assert status(plat, tid) == "invalida", tid
    f = {x["id"]: x for x in plat.desc.ferramentas()}
    assert "shell livre" in " ".join(f["com-shell"]["erros"]) and "adaptador" in " ".join(f["perfil-estranho"]["erros"])
    assert "política global" in " ".join(f["metodo-livre"]["erros"]) and "permissão" in " ".join(f["nao-exec"]["erros"])
    r = plat.c.post("/api/ferramentas/com-shell/habilitar", json={"manifesto_sha256": f["com-shell"]["manifesto_sha256"]})
    assert r.status_code == 422


def test_shared_e_apenas_area_de_entrada(plat):
    sh = plat.dados / "__shared__" / "candidata"
    sh.mkdir()
    (sh / "manifest.json").write_text("{}")
    v = scan(plat)
    f = next(x for x in plat.desc.ferramentas() if x["origem"] == "__shared__")
    assert f["status"] == "detectada" and f["utilizavel"] is False
    assert plat.desc.ferramenta("candidata") is None
    r = plat.c.post("/api/ferramentas/candidata/habilitar", json={"manifesto_sha256": "0" * 64})
    assert r.status_code == 422 and r.json()["codigo"] == "ferramenta_inexistente"


def test_habilitar_exige_hash_revisado_e_alteracao_suspende(plat):
    pasta = plat.instalar_ferramenta()
    r = plat.c.post("/api/ferramentas/http-client/habilitar", json={"manifesto_sha256": "0" * 64})
    assert r.status_code == 422 and r.json()["codigo"] == "revisao_desatualizada"
    plat.habilitar()
    assert status(plat, "http-client") == "habilitada"
    ev = [e for e in plat.arm.eventos(None) if e["tipo"] == "ferramenta_habilitada"][0]["dados"]
    assert ev["operador"] == "aluno-teste" and ev["manifesto_sha256"]
    for alteracao in ("exe", "doc", "manifesto"):
        if alteracao == "exe":
            (pasta / "executavel").write_bytes((pasta / "executavel").read_bytes() + b"#x")
        elif alteracao == "doc":
            (plat.dados / "documentacoes" / "http-client.md").write_text("# outra doc\n")
        else:
            m = json.loads((pasta / "manifest.json").read_text()); m["versao"] = "9"; (pasta / "manifest.json").write_text(json.dumps(m))
        assert status(plat, "http-client") == "suspensa_alterada", alteracao
        plat.habilitar()  # nova revisão explícita
        assert status(plat, "http-client") == "habilitada"
    plat.c.post("/api/ferramentas/http-client/desabilitar")
    assert status(plat, "http-client") == "pendente_habilitacao"


# ---------------- modelos ---------------- #
def test_candidatos_gguf_so_viram_modelo_apos_importacao_explicita(plat):
    imp = plat.dados / "modelos" / "importar"
    (imp / "bom.gguf").write_bytes(GGUF_FALSO)
    (imp / "bom.Modelfile").write_text('FROM bom.gguf\nPARAMETER temperature 0.1\nSYSTEM """Você é útil."""\n')
    (imp / "ruim.gguf").write_bytes(b"NAOGGUF....")
    (imp / "ruim.Modelfile").write_text("FROM ruim.gguf\n")
    (imp / "semdef.gguf").write_bytes(GGUF_FALSO)
    (imp / "outro.safetensors").write_bytes(b"x")
    (imp / "apontaoutro.gguf").write_bytes(GGUF_FALSO)
    (imp / "apontaoutro.Modelfile").write_text("FROM /etc/passwd\n")
    scan(plat)
    est = {m["id"]: m for m in plat.c.get("/api/estado").json()["modelos"]}
    assert est["bom.gguf"]["estado"] == "pendente_importacao"
    assert est["ruim.gguf"]["estado"] == "invalido" and "GGUF" in est["ruim.gguf"]["erro"]
    assert est["semdef.gguf"]["estado"] == "invalido" and "definição" in est["semdef.gguf"]["erro"]
    assert est["outro.safetensors"]["estado"] == "invalido"
    assert est["apontaoutro.gguf"]["estado"] == "invalido" and "FROM" in est["apontaoutro.gguf"]["erro"]
    assert plat.desc.modelo_disponivel("bom.gguf") is None  # candidato não é selecionável
    assert plat.c.post("/api/modelos/selecionar", json={"modelo_id": "bom.gguf"}).status_code == 422
    assert plat.c.post("/api/modelos/importar", json={"arquivo": "ruim.gguf", "nome": "ruim:1"}).status_code == 422
    assert plat.c.post("/api/modelos/importar", json={"arquivo": "../x.gguf", "nome": "ruim:1"}).status_code == 422
    assert plat.ollama.criados == []
    r = plat.c.post("/api/modelos/importar", json={"arquivo": "bom.gguf", "nome": "bom:1b"})
    assert r.status_code == 200, r.text
    criado = plat.ollama.criados[0]
    assert criado["model"] == "bom:1b" and criado["files"]["bom.gguf"].startswith("sha256:") and criado["parameters"] == {"temperature": 0.1}
    assert criado["system"] == "Você é útil."
    assert plat.desc.modelo_disponivel("bom:1b")["estado"] == "disponivel"
    assert any(e["tipo"] == "modelo_importado" for e in plat.arm.eventos(None))


def test_ollama_fora_do_ar_nao_derruba_a_varredura(plat):
    plat.ollama.app.router.routes.clear()  # todas as rotas somem -> 404
    v = scan(plat)
    assert v["estado"] == "concluida_com_erros" and any("Ollama" in e for e in v["erros"])
    assert plat.c.get("/api/estado").json()["sem_modelos"] is True


def test_selecao_e_troca_de_modelo_sao_explicitas_e_registradas(plat):
    plat.ferramenta_pronta()
    plat.ollama.modelos.append({"name": "outro-modelo:3b", "digest": "c" * 64, "size": 1, "modified_at": "x"})
    scan(plat)
    sid = plat.sessao()
    assert plat.estado(sid)["sessao"]["modelo_id"] == "modelo-teste:1b"
    plat.ollama.respostas.append(json.dumps({"tipo": "revisao_plano", "sugestoes": [{"texto": "Inclua cabeçalhos de segurança"}]}))
    assert plat.c.post(f"/api/sessoes/{sid}/iniciar").status_code == 200
    # já há interação: trocar exige confirmação do reinício do contexto
    r = plat.c.post(f"/api/sessoes/{sid}/modelo", json={"modelo_id": "outro-modelo:3b"})
    assert r.status_code == 409 and r.json()["codigo"] == "confirmacao_necessaria"
    assert plat.estado(sid)["sessao"]["modelo_id"] == "modelo-teste:1b"
    r = plat.c.post(f"/api/sessoes/{sid}/modelo", json={"modelo_id": "outro-modelo:3b", "reiniciar_contexto": True})
    assert r.status_code == 200 and r.json()["sessao"]["modelo_id"] == "outro-modelo:3b"
    ev = [e for e in plat.arm.eventos(sid) if e["tipo"] == "modelo_trocado"][0]["dados"]
    assert ev["contexto_reiniciado"] is True and ev["de"]["id"] == "modelo-teste:1b" and ev["para"]["digest"] == "c" * 64
    # o novo modelo não vê o contexto antigo
    plat.ollama.respostas.append(json.dumps({"tipo": "mensagem", "texto": "ok"}))
    plat.c.post(f"/api/sessoes/{sid}/mensagens", json={"texto": "Olá"})
    msgs = plat.ollama.requisicoes[-1]["messages"]
    assert plat.ollama.requisicoes[-1]["model"] == "outro-modelo:3b"
    assert not any("revisao_plano" in m["content"] and m["role"] == "assistant" for m in msgs)


def test_modelo_substituido_no_ollama_nao_migra_silenciosamente(plat):
    plat.ferramenta_pronta()
    sid = plat.sessao()
    plat.ollama.modelos[0]["digest"] = "d" * 64  # mesmo nome, outro conteúdo
    r = plat.c.post(f"/api/sessoes/{sid}/iniciar")
    assert r.status_code == 409 and r.json()["codigo"] == "modelo_alterado"
    assert plat.ollama.requisicoes == []
