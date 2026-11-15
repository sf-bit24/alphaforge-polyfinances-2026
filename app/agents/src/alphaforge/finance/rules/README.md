# Canadian personal-finance rules (`canada_2026.yaml`)

**Simulation only. This is not tax or financial advice.** Check every value against the official
source and with a professional before relying on it.

## Purpose
This folder holds the regulatory parameters the AlphaForge engine uses (TFSA, RRSP, RRIF, FHSA,
RESP/CESG/CLB, RDSP, CPP, QPP, OAS, GIS, CDIC, capital-gains inclusion, US withholding, the FP Canada /
IQPF projection assumptions, and a pointer to mortality tables). The code reads its numbers from this
file. The model must never invent them, and every number has to cite `source_url`.

## Entry schema
```yaml
<section>:
  <key>:
    value: <number | object | list | null>   # null when status is unverified
    unit: CAD | CAD/month | ratio | ratio_per_month | ratio_per_year | years | list | pointer
    year: 2026                                # tax/benefit year the value applies to
    applies_to: [who / which account]
    source_url: <exact official URL that was fetched>
    source_title: <page title>
    retrieved_utc: <ISO 8601>
    status: verified | unverified
    note: <caveats: indexation, conditions, derived values>
```
Rates are stored as ratios (0.18 means 18%). The engine **must refuse to use or display as fact**
any entry where `status: unverified`.

## How to refresh
1. Open each `source_url` again. The amounts change on these schedules: TFSA, RRSP, YMPE and CESG
   thresholds in January; OAS and GIS every quarter (Jan, Apr, Jul, Oct); the PAG every April.
2. Update `value`, `year` and `retrieved_utc`, then bump `meta.version` and `meta.generated_utc`.
3. Only official sources count (canada.ca/CRA/ESDC, retraitequebec.gouv.qc.ca, cdic.ca,
   laws-lois.justice.gc.ca, revenuquebec.ca, fpcanada.ca / institutpf.org, cia-ica.ca, irs.gov).
   If you cannot confirm a value there, set `value: null` and `status: unverified`.
4. Check that the file still parses: `python3 -I -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" canada_2026.yaml`
