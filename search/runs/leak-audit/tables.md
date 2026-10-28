### Table 1: leaked citations per system

| System | Citations | Leaked | Leaked % | Tasks with >=1 leak | Tasks where judge used a leaked citation |
|---|---:|---:|---:|---:|---:|
| rag-perplexity-fast | 2803 | 0 | 0.00 | 0 | 0 |
| rag-exa-fast-highlights | 3070 | 0 | 0.00 | 0 | 0 |
| rag-parallel-fast | 3070 | 2 | 0.07 | 2 | 0 |
| rag-parallel-turbo | 3046 | 0 | 0.00 | 0 | 0 |
| rag-exa-webcode | 3070 | 0 | 0.00 | 0 | 0 |
| rag-exa-instant-highlights | 2987 | 0 | 0.00 | 0 | 0 |
| rag-deepseek | 3011 | 4 | 0.13 | 4 | 0 |
| rag-firecrawl-search | 3058 | 2 | 0.07 | 2 | 0 |
| **all 8 runs** | 24115 | 8 | 0.03 | 8 | 0 |

### Table 2: groundedness, recorded vs. recomputed with leaked citations removed

| System | Graded tasks | Grounded (recorded) | Re-graded tasks | Flips (grounded -> ungrounded / ungrounded -> grounded) | Grounded (filtered) | Delta (pp) |
|---|---:|---:|---:|---:|---:|---:|
| rag-perplexity-fast | 307 | 94.5 | 0 | 0 / 0 | 94.5 | +0.0 |
| rag-exa-fast-highlights | 307 | 88.6 | 0 | 0 / 0 | 88.6 | +0.0 |
| rag-parallel-fast | 307 | 87.3 | 2 | 0 / 0 | 87.3 | +0.0 |
| rag-parallel-turbo | 307 | 87.0 | 0 | 0 / 0 | 87.0 | +0.0 |
| rag-exa-webcode | 307 | 86.6 | 0 | 0 / 0 | 86.6 | +0.0 |
| rag-exa-instant-highlights | 307 | 85.7 | 0 | 0 / 0 | 85.7 | +0.0 |
| rag-deepseek | 305 | 81.3 | 4 | 0 / 0 | 81.3 | +0.0 |
| rag-firecrawl-search | 307 | 54.4 | 2 | 1 / 0 | 54.1 | -0.3 |

Re-grades: 8 tasks, 8 judge calls (openai/gpt-6-luna via OpenRouter), $0.0043 reported cost.

Flips:
- rag-firecrawl-search rag_105: GROUNDED -> UNGROUNDED (repeat judge calls on the same filtered citations: GROUNDED, GROUNDED)

### Table 3: leaking domains

| Domain | Leaked citations | Reasons |
|---|---:|---|
| www.facebook.com | 4 | verbatim_query 4 |
| huggingface.co | 4 | host 4 |

Reasons overall: {'verbatim_query': 4, 'host': 4}
