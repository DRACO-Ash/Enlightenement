# Runbook: UDL characterisation pass (flight plan step 4)

**Who runs this:** Ash, on the networked workstation. Nothing in this runbook runs in the container
or in CI, and nothing here needs the repository's virtual environment.

**Shell: PowerShell on Windows.** Every command below is written for it. Where a POSIX form differs
it is given underneath, for anyone running this from Windows Subsystem for Linux or a Mac. The
earlier draft of this runbook was written for a POSIX shell and told you to run `chmod`, which is
the reason this note exists.

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
| `tools/udl_characterise.py` | this repository, `V0.23.19` | **Ready** |
| Python 3.11 or newer on the workstation | already there, or the system Python | `python --version` (PowerShell). If `python` opens the Microsoft Store, use `py --version` |
| UDL credentials at `~/.config/phase_offset/credentials.ini`, mode `600` | your existing file | Check |
| Endpoint profile: `[endpoints]` and `[query]` | the UDL API documentation, supplied 25 August 2026 | **Ready, pre-filled in the template** |
| Endpoint profile: `[fields]` | the service itself, via `--queryhelp` | **Step 2, about five minutes** |

Standard library only, single file, no install step. Copy the one file across and run it.

## Step 1. Prove the analysis half, before touching the network

Do this first. It needs no credentials, no profile, and no network.

```powershell
python .\tools\udl_characterise.py --self-test
```

POSIX: `python3 tools/udl_characterise.py --self-test`

Expect `SELF-TEST: PASS (15/15)` on stderr and a JSON assertion manifest on stdout. The manifest is
the evidence: fifteen named assertions over synthetic records with statistics known by
construction, each with its expected value, its actual value and why it matters. Four of them prove
the boundary in both directions: that a clean parameter file passes, that a planted
catalogue-number shape is refused, that a planted hyphenated marking is withheld from the emitted
distribution, and that it is still counted so the restricted proportion stays true.

If this fails, stop. Send me the manifest; the failing assertion names the problem.

## Step 2. Complete the endpoint profile - now five minutes, not a blocker

```powershell
python .\tools\udl_characterise.py --print-profile-template |
  Set-Content -Encoding utf8 udl-profile.ini
```

`Set-Content -Encoding utf8` rather than `>`: PowerShell's redirection writes UTF-16 by default,
which `configparser` reads as mojibake and reports as a malformed profile.

POSIX: `python3 tools/udl_characterise.py --print-profile-template > udl-profile.ini`

**`[endpoints]` and `[query]` now arrive pre-filled** from the UDL API documentation you supplied on
25 August 2026: the base address, the `/history` and `/count` path convention, the `from..to` range
form, `firstResult`, `maxResults`, and the two time-field names. Read them, correct anything the
documentation has since changed, and move on. The profile is still where a fact about the API is
fixed, so a change belongs here and not in the source.

Two of those values are worth knowing about rather than just accepting.

● **`observation_history_path` names an ENTITY, and the entity is a choice.** The template ships
  `/udl/eoobservation/history`. Change it to `radarobservation` or `rfobservation` if that is the
  sensor phenomenology you want characterised first, and change `observation_count_path` to match.
  One run measures one entity.
● **Element sets range on `epoch`, observations on `obTime`.** Both are in the template as separate
  keys. This matters more than it looks: an unrecognised query parameter returns an EMPTY result
  rather than an error, so one shared field name would have reported "no element sets in this
  window" and been believed.

**`[fields]` - the record field names. This is the only part left, and the service will tell you.**
The documentation covers the query grammar, not the per-entity schemas, so these are the values
neither of us can responsibly invent. Ask the service:

```powershell
python tools/udl_characterise.py --profile udl-profile.ini --queryhelp eoobservation
```

It prints the queryable parameter names with their descriptions, units of measure and formats, and
names any parameter the entity REQUIRES - some entities require a search parameter to stop a query
of millions of objects, and knowing that before a long run is cheaper than discovering it during
one. The mode reads only `base_url` from the profile, so it runs before `[fields]` is filled.

**The queryhelp output is API metadata rather than records, so it is normally the one retrieval you
can paste to me - and the tool checks that rather than asking you to trust it.** The response goes
through the same boundary guard as the parameter file before you ever see it, minus the URL rule,
which is switched off here for a stated reason: a schema legitimately carries `$ref` addresses, so
leaving that rule on would refuse every correct response and the guard would end up deleted rather
than relaxed. The catalogue-number rule, which is the one that matters here, stays on.

● **Clean response:** printed to your terminal, and the closing line says it was checked. Fill
  `[fields]` from it and send it to me.
● **A hit:** the response is **not printed**. It is written to `queryhelp-<entity>.json` in the
  current directory, mode `600` on POSIX, and the command exits `3`. That file is on your
  workstation and has crossed nothing. Read it there, fill `[fields]` from it, and send me the
  **field names** rather than the file.

Refused rather than printed-with-a-caution, because a caution is not a control; saved rather than
simply refused, because a discovery step that will not show you the schema blocks the work. A local
file is neither.

Then two rules govern what you fill in:

● **A blank field is reported as UNAVAILABLE, never estimated.** Fill what you can confirm and leave
  the rest; the output names what it could not measure. An absent measure is honest, an invented one
  is not, so a half-filled profile still produces a usable and truthful parameter file.
● **`sensor_id` and `object_identifier` are required.** They are what make revisit and epoch spacing
  per-sensor and per-object rather than a single meaningless pile. `object_identifier` is read for
  GROUPING only: it is replaced by a per-run salted hash before any statistic is computed and never
  appears in the output.

Keep the profile off the repository and inside your user profile directory. It is workstation
configuration, not content. Nothing in it is a secret, but it is an inventory of endpoints and field
names, which is the class of thing the redaction discipline keeps out of the content tree.

**On permissions, and how Windows differs.** There is no `chmod` in PowerShell, and Windows does not
have POSIX permission bits - `os.stat` reports synthetic ones, so a bit check there is meaningless.
The tool therefore checks the thing Windows actually enforces: your credentials file must sit inside
your user profile, where the default access control list restricts it to you. So
`C:\Users\<you>\.config\phase_offset\credentials.ini` is accepted, and the same file on a shared
drive is refused. On a POSIX machine the tool enforces mode `600` instead and tells you to `chmod`.

Note that OneDrive-synchronised folders live inside your profile but are also copied to the cloud.
Put the credentials file under `.config` in the profile ROOT, not under `Documents`, so it is not
swept into sync.

## Step 3. Retrieve and measure

Start with a SHORT window - an hour - to confirm the profile is right before committing to a long
run.

```powershell
python .\tools\udl_characterise.py `
  --profile udl-profile.ini `
  --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z `
  --raw-out udl-raw-1h.json `
  --emit noise-model-1h.json `
  --verbose
```

The line continuation is a **backtick**, not a backslash. A backslash here silently passes the next
line as a separate argument.

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

Every request carries `disableCapcoExtensions=true`, and it is worth knowing why, because it changes
what you will see in the output. UDL extends CAPCO markings on proprietary and limited-distribution
records to the form `U//PR-OWNER-DATATYPE`, which puts a **data owner's identity inside the marking
string**. The marking distribution is the one measure that crosses the boundary verbatim, so without
the flag the noise model would carry a list of every contributing provider under the name of a
statistic. With it, the service collapses those to `U//PR` and `U//DS`, which keeps exactly what the
measure is for - what proportion of a scenario's data is restricted - and drops the part that has no
business leaving the workstation. It is set in the URL builder, not in the profile, because a control
you can switch off in a configuration file is a default rather than a control.

The flag changes nothing about your obligations on the records themselves. Disabling the extension
does not disclaim the handling duty on anything retrieved, which is the other reason raw records stay
on the workstation.

`--raw-out` saves the fetched records so you can re-run the analysis offline without re-fetching. It
**stays on the workstation**: raw records are not the thing that crosses. On POSIX it is written mode
`600`; on Windows the profile-directory access control is what protects it, so write it inside your
profile and not into a synchronised folder.

Then widen the window. A representative pass wants enough time to cover a full revisit cycle across
the provider set; my recommendation is 7 days, and the sensible check is whether the per-sensor
`n` values are large enough to mean anything - a residual distribution over 4 observations is not a
distribution.

## Step 4. Read the output before committing it

```powershell
Get-Content noise-model-7d.json | python -m json.tool | more
```

POSIX: `python3 -m json.tool noise-model-7d.json | less`

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
| `... is mode 644, readable beyond its owner` | POSIX only: credentials file permissions | `chmod 600` the file. Refused rather than warned: what this tool can read, another local process can read |
| `... is outside your user profile` | Windows only: credentials file location | Move it under your profile, conventionally `C:\Users\<you>\.config\phase_offset\credentials.ini`. Windows has no POSIX permission bits, so location is the control |
| The profile is reported malformed straight after you wrote it | PowerShell `>` wrote UTF-16 | Re-create it with `Set-Content -Encoding utf8`, as in step 2 |
| `has no section with both username and password` | credentials layout | a `[udl]` (or `[DEFAULT]`) section with both keys |
| `the count endpoint returned N characters that are not an integer` | wrong count path | a count path is a query path plus `/count`, so `/udl/elset/history` becomes `/udl/elset/history/count` |
| `REFUSED: ...` from `--queryhelp`, exit `3` | the response held something identifier-shaped | Nothing was printed. Read `queryhelp-<entity>.json` in the current directory: usually a version string or an example value, occasionally not. Send me the field names, not the file |
| `... is not an entity name` | `--queryhelp` got something other than a bare lowercase token | `eoobservation`, `radarobservation`, `rfobservation`, `elset`. Refused rather than escaped: the value goes into a URL that carries your credentials |
| A query returns zero records over a window you know is busy | a query parameter the entity does not recognise | check `time_field` and `elset_time_field` against `--queryhelp`. An unknown parameter returns an empty result rather than an error, which is the one failure mode here that looks like an answer |
| `the history endpoint returned an object with no list under data, results or items` | the list is under another key | send me the key name and I will add it |
| `HTTP 401` | credentials, or the account lacks the endpoint | check the credentials file first |
| `REFUSED: $.… holds a bare 5-to-8 digit run` | something identifier-shaped reached the output | send me the message, not the file. This is the guard doing its job and it means a measure is carrying a value it should not |
| `WARNING: N window(s) are NOT represented` | density above the offset cap | narrow the window and run it in parts |

## What I still need from you

1. **The `--queryhelp` output for the entity you want characterised first** (step 2). This is the
   last unknown: the record field names. It is API metadata rather than records, and the tool scans
   it and tells you so before you send it. Paste it to me and I
   will map it onto the profile's logical fields. Nothing else blocks step 4 end to end.
2. **The sensor-label decision** in step 4 - pseudonymised or verbatim.
3. **Open question 14**, the re-run cadence, if you want it settled now rather than at review.
