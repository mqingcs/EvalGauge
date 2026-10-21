# Blinded Dual-Review Analysis

## Scope and protocol

The review covers all 35 released model-answer cases for which Official and
Strict-final disagree (33 unique benchmark rows). Two reviewers independently
received only the source image, question, raw released annotation, benchmark
instruction, and model response. Compiled contracts, automatic scores, policy
names, fault attribution, and the other verdict were hidden.

The dual-scale rule was finalized before reviewer B began: when a response
presents multiple final readings, every claimed reading must satisfy its paired
source interval. Before reviewer B began, reviewer A re-judged seven affected
cases under the finalized rule without access to reviewer B's verdicts. Both
the provisional labels and the finalized-SOP records are retained. A third
blinded reviewer independently adjudicated the three remaining disagreements.

## Agreement and adjudication

| Measure | Result |
|---|---:|
| Provisional first-pass exact agreement | 29/35 (82.86%) |
| Provisional first-pass three-label Cohen's kappa | 0.663 |
| Finalized-SOP exact agreement | 32/35 (91.43%) |
| Finalized-SOP three-label Cohen's kappa | 0.826 |
| Adjudicated final verdicts | 20 accept / 14 reject / 1 ambiguous |

The three finalized-SOP disagreements were localized rather than diffuse: one
concerned image readability, while two concerned the consistency of paired-scale
source intervals. All other 32 cases received matching independent verdicts.

## Alignment with executable profiles

The table below uses the 34 determinate adjudicated verdicts. These cases were
selected because Official and Strict-final disagree, so the rates describe this
transition set rather than all 4,884 released responses.

| Scoring policy | Human-aligned cases | Alignment |
|---|---:|---:|
| Official | 15/34 | 44.1% |
| Numeric-string patch | 21/34 | 61.8% |
| **Core-final** | **24/34** | **70.6%** |
| Physics-final | 17/34 | 50.0% |
| Strict-final | 19/34 | 55.9% |

Core-final is the closest executable profile on the adjudicated transition set.
The pattern is clearer when cases are grouped by claim scope:

| Claim scope | Determinate cases | Policy targeted by the scope | Human support |
|---|---:|---|---:|
| Source-declared Core | 19 | Core-final | 14/19 |
| Response safety | 4 | Strict-final | 3/4 |
| Physical-equivalence extension | 10 | Physics-final | 2/10 |
| Annotation ambiguity | 1 | Official | 1/1 |

The strongest human evidence therefore supports Core-level corrections to the
released scorer. Registered conversions remain useful as explicit semantic
coverage, but the review supports keeping them separate from source-declared
correctness rather than treating every conversion-triggered transition as a bug
fix. Response-safety decisions receive additional, narrower support.

## Source-annotation findings

Both reviewers independently flagged `transition-27` and `transition-34` as
paired-scale source inconsistencies and accepted the corresponding model
answers. These two cases show that the same typed review can expose annotation
debt in addition to evaluator control-flow debt. The casebook preserves each
reviewer's note and source-issue flag.

## Paper-level conclusions

1. The blinded review provides an independent check on the natural-output
   transitions, complementing the compiler-derived audit. Finalized-SOP
   agreement is high, and all disagreements are traceable to source or visual
   ambiguity rather than dispersed scorer behavior.
2. Core-final, not the most permissive or most restrictive profile, aligns best
   with adjudicated human judgments. Within the selected transition set, this
   provides case-level evidence for the paper's layered policy design.
3. Claim scope predicts human support: source-declared and response-safety
   changes receive substantially stronger support than optional conversion
   extensions.
4. Two independently identified paired-scale source issues extend the empirical
   story from evaluator faults to benchmark annotation consistency without
   changing the paper's central claim about executable scoring semantics.

Machine-readable evidence is in `analysis/dual_manual_review_analysis.json` and
`artifacts/dual_manual_review_casebook.csv`; the underlying reviews and
adjudication are under `artifacts/dual_manual_review/`.
