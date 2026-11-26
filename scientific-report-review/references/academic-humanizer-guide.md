# Academic Humanizer & Grammar Reference

Adopted from [AIScientists-Dev/academic-humanizer](https://github.com/AIScientists-Dev/academic-humanizer) (MIT License; builds on `blader/humanizer` and `ARMS`), integrated with the strict non-invention ground rules of `scientific-report-review`.

---

## Core Principle

Academic writing already has a clear human voice: **neutral, precise, evidence-bound, standard first-person plural ("we")**. Never inject casual humor, opinion, or blog-style "personality." The task is to:
1. Fix grammar and strip stereotypical AI-writing tells without casualizing the prose.
2. Enforce **claim–evidence discipline**: every empirical claim earns its number, figure, table, or citation, and no verb is stronger than its evidence.
3. **Never alter, invent, or drop** any number, equation, symbol, technical definition, or citation key.

---

## Layer 1: General AI-Tell Catalog

- **Inflated significance**: *"marking a pivotal moment"*, *"an enduring testament"*.
- **Superficial `-ing` tails** faking depth: *"..., highlighting its importance"*, *"..., underscoring the role of..."*.
- **Promotional / figurative language**: *rich, vibrant, groundbreaking*.
- **Vague attributions**: *"experts argue"*, *"researchers believe"* with no citation.
- **AI buzzwords**: *delve, underscore, intricate, tapestry, testament, landscape (abstract), pivotal, showcase, foster, leverage (filler), realm, seamless*.
- **Copula avoidance**: *"serves as"* → *"is"*, *"acts as"* → *"is"*.
- **Negative parallelisms**: *"not just X, but Y"*, *"not merely X, rather Y"*.
- **Rule-of-three padding** & **elegant variation** (cycling synonyms for the same technical referent).
- **Filler**: *"it is worth noting that"*, *"in order to"*.
- **Overlong, clause-stacked sentences**: sentences past ~30 words or chaining 3+ subordinate clauses (`which`, `that`, `while`, `with`) → split into crisp, single-idea sentences.
- **Em-dashes (`—` / `---`)**: remove entirely; recast with commas, colons, parentheses (only if essential), or separate sentences.

---

## Layer 2: Academic AI Tells

1. **Over-claiming verbs**: Empirical work *shows* and *provides evidence*; watch `prove`, `demonstrate`, `establish`, `confirm`, `guarantee`, and `"significantly"` without a statistical test or number.
2. **Significance hype**: *paves the way for*, *a crucial/pivotal step toward*, *has the potential to revolutionize*, *opens new avenues*, *sheds light on*, *of paramount importance*, *bridges the gap*.
3. **Empty intensifiers**: *extensive / comprehensive / thorough experiments*, *a wide range of*, *numerous*, *various* → replace with exact counts/names (or `[AUTHOR: exact count/list]` if missing).
4. **Novelty padding**: `"novel"` used more than once per section; *"to the best of our knowledge"*; *"for the first time"*.
5. **Formulaic openers**: *"In recent years, X has attracted increasing attention"*, *"With the rapid development of..."*, *"Despite recent advances,..."*.
6. **Connective overuse**: Consecutive sentences starting with *Moreover / Furthermore / Additionally / In particular*.
7. **Contribution-list clichés**: Generic bullets (*"a novel method; extensive experiments; strong results"*) instead of concrete quantified outcomes.
8. **Citation dumping**: Unexplained clusters like *"Many methods exist [3, 7, 9, 12, 15]."* Name and distinguish the 1–2 closest works.
9. **Hedging-by-vagueness**: *somewhat, relatively, fairly, to some extent, quite* → quantify or cut (or mark `[AUTHOR: quantify]`).
10. **Boilerplate emphasis**: *"It is worth noting that"*, *"It should be emphasized that"*, *"Notably,"*, *"Importantly,"*.
11. **Overlong, clause-stacked sentences**: Split sentences exceeding ~30 words or 3+ subordinate clauses.

---

## Layer 3: Preserve Scholarly Conventions (Do NOT Over-Correct)

- **Evidence-tied hedging is required when uncertain**: Keep *suggests*, *is consistent with*, *we hypothesize that*, *may indicate*, *appears to*. Never turn *"the results suggest X"* into *"the results prove X"*.
- **Passive voice** is valid when the actor is irrelevant (*"Samples were normalized..."*).
- **First-person plural "we"** is standard.
- **Semicolons and an occasional triple** are acceptable in moderation (em-dashes are still removed).
- **Formal definitions, named methods/metrics, technical terms, equations, symbols, numbers, and citation keys** remain strictly verbatim.

---

## Layer 4: Claim–Evidence Lexical Discipline

For every empirical claim:
- **Unbacked claim** → attach the existing figure/table/citation pointer, soften the claim, or flag `[AUTHOR: provide evidence pointer]`.
- **Verb stronger than evidence** → downgrade (e.g., *proves universally* → *matches or exceeds on these systems*).
- **Vague magnitude** (*"a large improvement"*) → prefer an attributed **range** (`2–6%` on metric X vs. strongest baseline) when the data are present in the paper, or flag `[AUTHOR: give attributed range vs. strongest baseline]` if missing. Lead comparisons with the strongest competitor, not a trivial baseline.

---

## Layer 5: Voice & Venue Matching

- If the author provides a prior paper (`voice_sample`), analyze sentence rhythm, connective habits, hedging style, section openings, and recurring phrasings so suggested edits match the author's genuine voice.
- Match the `target_venue` register (e.g., *Physical Review / domain-technical journals*: concise, quantitative, derivations-forward; *NeurIPS / ICLR*: terse, results-forward; *Nature / PNAS*: expository).

---

## Layer 6: Funding-Proposal Mode (`doc_type`: `proposal` / `nsf` / `nih`)

Proposals sell **vision plus feasibility**, not finished results. Do **not** flatten appropriate vision language (*long-term goal*, *transformative*, *establish a foundation*) when backed by a feasible plan. Instead:
- **First-3-pages primacy**: Focus hardest on the opening (NIH 1-page Specific Aims; NSF 1-page Project Summary with **Overview / Intellectual Merit / Broader Impacts** + first 1–2 pages of Project Description).
- **Fix proposal-specific weak moves**:
  - Vague importance (*"this is an important/timely problem"*) → concrete cost of the gap;
  - Method-as-aim (naming a technique instead of a scientific question/outcome);
  - Dominoed aims (Aim 2/3 collapse if Aim 1 fails — reframe as parallel/independently valuable or state fallback);
  - Ambition without feasibility (missing preliminary data, prior publication, classical foundation, or collaborator support — flag for author, never invent);
  - Boilerplate Broader Impacts / training plan → concrete, tied to research;
  - Hedged central hypothesis on the Aims page (must be a crisp falsifiable commitment).
- **Preserve funded-proposal craft**: Vision framing, scannable run-in lead-ins (**Goal:**, **Innovation:**), concrete running example, crisp aim questions, named classical foundations, and early foregrounding of real PI track record.
- **Claim ↔ Feasibility**: Keep ambitious verbs only when backed by credible means; otherwise flag the feasibility gap without inventing preliminary data, funding, or partners.
