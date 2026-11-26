# Scientific Writing Guidelines

Distilled from concise technical writing principles for quantitative scientific manuscripts: common structural, textual, and formatting pitfalls and practical recommendations.

---

## I. Paper Structure

Keep Title, Abstract, Introduction, and Conclusions in rough form throughout drafting so all parts work together cohesively; polish them once Methods/Theory and Results/Discussions are solid.

### 0. Title & Short-Route Scope Parity
- Name the scientific subject and core contribution without parameter, dataset-count, or implementation bloat.
- Shortening a title must never broaden claims by silently deleting a scope qualification.
- **Short-route check:** `Title -> Abstract -> Figures + Captions -> Conclusions` must tell one coherent, same-scope story without hidden caveats or shifting claims.

### 1. Abstract
Must fulfill all five functions (as functions, not a rigid 5-sentence template):
1. What problem is solved in this paper?
2. Why is this problem important?
3. What is the approach to solve it?
4. What are the main results?
5. What are the ramifications of these results?

Constraints:
- **Compact paragraph within the target journal's word limit** (self-contained: avoid terms, internal nicknames, or acronyms unclear without reading the whole paper).
- **Prior work vs. new delta:** Clearly separate what prior methods already achieved from what is genuinely new here so a reader seeing only the Abstract does not misattribute capability.

### 2. Introduction
Provide clear context so that after reading, the reader sees why this approach is well-suited to tackle an important problem (avoid `"only way"` framing and remote societal hype).

- **Context for the problem**:
  - *Why is it important?* State concrete stakes rather than vague generalizations; verbs like `"explore"` or `"understand"` are acceptable only when paired with *which specific behavior* is studied and *what remains unknown*.
  - *Prior work & gap*: Identify who addressed this problem previously and what shortcomings remain; frame room for improvement **politely** without direct confrontation (those authors may be your reviewers).
- **Context for the method/approach**:
  - **Stop-before-the-choice test:** Stopping right before any major methodological choice (even a borrowed method), the reader should see from preceding text *why* that choice is needed.
  - **Combined-method interaction:** When combining known ideas, explicitly explain where using one changes how the other must be used.
  - Explain why the approximations used are adequate and why existing alternatives are insufficient.
- **Teaser**: Near the end of the Introduction, give a short teaser of the main result achieved and the advantages of this perspective.

### 3. Methods / Theory
- Present all new theoretical developments in the **simplest and shortest optimal way** — **do NOT follow the historical order** of how the ideas were discovered.
- **Reader-first pedagogical flow:** Open with what constitutes a correct decision/problem (*do not answer questions the reader does not yet have*—keep schedules, priors, and solver details out of the opening); give a **minimal concrete toy example** before general notation; **define the estimator before asking the reader to optimize it**; place every **Proposition/Theorem *after* the objective it bounds**; explain the conceptual job in plain English before giving nicknames or numerical constants.
- **Three-way epistemic separation:** Clearly distinguish **(i) exact identities under explicit assumptions and stated space** (e.g., full space vs. fixed-sector subspace), **(ii) justified approximations**, and **(iii) empirical observations** (never conflating numerical truncation with exact termination).
- **Connect to known building blocks** rather than rewriting existing derivations; this aids comprehension and keeps the paper concise.
- **When to repeat prior work**: Only if **both** conditions hold:
  1. Your work is heavily based on it (and needs unified notation), **and**
  2. It is *not* textbook material (it is relatively new or comes from a different scientific field).
  Otherwise, cite it without rewriting it.
- **No premature applications**: Do not discuss applications of the theory in the Methods/Theory section.
- **Use Appendices / SI**: Move technical details necessary for reproducibility that distract from the main theoretical message into an appendix or SI.

### 4. Results / Benchmarks
- Define the model systems/datasets, **rationalize why those specific test cases were chosen**, and compare results against strong known methods.
- **Rationale before every figure/table**: Before presenting a plot or table (e.g., convergence with resolution, grid, or sample budget), state *why* assessing this property matters.
- **Analyze, do not merely narrate**: Never just describe numbers or curves already visible on the plot/table. State the **trends**, explain **why** they occur, and note whether they were **expected from theory or surprising** (checked surprising findings are legitimate scientific results, not flaws).
- **Uncertainty & table honesty**: Define every uncertainty measure explicitly (SD, SE, CI, plus sample count $N$) and separate sampling uncertainty from model/basis/convergence error; flag residuals much smaller than error bars as a possible overestimated-uncertainty signal (noting correlation or fitting caveats). In tables, distinguish missing/uncomputed entries from `0`, and numerical convergence digits from physical accuracy.
- Tie results back to the core problem identified in the Abstract and Introduction.
- **Reproducibility without textbook filler**: Do not waste space explaining standard algorithms while omitting your own problem formulation or exact parameters. Give exact numerical parameters for standard routines, summarize in 1–2 sentences how known building blocks combine, and place equation-level differences in an appendix/SI.

### 5. Conclusions
- Restate the core solution and summarize how model/benchmark results establish its performance and limits relative to alternatives (matching the scope of Title and Abstract).
- Briefly note future possibilities, **but restrain from giving away too much future work or indulging in wishful thinking**.

### 6. References
- Verify bibliographic accuracy: every entry must include **complete bibliographic information** (authors, journal, volume, page/article number, year, DOI where applicable) and **consistent formatting** across entries (e.g., do not mix abbreviated and full journal titles).
- **Citation-to-claim matching**: Match citations closely to the exact claims they support; avoid ambiguous citation clusters that blur which reference establishes which point.

---

## II. Usual Textual Problems

1. **Repetitions (judged by purpose)**:
   - *Your own text*: Repeating numbers/values already shown in a figure or table without explaining *why* they behave that way.
   - *Captions vs. main text*: Captions should make figures/tables standalone (system, axes/quantities, curves/symbols, uncertainty convention, brief descriptive takeaway), while main text supplies comparison, explanation, and scientific consequence rather than echoing the caption.
   - *Previous work*: Repeating extensive derivations or text already available in textbooks or cited papers.
2. **Terminology consistency, physical-action precision & ambiguous references**:
   - **One name for one concept**: Avoid drifting across near-synonyms (e.g., *approximate* vs. *quasi-* vs. *pseudo-* labels) for the same concept unless the technical criteria genuinely differ.
   - **Physical-action precision**: Replace blurry nouns or verbs that conceal actual physical/algorithmic operations (state the concrete operation, object, and quantity).
   - **Ambiguous references (`which`, `that`, `these`, `this`, `it`, `the`, `used by`, `in that case`)**: Every pronoun, relative clause, or demonstrative must have **one unmistakable antecedent** (no dangling `"it"` or misplaced clauses).
   - **Structural forward references**: Avoid forward references that the reader needs just to parse the current sentence (define the concept before relying on it).
3. **Bracket and dash abuse `(...)` and `—...—`**:
   - Parentheses are only for nonessential augmentations. Do not stuff new ideas into brackets as a temporary patch — integrate the explanation cleanly or delete it if already defined. Avoid vague pointers like *"elsewhere"*.
4. **Typos, omissions, word abuse, and LaTeX hygiene**:
   - Spellcheck and eliminate typos.
   - **Zero tolerance for undefined symbols, acronyms, or abbreviations.**
   - Audit repetitive transition words (`however`, `thus`, `therefore`, `hence`).
   - Use proper LaTeX quotation marks (`` ``text'' ``, not `"text"`).
   - Keep mathematical variables in math mode everywhere (e.g., `$N$` consistently, never plain text `N`).
5. **Absence of a clear point (descriptive discourse)**:
   - Continuously ask: *"What should the reader do with the information I provide?"* Write with specific conclusion points in mind and provide evidence for them.
6. **Unnecessary uncertainty / hedging**:
   - Writing should reduce uncertainty. Avoid weak `might be / may be / can be` when `is / are / will` holds — narrow the subject of the sentence if needed to be concrete and accurate rather than vague and general. *(Balance with scientific honesty: never overclaim beyond what the data support.)*
7. **Prune filler without mechanical over-deletion**:
   - Cut empty filler phrases wherever they add zero clarity:
     - `"We decided to use ..."` → `"We use ..."`
     - `"As we already know ..."` → *(delete)*
     - `"We concluded to ..."` → `"We ..."`
     - `"The reader could wonder ..."` → *(delete)*
     - `"One can ask ..."` → *(delete)*
     - `"As previously mentioned ..."` → *(delete)*
     - `"in fact"` / `"the fact that"` → *(delete, e.g., `"considering the fact that"` → `"considering that"`)*
   - **Do NOT optimize blindly for minimum word count:** preserve concise orienting transitions and guiding questions that do real explanatory work.
8. **Science-altering grammar & modifier clarity**:
   - Distinguish restrictive `that` from non-restrictive `, which`.
   - Keep replacement direction unambiguous (`substitute A for B`, not `substitute A and B`).
   - State trend direction explicitly (`as dt decreases`, not vague `at small dt` when describing scaling).
   - Eliminate dangling modifiers, incomplete comparisons (`Unlike B, the error of A...`), and `"obviously"` / `"clearly"` substituting for an actual explanation.
   - Unpack dense 4–5-noun modifier stacks without breaking standard technical compounds (e.g., `"parameter estimation"`).

---

## III. Formatting, Figures & Word Choice Recommendations

1. **Sentence-initial structural references**:
   - Abbreviate mid-sentence (`Fig.`, `Figs.`, `Eq.`, `Eqs.`, `Tab.`, `Sec.`), and spell out at the start of a sentence (`Equation (1) provides ...`, `Figure 2 shows ...`, `Section III describes ...`, `Table I lists ...`). Treat this as a structural reference convention rather than a blanket ban on all technical acronyms starting sentences.
2. **Making figures**:
   - **Final printed-size legibility**: Judge line weights, marker sizes, legends, and axis/tick font sizes at **final printed scale** (after 1-column reduction in the compiled PDF) rather than arbitrary script constants.
   - **Vector format**: Use vector graphics (`.pdf` or `.eps`) for plots and diagrams; keep raster images only where genuinely required (e.g., microscopy/heatmaps) at high resolution.
   - **Color + style redundancy**: Pair color-vision-safe palettes with distinct line styles or markers so curves remain distinguishable in grayscale and for color-vision-deficient readers.
   - **Titles vs. panel annotations**: Short in-plot regime or panel annotations are fine; omit embedded figure titles that merely repeat the caption.
   - **Plot-line & uncertainty honesty**: Explicitly state whether plotted lines are theoretical predictions, fits, or guides to the eye, and define every error bar or shaded band in the caption.
3. **Precise logical connectors**:
   - **THUS**: in this way
   - **HENCE**: for this reason
   - **THEREFORE**: as a result, as a consequence
   - **ERGO**: consequently, hence

---

## IV. Cover Letters & Referee Responses (Submission Practice)
- **Cover letter**: Briefly explain why the main finding fits the target journal's readership and scope without copy-pasting the Abstract.
- **Point-by-point referee response**: Quote or summarize each referee comment, answer directly first, and cite exact manuscript locations (section/page/equation) for every edit.
- **Declining a suggestion**: When keeping the original text/design, explain the technical reason politely and concretely rather than dodging the question.
- **Self-contained clarity**: Keep the response readable on its own so an editor can verify changes without hunting through diffs.
