"""Política de escopo: URL do alvo, parâmetros do modelo, limites."""
import pytest

from proxy.params import PolicyError, validar_http, validar_scan
from proxy.policy import ConfigPolitica, LimitadorTaxa, normalizar_url_alvo, revalidar_resolucao, validar_parametros
from proxy.schemas import Limites, Manifesto, PoliticaEscopo

CFG = ConfigPolitica()
SEM_RESOLVER = lambda h: (_ for _ in ()).throw(AssertionError("não deveria resolver"))  # noqa: E731


def alvo(url="http://192.168.1.50:3000/", **kw):
    return normalizar_url_alvo(url, modo=kw.pop("modo", "lan"), resolver=kw.pop("resolver", SEM_RESOLVER), cfg=CFG, **kw)


def codigo(fn, *a, **k):
    with pytest.raises(PolicyError) as e:
        fn(*a, **k)
    return e.value.codigo


def manifesto(perfil="http_client_curl", **pol):
    return Manifesto(id="ferramenta-x", versao="1", executavel="exe", perfil=perfil, descricao_modelo="ferramenta de teste unitário",
                     politica_escopo=PoliticaEscopo(**pol))


def http(params, politica=None, **kw):
    return validar_http(params, politica or PoliticaEscopo(), Limites(), metodos_globais=kw.get("metodos", {"GET", "HEAD"}),
                        cabecalhos_globais=set(CFG.cabecalhos_permitidos), permitir_corpo_global=kw.get("corpo", False))


# ---------------- URL do alvo ---------------- #
def test_url_normalizada_e_ip_fixado():
    e = alvo("http://192.168.1.50:3000/")
    assert (e.url_base, e.ip_efetivo, e.porta, e.portas_autorizadas) == ("http://192.168.1.50:3000/", "192.168.1.50", 3000, [3000])


def test_hostname_resolve_e_fixa_todos_os_ips():
    e = alvo("http://lab.local:3000/app", resolver=lambda h: ["10.1.2.3"])
    assert e.ips_autorizados == ["10.1.2.3"] and e.caminho_base == "/app" and e.url_base.endswith(":3000/app/")


@pytest.mark.parametrize("url,esperado", [
    ("http://127.0.0.1:3000", "alvo_loopback"), ("http://[::1]:3000", "alvo_loopback"),
    ("http://8.8.8.8:3000", "alvo_publico"), ("http://169.254.169.254/", "alvo_link_local"),
    ("ftp://10.0.0.1/", "esquema_invalido"), ("http://u:p@10.0.0.1/", "url_invalida"),
    ("http://10.0.0.1/?a=b", "url_invalida"), ("http://10.0.0.1/ x", "url_invalida"), ("http://ollama:11434", "host_reservado"),
    ("http://juice-shop:3000", "host_reservado"), ("", "url_invalida"), ("http://0.0.0.0:80", "alvo_ip_nao_permitido"),
])
def test_urls_rejeitadas(url, esperado):
    assert codigo(alvo, url, resolver=lambda h: ["10.0.0.9"]) == esperado


def test_modo_local_so_aceita_juice_shop():
    assert codigo(alvo, "http://10.0.0.1:3000", modo="local") == "modo_local_host"
    e = alvo("http://juice-shop:3000/", modo="local", resolver=lambda h: ["172.30.77.2"])
    assert e.ip_efetivo == "172.30.77.2"


def test_dns_que_resolve_para_ip_publico_ou_loopback_e_recusado():
    assert codigo(alvo, "http://x.exemplo:3000", resolver=lambda h: ["8.8.8.8"]) == "alvo_publico"
    assert codigo(alvo, "http://x.exemplo:3000", resolver=lambda h: ["10.0.0.5", "127.0.0.1"]) == "alvo_loopback"


def test_dns_rebinding_detectado():
    e = alvo("http://lab.local:3000/", resolver=lambda h: ["10.1.2.3"])
    revalidar_resolucao(e, lambda h: ["10.1.2.3"])
    assert codigo(revalidar_resolucao, e, lambda h: ["10.9.9.9"]) == "dns_alterado"
    assert codigo(revalidar_resolucao, e, lambda h: ["10.1.2.3", "10.9.9.9"]) == "dns_alterado"


def test_portas_extra():
    assert alvo(portas_extra=[22, 8080]).portas_autorizadas == [22, 3000, 8080]
    assert codigo(alvo, portas_extra=[70000]) == "porta_invalida"


# ---------------- parâmetros HTTP ---------------- #
def test_http_valido_e_normalizado():
    n = http({"metodo": "get", "caminho": "/rest/products/search?q=apple", "cabecalhos": {"accept": "application/json"}})
    assert n["metodo"] == "GET" and n["caminho"].startswith("/rest") and n["timeout_s"] == 20


@pytest.mark.parametrize("chave", ["host", "url", "porta", "proxy", "flags", "comando", "shell", "ip", "args", "script", "arquivo"])
def test_chaves_proibidas(chave):
    assert codigo(http, {"caminho": "/", chave: "x"}) == "parametro_proibido"


def test_chave_desconhecida_tambem_e_rejeitada():
    assert codigo(http, {"caminho": "/", "xyz": 1}) == "parametro_desconhecido"


@pytest.mark.parametrize("caminho,esperado", [
    ("http://evil.com/", "caminho_invalido"), ("//evil.com/x", "caminho_invalido"), ("rest/x", "caminho_invalido"),
    ("/a b", "caminho_invalido"), ("/a\r\nHost: evil", "caminho_invalido"), ("/\\evil", "caminho_invalido"), ("/á", "caminho_invalido"),
])
def test_caminhos_invalidos(caminho, esperado):
    assert codigo(http, {"caminho": caminho}) == esperado


def test_metodos_so_get_head_por_padrao():
    assert codigo(http, {"caminho": "/", "metodo": "POST"}) == "metodo_nao_permitido"
    assert codigo(http, {"caminho": "/", "metodo": "TRACE"}) == "metodo_invalido"
    # política do manifesto permite, mas a global não: continua bloqueado
    assert codigo(http, {"caminho": "/", "metodo": "POST"}, PoliticaEscopo(metodos=["GET", "POST"])) == "metodo_nao_permitido"
    # com as duas políticas explícitas, passa
    assert http({"caminho": "/", "metodo": "POST"}, PoliticaEscopo(metodos=["GET", "POST"]), metodos={"GET", "HEAD", "POST"})["metodo"] == "POST"


def test_corpo_exige_politica_global_e_do_manifesto():
    p = {"caminho": "/", "metodo": "POST", "corpo": "{}"}
    pol = PoliticaEscopo(metodos=["POST"], permitir_corpo=True)
    assert codigo(http, p, pol, metodos={"POST"}) == "corpo_nao_permitido"
    assert http(p, pol, metodos={"POST"}, corpo=True)["corpo"] == "{}"
    assert codigo(http, {"caminho": "/", "metodo": "GET", "corpo": "x"}) == "corpo_nao_permitido"


@pytest.mark.parametrize("cab,esperado", [
    ({"Host": "evil"}, "cabecalho_proibido"), ({"X-Forwarded-For": "1.1.1.1"}, "cabecalho_proibido"),
    ({"X-Custom": "1"}, "cabecalho_nao_permitido"), ({"Accept": "a\r\nX: y"}, "cabecalho_invalido"),
    ({"Bad Name": "1"}, "cabecalho_invalido"),
])
def test_cabecalhos(cab, esperado):
    assert codigo(http, {"caminho": "/", "cabecalhos": cab}) == esperado


def test_limites_do_manifesto_prevalecem():
    n = http({"caminho": "/", "timeout_s": 9999, "max_corpo_bytes": 10**9})
    assert n["timeout_s"] == 20 and n["max_corpo_bytes"] == 65536


# ---------------- varredura ---------------- #
def scan(params, **pol):
    return validar_scan(params, PoliticaEscopo(**pol), Limites(), portas_autorizadas=[3000], perfis_adaptador={"conectar_tcp", "versao_servico"})


def test_scan_somente_portas_autorizadas_e_perfil_predefinido():
    assert scan({"perfil": "conectar_tcp", "portas": [3000, 3000]})["portas"] == [3000]
    assert codigo(scan, {"perfil": "conectar_tcp", "portas": [22]}) == "porta_nao_autorizada"
    assert codigo(scan, {"perfil": "versao_servico", "portas": [3000]}) == "perfil_scan_invalido"  # manifesto só liberou conectar_tcp
    assert codigo(scan, {"perfil": "conectar_tcp", "portas": [3000], "host": "10.0.0.2"}) == "parametro_proibido"
    assert codigo(scan, {"perfil": "conectar_tcp", "portas": ["3000"]}) == "parametros_invalidos"
    assert codigo(scan, {"perfil": "conectar_tcp", "portas": [True]}) == "parametros_invalidos"


def test_validar_parametros_usa_alvo_da_sessao_nao_do_modelo():
    e = alvo()
    a = validar_parametros(manifesto(), {"metodo": "GET", "caminho": "/ftp"}, e, CFG)
    assert a.alvo.ip == "192.168.1.50" and a.alvo.porta == 3000 and a.resumo_legivel == "GET http://192.168.1.50:3000/ftp"
    assert codigo(validar_parametros, manifesto(perfil="desconhecido"), {}, e, CFG) == "perfil_desconhecido"


# ---------------- taxa e concorrência ---------------- #
def test_limitador_taxa_e_concorrencia():
    l = LimitadorTaxa(2)
    l.reservar("s", 0.0)
    assert codigo(l.reservar, "s", 1.0) == "concorrencia"
    l.liberar("s")
    l.reservar("s", 2.0)
    l.liberar("s")
    assert codigo(l.reservar, "s", 3.0) == "taxa_excedida"
    l.reservar("s", 70.0)  # janela de 60 s liberou
