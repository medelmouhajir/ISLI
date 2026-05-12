# Agent 10 — Compliance & Legal Findings Report

**Date:** 2026-05-11
**Scope:** ISLI Architecture, Memory System, Channels & Gateways
**Reviewer:** Research Agent 10 (Compliance & Legal)

---

## Domain Summary

ISLI is a multi-agent, multi-channel system that processes personal data across Telegram, WhatsApp, Email, and Web Chat, storing it in a 4-tier memory hierarchy with an append-only archival tier. Despite handling EU/MENA-facing languages and channel-specific regulated communications, the current documentation contains no evidence of GDPR erasure mechanisms, consent logging, data residency controls, or channel-specific regulatory compliance (CAN-SPAM, TCPA, Meta Business Platform).

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F01 | **Critical** | GDPR Art. 17 (Right to Erasure) | Tier 4 Archival Memory is explicitly append-only and "Never deleted". This directly conflicts with the GDPR right to erasure for personal data. | `03-memory.md` lines 30-33: "TIER 4 — ARCHIVAL MEMORY (Frozen) ... PostgreSQL append-only · Never deleted" | Implement a "soft-delete + crypto-shredding" or pseudonymization strategy for Tier 4: replace direct PII with irreversible tokens and shred the key on erasure request, or maintain a documented legal basis for exemption and data-minimization fallback. |
| F02 | **Critical** | GDPR / PII in Vectors | No mechanism is documented for scrubbing PII from ChromaDB vector embeddings when a user requests deletion. Episodic and Semantic memories store embeddings derived from personal data. | `03-memory.md` lines 74-88 (episodic with embedding), 106-114 (semantic collections); no deletion procedure described. | Implement vector index re-building or embedding invalidation logic that runs as part of the erasure workflow. Document how embeddings containing PII are identified and removed or anonymized. |
| F03 | **Critical** | Lawful Basis / Consent | There is no description of how user consent is captured, logged, or stored before personal data is processed across any channel. | Entire `07-channels.md` describes inbound message flow (lines 73-91) with no consent gate; `01-architecture.md` data flow (lines 74-111) starts at "User sends message" with no pre-processing consent check. | Add a consent-management layer: capture affirmative consent per channel, log timestamp/method/version, store in Tier 3 semantic memory, and gate task creation on valid consent. |
| F04 | **High** | GDPR Art. 15 (Subject Access Requests) | No mechanism is described for handling Subject Access Requests (SARs), data portability, or user data exports. | No SAR/export/portability mentions in any of the three documents. | Design and document a SAR fulfillment pipeline that aggregates user data across Tiers 1-4 and delivers it in a machine-readable format (e.g., JSON) within the statutory 30-day window. |
| F05 | **High** | GDPR Art. 37 (DPO Requirement) | Multi-language support includes Arabic, French, and Darija (Moroccan Arabic), implying EU/MENA jurisdictions where a Data Protection Officer is likely required for systematic monitoring of personal data at scale. | `07-channels.md` lines 155-163: "Supported languages for detection: Arabic, French, Darija ..." | Conduct a DPO necessity assessment under GDPR Art. 37 and local MENA data-protection laws; if required, designate a DPO and publish contact details in the privacy notice. |
| F06 | **High** | Data Residency | No data residency or data-localization controls are documented, despite EU/MENA jurisdictional exposure. | No mention of region-specific PostgreSQL/ChromaDB instances, geo-fencing, or cross-border transfer safeguards in `01-architecture.md` or `03-memory.md`. | Document the intended deployment regions and implement geo-fenced data stores with region-specific DB instances and legal transfer mechanisms (SCCs, adequacy decisions) before processing EU/MENA personal data. |
| F07 | **High** | CAN-SPAM / TCPA (Email & SMS) | The Email (SMTP/IMAP) and SMS (Twilio) channels are fully built-in, but no opt-out, unsubscribe, or prior-express-consent mechanisms are documented. | `07-channels.md` lines 42-48 (email config), 68 (SMS Twilio adapter); no compliance text. | Add CAN-SPAM unsubscribe headers and footer links for email; implement TCPA-compliant opt-in/opt-out logging for SMS; document retention of consent records. |
| F08 | **High** | Third-Party DPAs | Data Processing Agreements (DPAs) with channel providers (Telegram, Twilio, Meta Cloud, SMTP hosts) are not mentioned. Each provider processes personal data on ISLI's behalf. | `07-channels.md` lines 56-70 lists providers but has no DPA documentation; `01-architecture.md` Layer 4 lists channels with no legal annex. | Negotiate and file DPAs (or Data Processing Addenda) with every channel provider that handles personal data; maintain a vendor compliance register. |
| F09 | **High** | Storage Limitation (GDPR Art. 5) | The "never deleted" policy for Tier 4 violates the GDPR principle that personal data shall be kept no longer than necessary. | `03-memory.md` line 32: "Never deleted"; no retention schedule or TTL is defined for archival tables. | Define and enforce a retention schedule for Tier 4 that aligns data retention with the longest applicable legal/statutory period; implement automated purging or anonymization after the retention window expires. |
| F10 | **High** | Audit Trail Integrity | Tier 4 is described as an audit trail, but there is no evidence of cryptographic hashing, digital signatures, or tamper-evident seals to guarantee integrity. | `03-memory.md` lines 128-161 describes `task_archive` and `message_archive` with standard UUID keys and timestamps, but no hash chains or HMAC fields. | Append a `sha256(previous_row_hash + payload)` or equivalent Merkle/chain hash to each archival row; store verification keys separately; document the integrity check procedure. |
| F11 | **High** | Pseudonymization / Raw PII Exposure | `message_archive` stores raw `content TEXT` and `channel_user_id` (phone numbers, Telegram IDs, emails) without documented pseudonymization or encryption-at-rest for PII fields. | `03-memory.md` lines 147-156: `message_archive` schema shows `content TEXT` and `session_id VARCHAR(64)` stored in plaintext. | Encrypt `content` and `channel_user_id` at the application layer (AES-256-GCM with per-user keys) or replace `channel_user_id` with a pseudonymous token in Tier 4. |
| F12 | **Medium** | Meta Business Platform Terms | WhatsApp via Meta Cloud API is supported, but compliance with Meta Business Platform messaging policies, message-template rules, and data-usage restrictions is undocumented. | `07-channels.md` lines 35-40 (WhatsApp config), 62 (Meta Cloud status: Built-in); no legal/policy annex. | Create a Meta Business Platform compliance addendum covering message-template approval, 24-hour session rules, prohibited use-cases, and data-sharing restrictions; assign an internal owner. |
| F13 | **Medium** | HIPAA / SOC 2 / ISO 42001 Evidence | The external context cites HIPAA, SOC 2, and ISO 42001 requirements, yet the system documentation contains zero evidence of Business Associate Agreements (BAAs), access-control matrices, or AI-management-system controls. | No mentions of "HIPAA", "SOC 2", "ISO 42001", "BAA", or "access control matrix" in any of the three documents. | If any tenant processes health data, execute BAAs and implement HIPAA Minimum Necessary standards; for SOC 2 and ISO 42001, align Tier 4 integrity, consent logging, and DPA coverage with control-objective mapping. |
| F14 | **Medium** | Cross-Border Transfer Safeguards | No Standard Contractual Clauses (SCCs), adequacy decisions, or transfer impact assessments are documented for multi-jurisdictional data flows. | `01-architecture.md` shows a generic single-machine/docker-compose layout with no region-specific routing or legal transfer mechanism. | Perform a Transfer Impact Assessment (TIA) for each target jurisdiction; implement SCCs (2021/914 EU model clauses) with channel providers and document the assessment. |

---

## Cross-Cutting Concerns

1. **Append-Only vs. Regulatory Reality**: The foundational design choice of an append-only, never-deleted Tier 4 is in direct tension with GDPR Article 17, Article 5(1)(e), and similar regimes (LGPD, POPIA). Unless ISLI can demonstrate that every piece of personal data in Tier 4 is either (a) anonymized beyond re-identification, or (b) retained under a specific legal obligation, the current design is non-compliant in any EU-facing deployment. This is not a documentation gap; it is an architectural conflict.

2. **Channel Provider Liability Cascade**: ISLI delegates outbound delivery to third-party APIs (Telegram, Twilio, Meta). Under GDPR Article 28, ISLI remains the controller (or joint controller) and must ensure every processor provides sufficient guarantees. The absence of documented DPAs, combined with the fact that raw PII flows through these adapters, creates a liability cascade: a breach or unlawful subprocessoring by any channel provider will be attributed to ISLI.

3. **Consent Vacuum**: Because there is no consent gate, logging mechanism, or lawful-basis registry, ISLI cannot currently demonstrate a valid legal basis for processing under GDPR Article 6. This undermines the lawfulness of the entire data flow from the first inbound message.

4. **Audit Trail vs. Tamper-Proofing**: Append-only tables provide chronological fidelity but not cryptographic integrity. Without hash chaining or HMAC, an attacker with database access can retroactively alter rows, and the system would not detect it. For SOC 2 Type II and ISO 42001 AI governance, tamper-evident logs are typically required.

---

## Confidence per Finding

| ID | Confidence | Rationale |
|----|------------|-----------|
| F01 | **Very High** | Explicit "append-only · Never deleted" text in `03-memory.md`. |
| F02 | **High** | ChromaDB embeddings are confirmed to store personal data; absence of deletion logic is an omission, not an ambiguity. |
| F03 | **Very High** | Complete absence of consent, lawful basis, or privacy-notice references across all three documents. |
| F04 | **Very High** | No SAR/export mechanism referenced anywhere. |
| F05 | **High** | Language support implies jurisdiction; DPO requirement is statutory for large-scale systematic monitoring in the EU. |
| F06 | **High** | No residency/geo-fencing text found; multi-region language support increases likelihood of EU data subjects. |
| F07 | **Very High** | Email and SMS adapters are present; zero compliance text found. |
| F08 | **Very High** | Provider list exists but no DPA annex or vendor register exists in docs. |
| F09 | **Very High** | "Never deleted" is explicit; no retention schedule is documented. |
| F10 | **High** | Schema is documented in detail and lacks any hash/HMAC field; no separate integrity doc found. |
| F11 | **High** | Schema explicitly shows plaintext TEXT fields for content and channel identifiers. |
| F12 | **High** | Meta Cloud is listed as built-in; no policy annex exists. |
| F13 | **Medium** | The external context cites these frameworks, but the docs do not claim compliance; however, the gap is notable if the project intends to serve regulated industries. |
| F14 | **High** | Generic docker-compose layout with no transfer-safeguard documentation. |

---

*End of Report*
