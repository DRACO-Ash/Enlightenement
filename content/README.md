# Content tree

Versioned training content, loaded and validated by `src/enlightenment/content/`. This is DATA:
a content author edits a procedure's steps or thresholds, or adds a whole procedure, without a
code deployment. Flight plan step 5.

## Layout

One directory per content kind. The directory name IS the kind, so the loader needs no branch
and adding a file needs no code change.

```
content/procedures/  Procedure       the governing Protect and Defend procedure
content/scenarios/   ScenarioTemplate  fixed expected response, seeded instantiation
content/rubrics/     Rubric          how a run against one procedure VERSION is scored
content/traces/      ExpertTrace     what the expert saw, at which tick, and what it told them
```

Files are JSON, one item per file, named `<id>-<version>.json` for readability. The loader keys
on the `meta.id` and `meta.version` INSIDE the file, never on the filename, so a rename is not a
content change.

## The rules the loader enforces

- Every field is validated against the schema for its kind. An unknown key is a REJECTED file,
  not a silently ignored field: a typed key that scores nothing is worse than an error.
- A version is immutable. Two files may not claim the same `id@version`.
- Procedure step ordinals are a contiguous run from one. A gap or a duplicate means a step is
  unreachable or ambiguous.
- Every reference resolves to a LOADED version: scenario to procedure, rubric to procedure,
  trace to scenario. A rubric that floats to the latest procedure version silently rescores
  history, so a rubric pins the version it scores.
- `status: "draft"` never scores a run.
- **One bad file yields NO store, not a partial library.** A partially loaded procedure library
  scores against whichever rules happened to parse. A failed reload keeps the last good tree
  serving, so an authoring typo is not an outage.

## The redaction gate

Runs BEFORE schema validation, because a file that holds a protected-object identifier is a
disclosure risk whether or not it also parses. Four shapes are refused anywhere in a file:

| Rule | Shape | Write this instead |
| --- | --- | --- |
| `catalogue-number` | a bare 5-to-8 digit run | the class of object, or a clearly synthetic designator |
| `url` | any scheme-and-authority address | the action, not the address |
| `windows-path` | a drive-letter or UNC path | the action, not the click-path |
| `chat-channel` | a `#name` token | the reporting route in general terms |

A finding names the rule and NEVER echoes the offending text.

**A stated limit.** A five-digit altitude such as the geostationary belt is refused, because a
bare five-digit run is indistinguishable from a catalogue number by shape alone. The gate fails
closed on purpose; write `35,786 km` or use words. `test_a_five_digit_altitude_is_refused_a_known_and_accepted_false_positive`
pins this so it is documented rather than discovered.

The mechanical gate is half of the discipline. Ash is the redaction reviewer and is the other
half: ENLIGHTENMENT teaches that a protected-object exclusion list exists and must be checked;
it never holds the list. The same applies to internal tool click-paths, channel and product
naming conventions, and OPSEC guidance.

## Validating a file before committing

`enlightenment.content.json_schemas()` emits JSON Schema for each kind, generated from the same
models the loader enforces, so an editor or a pre-commit hook validates against exactly the
rules that will apply. One definition, two consumers, no drift.

```
.venv/bin/python -c 'import json;from enlightenment.content import json_schemas;print(json.dumps(json_schemas()["procedures"],indent=2))'
```

## Status

The schemas, loader and suite are in place and green. **The content itself is not written.** The
plan's step 5 asks for all fifteen procedures seeded as data; the fifteen names and the text for
the three v1 procedures (Manoeuvre, RPO, Separation versus Breakup) are the project owner's to
supply and are NOT inferred here.
