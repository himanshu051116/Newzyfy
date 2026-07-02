# News Intelligence Platform — Critical Implementation Guardrails

Status: Mandatory  
Applies to: Backend, workers, AI workflows, APIs, UI, tests, and operations

These are release-blocking requirements. A feature is not complete merely because an endpoint, interface, prompt, or demonstration exists.

The event-first rules in [Event-Centric Intelligence Architecture](EVENT_INTELLIGENCE_ARCHITECTURE.md) are also mandatory. Every displayed event statement must resolve through a valid evidence-lineage path.

The acquisition rules in [Recall-Optimized News Acquisition Architecture](ACQUISITION_ARCHITECTURE.md) are mandatory. Recall claims require cross-channel evidence and uncertainty; automatic source discovery cannot bypass policy or access controls.

## 1. No-placeholder rule

Production paths must not contain:

- fabricated articles, evidence, citations, timelines, verdicts, or confidence scores;
- hard-coded analytical outputs;
- random or LLM-invented scores;
- mock verification presented as real verification;
- fallback text that implies retrieval or analysis occurred when it did not;
- silent substitution of model memory for retrieved evidence;
- UI sections populated without corresponding persisted provenance records.

Mocks, fixtures, and synthetic records are allowed only inside tests and local demonstration datasets, must be visibly marked, and must never be reachable from production configuration.

Every user-facing intelligence feature must have:

1. a real ingestion or retrieval path;
2. persisted input evidence;
3. a versioned processing implementation;
4. persisted intermediate calculations;
5. a reproducible output record;
6. automated tests;
7. observable failure and refusal states.

Every processed source record must also have a current event assignment or an explicitly provisional event, with assignment candidates, scores, method/version, and history retained.

Every discovered article identity must retain its discovery channels, discovery timestamps, original URLs, canonicalization decisions, and publisher-strategy version. Frontier priority and adaptive scheduling decisions must retain their component scores and may not starve publishers, sections, locales, or bounded exploration channels.

## 2. Evidence-first invariant

No verification, historical timeline, analyst assessment, report conclusion, or research answer may be generated before evidence retrieval completes.

The retrieval plan must consider, where relevant and legally accessible:

- historical reporting;
- government documents and official statistics;
- legislation, court records, and regulatory material;
- scientific papers and datasets;
- company or institutional press releases;
- regulatory and financial filings;
- independent original reporting;
- specialist and professional fact-checking sources.

Retrieved material is stored before analysis with:

- canonical URL;
- source/publisher;
- source type;
- title or record identifier;
- publication/record date;
- retrieval timestamp;
- content hash;
- permitted extracted text or structured data;
- object-storage key where allowed;
- rights policy;
- extraction version and quality;
- query/retrieval run that found it.

If the minimum retrieval coverage for the task is not met, the output is:

> Insufficient evidence available.

The system must not convert retrieval failure into `Unsupported`, invent an assessment, or answer from model memory.

Community/social records are early signals unless independently supported by admissible evidence. Popularity, repost count, or discussion intensity never constitutes factual confirmation.

## 3. Claim verification contract

The only published claim labels are:

- `supported`
- `disputed`
- `misleading`
- `unsupported`
- `contradicted`
- `not_checkable`

A whole article never receives one of these labels.

Each published claim verification must include:

1. exact original claim text and normalized claim;
2. article offsets or structured source location;
3. exact evidence passages or structured record fields;
4. source URLs or stable record identifiers;
5. source type;
6. retrieval timestamps;
7. supporting, contradicting, and contextual stance;
8. source-lineage/independence group;
9. deterministic decision trace;
10. confidence methodology and all component values;
11. policy, model, prompt, extractor, and retrieval versions;
12. last-checked time and review state.

### 3.1 Model boundary

Models may:

- propose check-worthy claims;
- normalize claim wording;
- identify candidate evidence passages;
- classify evidence stance with a stored probability/distribution;
- draft a plain-language explanation from an approved evidence manifest.

Models may not:

- directly set the final claim label;
- directly produce the published confidence score;
- count independent confirmations;
- invent missing evidence;
- override the deterministic verification policy;
- change an existing verdict through Analyst Assessment.

Model proposals are validated against schemas, citations, source offsets, and deterministic rules before use.

### 3.2 Decision trace

“Reasoning trace” means a reproducible decision trace, not private model chain-of-thought. It contains:

- retrieval queries and filters;
- candidate and selected evidence IDs;
- evidence exclusion reasons;
- source-lineage resolution;
- stance values and model/rule versions;
- feature values;
- policy rules triggered;
- confidence calculation;
- final label;
- optional concise rationale generated only from those records.

## 4. Source independence and lineage

Independence is determined at the evidence-lineage level, not by domain count.

The system must identify cases such as:

```text
Reuters original
├── Yahoo republication
├── MSN republication
└── Local newspaper republication
```

as one underlying evidence lineage.

Lineage detection uses:

- exact and near-duplicate body similarity;
- byline and attribution phrases;
- canonical/original-source links;
- publication ordering;
- quoted-passage overlap;
- known syndication relationships;
- press-release or filing text overlap;
- publisher ownership group;
- citation and hyperlink chains.

Each evidence item stores `lineage_id`, `origin_evidence_id`, `ownership_group_id`, `syndication_type`, detection method, and confidence. Independent-confirmation calculations use at most one effective vote per lineage. Human corrections to lineage are audited and trigger verification recalculation.

## 5. Deterministic verification and confidence

For each evidence item `i`, calculate and persist:

```text
item_weight_i =
    source_reliability_i
  × claim_relevance_i
  × extraction_quality_i
  × temporal_applicability_i
```

All factors are normalized to `[0, 1]`.

- `source_reliability` comes from a versioned, governed source/evidence-type registry and measurable correction/original-sourcing history; it is not generated per article by an LLM.
- `claim_relevance` measures whether the evidence directly addresses the claim.
- `extraction_quality` reflects text/record integrity and source-location confidence.
- `temporal_applicability` measures whether the evidence applies to the claim's stated period. “Recency” must not penalize older primary evidence that is temporally correct.

Evidence is collapsed by lineage before aggregation. Persist:

- supporting evidence mass;
- contradicting evidence mass;
- contextual/inconclusive mass;
- unique independent lineages;
- required source classes attempted;
- retrieval coverage;
- source reliability aggregate;
- evidence consistency;
- temporal applicability;
- contradictory evidence weight;
- triggered label rules.

### 5.1 Label policy

The versioned policy engine determines labels:

- `not_checkable`: the claim is opinion, prediction, value judgment, vague, or not externally testable.
- `supported`: adequate retrieval coverage and strong directly relevant supporting evidence dominate contradictory evidence.
- `contradicted`: adequate retrieval coverage and strong directly relevant contradictory evidence dominate supporting evidence.
- `disputed`: credible independent supporting and contradictory evidence are both material.
- `misleading`: the literal statement has some support, but stored decisive context makes the presented implication materially inaccurate. This requires explicit context evidence and stricter review rules.
- `unsupported`: retrieval coverage is adequate, but no sufficient evidence supports the claim and evidence does not justify `contradicted`.

If retrieval coverage is inadequate, no label is published and the system returns `Insufficient evidence available.`

Exact thresholds are configuration, versioned, evaluated, and recorded with every verdict. They are never hidden in a prompt.

### 5.2 Confidence calculation

The published confidence value is computed by code from stored features:

- source reliability;
- independent-confirmation strength;
- evidence consistency for the selected label;
- temporal applicability/recency;
- contradictory evidence weight;
- retrieval coverage;
- claim specificity and extraction quality.

The initial uncalibrated implementation uses:

```text
raw_confidence =
  100 × clamp(
      0.25 × source_reliability
    + 0.20 × independence_strength
    + 0.25 × label_evidence_fit
    + 0.10 × temporal_applicability
    + 0.10 × retrieval_coverage
    + 0.10 × claim_and_extraction_quality
    - 0.20 × unresolved_conflict_penalty,
    0,
    1
  )
```

`independence_strength` uses unique evidence lineages with diminishing returns, for example `1 - exp(-effective_lineage_count / 2)`. `label_evidence_fit` is label-specific:

- `supported`: supporting mass divided by supporting plus contradicting mass;
- `contradicted`: contradicting mass divided by supporting plus contradicting mass;
- `disputed`: strength and balance of both supporting and contradicting mass;
- `misleading`: minimum of literal-support strength and decisive-context strength;
- `unsupported`: adequate retrieval coverage combined with absence of sufficient supporting evidence;
- `not_checkable`: no truth-confidence score.

`unresolved_conflict_penalty` measures material evidence inconsistent with the selected label after lineage collapse. All zero-denominator and minimum-evidence rules are explicit in the versioned policy configuration.

This formula is a transparent baseline, not an asserted probability. Numeric percentages are not displayed until it is calibrated against a labeled verification dataset using a non-generative calibrator such as isotonic regression or logistic calibration.

The stored confidence record contains:

- raw feature vector;
- formula/calibrator version;
- uncalibrated score;
- calibrated score, if available;
- categorical band;
- contribution of each feature;
- threshold and label-policy version.

An LLM response is never accepted as a confidence value.

## 6. Historical timeline integrity

A timeline event must map to stored evidence and contain:

- event date and date precision;
- event description;
- citation/evidence ID;
- source URL or stable record identifier;
- source type;
- publication/record date;
- retrieval timestamp;
- extraction/source offsets;
- timeline-generation version.

The LLM may rewrite a cited event into concise language, but it may not create the event, date, or citation. A deterministic validator rejects timeline entries without valid evidence mappings, dates outside the requested interval, or references published after the cutoff when producing prior context.

## 7. Analyst Assessment isolation

Analyst Assessment runs only after verification is persisted. It has read-only access to:

- verified claims;
- evidence manifests;
- historical timeline;
- unresolved contradictions;
- open questions.

It cannot update claim labels, confidence features, evidence stances, or source-lineage records.

Its output schema separates:

- implications;
- risks and uncertainties;
- alternative interpretations;
- missing evidence;
- evidence that would increase confidence;
- evidence that would decrease confidence;
- time horizon;
- analytical confidence;
- citations and assumptions.

If evidence is insufficient, the assessment is not generated.

## 8. Audit and observability

Persist or durably reference:

- source responses and permitted extracted artifacts;
- retrieval queries, filters, timestamps, and results;
- embeddings and embedding model versions;
- vector similarity and reranking scores;
- candidate and selected evidence;
- evidence mappings and source lineage;
- claim extraction outputs;
- deterministic feature values and calculations;
- verification labels and revisions;
- prompt templates and fully rendered prompts, subject to access controls;
- complete structured model responses;
- parser/validator results;
- generated artifacts and citation manifests;
- event assignments, candidate scores, merges, splits, and reassignments;
- event snapshots and snapshot diffs;
- occurrence, publication, observation, retrieval, and detection timestamps;
- propagation and attribution edges;
- geographic resolutions and alternatives;
- source-reliability profile inputs and snapshots;
- contradiction and contextual-gap records;
- knowledge-graph and W3C PROV-inspired lineage relations;
- worker/job events, retries, errors, and trace IDs.

Sensitive or licensed content is access-controlled and retention-governed. Auditability does not authorize unrestricted logging or display.

## 9. Required automated testing

Every feature requires unit and integration tests. Mandatory suites include:

1. exact, near-duplicate, and syndication detection;
2. source-lineage and independence resolution;
3. historical timeline date/citation accuracy;
4. claim extraction quality against labeled fixtures;
5. evidence retrieval coverage by source class;
6. evidence-stance and mapping accuracy;
7. citation completeness and source-offset validity;
8. verification label consistency for fixed feature inputs;
9. confidence calculation reproducibility and calibration;
10. insufficient-evidence refusal behavior;
11. Analyst Assessment isolation from verification state;
12. replay/idempotency and failure recovery;
13. permission and rights-policy enforcement;
14. throughput, queue backpressure, and horizontal worker scaling.

Production release gates use fixed labeled evaluation sets and explicit quality thresholds. A passing unit test alone is insufficient for probabilistic components.

## 10. Production execution requirements

- All fetch, extraction, embedding, clustering, verification, timeline, assessment, and report jobs run asynchronously in worker processes.
- APIs enqueue work and return status/stream updates; they do not execute long workflows in request processes.
- Queue messages are at-least-once and handlers are idempotent.
- Worker pools scale independently by task type.
- Backpressure, per-source rate limits, retries, circuit breakers, dead letters, and replay are mandatory.
- PostgreSQL remains the source of truth; Qdrant and generated indexes are rebuildable.
- The platform is load-tested at and beyond the projected thousands-of-articles-per-day workload.

## 11. Definition of done

A feature is complete only when:

- the real pipeline exists end to end;
- data and intermediate calculations are persisted;
- evidence and rights checks are enforced;
- refusal and failure states are implemented;
- unit, integration, and evaluation tests pass;
- metrics, traces, and audit records are emitted;
- horizontal execution behavior is verified where applicable;
- no production code path substitutes mock or fabricated output.
