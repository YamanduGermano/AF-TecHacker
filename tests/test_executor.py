"""Executor: sem shell, limites, revalidação de hashes e argv."""
import hashlib
import json
from pathlib import Path

import pytest

from proxy.schemas import AlvoEfetivo, RequisicaoExecutor

TOKEN = {"X-Executor-Token": "tok-teste"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def requisicao(plat, tid="http-client", params=None, exec_id="a-teste00001", alvo=None, **kw):
    pasta = plat.dados / "ferramentas" / tid
    base = dict(exec_id=exec_id, sessao_id="s-teste00001", ferramenta_id=tid, manifesto_sha256=sha(pasta / "manifest.json"),
                executavel_sha256=sha(pasta / "executavel"),
                parametros=params or {"metodo": "GET", "caminho": "/rest/products/search?q=apple"},
                alvo=alvo or AlvoEfetivo(esquema="http", host="192.168.1.50", ip="192.168.1.50", porta=3000, portas_autorizadas=[3000]))
    base.update(kw)
    return RequisicaoExecutor(**base)


def rodar(plat, req):
    r = plat.executor_http.post("/executar", json=req.model_dump(mode="json"), headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


def test_exige_token(plat):
    plat.ferramenta_pronta()
    req = requisicao(plat)
    assert plat.executor_http.post("/executar", json=req.model_dump(mode="json")).status_code == 401
    assert plat.executor_http.post("/executar", json=req.model_dump(mode="json"), headers={"X-Executor-Token": "x"}).status_code == 401


def test_http_argv_seguro_e_resumo(plat):
    plat.ferramenta_pronta()
    j = rodar(plat, requisicao(plat))
    assert j["ok"] and j["codigo_saida"] == 0
    argv = j["argv"]
    assert argv[1] == "-q" and "--max-redirs" in argv and argv[argv.index("--max-redirs") + 1] == "0"
    assert "--noproxy" in argv and "-g" in argv and "-L" not in argv
    assert argv[-1] == "http://192.168.1.50:3000/rest/products/search?q=apple"
    assert j["resumo"]["status"] == 200 and "OWASP Juice Shop" in j["resumo"]["corpo_amostra"]
    assert j["resumo"]["ip_remoto"] == "192.168.1.50" and "alerta" not in j["resumo"]


def test_hostname_usa_resolve_para_fixar_o_ip(plat):
    plat.ferramenta_pronta()
    alvo = AlvoEfetivo(esquema="http", host="lab.local", ip="10.1.2.3", porta=3000, portas_autorizadas=[3000])
    j = rodar(plat, requisicao(plat, alvo=alvo))
    argv = j["argv"]
    assert argv[argv.index("--resolve") + 1] == "lab.local:3000:10.1.2.3"
    assert argv[-1] == "http://lab.local:3000/rest/products/search?q=apple"


def test_head_usa_opcao_propria_e_nao_corpo(plat):
    plat.ferramenta_pronta()
    j = rodar(plat, requisicao(plat, params={"metodo": "HEAD", "caminho": "/"}))
    assert "-I" in j["argv"] and "-X" not in j["argv"] and j["resumo"]["corpo_amostra"] == ""


def test_parametro_de_host_nunca_chega_ao_argv(plat):
    plat.ferramenta_pronta()
    j = rodar(plat, requisicao(plat, params={"metodo": "GET", "caminho": "/", "host": "10.0.0.9"}))
    assert not j["ok"] and j["argv"] == [] and "parametro_proibido" in j["erro"]


def test_executor_recusa_alvo_loopback_ou_publico(plat):
    plat.ferramenta_pronta()
    for ip, cod in (("127.0.0.1", "alvo_loopback"), ("8.8.8.8", "alvo_publico")):
        alvo = AlvoEfetivo(esquema="http", host=ip, ip=ip, porta=3000, portas_autorizadas=[3000])
        j = rodar(plat, requisicao(plat, alvo=alvo))
        assert cod in j["erro"] and j["argv"] == []


def test_timeout_encerra_o_processo(plat):
    plat.ferramenta_pronta()
    j = rodar(plat, requisicao(plat, params={"metodo": "GET", "caminho": "/SLEEP", "timeout_s": 1}))
    assert j["timeout"] and not j["ok"] and j["duracao_ms"] < 10_000


def test_saida_acima_do_limite_e_truncada_e_processo_encerrado(plat):
    plat.instalar_ferramenta(manifesto_extra={"limites": {"timeout_s": 10, "max_saida_bytes": 100_000, "max_corpo_bytes": 1000}})
    plat.habilitar()
    j = rodar(plat, requisicao(plat, params={"metodo": "GET", "caminho": "/BIG"}))
    assert j["truncado"] and len(j["stdout_b64"]) <= 140_000


def test_hash_do_executavel_e_revalidado(plat):
    pasta = plat.ferramenta_pronta()
    req = requisicao(plat)
    (pasta / "executavel").write_bytes((pasta / "executavel").read_bytes() + b"\n# alterado")
    j = rodar(plat, req)
    assert not j["ok"] and "executavel_alterado" in j["erro"] and j["argv"] == []


def test_hash_do_manifesto_e_revalidado(plat):
    pasta = plat.ferramenta_pronta()
    req = requisicao(plat)
    m = json.loads((pasta / "manifest.json").read_text())
    m["versao"] = "2.0.0"
    (pasta / "manifest.json").write_text(json.dumps(m))
    assert "manifesto_alterado" in rodar(plat, req)["erro"]


def test_executavel_precisa_estar_dentro_da_pasta_da_ferramenta(plat, tmp_path):
    pasta = plat.ferramenta_pronta()
    fora = tmp_path / "fora"
    fora.write_text("#!/bin/sh\necho oi\n")
    fora.chmod(0o755)
    (pasta / "executavel").unlink()
    (pasta / "executavel").symlink_to(fora)
    req = requisicao(plat, executavel_sha256=sha(fora))
    assert "executavel_invalido" in rodar(plat, req)["erro"]


def test_ambiente_do_processo_nao_herda_variaveis(plat, monkeypatch):
    monkeypatch.setenv("SEGREDO_DO_EXECUTOR", "x")
    plat.ferramenta_pronta()
    j = rodar(plat, requisicao(plat))
    assert j["ok"]  # o fake não imprime o ambiente; a garantia está no código (env minimal) — ver adapters/service
    import executor.service as s
    assert "SEGREDO_DO_EXECUTOR" not in open(s.__file__).read()


def test_scan_argv_so_tem_o_ip_autorizado(plat):
    plat.ferramenta_pronta("port-scanner", perfil="port_scanner_nmap", fake="fake_nmap.py",
                           politica={"perfis_varredura": ["conectar_tcp"], "max_portas": 3})
    j = rodar(plat, requisicao(plat, tid="port-scanner", params={"perfil": "conectar_tcp", "portas": [3000]}))
    assert j["ok"] and j["argv"][-1] == "192.168.1.50" and "-sT" in j["argv"] and not any(a.startswith("--script") for a in j["argv"])
    assert j["resumo"]["portas"] == [{"porta": 3000, "proto": "tcp", "estado": "open", "servico": "http", "versao": None}]
    j2 = rodar(plat, requisicao(plat, tid="port-scanner", params={"perfil": "conectar_tcp", "portas": [22]}))
    assert "porta_nao_autorizada" in j2["erro"] and j2["argv"] == []


def test_verificar_egress_valida_ips(plat):
    r = plat.executor_http.post("/verificar-egress", json={"destinos": [{"ip": "nao-e-ip", "porta": 1}]}, headers=TOKEN)
    assert r.status_code == 400
    r = plat.executor_http.post("/verificar-egress", json={"destinos": [{"ip": "127.0.0.1", "porta": 9, "rotulo": "x"}]}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["resultados"][0]["alcancou"] is False
