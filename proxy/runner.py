"""Pedido controlado ao executor (API interna restrita, autenticada por token)."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from .schemas import (
    AlvoEfetivo,
    DestinoEgress,
    RequisicaoExecutor,
    RespostaExecutor,
    SondagemRequisicao,
    VerificacaoEgressRequisicao,
)


class ErroExecutor(Exception):
    pass


class ClienteExecutor:
    """Cliente síncrono do executor.

    ``client`` pode ser injetado (testes usam ``fastapi.testclient.TestClient``).
    """

    def __init__(self, base_url: str, token: str, client: Optional[httpx.Client] = None, timeout_s: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client or httpx.Client(timeout=timeout_s)

    def _req(self, metodo: str, caminho: str, json: Optional[dict] = None, timeout: Optional[float] = None) -> Any:
        try:
            kw: dict[str, Any] = {"headers": {"X-Executor-Token": self.token}}
            if json is not None:
                kw["json"] = json
            if timeout is not None:
                kw["timeout"] = timeout
            r = self._client.request(metodo, f"{self.base_url}{caminho}", **kw)
        except httpx.HTTPError as e:
            raise ErroExecutor(f"executor inacessível: {e}") from e
        if r.status_code != 200:
            raise ErroExecutor(f"executor respondeu {r.status_code}: {r.text[:500]}")
        return r.json()

    def executar(self, req: RequisicaoExecutor) -> RespostaExecutor:
        # O executor aplica o timeout da ferramenta (<= 300 s); aqui só damos folga à chamada HTTP.
        dados = self._req("POST", "/executar", req.model_dump(mode="json"), timeout=330.0)
        return RespostaExecutor(**dados)

    def resolver(self, host: str) -> list[str]:
        return list(self._req("POST", "/resolver", {"host": host}, timeout=15.0)["ips"])

    def sondar(self, alvo: AlvoEfetivo) -> dict[str, Any]:
        req = SondagemRequisicao(esquema=alvo.esquema, host=alvo.host, ip=alvo.ip, porta=alvo.porta)
        return self._req("POST", "/sondar", req.model_dump(mode="json"), timeout=20.0)

    def verificar_egress(self, destinos: list[DestinoEgress]) -> dict[str, Any]:
        req = VerificacaoEgressRequisicao(destinos=destinos)
        return self._req("POST", "/verificar-egress", req.model_dump(mode="json"), timeout=60.0)

    def saude(self) -> bool:
        try:
            self._req("GET", "/saude", timeout=5.0)
            return True
        except ErroExecutor:
            return False
