---
# Required
source_url: https://example.com/path/to/article
source_title: "Exact title as published"
date_fetched: YYYY-MM-DD

# Strongly recommended
author: "Author name"                  # or "unknown"
publication: "Publication / site name"
date_published: YYYY-MM-DD             # or "unknown"

# Organization
subjects: [subject-slug, subject-slug]        # One or more SUBJECT slugs (stable, cross-run) this source speaks to. Not candidate-slugs. Empty = purely background.
topics: [range, battery, warranty]            # Dimensions / criteria this source informs. Drives reuse across future runs.
domain: used-ev                                # Broad domain label so cross-run reuse can filter. e.g. used-ev, saas-pm-tool, llm-provider
research_round: 1                              # Round within this run in which THIS file was created. Immutable once written.

# Quality / provenance
source_type: primary | secondary | aggregator | forum | vendor
access: open | paywalled | login-required
tags: [anecdotal]                              # Optional. Flag forum/Reddit as anecdotal, etc.

# Optional back-references
supersedes: []                                 # Full relative paths from `research/` of older files this replaces (e.g., used-ev/kia-ev6/_archive/sc302-early.md). Not bare slugs.
related: []                                    # Full relative paths from `research/` of adjacent research files
---

# <Source title — exact>

> Fetched from <source_url> on <date_fetched>.

<Verbatim or close-to-verbatim extract of the relevant content. Preserve quotes, numbers, tables, dates. Trim navigation, ads, unrelated sections. Add subheadings only to mirror the source's own structure.>

<Do not paraphrase here — paraphrasing is the battlecard's job. This file is evidence.>
