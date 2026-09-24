# Copiloto Monotributo

A LangGraph copilot for Argentine monotributistas: it reads synthetic invoices,
validates them in code, and estimates category and exclusion risk.

> **Disclaimer.** This project is for informational and educational purposes only.
> It is not tax or legal advice and does not replace a licensed accountant. It never
> files anything with ARCA: it does not submit returns, recategorize, or perform any
> procedure on your behalf. All invoices, CUITs and taxpayers in this repository are
> synthetic.

Work in progress. Full documentation, graph diagram and quickstart land with the MVP.
See [docs/configuration.md](docs/configuration.md) for the extractor modes.

## Verified against

The design does not rely on remembered API shapes. These facts were checked
against the installed packages on 2026-09-24 and are pinned by
`tests/graph/test_langgraph_api.py`:

| Question | Answer |
| --- | --- |
| Versions | `langgraph` 1.2.12, `langchain-core` 1.6.4, Python 3.12.14 |
| `InMemorySaver` or `MemorySaver`? | Both are exported and `MemorySaver is InMemorySaver`. The project uses `InMemorySaver`. |
| How is a pause observed? | The `invoke` result carries an `__interrupt__` key; `result["__interrupt__"][0].value` is the payload. |
| Does resuming replay the node? | **Yes.** The node runs again from its first line, so anything before `interrupt()` happens twice. Review nodes therefore only build a pure payload before pausing. |
| Diagram | `graph.get_graph().draw_mermaid()` |

Python is pinned to 3.12 because `langchain-core` warns that Pydantic V1
internals are not compatible with Python 3.14 or greater.
