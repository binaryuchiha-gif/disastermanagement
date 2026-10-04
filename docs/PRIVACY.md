# Privacy & Security Note

ResQFlow-X handles location data in a life-critical context. We minimize what we
store and are explicit about it.

## Data minimization
- **Location:** the app routes **on-device**; a user's position is not sent to
  any server for routing. Location leaves the device only inside an **SOS**
  payload the user explicitly triggers, or an optional hazard report the user
  explicitly submits.
- **SOS payload** is compact (<200 bytes): coarse location (5-dp lat/lon ≈ 1 m),
  battery %, group size, timestamp, and a client-generated UUID. No name, no
  contact, no continuous tracking.
- **No background location tracking.** Geolocation is used only while the app is
  open and the user has granted permission.

## Consent
- Explicit permission prompt before using geolocation.
- SOS and hazard reporting are user-initiated actions, each with a confirmation.

## Security
- Transport: **HTTPS only** in deployment.
- Admin/coordinator actions require **JWT role-based auth**; every admin action
  is written to an **audit log**.
- **Input validation** on all API inputs (Pydantic models).
- **Rate limiting** on public endpoints (SOS, reports) to resist abuse.
- **No secrets in the repo.** The JWT secret comes from an environment variable
  (`RESQFLOW_SECRET`); the default is a clearly-labeled dev placeholder.

## Retention
- SOS and reports are retained only as long as operationally needed for an
  active event; a retention/pruning policy should be set per deployment
  (documented as a deployment decision, not hard-coded).

## Reporter data
- Hazard-report reliability scoring uses a reporter id and coarse location;
  reporter history is an accuracy score, not a profile. No demographic or
  protected-attribute data is collected or used.

## Not collected
No names, phone numbers, demographic data, or persistent cross-session
identifiers beyond a locally-generated device/report UUID.
