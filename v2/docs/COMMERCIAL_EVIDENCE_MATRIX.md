# Commercial Evidence Matrix (Public / No-Login)

Last updated: 2026-05-10

This matrix maps hidden commercial questions to public evidence proxies and source classes.

## 10 Hidden Buying Questions

| Question | Primary Proxies | Source Classes |
|---|---|---|
| Budget confidence | hiring velocity, senior role openings, funding mentions, ad spend language | jobs/news/reddit/github/procurement pages |
| Urgency | deadline language, backlog, outages, migration urgency | jobs/news/reddit/issues/forums |
| Internal politics | reorg/new leadership/ownership overlap | leadership/news/jobs |
| Procurement complexity | security/legal/procurement terms, RFP references | security pages/legal pages/news |
| Vendor lock-in | incumbent tool mentions, migration/switch references | jobs/stack pages/case studies |
| Board pressure | efficiency/burn/profitability language, funding stage | news/investor language |
| Operational maturity | RevOps/DataOps/automation/SLA language | jobs/docs/product pages |
| Strategic alignment | expansion, GTM, launch, customer acquisition priorities | website/news/blog |
| Buying committee dynamics | multi-role dependency signals across Ops/IT/Security/Finance | job clusters/org signals |
| Implementation readiness | integration/API/project/implementation staffing | jobs/integration docs |

## Public Source Priorities

1. Google X-ray + jobs
2. Crunchbase public feeds
3. Indeed/Glassdoor/JobSpy velocity
4. Google News
5. Reddit + GitHub
6. DDG broadening
7. Tech-stack/reviews/firmographics (pending adapters)

## External OSS Research References

- Mira (company enrichment orchestration): [DimiMikadze/Mira](https://github.com/DimiMikadze/Mira)
- Company research multi-agent pipeline: [guy-hartstein/company-research-agent](https://github.com/guy-hartstein/company-research-agent)
- Multi-agent deep research stack: [trilogy-group/nexus-agents](https://github.com/trilogy-group/nexus-agents)
- Sales agent category map: [Salesably/awesome-ai-agents-for-sales](https://github.com/Salesably/awesome-ai-agents-for-sales)
- OSINT source catalog: [r3p3r/jivoi-awesome-osint](https://github.com/r3p3r/jivoi-awesome-osint)
- Jobs-market proxy dataset: [hiring-lab/ai-tracker](https://github.com/hiring-lab/ai-tracker)

## Notes

- Scores are probabilistic, not deterministic truth.
- Every dimension score must include evidence terms and confidence.
- Unknown is valid output; missing evidence must not be hallucinated.

