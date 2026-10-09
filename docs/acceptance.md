# Rules, requirements and client acceptance

## Scoring version 1

Use 3–50 owner-approved comparable **asking prices**, observed in the past 60 days, matching make/model/trim/currency, model year ±1 and mileage within ±20,000 miles. The median is a comparison proxy. A larger set still needs human independence checks: syndicated copies must not be approved as separate market evidence.

Score = clamp(round((median − asking price) / median × 400), 0, 100), minus 10 for fair condition, floored at zero. Reserve is 2,000 currency units for good/unknown/poor condition or 2,500 for fair condition. Estimated spread = median − asking − reserve. Review threshold is at least 2,500 currency units after reserve. All amounts remain within their original currency; no FX normalization or cross-currency ranking is implied. These are explicit initial business rules, not learned valuation or a profit forecast. Have the client approve/tune them before live use.

Hold the lead if withdrawn, older than 72 hours, unknown/poor condition, fewer than three comparables, duplicated active VIN or spread below threshold. VIN syntax is not proof of identity. Inspect title/history, mechanical condition, liens, shipping, taxes, auction fees, reconditioning and current saleability independently. The reserve does not claim to model all those costs.

Outreach additionally requires New Lead stage, a seller phone, current recorded permission, no suppression, no prior initial attempt, owner approval and enabled/configured integration. Feed collection is automatic once a source is approved; outbound approval is deliberate and per job.

## Requirements mapping

| Brief | Implementation / boundary |
|---|---|
| Public marketplace listings | Scheduled authorized HTTPS JSON feed and reviewed upload contract; actual marketplace access/adapter supplied per client |
| Year/make/model/mileage/price/details/contact | Strict normalized fields, source identity, observed time, optional E.164 contact and VIN |
| Price/mileage/condition scoring | Approved comparable median, mileage matching, condition penalty/reserve and explicit holds |
| Existing CRM stages | Four local stages and tested HubSpot unique-key upsert; other CRMs require their own adapter |
| First automated SMS | Twilio API worker after owner review, permission/freshness checks, signed callbacks and opt-outs |
| Solid first build / continued work | Deployment, restore, source contracts, tests, activity history and handover plan |

## Go-live checklist

- [ ] Client confirms the actual marketplace feeds and right to collect/use their fields; mappings tested against real permitted samples.
- [ ] Mileage units/currencies/condition mappings and comparable independence are approved.
- [ ] Owner/operator access tested using named accounts; no default/demo credentials or synthetic permission evidence remain.
- [ ] CRM vendor confirmed; actual pipeline/stages, unique property, seller-phone property and currency mapping accepted.
- [ ] SMS sender account, required registration, exact company identity, documented recipient permissions and retention agreed.
- [ ] Signed status and opt-out callbacks tested with the client's approved test number; no unapproved real seller receives test messages.
- [ ] Timeout/unknown, STOP, stale listing, duplicate seller, changed owner role and worker interruption scenarios witnessed.
- [ ] Off-host restore completed and contact-lock/suppression reconciliation process approved.
- [ ] Hosting, monitoring, update owner, support scope and handover agreed.

These are uncompleted client acceptance items. The implementation and synthetic tests do not claim a client deployment, unrestricted marketplace access, live provider certification or real acquisitions.
