# 11 — Data Protection Officer (DPO) Assessment

> **Last updated:** 2026-05-11

## Necessity Assessment

Under GDPR Article 37, a DPO is required when:
1. Processing is carried out by a public authority or body.
2. The core activities of the controller/processor consist of processing operations which require regular and systematic monitoring of data subjects on a large scale.
3. The core activities consist of processing on a large scale of special categories of data (Art. 9) or data relating to criminal convictions (Art. 10).

## ISLI Assessment

| Criterion | ISLI Status | Notes |
|-----------|-------------|-------|
| Public authority | No | Private deployment |
| Large-scale systematic monitoring | Potentially | Multi-agent systems may process user conversations at scale |
| Special categories / criminal data | No | Default configuration does not process these |

## Conclusion

ISLI **should designate a DPO** if:
- The deployment serves more than 5,000 active users.
- Conversations include health, biometric, or special-category data.
- The deployment is offered as a SaaS to third parties.

For personal/small-team deployments, a DPO is not mandatory but recommended as a best practice.

## MENA Law Considerations

| Jurisdiction | Requirement |
|--------------|-------------|
| UAE (PDPL) | DPO required for high-risk processing |
| Saudi Arabia (PDPL) | DPO mandatory for public and large private entities |
| Qatar (NDP Law) | Data controller must appoint a responsible person |
| Bahrain (PDPL) | DPO required for controllers processing sensitive data |

## Recommended Actions

1. Document the decision to appoint (or not appoint) a DPO.
2. If no DPO is appointed, assign a privacy contact for user requests.
3. Review annually or when user scale crosses 5,000 active users.
