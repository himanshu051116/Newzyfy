# Zero-Cost Local AI Strategy

The first acquisition and event-identity phases require no generative AI.

When model-backed features begin, the application will use a provider interface with:

- `disabled` as the safe default;
- local open-source embeddings and rerankers;
- a local model server such as Ollama or llama.cpp only when installed;
- no automatic paid API fallback;
- no simulated responses when a model is unavailable;
- explicit `service unavailable` or `insufficient evidence` outcomes.

Candidate local components will be benchmarked before adoption:

- multilingual sentence-transformer embeddings;
- a local cross-encoder reranker;
- compact instruction models for structured claim/entity proposals;
- deterministic verification and confidence code outside the model.

Hardware feasibility, latency, retrieval quality, extraction accuracy, and licensing will be evaluated with the platform's labeled test sets. Model selection is deferred until that evidence exists.

