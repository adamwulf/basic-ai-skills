---
# Required — downstream phases parse these to resolve paths and apply rules
domain: <domain-slug>                          # e.g. used-ev, saas-pm-tool, llm-provider. Reuse an existing slug from research/ where possible.
subject_slugs: [<subject-slug>, <subject-slug>] # Stable subject slugs for every candidate in scope. Maps to research/<domain>/<subject-slug>/.
candidates:                                    # One entry per candidate in this run.
  - candidate_slug: <candidate-slug>           # Battlecard filename. Often equals subject_slug; diverges only when one subject plays two candidate roles.
    subject_slug: <subject-slug>
    display: <Human-readable name>
hard_constraints:                              # Eliminators. A candidate failing any of these drops out regardless of score.
  - <one-line constraint>
scoring_criteria:                              # 5-9 dimensions battlecards score 1-10. Order here = section order in battlecards.
  - name: <criterion-name>
    weight: <0.0-1.0>                          # Weights should sum to ~1.0
    description: <what good looks like for this user>
tie_breakers:                                  # What matters most when two candidates score similarly.
  - <one-line tie-breaker>
out_of_scope:                                  # Things the user has decided or doesn't care about. Keeps research focused.
  - <one-line item>
staleness_days: 60                             # Days before a fetched source needs a refresh check. Default 60 for recall-sensitive domains, 180 for stable.
---

# <Run name> — Goal

## The decision

<One sentence. "Choose a project management tool for a 10-person team for the next 3 years.">

## Candidates in scope

<For each candidate: one paragraph with the "why in scope" rationale and any per-candidate notes (e.g., "narrow to 2024+ trims"). The structured frontmatter `candidates:` list above is the canonical source of slugs and display names — do not duplicate them here as a second structured list. This section is narrative-only.>

## Hard constraints

<Restate the frontmatter hard_constraints with one paragraph each explaining the why. Hard constraints eliminate candidates — they're not scored.>

## Scoring criteria

<For each criterion in frontmatter: one paragraph defining what 1, 5, and 10 look like for this user. Battlecards score against these definitions, so be specific.>

## Tie-breakers

<For each tie-breaker in frontmatter: one sentence on how to apply it.>

## Out of scope

<For each out_of_scope item: one sentence on why it's out (already decided, doesn't matter, or covered by a hard constraint).>

## Source-staleness window

<One paragraph explaining the chosen `staleness_days` and the rationale (e.g., "recall-sensitive domain — 60 days catches new NHTSA actions").>

## Preference-question topic scratch

<Optional Phase 1 scratch space. List candidate question topics for `preference-questions.md` (one per scoring dimension). DO NOT assign candidates to tiers — that requires battlecard data and is a Phase 4-late artifact. This scratch list seeds Phase 4-late authoring; it is not the final preference-questions file.>
