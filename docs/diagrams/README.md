# Architecture & Workflow Diagrams

Editable [draw.io](https://www.drawio.com/) sources plus committed SVG renders for the
County Assistant prototype. The SVGs are embedded directly in the docs; the `.drawio`
files are the editable source — open them with the **Draw.io Integration** VS Code
extension (`hediet.vscode-drawio`) or at [app.diagrams.net](https://app.diagrams.net),
edit, then re-export the matching `.svg`.

| Diagram | Source | Render | Used in |
| --- | --- | --- | --- |
| Baseline architecture | [baseline-architecture.drawio](baseline-architecture.drawio) | [baseline-architecture.svg](baseline-architecture.svg) | [reference-architecture.md](../reference-architecture.md) |
| Advanced / full architecture | [advanced-architecture.drawio](advanced-architecture.drawio) | [advanced-architecture.svg](advanced-architecture.svg) | [reference-architecture.md](../reference-architecture.md) |
| Chat request sequence | [chat-sequence.drawio](chat-sequence.drawio) | [chat-sequence.svg](chat-sequence.svg) | [reference-architecture.md](../reference-architecture.md) |
| Orchestrator agent flow | [orchestrator-flow.drawio](orchestrator-flow.drawio) | [orchestrator-flow.svg](orchestrator-flow.svg) | [retrieval-patterns.md](../retrieval-patterns.md) |

## Palette (shared with the Mermaid diagrams)

| Layer | Fill | Stroke |
| --- | --- | --- |
| AWS — experience layer | `#FF9900` | `#7A4900` |
| Azure — gateway / app | `#0078D4` | `#004578` |
| Azure AI Foundry | `#50E6FF` | `#004578` |
| Grounding / data | `#7FBA00` | `#3A5400` |
| Government overlays / security | `#E3008C` | `#6E0044` |

All diagrams are **illustrative**; service choices and network topology are decided per
deployment. All depicted content is synthetic.
