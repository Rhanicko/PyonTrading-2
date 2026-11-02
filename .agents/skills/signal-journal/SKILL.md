---
name: signal-journal
description: Preserve immutable PyonTrading candidate and outcome records with decision-time evidence, fill status and uncertainty labels.
---

# Signal journal

Append decision-time records; do not rewrite a historical candidate after later market movement. Distinguish observed, armed, rejected, expired, invalidated, missed and actually filled outcomes.

An unfilled candidate is never a winning trade merely because price later reached a hypothetical target. Store source timestamps, strategy version, data-quality status and explicit reasons for every classification.
