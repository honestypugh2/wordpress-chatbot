# Examples / Seed Payloads

Sample requests and seed data for exercising the assistant.

- `sample_chat_request.json` — example body the WordPress widget POSTs to APIM → backend.
- See [../data/county_kb.seed.json](../data/county_kb.seed.json) for the synthetic county
  knowledge base used for grounding.

The chat endpoint is implemented at `POST /api/chat` ([src/app/api/routes/chat.py](../src/app/api/routes/chat.py));
these payloads document the request contract.
