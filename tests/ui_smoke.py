"""Teste de fumaça da interface (opcional, não roda no pytest): navegador headless + backend simulado.

Uso:  pip install playwright && playwright install chromium && python tests/ui_smoke.py [pasta-de-capturas]
Sobe o agente com Ollama/ferramentas/alvo SIMULADOS (nenhuma rede, nenhum Docker) e percorre o fluxo principal
pela interface: varredura → modelo → habilitar ferramenta → sessão → plano → modelo revisa → investigação →
aprovação da ação → saída → evidência → relatório.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import uvicorn  # noqa: E402
from conftest import Plataforma, proposta  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

PORTA = 8765


def main() -> int:
    capturas = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-"))
    capturas.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="plat-"))
    plat = Plataforma(tmp)
    plat.app.mount("/", StaticFiles(directory=RAIZ / "web_ui", html=True), name="ui")
    srv = uvicorn.Server(uvicorn.Config(plat.app, host="127.0.0.1", port=PORTA, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)

    erros: list[str] = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page(viewport={"width": 1400, "height": 1000})
        pg.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
        pg.goto(f"http://127.0.0.1:{PORTA}/")
        pg.fill("#operador", "aluna")

        # 1) estado inicial vazio: sem ferramentas, modelo disponível só depois da varredura
        expect(pg.locator("#ferramentas-vazio")).to_be_visible()
        expect(pg.locator("#ferramentas-vazio")).to_contain_text("manifest.json")
        pg.screenshot(path=str(capturas / "01-inicio.png"))

        # 2) recursos adicionados "de fora" + varredura pelo botão
        plat.instalar_ferramenta("http-client")
        pg.click("#btn-varrer")
        expect(pg.locator("#varredura")).to_contain_text("http-client")
        expect(pg.locator("#lista-ferramentas")).to_contain_text("pendente habilitacao")
        pg.click('#tabela-modelos button:has-text("Selecionar")')
        expect(pg.locator("#tabela-modelos")).to_contain_text("ativo")
        pg.click('#lista-ferramentas button:has-text("Revisar")')
        expect(pg.locator("#dialogo")).to_contain_text("Manifesto")
        pg.click("#dialogo-ok")  # Habilitar
        expect(pg.locator("#lista-ferramentas")).to_contain_text("habilitada")
        pg.screenshot(path=str(capturas / "02-recursos.png"))

        # 3) nova sessão (LAN)
        pg.click("#btn-nova-sessao")
        pg.fill("#ns-url", "http://192.168.1.50:3000/")
        pg.check("#ns-confirma")
        pg.fill("#ns-nome", "Sessão de fumaça")
        pg.fill("#ns-objetivo", "Validar o fluxo pela interface")
        pg.click("#ns-validar")
        expect(pg.locator("#ns-resultado")).to_contain_text("IP efetivo")
        pg.click("#ns-criar")
        expect(pg.locator("#cabecalho-sessao")).to_contain_text("Sessão de fumaça")

        # 4) plano precede o modelo; modelo sugere revisões; grupo decide
        expect(pg.locator("#btn-consultar")).to_be_disabled()
        for k, v in {"aspectos": "Busca", "hipoteses": "Reflexão de entrada", "estrategia": "Observar antes de variar",
                     "ferramentas": "http-client", "evidencias_esperadas": "Resposta bruta"}.items():
            pg.fill(f"#plano-{k}", v)
        pg.click("#btn-plano")
        expect(pg.locator("#plano-info")).to_contain_text("Plano v1")
        plat.ollama.respostas.append(json.dumps({"tipo": "revisao_plano", "sugestoes": [{"texto": "Incluir o endpoint de login no plano", "item": "aspectos"}]}))
        pg.click("#btn-consultar")
        expect(pg.locator("#sugestoes")).to_contain_text("endpoint de login")
        pg.fill("#sugestoes textarea >> nth=0", "Fora do escopo desta sessão")
        pg.click('#sugestoes button:has-text("Rejeitar")')
        expect(pg.locator("#sugestoes")).to_contain_text("rejeitada")

        # 5) investigação → proposta → aprovação humana → execução
        plat.ollama.respostas.append(json.dumps(proposta()))
        pg.click("#form-investigacao summary")
        pg.fill("#inv-titulo", "Busca de produtos")
        pg.fill("#inv-hipotese", "Observar a API de busca")
        pg.click("#btn-iniciar-inv")
        expect(pg.locator("#painel-acao")).to_contain_text("aguardando a sua decisão")
        expect(pg.locator("#painel-acao")).to_contain_text("192.168.1.50")
        pg.screenshot(path=str(capturas / "03-acao-pendente.png"))
        assert plat.chamadas_executor == 0, "nada pode ser executado antes da decisão"
        plat.ollama.respostas.append(json.dumps({"tipo": "mensagem", "texto": "A resposta parece normal."}))
        pg.click('#painel-acao button:has-text("Autorizar")')
        expect(pg.locator("#acoes")).to_contain_text("executada")
        assert plat.chamadas_executor == 1

        # 6) saída, evidência, linha do tempo, chat, relatório
        pg.click('#acoes button:has-text("Saída")')
        expect(pg.locator("#saida-acao")).to_contain_text("sha256=")
        pg.click('#saida-botoes button >> nth=0')
        pg.fill("#dialogo-corpo textarea", "A resposta bruta mostra o formato da busca")
        pg.click("#dialogo-ok")
        expect(pg.locator("#acoes")).to_contain_text("EV-")
        expect(pg.locator("#linha-tempo")).to_contain_text("acao_proposta")
        expect(pg.locator("#chat")).to_contain_text("Interpretação do modelo")
        pg.click("#btn-rel-gerar")
        pg.wait_for_function("document.getElementById('relatorio').value.includes('PENDENTE')")
        pg.screenshot(path=str(capturas / "04-sessao.png"), full_page=True)

        # 7) exportação baixa arquivo
        with pg.expect_download() as d:
            pg.click('#cabecalho-sessao a:has-text("resultados")')
        assert d.value.suggested_filename.endswith("-resultados.zip")
        nav.close()

    srv.should_exit = True
    # avisos esperados: nenhum erro de página/console
    graves = [e for e in erros if "favicon" not in e]
    print("capturas em", capturas)
    if graves:
        print("ERROS NO NAVEGADOR:\n" + "\n".join(graves))
        return 1
    print("UI OK — fluxo completo percorrido sem erros de console")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
