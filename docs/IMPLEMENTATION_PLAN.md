# News Intelligence Platform — Implementation Plan

Status: Proposed  
Companion: [System architecture](ARCHITECTURE.md)
Mandatory constraints: [Critical implementation guardrails](IMPLEMENTATION_GUARDRAILS.md)
Event architecture: [Event-centric intelligence architecture](EVENT_INTELLIGENCE_ARCHITECTURE.md)
Acquisition architecture: [Recall-optimized acquisition architecture](ACQUISITION_ARCHITECTURE.md)

## Delivery approach

Build a thin vertical slice first: collect a permitted source, extract an article, store it, index it, cluster it, and display it with provenance. Expand breadth only after that path is measurable and replayable.

Each phase ends with acceptance criteria. Phase estimates assume a small experienced team and are directional, not commitments.

## Phase 0 — Product, source, and quality foundations

Estimated duration: 1–2 weeks

### Deliverables

- Confirm target users: individual researcher, newsroom, enterprise intelligence team, or mixed.
- Define launch geographies, languages, and retention requirements.
- Create a source onboarding checklist covering API/feed availability, rate limits, robots, terms, storage, display, and attribution.
- Approve an initial set of 10–20 sources with clear access paths.
- Define the v1 taxonomy and category descriptions.
- Create labeled seed datasets for extraction, duplicates, event pairs, categories, and search.
- Create labeled datasets for claim extraction, evidence stance, source lineage, timelines, verification labels, and confidence calibration.
- Define the deterministic verification-label policy and retrieval-coverage thresholds.
- Define the governed source/evidence reliability registry and review process.
- Define a production-code check that prevents fixture/mock providers from loading outside test/demo environments.
- Define publisher-level freshness and recall SLOs, including estimation uncertainty and minimum channel coverage.
- Create labeled datasets for event assignment, source attribution, propagation, geography, contradiction, and contextual-gap evaluation.
- Select model providers and document fallback/cost policies.
- Define SLOs, monthly cost ceiling, and data retention.
- Write architecture decision records for broker, workflow scheduler, embedding model, and authentication provider.

### Acceptance criteria

- Every launch source has an owner and recorded collection policy.
- Evaluation datasets and baseline metrics exist before model tuning.
- The six-label claim contract and insufficient-evidence state are machine-readable and versioned.
- No confidence percentage is approved before calibration results exist.
- Release gates from the implementation guardrails are wired into CI.
- Legal/content-rights risks have an explicit launch decision.
- MVP scope and non-goals are approved.
- Priority publishers have documented channel inventories and recall-audit baselines.

## Phase 1 — Recall-optimized acquisition and searchable event MVP

Estimated duration: 2–4 weeks

### Build

- Repository scaffolding, configuration, CI, typed settings, and structured logging.
- Docker Compose development environment.
- PostgreSQL schema and migrations for publishers, acquisition profiles, channels, frontier, discoveries, source records, articles, versions, provisional events, chunks, jobs, and outbox.
- Multi-channel source registry with RSS/Atom, sitemap indexes, Google News sitemaps, homepage/section monitors, Hacker News API, and arXiv API.
- WebSub discovery, subscriptions, lease renewal, signature validation, delivery deduplication, and fallback polling.
- Publisher-specific strategy and publication-pattern models.
- Distributed frontier with reproducible priority calculations, leases, per-host budgets, backpressure, retries, and dead letters.
- Adaptive scheduler with coverage floors and per-host rate limits.
- Safe HTTP fetcher with SSRF protections and conditional requests.
- DOM/link-set fingerprints and incremental change detection for monitored listing pages.
- Raw artifact storage in S3/MinIO.
- Generic extraction plus two or three source-specific adapters.
- Field-level metadata fusion across feed/API, JSON-LD, schema.org, OpenGraph, HTML metadata, and DOM rules.
- Extraction quality score and quarantine state.
- URL canonicalization, variant identity, exact content deduplication, and immutable article versions.
- Per-article discovery-channel provenance and first-discovery timing.
- Initial publisher recall estimator, cross-channel coverage matrix, and delayed archive audit.
- Provisional event creation/assignment for every processed source record.
- Qdrant article/chunk indexing.
- FastAPI event/article list/detail and basic semantic search.
- Minimal Next.js dashboard centered on events, with article/source evidence views.
- Acquisition dashboards for recall, latency, channel health, frontier, retries, and dead letters.
- Durable audit records for retrieval, embedding/indexing, and processing decisions.

### Acceptance criteria

- At least 10 approved publishers ingest automatically for seven days through multiple channels.
- Every monitored publisher has at least two active channels when two permitted viable channels exist.
- Priority-source items are discovered within 2 minutes of appearing in an official feed/API/push endpoint at p95.
- Replaying a message does not create duplicate records.
- Exact duplicate precision exceeds 99% on the seed set.
- Extraction succeeds above the agreed threshold on launch-source fixtures.
- Search supports date, source, language, and category filters.
- Every result exposes original URL, publisher, and publication time.
- Every processed article/source record has a current or provisional event assignment.
- Every article identity retains all channel discoveries and URL variants.
- Recall reports expose observed lower bounds, estimates, uncertainty, estimator version, and blind spots.
- Unchanged listing/article pages skip full reprocessing after validated conditional/hash/DOM checks.
- No publisher, section, locale, or exploration channel is starved by priority scoring.
- Production configuration cannot load mock collectors, fabricated content, or hard-coded intelligence outputs.

## Phase 2 — Enrichment, near deduplication, and event intelligence

Estimated duration: 3–5 weeks

### Build

- Versioned category taxonomy and multi-label classification cascade.
- Named-entity extraction/linking.
- Target-aware tone/sentiment.
- SimHash and MinHash candidate generation.
- Semantic near-duplicate confirmation and duplicate groups.
- Online event assignment with Qdrant candidate retrieval.
- Nightly event merge/split reconciliation.
- Event lifecycle, source diversity, velocity, and importance scores.
- First-class source records for government announcements, regulatory filings, court documents, scientific papers/datasets, company releases, earnings/financial filings, legislative proceedings, and official statements.
- Event assignment candidate/history records, aliases, reversible merge/split/reassignment, and append-only event snapshots.
- Distinct occurrence, source publication, observation, retrieval, event detection, earliest public evidence, and material-change timestamps.
- News latency and information-propagation calculations.
- Attribution/source network covering original reporting, syndication, citation, quotation, derivative reporting, and independent confirmation.
- Article and event summary generation with structured outputs.
- Historical-context retrieval over prior indexed articles and related events.
- Versioned background timelines with dated citations.
- Check-worthy claim extraction and evidence discovery.
- Retrieval connectors and indexes for applicable historical reporting, official/government records, scientific papers, press releases, regulatory filings, and independent reporting.
- Persistent retrieval runs/results with similarity, reranking, selection, and exclusion records.
- Evidence records containing exact passages/fields, source URLs/types, retrieval timestamps, hashes, rights, and source offsets.
- Source-lineage detection that collapses Reuters → Yahoo/MSN/local republications into one independent confirmation.
- Deterministic six-label verification policy; models cannot set labels.
- Deterministic confidence feature calculation and persisted intermediate values; models cannot set confidence.
- Explicit insufficient-evidence workflow that publishes no verdict or assessment.
- Canonical article-intelligence response schema with fixed, separately rendered sections.
- Separately labeled analytical assessments covering implications, risks, alternatives, missing information, confidence-changing evidence, and time horizon.
- Source-independence score based on ownership, syndication, citation chains, and evidence lineage.
- Event-level contradiction sets with normalized competing positions and evidence on each side.
- Contextual-gap and open-question detection with event-type completeness templates.
- Geographic entity resolution, event-location roles, PostGIS storage, and spatial APIs.
- Multidimensional, domain/time-bounded source reliability profiles with uncertainty and anti-feedback safeguards.
- Canonical knowledge nodes/edges and W3C PROV-inspired evidence lineage in PostgreSQL.
- Open-questions and method/provenance sections.
- Confidence calibration workflow that suppresses percentages until adequately calibrated.
- Stored decision traces containing retrieval inputs, evidence selection/exclusions, lineage resolution, weights, rules triggered, and formula/policy versions.
- Stored rendered prompts, structured model responses, validators, and trace IDs under access and retention controls.
- Citation manifest and generated-artifact versioning.
- Event list/detail APIs and dashboard pages.
- Background, claim-check, and analyst-assessment UI sections.
- Admin merge/split and reprocessing controls.

### Acceptance criteria

- Near-duplicate and event clustering meet agreed precision/recall on labeled pairs.
- Event over-merge, fragmentation, assignment, and reconciliation metrics pass release thresholds.
- Merge/split/reassignment preserves all prior event URLs, memberships, snapshots, and provenance.
- Every event statement resolves through a valid evidence-lineage path.
- Primary-source records are distinguishable from reporting and traceable from claims where available.
- Latency metrics use distinct clock semantics and expose timestamp uncertainty.
- Independent reports remain visible even when syndicated copies collapse.
- Event summaries cite diverse, non-duplicate sources.
- Background timelines cite earlier material developments and never use post-publication material as prior context.
- Repeated syndications are not counted as independent verification.
- Reuters-derived republications on Yahoo, MSN, and a local publisher produce one evidence-lineage vote in integration fixtures.
- Claim checks expose evidence for and against, last-checked time, and uncertainty.
- Only Supported, Disputed, Misleading, Unsupported, Contradicted, and Not Checkable can be published.
- Inadequate retrieval coverage returns exactly `Insufficient evidence available.` and publishes no claim verdict.
- The interface never labels a whole article true or false from automated checks.
- Facts, unresolved claims, and analyst assessment are visually and structurally separate.
- The interface renders Article Summary, Key Claims, Historical Timeline, Evidence Review, Source Independence Score, Analyst Assessment, Open Questions, and Method and Provenance in that order.
- Every factual statement and analytical conclusion has an evidence-manifest reference.
- Speculation is explicitly labeled and includes its assumptions.
- Percentage confidence is displayed only after calibration; otherwise confidence is categorical.
- Users can inspect the factors behind verdict, confidence, and source-independence scores without exposing private model reasoning.
- Re-running a verification from the same versioned inputs reproduces its label and confidence calculations.
- Every timeline event maps to a stored evidence record, source URL, retrieval timestamp, and valid date.
- Every event snapshot reproduces from versioned inputs and supports factual/claim/evidence diffs.
- Contradictions preserve both positions and do not collapse scope differences into false conflicts.
- Geographic resolutions retain alternatives and confidence.
- Source reliability remains domain/time specific and exposes sample size and uncertainty.
- Analyst Assessment has no write path to claims, labels, confidence calculations, evidence stances, or lineages.
- Every generated artifact records prompt, model, evidence, and version.
- Model failure does not block article searchability.

## Phase 3 — Hybrid search and research assistant

Estimated duration: 3–4 weeks

### Build

- Dense and sparse Qdrant vectors.
- Reciprocal rank fusion and metadata filters.
- Cross-encoder or model reranking.
- Duplicate collapse and publisher diversification.
- Query intent, date-range, entity, and taxonomy parsing.
- Event-first and chunk-level retrieval.
- Evidence-constrained knowledge-graph neighborhood and multi-hop exploration.
- Evidence-pack builder with token and per-source budgets.
- Grounded answer generation with inline citations.
- Citation/claim validation and insufficient-evidence behavior.
- Research answers can use verified historical context and claim evidence.
- Streaming answer API using SSE.
- Research workspace UI with filters, answer history, and evidence panel.
- Search and RAG evaluation harness.

### Acceptance criteria

- Hybrid search improves NDCG/MRR over dense-only and keyword-only baselines.
- Answers contain no uncited material claims in the reference evaluation set.
- Missing retrieval coverage returns `Insufficient evidence available.` instead of a model-memory answer.
- Restricted content cannot enter an unauthorized answer.
- Research queries expose interpreted time range and filters.
- Users can open the exact supporting article from every citation.
- Graph answers and paths contain evidence on every displayed relationship.

## Phase 4 — Trends, reports, and personalization

Estimated duration: 3–5 weeks

### Build

- Windowed topic, entity, and event aggregates.
- Community and social-signal adapters through official/permitted APIs, isolated from verified reporting.
- Manipulation-resistant signal metrics and cross-domain attention tracking.
- Event-level emerging-story scoring from volume growth, velocity, independent-lineage growth, source diversity, discussion acceleration, novelty, geography, and primary evidence.
- Burst, novelty, velocity, and source-diversity trend scoring.
- Trending topics and emerging stories pages.
- Geographic maps, regional feeds, and spatial trend exploration.
- Daily, weekly, and monthly report templates.
- Report generation, revision, publication, and export.
- Topic/entity/publisher follows and saved searches.
- Reading-event collection with privacy controls.
- User interest profiles.
- Deterministic briefing selection and AI narrative composition.
- Recommendation diversity and exploration controls.
- Email/push integration only after in-app briefing quality is proven.

### Acceptance criteria

- A trend requires multiple independent sources.
- Community attention can trigger an emerging alert but cannot verify a claim.
- Emerging scores expose every component, penalty, version, and supporting event/source record.
- Trend explanations show the events and metrics that caused the rank.
- Reports have section-level citations.
- Briefings respect follows, blocks, language, and timezone.
- Users can view/reset personalization inputs.

## Phase 5 — Production hardening and scale

Estimated duration: 4–6 weeks

### Build

- Kafka-compatible production event bus and consumer groups.
- Transactional outbox relay and replay tooling.
- Kubernetes/Terraform production infrastructure.
- Separate autoscaled worker pools.
- Managed PostgreSQL HA, pooling, PITR, and restore drills.
- Qdrant replication, snapshots, payload indexes, and reindex tooling.
- Object lifecycle and backup policies.
- OIDC, RBAC, audit logs, WAF, and secrets manager.
- Source and model-provider circuit breakers.
- OpenTelemetry traces, dashboards, paging alerts, and runbooks.
- Load, soak, chaos, and disaster-recovery tests.
- Sustained throughput testing above 10,000 articles/day with at least 10× average-arrival bursts.
- Independent autoscaling and backpressure tests for collection, extraction, retrieval, model, verification, and reporting workers.
- Cost budgets and per-model usage controls.
- Publisher takedown/deletion workflow across all stores.

### Acceptance criteria

- SLOs hold under at least 2× expected peak load and the defined burst profile.
- PostgreSQL and Qdrant restore procedures are timed and verified.
- Broker and model-provider outages degrade gracefully without data loss.
- Security review and dependency/image scans pass.
- Source removal deletes/restricts artifacts, vectors, caches, and excerpts.
- On-call dashboards and runbooks cover every critical dependency.

## Phase 6 — Advanced intelligence

Ongoing, after production quality is stable

Potential work:

- multilingual embeddings and cross-lingual event clustering;
- deeper claim extraction and cross-source contradiction analysis;
- entity timelines and knowledge graph;
- event causality and follow-up linking;
- geospatial intelligence;
- custom enterprise taxonomies and tenant isolation;
- analyst annotations and collaborative workspaces;
- domain-specific classifiers trained from feedback;
- local/self-hosted models for cost or data residency;
- forecasting experiments clearly labeled as probabilistic;
- source-bias and coverage-gap analysis.

## Suggested first implementation milestone

The first milestone should demonstrate this full path:

```text
RSS/API discovery
→ safe fetch
→ clean extraction
→ PostgreSQL article/version
→ exact dedupe
→ article embedding in Qdrant
→ semantic search
→ article page with provenance
```

Do not begin with report generation or a conversational UI. Those features depend on reliable evidence, identity, extraction, and retrieval.

## Cross-cutting workstreams

### Testing

- Unit tests for domain rules and URL normalization.
- Contract fixtures for every source adapter.
- Golden-file extraction tests.
- Integration tests with PostgreSQL, Qdrant, object storage, and broker.
- Replay/idempotency tests.
- Search and AI evaluation suites.
- Duplicate, syndication, and evidence-lineage tests.
- Timeline date/citation/cutoff validation tests.
- Claim extraction and evidence-mapping evaluation tests.
- Citation completeness and exact-offset tests.
- Verification-label consistency and confidence-reproducibility tests.
- Retrieval-coverage and insufficient-evidence refusal tests.
- Analyst Assessment isolation tests.
- Load, queue-backpressure, and horizontal-scaling tests.
- Browser tests for core user journeys.

### Data and model operations

- Version every model, prompt, taxonomy, and threshold.
- Shadow new models before promotion.
- Cache deterministic results by content hash.
- Maintain a replay queue for selective backfills.
- Track quality, latency, and cost together.
- Store retrieval results, similarity/reranking scores, evidence selections, lineage decisions, calculation features, prompts, structured responses, and validators.
- Prevent model outputs from directly updating labels or confidence columns at repository and database permission boundaries.

### Documentation

- Architecture decision records.
- Source onboarding records.
- OpenAPI and event-contract documentation.
- Data dictionary.
- Operational runbooks.
- Model cards and evaluation reports.

## Initial backlog order

1. Repository and local infrastructure.
2. Core database schema and outbox.
3. Source registry and RSS adapter.
4. Safe fetcher and object storage.
5. Extraction and quality scoring.
6. Article APIs and feed UI.
7. Qdrant indexing and semantic search.
8. Exact/near deduplication.
9. Taxonomy and entity enrichment.
10. Event clustering and event UI.
11. Evidence-grounded summaries.
12. Hybrid search and research assistant.
13. Trends, reports, and personalization.
14. Production infrastructure and hardening.

## Release-blocking definition of done

A feature is not complete until:

- its real data pipeline runs end to end without production mocks;
- inputs, evidence, intermediate calculations, outputs, and revisions are persisted;
- insufficient-evidence and dependency-failure states are implemented;
- unit, integration, evaluation, and applicable load tests pass;
- citations and source offsets validate;
- metrics, traces, and audit records are emitted;
- deterministic operations reproduce from the same versioned inputs;
- production configuration contains no hard-coded analytical result or fabricated fallback.

## Decisions to make before code generation

- Initial approved source list and which sources allow full-text retention.
- Initial language and geography scope.
- Cloud and deployment target.
- Hosted versus self-managed PostgreSQL/Qdrant/broker.
- Model providers for embeddings, reranking, and generation.
- Authentication model: public consumer, organization accounts, or both.
- Raw/full-text retention duration.
- Monthly infrastructure and model budget.
- Whether the MVP needs email delivery or only an in-app briefing.
