import io
import zipfile
from .storage import encode, digest


def filled(value):
    if isinstance(value, list):
        return "\n".join("- " + str(v) for v in value) or "**PENDENTE**"
    return str(value).strip() if value and str(value).strip() else "**PENDENTE**"


def report(s):
    lines = ["# Rascunho — Tecnologias Hackers", "", "> Rascunho editável. Revisão acadêmica pendente; não é um relatório final de 4–6 páginas.",
             "", "## Identificação", f"Sessão: {s['title']} ({s['id']})", f"Alvo autorizado: {s['target']}",
             f"Modelo: {s['model']}", f"Criada em: {s['created_at']}", "", "## Plano inicial do grupo"]
    labels = {"objective": "Objetivo", "hypotheses": "Hipóteses", "strategy": "Estratégia", "tools": "Ferramentas previstas", "evidence": "Evidências necessárias"}
    for k, label in labels.items():
        lines.extend([f"### {label}", filled(s["initial_plan"].get(k)), ""])
    for idx, inv in enumerate(s["investigations"]):
        lines.extend([f"## Investigação {idx + 1} — {inv['title']}", "### Hipótese", filled(inv["hypothesis"]),
                      "### Estratégia", filled(inv["strategy"]), "### Sugestões e sínteses da IA"])
        syntheses = inv["syntheses"]
        lines.append(filled([x["synthesis"] for x in syntheses]))
        lines.append("### Execução e intervenção humana")
        proposals = [p for p in s["proposals"] if p["investigation"] == idx]
        if not proposals:
            lines.append("**PENDENTE** — Nenhum comando registrado.")
        for p in proposals:
            lines.extend([f"- Proposta {p['id']}: `{p['command']}`", f"  Estado: {p['status']}; motivo: {p['rationale']}",
                          f"  Possíveis efeitos: {p['effects']}", f"  Decisão humana: {filled(p.get('decision'))}"])
            for edit in p["edits"]:
                lines.append(f"  Edição humana: {edit['command']} — {edit['reason']}")
            if p.get("result"):
                r = p["result"]
                lines.append(f"  Saída: código {r['exit_code']}; motivo {r['reason']}; duração {r['duration']} s. Evidências: {', '.join(r.get('artifacts', []))}")
        lines.extend(["### Conclusão do grupo", filled(inv["conclusion"]), "### Evidências", filled(inv["evidence"]), ""])
    lines.extend(["## Comparação: plano humano e contribuições da IA", filled(s["report_notes"].get("comparison")), "### Revisões propostas"])
    lines.append(filled([f"{r['field']}: {r['value']} | {r['status']} | Texto final: {r.get('effective_value', 'PENDENTE')} | Justificativa humana: {r.get('decision', 'PENDENTE')}" for r in s["revisions"]]))
    lines.extend(["## Limitações concretas", filled(s["report_notes"].get("limitations")), "## Restaurações do Juice Shop"])
    lines.append(filled([f"{r['at']} — investigação {r['investigation'] + 1}, modo {r['mode']}: {r['procedure']} | Confirmação: {r['confirmation']}" for r in s["restorations"]]))
    lines.extend(["## Índice de arquivos", ""])
    lines.append(filled([f"{a['id']} | {a['name']} | origem: {a['origin']} | SHA-256: {a['sha256']}" for a in s["artifacts"]]))
    return "\n\n".join(lines) + "\n"


def export(store, s, kind):
    if kind == "report":
        return report(s).encode(), "text/markdown; charset=utf-8", "relatorio.md"
    if kind == "chat":
        return encode(s["chat"]), "application/json", "chat.json"
    if kind == "logs":
        return encode({"events": s["events"], "proposals": s["proposals"]}), "application/json", "logs.json"
    if kind != "files":
        raise ValueError("Exportação desconhecida.")
    files = {"sessao.json": encode(s), "relatorio.md": report(s).encode(), "chat.json": encode(s["chat"]),
             "logs.json": encode({"events": s["events"], "proposals": s["proposals"]})}
    for artifact in s["artifacts"]:
        # Do not nest older ZIP exports recursively inside later exports.
        if artifact["origin"] == "exportação files":
            continue
        path = store.directory(s["id"]) / "arquivos" / artifact["name"]
        if not path.is_file() or path.is_symlink():
            raise ValueError("Arquivo de evidência ausente: " + artifact["name"])
        data = path.read_bytes()
        if digest(data) != artifact["sha256"]:
            raise ValueError("Hash divergente: " + artifact["name"])
        files["arquivos/" + artifact["name"]] = data
    files["manifesto.json"] = encode([{"id": digest(data)[:32], "name": name, "sha256": digest(data), "bytes": len(data), "origin": "exportação da sessão " + s["id"]} for name, data in files.items()])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue(), "application/zip", "sessao-" + s["id"][:8] + ".zip"
