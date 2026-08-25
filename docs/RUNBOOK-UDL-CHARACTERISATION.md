# Runbook: UDL characterisation pass (flight plan step 4)

**Who runs this:** Ash, on the networked workstation. Nothing in this runbook runs in the container
or in CI, and nothing here needs the repository's virtual environment.

**Why it exists:** every scenario ENLIGHTENMENT generates has to look like real data or the training
transfers nothing. That means measuring real UDL noise once - revisit intervals, residual
distributions, epoch spacing, missing-field and outlier rates, marking mix, correlation quality -
and committing the measurements as versioned content. The scenario engine then samples from
distributions that were observed rather than invented.

**What crosses the boundary:** one parameter file of distributions. No records, no object
identifiers, no credentials. The tool refuses to write a file that fails that check.

**Time:** about 20 minutes of your attention, plus however long the retrieval takes.

## What you need before you start

| Item | Where it comes from | Status |
|---|---|---|
| `tools/udl_characterise.py` | this repository, `V0.23.6` | **Ready** |
| Python 3.11 or newer on the workstation | already there, or the system Python | Check with `python3 --version` |
| UDL credentials at `~/.config/phase_offset/credentials.ini`, mode `600` | your existing file | Check |
| **A completed endpoint profile** | **you, from the UDL API documentation** | **BLOCKED - see step 2** |

Standard library only, single file, no install step. Copy the one file across and run it.

## Step 1. Prove the analysis half, before touching the network

Do this first. It needs no credentials, no profile, and no network.

```
python3 tools/udl_characterise.py --self-test
```

Expect `SELF-TEST: PASS (14/14)` on stderr and a JSON assertion manifest on stdout. The manifest is
the evidence: fourteen named assertions over synthetic records with statistics known by
construction, each with its expected value, its actual value and why it matters. Two of them prove
the boundary guard in both directions - that a clean parameter file passes, and that a planted
catalogue-number shape is refused.

If this fails, stop. Send me the manifest; the failing assertion names the problem.

## Step 2. Write the endpoint profile - THIS IS THE PART I CANNOT DO

```
python3 tools/udl_characterise.py --print-profile-template > udl-profile.ini
```

Then fill it in from the UDL API documentation. Every blank is a fact about the UDL API that is not
in the flight plan, and the tool refuses to guess any of them: an invented endpoint or field name
produces an integration that looks like it works until it is run against the real service.

**`[endpoints]` - five values.**

● `base_url` - scheme and host, no trailing slash. **Must be `https://`**; anything else is refused
  rather than corrected, because `urlopen` honours `file:` and the request carries your credentials.
● `observation_history_path` - the path returning a LIST of historical observations for a time range.
● `observation_count_path` - the path returning a BARE INTEGER count for the same range. Queried
  first, so the tool knows whether it must time-slice before it fetches anything.
● `elset_history_path` and `elset_count_path` - the same pair for element sets, for epoch spacing.

**`[query]` - the parameter names.** `time_field` is pre-filled as `obTime` and
`first_result_param` as `firstResult`, both from the plan's LEARNED register. Confirm them, and fill
`max_results_param` and `page_size` (the page size must not exceed the platform maximum). Leave
`columns_param` blank if the API has no projection support.

**`[fields]` - the record field names.** `observation_time` is pre-filled as `obTime`. The rest are
blank. Two rules govern them:

● **A blank field is reported as UNAVAILABLE, never estimated.** Fill what you can confirm and leave
  the rest; the output names what it could not measure. An absent measure is honest, an invented one
  is not, so a half-filled profile still produces a usable and truthful parameter file.
● **`sensor_id` and `object_identifier` are required.** They are what make revisit and epoch spacing
  per-sensor and per-object rather than a single meaningless pile. `object_identifier` is read for
  GROUPING only: it is replaced by a per-run salted hash before any statistic is computed and never
  appears in the output.

`chmod 600 udl-profile.ini` and keep it off the repository. It is workstation configuration, not
content. Nothing in it is a secret, but it is an inventory of endpoints and field names, which is
the class of thing the redaction discipline keeps out of the content tree.

## Step 3. Retrieve and measure

Start with a SHORT window - an hour - to confirm the profile is right before committing to a long
run.

```
python3 tools/udl_characterise.py \
  --profile udl-profile.ini \
  --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z \
  --raw-out udl-raw-1h.json \
  --emit noise-model-1h.json \
  --verbose
```

What it does, in order:

1. Asks the count endpoint for the window, with `Accept: text/plain`, because it returns a bare
   integer.
2. If the count is over the 10,000 `firstResult` cap, **bisects the window in time** and repeats.
   Offset pagination past the cap silently truncates, which is the failure that produces a confident
   answer from a third of the data. A window that cannot be narrowed below the cap is reported as an
   unrepresented gap in `provenance.unrepresented_windows`, never quietly sampled - so **read that
   list before you trust the numbers**.
3. Fetches each in-cap slice with `Accept: */*`, paging within it.
4. Measures, then checks the output against the boundary guard, then writes.

`--raw-out` saves the fetched records so you can re-run the analysis offline without re-fetching. It
is written mode `600` and **stays on the workstation**: raw records are not the thing that crosses.

Then widen the window. A representative pass wants enough time to cover a full revisit cycle across
the provider set; my recommendation is 7 days, and the sensible check is whether the per-sensor
`n` values are large enough to mean anything - a residual distribution over 4 observations is not a
distribution.

## Step 4. Read the output before committing it

```
python3 -m json.tool noise-model-7d.json | less
```

Look at four things:

● `provenance.unrepresented_windows` - empty, or you have a coverage gap and the measures below are
  a statement about an unknown subset.
● `measures.measures_unavailable` - which fields you left blank. Expected, but know what is missing.
● `measures.record_counts` and each sensor's `n` - is this enough data to be a distribution.
● `measures.sensor_labels` - `pseudonymised` by default. **Your decision:** the noise model is more
  useful with real sensor names, and less shareable. Pass `--sensor-labels verbatim` only if you are
  content that the sensor set is not itself sensitive. I have defaulted it closed.

## Step 5. Commit it as content

The parameter file is versioned content, like a procedure. Put it in the repository, bump the
version, and add a changelog row recording the window it was measured over, the profile hash from
`provenance.endpoint_profile_sha256`, and any unrepresented windows.

Send me the file and I will wire it into the scenario engine. **Do not send `udl-raw-*.json` or
`udl-profile.ini`** - neither crosses the boundary, and the parameter file is sufficient.

## Re-running it later

The characterisation goes stale as the sensor mix changes. Open question 14 in the flight plan is
still open on the cadence; my recommendation stands: review on the same cycle as the procedure
library, and re-run on any known change to the UDL provider set. Because the parameter file records
the profile hash and the window, two runs are comparable and a drift is visible rather than
inferred.

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `no endpoint profile at ...` | no `--profile`, or the path is wrong | step 2 |
| `... is incomplete. These keys are required and empty: ...` | a required blank | fill exactly the keys it names |
| `base_url must be an https:// address` | scheme wrong or missing | `https://` and a host, no trailing slash |
| `... is mode 644, readable beyond its owner` | credentials file permissions | `chmod 600` the file. Refused rather than warned: what this tool can read, another local process can read |
| `has no section with both username and password` | credentials layout | a `[udl]` (or `[DEFAULT]`) section with both keys |
| `the count endpoint returned N characters that are not an integer` | wrong `observation_count_path` | the COUNT path, not the history path |
| `the history endpoint returned an object with no list under data, results or items` | the list is under another key | send me the key name and I will add it |
| `HTTP 401` | credentials, or the account lacks the endpoint | check the credentials file first |
| `REFUSED: $.… holds a bare 5-to-8 digit run` | something identifier-shaped reached the output | send me the message, not the file. This is the guard doing its job and it means a measure is carrying a value it should not |
| `WARNING: N window(s) are NOT represented` | density above the offset cap | narrow the window and run it in parts |

## What I still need from you

1. **The endpoint profile**, or the UDL API documentation to write it from. This is the only thing
   blocking step 4 end to end.
2. **The sensor-label decision** in step 4 - pseudonymised or verbatim.
3. **Open question 14**, the re-run cadence, if you want it settled now rather than at review.
