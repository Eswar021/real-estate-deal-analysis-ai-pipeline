# Anchor-first workflow (proposed)

**Status:** under discussion — the client's 3-stage redesign, plus one addition on our
side (the AI structure agent as an anchor-candidate source). The *current* pipeline
diagram still lives in [t12_parsing_proposal.md](./t12_parsing_proposal.md); this file
shows what it would become if we adopt the anchor-first design.

**Build status (2026-07-11):** Phase 1 (unknown branch) is **implemented and tested** in the notebook — a new `Module 9b` anchor lock (`lock_anchors`, driven by `anchor_keywords.json`), the `apply_anchor_overrides` fact-override after Module 10, Module 11 reduced to a positional tag from the locked anchors, and the feedback loop constrained so it can't touch locked rows. On the 7-file unknown set: **6 auto-lock to the correct anchors and reconcile with no feedback loop; Eleven11 flags GATE (4 valid triples — genuinely ambiguous) and still reconciles.** Phase 2 (known branch) is not built yet.

---

## At a glance — same 3 stages as the client's, one box each

```mermaid
flowchart TD
    U[File uploaded → cell_grid] --> D{Module 4<br/>format detection}
    D -->|known| KC[Resolve columns<br/>from the format template]:::res
    D -->|unknown| AIC[AI structure agent<br/>resolves columns + candidate R/E/NOI rows]:::res
    KC --> S1
    AIC --> S1
    S1["STAGE 1 · Lock R / E / NOI anchors<br/>keywords + AI nominate → R−E=NOI arithmetic decides<br/>ambiguous / no-NOI → manual gate (raw file, both branches)"]:::st --> S2
    S2["STAGE 2 · Classify rows WITHIN locked regions<br/>(our EXISTING pipeline: signal score + arithmetic override · NOI · feedback)"]:::st --> S3
    S3["STAGE 3 · Map to canonical categories<br/>(existing rulebook + LLM residue)"]:::st --> O[Canonical T12 + provenance]
    O -.->|every gate correction → rulebook + golden set| D
    classDef st fill:#1f3a5f,stroke:#3d6aa5,color:#e6eefb
    classDef res fill:#0f5132,stroke:#1a7f4b,color:#e8f5ec
```

**The key sequencing point (validated against our code):** the R−E=NOI lock needs the value
columns first, so **column resolution comes before Stage 1** — from the format template on the
known branch, from the AI structure agent on the unknown branch (a deterministic column detector
was tried and dropped; it grabbed wrong columns like a "Variance" column). So the anchor-lock sits
right after column resolution, not "before every step."

That's the whole thing — no more complex than the current pipeline. The **detailed view**
below is the *same* three stages with every decision branch drawn out (auto-lock vs manual,
override yes/no, NOI pass/fail); it only looks busier because it zooms in. You do not have to
adopt all of it — Stage 2 is already built, Stage 3 already exists, and the three gates +
learning loop are optional product layers that can come later.

## Detailed view — every decision branch

```mermaid
flowchart TD
    Raw[Raw extraction → cell_grid] --> D{Module 4 — format detection}
    D -->|known| KC[Resolve columns from format template<br/>desc / value / month-header known]:::auto
    D -->|unknown| AIC[AI structure agent<br/>resolves columns + proposes R/E/NOI rows]:::ai
    KC --> S1
    AIC --> S1

    subgraph S1["STAGE 1 — Lock R / E / NOI anchors (needs columns first)"]
        direction TB
        Nom[Nominate candidates<br/>anchor_keywords.json: grand / intermediate / exclusion + split-pairs<br/>plus the AI's proposed rows]:::auto
        Nom --> Search{{"R − E = NOI search<br/>every candidate triple, month-by-month<br/>tolerance max($1, 0.5%)"}}:::auto
        Search -->|exactly one triple passes| Lock[Auto-lock 3 anchors]:::auto
        Search -->|no NOI row exists| Derive[Derive N = R − E<br/>flag 'derived']:::auto
        Search -->|zero or many pass| G1[Manual gate 1 — raw file<br/>candidates + arithmetic evidence<br/>click-any-row · live re-verify]:::manual
        Lock --> Anchors[(Locked anchors →<br/>revenue / expense / capex regions)]
        Derive --> Anchors
        G1 --> Anchors
    end

    S1 --> S2

    subgraph S2["STAGE 2 — Classify rows WITHIN the locked regions"]
        direction TB
        Sig[Signal scoring<br/>normalized match: data / subtotal / header]:::auto
        Sig --> Over{Arithmetic-verified fact?<br/>sum-of-above / validated subtotal}:::auto
        Over -->|yes| Force[Override the score with the fact]:::auto
        Over -->|no| Keep[Keep the score]:::auto
        Force --> NOI{Per-month NOI check<br/>OUR DATA-row sums vs vendor totals}:::auto
        Keep --> NOI
        NOI -->|fail| Diag[Diagnosis agent → feedback loop]:::ai
        Diag -->|re-verify| NOI
        Diag -->|unresolved / low-confidence| G2[Manual gate 2<br/>low-confidence rows]:::manual
        NOI -->|pass| Done2[Rows classified + sectioned]
        G2 --> Done2
    end

    S2 --> S3

    subgraph S3["STAGE 3 — Map accounts to canonical categories"]
        direction TB
        Rule[Rulebook lookup<br/>deterministic, target 80%+ coverage]:::auto
        Rule -->|covered| Out[Canonical T12 + provenance]
        Rule -->|residue| LLM[LLM residue only<br/>strict JSON + confidence]:::ai
        LLM -->|high confidence| Out
        LLM -->|uncertain| G3[Manual gate 3<br/>override mappings]:::manual
        G3 --> Out
    end

    S3 --> Learn[↻ Every correction learns]:::learn
    G1 -.->|anchor fixes| Learn
    G2 -.->|class fixes| Learn
    G3 -.->|mapping fixes| Learn
    Learn -.->|golden set + format priors| S1
    Learn -.->|rulebook updates| S3

    classDef auto fill:#0f5132,stroke:#1a7f4b,color:#e8f5ec
    classDef ai fill:#1f3a5f,stroke:#3d6aa5,color:#e6eefb
    classDef manual fill:#7a4d00,stroke:#c07f1a,color:#ffedcc
    classDef learn fill:#3b2f78,stroke:#6b5bd6,color:#e9e4ff
```

Legend: **green** = automatic/deterministic · **blue** = AI · **amber** = manual gate (fallback) · **purple** = learning loop.

---

## What changes vs the current workflow

| Today (current diagram)                                                              | Anchor-first (proposed)                                                                                            |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| AI structure agent proposes R/E/NOI, we trust it, validate later                     | R/E/NOI**locked first** via arithmetic search over candidates; classification runs *inside* locked regions |
| Section tag assigned**after** classification (Module 11 keyword state machine) | Section is just "which region between anchors" —**state machine deleted**                                   |
| Classifier is a pure signal score                                                    | Score**plus** an arithmetic-fact override (our deferred override layer)                                      |
| Human review is effectively per-file                                                 | Three**exception-triggered** gates; humans only touch ambiguous cases                                        |
| No learning loop                                                                     | Every gate correction feeds the rulebook + a golden test set                                                       |
| Canonical mapping = existing src stage                                               | Same, now framed as Stage 3                                                                                        |

The genuinely **new** build: Stage 1 (candidate pool + R−E=NOI lock), the Stage 2 fact-override,
the three gates, and the learning loop. Stage 2's classifier/arithmetic/diagnosis and Stage 3's
rulebook mapping **already exist**.

---

## Key clarifications (the things that are easy to get wrong)

### The candidate pool must be multi-source, or it isn't dynamic

The client's Stage 1 draws candidates from **template + keyword** only. On a truly unknown
format (code-only totals like `…099/…999`, "Net Rental Revenue", abbreviations) no keyword
fires, so no triple can be tested → it drops to Manual gate 1 **every** unknown file. Fix:
add the **AI structure agent** (which already auto-locks unknown layouts, 7/7 on the test set)
as a third candidate source. The R−E=NOI arithmetic test itself is fully format-agnostic; only
the *shortlist* was biased.

### There are TWO different NOI checks — they are not the same

- **Stage 1 check** — `R − E = NOI` on the **vendor's own 3 grand-total rows**. Purpose: pick
  the anchors *and* detect whether the vendor's totals are internally consistent. Does not use
  our row classification at all.
- **Stage 2 check** — sum of the rows **we** labeled DATA, per section, vs the vendor totals,
  per month. Purpose: validate *our classification* inside the locked regions.

### Anchors do NOT replace classification

Locking R/E/NOI only fixes the **region boundaries** (revenue-side vs expense-side vs capex).
It says nothing about which rows inside a region are data / subtotal / header — so the full
classifier still runs; it just runs on known-good regions.

### What "manual override = fallback, not primary" means

Today the **human** is the mechanism that catches a wrong anchor (they eyeball/fix every file).
In the new design the **arithmetic** is that mechanism; the human's active correction only fires
when auto-lock fails. The user is still *shown* the result ("lock … and send to UI"); on clean
files it's a confirmation glance rather than active editing.

### Failure handling

- **Stage 1, zero triples pass** → AI resolve → manual pick. If it's zero because the **vendor's
  own numbers are inconsistent**, manual can identify the 3 rows but the math still won't
  reconcile → flagged as a **DATA_PROBLEM** (vendor error), not auto-fixable.
- **Stage 1, multiple triples pass** → ambiguous → AI resolve → manual disambiguate. Testing
  month-by-month (not just the annual total) makes coincidental multiples rare; keeping
  candidates to **grand-total-level** rows (not every subtotal) reduces them further.
- **Stage 2 NOI fails** → diagnosis agent + feedback loop reclassify until it reconciles (no
  human needed for the common case).

---

## Open decisions for us + the client

1. **Auto-lock approval:** on a clean auto-locked file, hard "user must click approve," or flow
   straight through? (liability vs throughput)
2. **Candidate sources:** confirm Stage 1 = Template ∪ Keyword ∪ **AI agent** (not keyword-only).
3. **Gate triggering:** confirm the three gates are exception-only, not mandatory per file.
