# legacy/ — baseline prototype (comparison hook)

The original "ResQFlow" prototype did **not** exist in this repository at the
start of the project (the repo was empty — see the Phase 0 audit). Per the
project decisions, we proceed greenfield and provide a **legacy comparison
hook**: a faithful reimplementation of the kind of hand-tuned logistic
"ML" model the prototype description specifies, so that hypothesis **H1**
("learned risk beats hand-tuned/static risk") has a real baseline to beat.

If you drop your actual prototype in here later, wire it into the same
interface (`hand_tuned_risk(features: dict) -> float`) and it will slot
straight into the H1 comparison in `risk_model/` and the simulator in `sim/`.

Files:
- `hand_tuned_model.py` — hand-tuned logistic road-failure model + static-risk
  baseline, pure stdlib. Used as a baseline in H1/H2.
