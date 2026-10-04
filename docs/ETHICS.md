# Ethics

ResQFlow-X gives routing advice in a **life-critical** setting. Wrong advice can
send people into danger. This document states the risks, the fail-safe design,
and the disclaimers.

## Core risk: wrong routing advice
A learned model **will** be wrong sometimes — especially out-of-distribution
(new rainfall regimes, unmapped roads, correlated failures the model treats as
independent). A confident-looking "safest route" can still be blocked.

## Fail-safe design (enforced in code)
`routing/facade.route()` implements conservative fallbacks and **always tells the
user** when one triggers:
1. **Model unavailable / not loaded** → fall back to static-risk routing and
   display that the risk model is not in use.
2. **Chosen route exceeds a block-probability threshold** → switch to a safer
   chance-constrained route and display why.
3. **Tap/GPS outside the graph** → refuse to invent a route; tell the user.
These behaviors are unit-tested (`tests/test_accessibility_facade.py`).

## Human-in-the-loop for officials
The admin/coordinator view is for trained officials to **verify** closures, set
shelter capacities, and override. Crowd reports do not auto-close roads unless
their transparent reliability score clears a threshold, and the scorer is
designed to resist adversarial reporters (precision ≥0.9 even at 60% adversarial
in simulation). Officials remain the final authority.

## Disclaimers (shown in-app and in the README)
- This is a **research prototype**, not a certified emergency tool.
- It must not be the sole basis for life-safety decisions.
- Follow official evacuation orders and local authorities first.

## Data & privacy ethics
- Minimal location data; on-device routing; explicit consent; no background
  tracking; no demographic/protected-attribute data. See `docs/PRIVACY.md`.
- Map data © OpenStreetMap contributors; we respect tile usage policies and do
  not bulk-scrape tile servers.

## Fairness
We report **fairness as variance of evacuation time across neighbourhoods**
(`SimResult.fairness_variance`). A routing method that is fast on average but
abandons certain zones is not acceptable; the metric surfaces that. (Evaluated
on synthetic zones; real-equity analysis needs real demographic/geographic data
and is future work.)

## Honesty commitments (met in this repo)
- No fabricated data, metrics, results, or citations. Synthetic results are
  labeled SYNTHETIC everywhere; unmeasured items are labeled UNVERIFIED with the
  command to reproduce them.
- Negative and nuanced results (AUC ties, distribution shift, wide conformal
  intervals, low recall under sparse reporting) are reported, not hidden.

## Potential misuse
A routing/▪location tool could be misused for surveillance or to direct people
*toward* danger. Mitigations: on-device routing (no central location store),
minimal SOS payload, audit logging of admin actions, and open, inspectable
scoring logic. Deployers must not add covert tracking.
