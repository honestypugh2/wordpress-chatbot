# Scripts

Developer helper scripts:

- [index_kb_to_search.py](index_kb_to_search.py) — chunk, embed, and upload the synthetic
  county knowledge base into an Azure AI Search index (`county-kb`). Used by retrieval
  patterns 2 (Azure AI Search) and 3 (Hybrid). Re-running is idempotent.
- [set_demo_site.py](set_demo_site.py) — switch the active demo site profile
  (`westvale` | `staging`) and its recommended `RETRIEVAL_PATTERN`. Pass `--write .env`
  to persist the values.

Quality gates run directly with `uv`:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```
