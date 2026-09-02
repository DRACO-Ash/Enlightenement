# Changelog: Enlightenment

One audit row per change: what changed, why, and how it was verified.

## V0.26.14 (2026-09-02)

**What.** Two majors. A SIXTH instance of the shortened-identifier class, outside the module a
scoped sweep had cleared, and a claim in the V0.26.13 audit row that was false: one of the five
mutations it said were "each killed by its own test" was killed by nothing.

**The sixth instance.** `training_api` named an authored identifier in the anonymous
`document_too_large` 503 through a **cross-module import of a private helper** - which
`bounded_reason`'s own docstring forbids, and while the public `served_identifier` already existed.
Two procedure ids sharing an 85-character prefix, both over the reference budget, were refused under
ONE name matching neither id an author wrote. A `drill.py`-scoped sweep missed it, which is why the
rule is "one function, everywhere" rather than "this module is clean".

**My own claim, false.** V0.26.13 said the served drill payload's `item_id` AND `cue_id` collapsed
and that five mutations were each killed. Reverting the `cue_id` site left all 978 tests green,
because the reshape stopped at `row["id"]`: the tree still put the distinguishing part BEFORE the cap
for `cue_id`. **The identical shape fault, one field along, in the file whose own comment names
`cue_id` as the field that "asserted nothing" once before.** The reshape did not go far enough, and
that is what left `cue_id` and the dashboard's `competency_id` unheld while the row claimed them.

**Four distinctness assertions where there were length assertions.** The served `cue_id` across the
traversal, the reveal's `item_id` on the answer route, the dashboard's `competency_id`, and the two
oversized library documents in the 503. Each was a separate live collapse and each dies to its own
mutation now.

**What is NOT held, said plainly rather than counted as covered.** Five call sites survive inversion:
`procedure_id` and `axis` on the run record, the refusal name in `_serve_one`, and the unread-params
census key. All are write-only audit labels or a census dimension nothing compares, verified by
reading every consumer rather than assumed. They use the one function for consistency, so the next
site is right by default, and they are recorded here as unheld rather than folded into a count.

**The migration question, answered with a measurement.** Routing the STORED `RunRecord.item_id`
through the shortening function changes the form of an existing progress row. The longest identifier
anywhere in the shipped library is 30 characters, measured across every id leaf, so the shortened
form equals the raw form for every shipped id and no existing row can hold a different one. Nothing
is deployed. The residual, bounded and non-corrupting: `CONTENT_DIR` is a supported operator knob, so
a tree with ids over 64 characters plus a pre-V0.26.13 progress file resets that item's attempt count
to zero ONCE, giving one repeated seed before it self-heals as new rows are written in the new form.
No code, one sentence, which is what the evidence supports.

**How it was verified.** Loop green on all seven legs: 979 passed, 2 skipped, coverage 97.42%. Four
mutations, each killed by its own test: the 503 name, the payload `cue_id`, the reveal `item_id`, and
the dashboard `competency_id`.

## V0.26.13 (2026-09-02)

**What.** The V0.26.12 fix for the keying bug was itself held by no test, and the gate proved it by
**reinstating the live product bug with the whole suite green**. Two more instances of the same class
were live and unfixed, and reshaping the hostile tree to find them exposed a fifth. One blocker, two
majors, two minors.

**The fix that was held by nothing.** Keying `_unresolvable` on the SHORTENED id keeps every key
inside the cap and collision-distinct, so the wire stays honest and the collision test still passes -
and `select` still compares a raw id, so a long-id item is declared withheld and served anyway. The
collision test only ever caught a bounded key because bounded keys collapse PREFIX-SHARING ids; it
never reached exclusion. That is precisely how the bug survived from V0.26.6 to V0.26.11. The
exclusion is now asserted on an item with a long id and no prefix-sharing sibling: the manifest names
it AND twelve consecutive serves never return it.

**A promise the docstring makes and the code broke.** `RunRecord.item_id` is stored shortened,
because the progress file is read whole on every request, and `serve` counted attempts against the
RAW id. For any id over the cap the count was permanently zero, so `_seed` lost its attempt component
and every re-drill of that item redrew the identical stimulus - **three attempts, one distinct
seed** - against a docstring promising "a stable seed per operator, item and attempt".

**A fabricated identifier still on an anonymous route.** `due_items` served three distinct authored
ids as ONE name, which is the fault `served_identifier` was written to end, on a line the previous
release did not touch.

**And a fifth, found only by reshaping the tree.** The served drill payload's own `item_id` and
`cue_id` collapsed the same way. The hostile tree's ids differed BEFORE the cap, so nothing collapsed
and three distinctness assertions could not fail; moving the distinguishing part past the cap turned
`due_items` red and then turned the traversal red on a fault nobody had named. **A hostile tree has
to be hostile in the SHAPE a fault needs, not only in length.**

**The rule this release actually installs.** Every shortened IDENTIFIER goes through one function, at
every wire and every storage sink, so the next site is right by default rather than right if somebody
remembers. Five instances, each having survived the fix for the one before it, is not five oversights;
it is a rule that existed in one place and was applied by hand everywhere else. A competency NAME
keeps the plain bound, because prose is not an identity.

**Named limits, recorded rather than defended.** The digest is 32 bits - collision-free by a wide
margin inside a 25-entry cap, grindable by a determined content author - and `~` is not reserved, so
an author could write a 63-character id ending in a tilde and eight hex digits that reads as
shortened. Neither matters at these stakes.

**How it was verified.** Loop green on all seven legs: 978 passed, 2 skipped, coverage 97.42%. Five
mutations, one per instance, each killed by its own test - including the gate's own reinstatement of
the original bug, which now fails on the exclusion assertion. Two register rows.

## V0.26.12 (2026-09-02)

**What.** Two blockers, two majors, two minors - and for the first time in this sequence the finding
is a **live product bug rather than a test weakness**, introduced by one of my own fixes and hidden
for six releases behind the tests that were supposed to hold it.

**The bug.** `_unresolvable` was keyed on the BOUNDED item id from V0.26.6, and `select` tests
membership with the RAW id. So any authored id over 64 characters was **declared withheld on the
anonymous manifest and still selected**. Measured at 65 characters: 94 declared, zero excluded.
Measured at 3,007: eight consecutive serves returned the same item with no run recorded, no rating
movement and no schedule advance.

**That is the absorbing state this project closed at V0.26 and the serve-time withhold feedback it
added at V0.26.1, both defeated, on a route that needs no token, while `CLAUDE.md` and
`docs/SECURITY.md` recorded both as closed.** The bound was a real fix for a real fault applied to
the wrong thing: a bound belongs at the wire, where a string is a disclosure, not at the key, where
it is an identity. Keys are raw now.

**And my diagnosis of it last release was the wrong half.** V0.26.11 said the fixture stalled
because an unscorable item advances no schedule. It stalled because **the exclusion never happened
at all**, and making the withhold poison opt-in hid the bug rather than isolating it.

**A fabricated name on an operator-facing surface.** `_bounded` truncates without a marker, so ids
sharing a 64-character prefix collided: 140 distinct authored ids served ONE entry, under a synthetic
id matching nothing an author wrote, while the gap was 94 items wide. Two rules broken in one line -
never invent a name, and never let a shortened disclosure read as a complete one. A cut id now
carries an eight-character digest of the whole string, so two shortened ids differ and a reader can
see it was shortened.

**A total that was wrong in both directions and bound by nothing.** It overstated - 94 withheld
while zero were excluded - and understated, reporting 1 for 94 on colliding keys. Replacing it with
`len(...) * 7 + 1000`, and with a hardcoded 26, both left the whole suite green. It is computed
before any bounding now, and its VALUE is pinned against a measured literal, because a range check
alone admits any number over the cap and a hardcoded 26 survived one.

**An assertion vacuous by construction, on the line written to end that.** The check meant to hold
the total ended `or total > MAX_SERVED_WITHHELD` - the exact condition asserted four lines above -
so the disjunction was unconditionally true and the equality branch was dead code.

**A ceiling green only because of the bug.** `GET /api/v1/drill/next` carried the 16 kB diagnostic
ceiling over its whole body, and passed only because the defective `select` drew the one small item;
with selection working it serves 120,000 bytes of legitimate stimulus on the hostile tree. The sweep
now splits any body carrying a stimulus: the envelope against the diagnostic ceiling, the stimulus
against `MAX_PAYLOAD_BYTES`.

**Arithmetic corrected and named.** The envelope is measured with the separators and `ensure_ascii`
setting the route actually renders, in one shared helper, and the twelve-byte approximation from
reconstructing it out of the remaining keys is stated where it is made.

**A third destructive `git checkout` in one session, recorded because it cost real work.** I ran
`git checkout HEAD -- src/enlightenment/training/drill.py` while it carried every uncommitted repair
above. Replayed step by step with a `count(old) == 1` guard on each, then **every control re-proved
by mutation**, because a replay is not evidence. One of those mutations re-introduces the original
keying bug and is killed by the collision test, which is the strongest form of the guarantee.

**How it was verified.** Loop green on all seven legs: 976 passed, 2 skipped, coverage 97.42%. Four
mutations after the replay, each killed by its own test: re-keying on the bounded id, colliding the
served ids, uncapping the list, and hardcoding the total. Two register rows.

## V0.26.11 (2026-09-02)

**What.** The ninth surface, two majors and three minors. The ninth is the same shape as the eighth
one order along: two collections that were bounded per entry and uncapped in COUNT, so their size
was set by the number of drills and by accumulated runtime state rather than by any limit the server
holds.

**The ninth surface.** `items_without_a_resolvable_answer` and `withheld_reasons` on the anonymous
manifest. Measured on a tree that loads clean and answers 200: **140 drills served 17,014 bytes -
already over this project's own 16 kB ceiling - and 560 served 64,675.** The runtime path is worse
than the content path, because `_withhold` adds an entry per render refusal carrying a reason up to
256 characters rather than the 32-character load-time one, so the route grew over the container's
life. Every sibling field on that same dict was already count-capped; these two were the odd ones
out, against this module's own sentence that entry count and per-entry length are different limits.
Capped at `MAX_SERVED_WITHHELD`, with the **untruncated total served beside them**, because capping
a disclosure without saying how much was cut turns "these are the gaps" into "here are
twenty-five of an unstated number".

**And the ceiling could not see it, exactly as this file says a ceiling cannot.** With ids bounded
to 64 and load-time reasons at 32 characters, 140 uncapped entries are about 13 kB - under the
ceiling - so both caps survived inversion until an explicit count assertion existed, guarded by a
check that the tree withholds more than the cap admits.

**An assertion that asserted nothing, for the second time on the same line.** `cue_id` was bounded
in code and the hostile tree never stretched it, so real seven-character cue ids made the assertion
vacuous and deleting the bound left the whole suite green. The V0.26.10 changelog claimed that
mutation was killed. True of `item_id`, untrue of `cue_id`, in a sentence naming both.

**A guard defeatable from an unrelated constant.** The traversal's answer POST had no status
assertion, and `DRILL_LIMIT` is 20 against a 24-draw loop, so four draws already re-measured one
item at head; lowering that unrelated constant to 5 left the test green while it measured six items
of 140. The answer must now return 200, a permissive limiter is injected for this test because it
measures size rather than rate, and the floor is set from what the traversal actually reaches.

**A fixture that reproduced a fault the product had already fixed.** Making every item unresolvable
to lengthen the withheld collections also made every item unscorable, and an unscorable item records
no run and advances no schedule - the absorbing state closed at V0.26, rebuilt in a test fixture.
The traversal drew one item of 140 and its own guard caught it. The withhold poison is now opt-in
and the two trees are separate.

**Arithmetic that was wrong in the loose direction.** The envelope was measured by subtracting a
re-serialisation, and `json.dumps` defaults differ from what `JSONResponse` renders: understated by
up to 7,643 bytes and **negative on six of twenty-four draws**, where the assertion held nothing and
would have printed a negative byte count as its diagnosis. Measured directly now.

**One measurement, two figures, again.** 342,786 against 342,884 for the same stretched product,
in the comment whose neighbouring figure the previous release corrected.

**How it was verified.** Loop green on all seven legs: 974 passed, 2 skipped, coverage 97.42%. Six
mutations, each killed by its own test: both withheld count caps, `cue_id`, `item_id`, and the two
re-proved from the previous round. The changelog binding tightened at V0.26.6 caught the missing
audit row for this release before the loop would go green, which is that check doing its job for the
third release running.

## V0.26.10 (2026-09-02)

**What.** One blocker, three majors and two minors. The eighth surface is not a field: it is that a
sweep enumerating ROUTES still certifies whichever STATE a stateful route happens to serve from.
And the V0.26.9 rebuild of that sweep silently deleted two assertions it inherited, which is a
control lost to a refactor of the test that held it.

**The eighth surface.** `/api/v1/drill/next` is idempotent until answered, so the route sweep
measured one item out of 140. Driven serve-then-answer across the item space on the same hostile
tree, **eight of the first twenty-one items exceeded the ceiling, to 145,130 bytes** - 8.9 times the
ceiling and 17 times the "measured hostile maximum" the previous entry asserted. The V0.26.9 pass
was an accident of draw order.

**And the ceiling on that route was the wrong control anyway.** The overflow is `stimulus`, which
answers to `MAX_PAYLOAD_BYTES` - a four-megabyte picture budget structurally incompatible with a
16 kB text ceiling. The two are split now: the diagnostic envelope against the ceiling, the rendered
stimuli against the payload budget. V0.26.8 excluded this route on a false rationale and V0.26.9
included it under a false ceiling; both were one number doing two jobs.

**A control lost to a refactor.** Rebuilding the sweep at V0.26.9 deleted the two count-cap
assertions on `/api/v1/me` that V0.26.8 had added, and the register went on citing them. Both caps
returned to surviving inversion. Restored, with a non-vacuity guard, and the deleted block's own
reason restated: a body ceiling cannot see a count cap that never bites, because 140 uncapped due
items with bounded ids are about 9 kB.

**Bounds the code had and no test agreed with.** `item_id` and `cue_id` on the served drill were
`_bounded` at V0.26.9 and asserted by nothing: reverting both left the whole suite green, because at
3,003-character ids the body reached about 6.5 kB, under the ceiling. The changelog claimed they
were bounded. True of the code, unheld.

**The discovery filter was still narrower than the claim.** It scoped to `startswith("/api/")` and a
hand-written method set, so a DELETE route or a JSON route under another prefix was invisible to the
sweep AND to the exact-set assertion that exists to notice narrowing. It now takes the whole route
table and subtracts HEAD and OPTIONS, and every exclusion - the five health paths, `/`, the three
`/ui` routes, the three session routes - is named with its reason rather than made by a filter.

**A figure that was measured wrong.** "The largest product is 2,304 bytes" was the product document
alone; the route serves the layout beside it, and the largest is 5,616. The conclusion is unchanged
at 4.7 times headroom, but the number was asserted and untrue.

**What the gate confirmed rather than found.** Fail-closed-with-503 on the library documents is the
right call over bounding the leaves, and 64 kB is the right budget. `cues[]` and `thresholds.source`
are not content surfaces: the first reaches the wire only as `cue_id`, the second is set by loader
code from a fixed filename.

**A process failure of mine, recorded because it cost real work.** Splitting an over-long test, I
ran `git checkout -- tests/test_training_api.py` and destroyed every uncommitted repair in that
file. This project has recorded that exact mistake before. The work was replayed from the session
rather than reconstructed from memory, and every control re-proved by mutation afterwards rather
than assumed to have survived the replay.

**How it was verified.** Loop green on all seven legs: 974 passed, 2 skipped, coverage 97.42%. Six
mutations, each killed by its own test: `item_id`/`cue_id`, both count caps, `prompt`, `explain`,
and the narrowed route discovery.

## V0.26.9 (2026-09-02)

**What.** The V0.26.8 sweep was written to end this class and was itself three instances of it. Two
blockers and five majors, all taken. **Seven surfaces now, across five releases: each fix correct
and each sweep incomplete, because the sweep kept being narrower than the sentence describing it.**

**The seventh surface, and why the sweep could not see it.** `POST /api/v1/drill/answer` takes no
token and `ScoredDrill.as_dict` served raw `explain`, `note` and `why_wrong`: 201,084 bytes from one
stretched authored field. The sweep filtered on `"GET" in methods`, so an anonymous POST was
invisible to it by construction.

**Two more the path filter dropped.** `"{" not in path` silently excluded both library routes.
Measured anonymous: 2,497,065 bytes for a procedure and 342,884 for a product. An undocumented
regex was making a scoping decision that belongs to the owner and the register.

**The exclusion that rested on a false claim.** `/api/v1/drill/next` was excluded because
`MAX_PAYLOAD_BYTES` was said to govern it. That budget governs the rendered stimuli only: it saw
2,904 bytes of a 206,027-byte body whose `prompt` was 200,085. `prompt`, `item_id` and `cue_id` are
bounded now and the route is swept like the rest.

**The control could not tell it had stopped controlling.** Narrowing the discovery filter to a
single route left the test green - `assert paths` only asked that the list was non-empty. And the
five explicit assertions passed over empty collections, which is the "assertion that cannot reach
the mechanism" fault reproduced inside the fix for it. The discovered set is now compared against
an EXACT expected set, every swept route must be reached, its status is asserted before its size,
and an empty measurement fails.

**The exact-set assertion earned itself immediately.** It refused to pass until
`PATCH /api/v1/sessions/{session_id}` was listed - a route the previous filter had never seen.

**A route certified by a measurement of nothing.** `/api/v1/sessions` was swept against an empty
fixture store at 33 bytes, and the 64 kB ceiling would have failed falsely the moment anyone
populated it: twenty legitimate sessions are 49,394 bytes against a store admitting five hundred.
It is excluded by name for two independent reasons, either sufficient - it is token-gated, and its
size is governed by `MAX_SESSIONS` rather than by content.

**The library routes fail closed rather than truncate.** Their fields are NOT individually bounded,
because the flight plan makes the procedure and product library an anonymous reference and a
per-field cap would mutilate it. An over-budget document is refused with a 503 naming it, on a
64 kB budget measured against the shipped library's 13,888-byte largest procedure. A companion
assertion proves the real library still serves, so the fail-closed branch is not bought by refusing
everything.

**And my own hostile tree skipped a file.** It listed `procedures.json`, which does not exist -
procedures live under `procedures/procedures-core.json` - and the loop skipped it with `continue`,
so the procedure route was swept against unstretched content and its mutation survived. The file
list now comes from the loader's own manifest. A tree that silently skips a file certifies the
fields it happened to poison, which is the fault this whole control exists to end.

**The ceiling, tightened on measurement.** 64 kB caught two of five real faults in isolation
testing, because a 32 kB body fitted under it. 16 kB for the diagnostic routes, against a measured
hostile maximum of 8,131 bytes and honest bodies far smaller.

**The token claim, made true.** The register said these routes answer "with a team token
configured"; the fixture the test used sets an empty token. It uses `token_config` now.

**How it was verified.** Loop green on all seven legs: 973 passed, 2 skipped, coverage 97.42%. Five
mutations against the rebuilt control, each killed: prompt, explain, procedure, product, and the
narrowed route discovery that previously passed.

## V0.26.8 (2026-09-01)

**What.** Fourth consecutive release in which this project recorded the unbounded-anonymous-string
class as closed while a surface was live. The gate found a FIFTH and SIXTH, both on `/api/v1/me`,
and disproved a claim V0.26.7 made about a guard. The fix this time is not another bounded field: it
is a control that enumerates ROUTES, because a per-field assertion can only ever hold the fields
somebody thought of, and that is precisely what kept getting through.

**Surfaces five and six.** `due_items` was a bare `[:20]` over raw drill ids and the competency `id`
and `name` had neither a length bound nor a count cap. Measured on the shipped library with ids
stretched to 3,010 characters and names to 20,000: **221,589 bytes from a route that needs no token
even when one is configured.** All four are bounded now, with `MAX_SERVED_DUE_ITEMS` and
`MAX_SERVED_COMPETENCIES` named rather than left as literals.

**The control that should have been written three releases ago.** A new test walks the app's own
route table, calls every anonymous API GET that is not the drill payload, and asserts a body ceiling
on a hostile tree. A new route, or a new raw content string on an existing route, now fails there
without anyone having to spot it. `/api/v1/drill/next` is excluded by name: it serves the product
payload under the explicit `MAX_PAYLOAD_BYTES` budget, and folding a 4 MB allowance into this
ceiling would make the ceiling meaningless.

**Why the ceiling alone is not enough, measured rather than assumed.** The first version of that
test caught one of the four faults. Twenty raw 3,010-character ids are 60,200 bytes, which fits
under any ceiling loose enough for honest content, and the competency cap was unfalsifiable because
the shipped library has eight competencies against a cap of thirty-two - a cap nothing can reach is
not a control. So explicit count and length assertions sit beside the ceiling, and the hostile tree
now carries more competencies than the cap admits and poisons every field the route serves. An
earlier version poisoned names and not ids, and certified the fields it happened to poison.

**A claim of mine the gate disproved by running it.** V0.26.7 labelled the denial-path `re.escape`
"defensive only... the escape cannot change an OUTCOME here", arguing that rule one returns early
whenever the response names a direction outside the wanted set. The counter-example is a response
that names no direction at all: token `east(`, response "not moving". Rule one does not fire, the
raw stem is interpolated, and unescaped it raises `re.error: missing )` out of `_contradicted`, out
of `DrillLoop.score`, into a 500 - `training_api` catches `DrillError` and not this. **The label was
wrong.** Both escape sites are outcome-bearing, the comment says so, and case C holds it.

**And the case that was supposed to fix a wrong narrative had a wrong narrative.** V0.26.7's group A
claims `east[a-z` reaches the denial pattern as the stem `east[az`. It does not: both its responses
name the real word "east", so rule one returns first, and with BOTH escapes deleted those two
assertions still passed. The same "described mechanism the assertion cannot reach" fault, reproduced
inside its own fix. Group A is kept for the positive-match escape and the narrative is corrected
rather than the assertions left looking like more than they are.

**The register row, rewritten and SCOPED.** It asserted universally that every content-supplied
string on an unauthenticated route is bounded. That was false three releases running. It now records
all six surfaces, names the enumerating control, and states plainly what it does not prove: it holds
the anonymous API GET routes the app declares, on the fields the hostile tree poisons, and it is not
a proof that no unbounded string exists.

**How it was verified.** Loop green on all seven legs: 973 passed, 2 skipped, coverage 97.40%. Ten
mutations, each killed by its own test: five on `/api/v1/me` (two length bounds, two count caps, the
competency id), the denial-path escape, and the four from V0.26.7 re-run. Two of my own mutation
runs initially reported a false pass and were re-run with `__pycache__` purged, which is the same
harness fault the gate reported against itself last round.

## V0.26.7 (2026-09-01)

**What.** The engineering gate failed V0.26.6 with one major and five minors, and the major is the
worst kind this project produces: **there were FOUR surfaces carrying the unbounded-string fault,
not three, and the fourth was live in the file V0.26.6 edited, 110 lines from the fix, while
`docs/SECURITY.md` recorded the class as closed.** Measured on the hostile tree that release's own
new test already builds, `/api/v1/content/manifest` served 86,317 bytes - LARGER than the
85,151-byte response cited as the defect being shut. The release's central sentence, "a bound
applied at one of two exits is a bound at neither", was reproduced by the fix for it.

Bounded per entry now, with the count cap named as `MAX_SERVED_ERRORS` and shared by both routes
rather than repeated as a literal in each, since the two literals had already drifted apart once.

**All four count caps were unheld, and the docstring claimed otherwise.** The gate deleted each of
them - the 503's twenty, the manifest's twenty, the census's twenty-five - and the whole suite
stayed green, while the test said "the count cap stays: both are needed, and either alone is not a
bound". Every scenario poisoned exactly as many rows as its cap admits, so no cap ever had anything
to cut. The hostile trees now author twice the cap, and each cap dies to its own mutation.

**A guard that cannot change an outcome, said so rather than left to look tested.** `re.escape` has
two sites. Only the positive match can decide a verdict: `_contradicted`'s rule one returns early
whenever the response names a direction outside the wanted set, and a hostile stem is never a real
compass word, so any response reaching the denial-path pattern also fails the positive match. The
denial-path escape is kept and labelled defensive-only, because that reasoning is a property of rule
one's ordering rather than of the line itself.

**And its comment described a mechanism that cannot occur.** The test said an unescaped `east[a-z`
would compile to "east followed by one letter" and accept "eastx". It does not compile at all -
`re.error`, an unterminated character set - so the silent-over-match half was claimed and never
tested. Two tokens now: `east[a-z` for the raise, `east.` for the silent over-match.

**A refusal to take a gate's suggested fix.** The gate proposed adding `tools/` to the upload
allowlist so the verification loop can run from an unpacked artefact. Refused:
`tools/udl_characterise.py` reads real UDL credentials and the flight plan is explicit that it runs
on the networked workstation and never ships, which
`test_the_workstation_tools_never_reach_the_upload_or_the_image` holds in both contracts. Adding it
would have put a credential-reading script into the artefact to buy a convenience. The limitation is
real and is now documented at leg 2 of `verify.sh`, which is the gate's own alternative: the
platform runs pytest against the zip, not this loop.

**The rename was half-landed.** `bounded_reason` was public but absent from
`training/__init__.py`, so `training_api` imported it from the submodule two lines below importing
its siblings from the package - which is the divergence the rename existed to prevent. Re-exported.

**One measurement, two figures.** The changelog said 4,253 characters and "reproduced exactly"; the
code comment and the test said 4,247, and twenty errors six characters apart cannot both give
85,151 bytes. My measurement is 4,253 and that figure is now in all four places, with the changelog
saying two runs of one scenario rather than claiming they matched.

**How it was verified.** Loop green on all seven legs: 972 passed, 2 skipped, coverage 97.40%. Seven
mutations this round, each killed by its own test: the manifest per-entry bound, all four count
caps, the outcome-bearing escape, and the census cap. One register row rewritten from three
surfaces to four, and it now records that the count caps were unheld until this release.

## V0.26.6 (2026-09-01)

**What.** Both gates passed V0.26.5 - the first commit in this project where engineering and
security have passed the same build. Neither found a blocker or a major. Between them they left ten
minors, and this release takes all ten. Two of them were false claims of mine and one was a false
claim in `CLAUDE.md`.

**A refusal must not quote content.** The security gate proved a disclosure channel rather than
arguing one: it set `newest_at` to a real accept string from DRL-0005's own key, and the anonymous
`/api/v1/content/manifest` served the string back inside `withheld_reasons`. Nothing scoreable
travelled, because `newest_at` is a two-value layout flag, and nothing bound the message either. A
validation refusal now names the KEY and its DOMAIN. Structural identifiers - a generator name, a
product id - are still named, because a typo in one is undiagnosable otherwise, and both are
length-bounded on the way out.

**A count cap and a length cap are different bounds.** Three surfaces carried the same fault, and
the withhold reason bounded at V0.26.3 was the third of them rather than the only one. The anonymous
content 503 capped the error LIST at twenty and not the errors: reproduced on the same hostile
tree, twenty errors, the longest 4,253 characters, 85 kB served without a token. The gate's own run
measured 4,247 on the longest, six characters apart - two runs of one scenario rather than one
figure, and the earlier text said "reproduced exactly" of figures that were not identical. The manifest capped
`stimulus_params_unread.params` at twenty-five entries and not the NAMES: a 500-character authored
key served verbatim, and an unread parameter is by definition one no renderer honours, so any string
becomes a key there just by being authored. And the withheld item ID was raw content at both write
sites: forty items with 3,003-character ids produced a 243,539-byte anonymous manifest, of which
242 kB was ids and 32 characters was the longest reason - under a comment saying content does not
get to set the size of an anonymous response.

**And bounding the key alone made the message useless.** Every refusal prefixes its message with
the item id, so a 3,004-character id filled `MAX_WITHHOLD_REASON` before the sentence began: the
served reason was the id and the truncation marker, and the diagnosis was truncated away. That is
the exact failure the mark exists to prevent, produced by the fix for a different fault. The id is
bounded where the reason is composed as well as where it is stored.

**`MAX_WITHHOLD_REASON` is 256 CODE POINTS.** Measured: 256 astral characters are 988 UTF-8 bytes,
so the 140-item ceiling is about 138 kB, not the 36 kB a reader computes from "256 x 140". Stated
rather than quietly changed. The code-point cap is kept, because buying four times on an
already-bounded response is not worth a new way to emit invalid UTF-8.

**A guard held before it is load-bearing.** `re.escape` on the derived direction token survives
deletion, because `expected_text` is only ever one of four literals today. Unheld rather than
exploitable, and both readings are right - the guard is the cheaper of the two things to keep. A
metacharacter-bearing token would either raise `re.error` inside scoring, failing an operator's
submission on content they cannot see, or silently match something the plot never drew.

**A binding test that did not bind, and the false claim it supported.** The changelog version
assertion read `f"## V{major_minor} "`, so it looked for `## V0.26 ` and was satisfied by any older
V0.26.x heading. The gate defeated it two ways: renaming the newest heading to `## V0.27.9`, and
suffixing it to `## V0.26.55`, both green. **A patch release with no audit row shipped green**, while
`CLAUDE.md` claimed six tests bind this document "so a missed site fails the loop rather than
shipping". The major.minor form was not a shortcut but a mistake about what varies: this project
bumps the patch on EVERY change by owner decision, so major.minor is precisely the component that
does not identify a build. It asserts the full version now, and both defeats fail.

**A diagnosis that sent a reader to the wrong line.** One regex covered both the drain and the
disconnect, so dropping `.disconnect()` reported "the list is not drained" - and the list IS
drained, `pop()` empties it; the observers are simply dropped still live. Two assertions now, with
their own messages, each verified against its own mutation. The changelog row that described it
wrongly is corrected too.

**Declared brittleness.** The two shape regexes reject three behaviour-identical refactors, and no
JavaScript formatter runs in the loop to trip them. That is deliberate and fails closed, but it was
undeclared: the comment now names which reformats will trip it, so the next author reformats the
test rather than reverting the code. The known survivor is named in the same place - inserting
`plotRefits.splice(0);` after the push is a real leak both regexes accept, because it is an
insertion and no mutation operator produces one.

**Ledger corrections.** The V0.26.5 table described "every guard the two releases add"; four of its
ten rows are pre-existing guards newly BOUND, not new code. And it omitted the truncation mark,
which is a separate control from the length bound with its own killing mutation. Both fixed, and
every row re-verified by running it rather than by reading it.

**How it was verified.** Loop green on all seven legs: 972 passed, 2 skipped, coverage 97.40%.
Fourteen mutations this round, each killed by the test written for it, each applied with a
`count(old) == 1` guard. Four register rows.

**Three test harnesses of mine that asserted nothing, all caught before commit.** One stretched an
item id in the parsed JSON after the package had loaded, so `_named` refused an id the library did
not have and `pytest.raises` passed on the wrong error. One bounded only the load-time withhold and
left the serve-time write site alive. One built a hostile content tree as a lone `drills.json` in an
empty directory, so loading stopped at "missing: cues.json", the errors were 44 characters, and the
mutation survived - the error had to be the one that quotes content, which only the real tree with
one poisoned field produces.

## V0.26.5 (2026-09-01)

**What.** The engineering gate failed V0.26.4 with one major, and it is the same pattern a THIRD
time - this instance introduced by the fix for the second. Three minors alongside it, all taken.

**The observer release was held by nothing that mattered.** The three assertions V0.26.4 added
checked that the strings `releasePlotRefits` and `.disconnect()` appear in the served source.
Neither could see whether anything is ever TRACKED, nor whether the release DRAINS. Deleting
`plotRefits.push(refit)` left the release iterating a permanently empty array, and `while` to `if`
released one observer per redraw while the list itself grew without bound - two leaks, both with 967
tests green. Bound to the shape now, and the comment beside the assertions says they hold the shape
and not the behaviour, because that is all a grep can do. Three mutations kill them.

**A bound with slack is not a bound against a literal.** The budget-message assertion allowed
`MAX_WITHHOLD_REASON + 128`, where the 128 came from nothing: a 384-character allowance against a
real 317-character message. The fixed prefix is measured now, so the limit is the bound plus exactly
what the sentence costs, and this exit is held to MARKING its cut as well as bounding it - the
sibling control on the same message already carried that rule.

**A count is not evidence.** V0.26.4 said "six mutations this round, each killed by its own test",
in the entry that records "mutate every guard the range ADDS" as its own lesson. A count cannot be
checked by a reader, and it was not even true: that range added a guard whose inversion survived the
whole suite. Replaced with a table of every guard these two releases add OR NEWLY BIND, the mutation
applied to each and how it fails.

**Placement recorded rather than left to be guessed.** `releasePlotRefits()` sits outside
`loadDrill`'s `try`, deliberately, and now says so: the array only ever holds ResizeObserver
instances created under the `typeof` guard and `disconnect()` does not throw, but a future entry
that could throw would reject before `banner(error.message)` exists, leaving the operator with the
loading text and no error.

**How it was verified, enumerated rather than counted.** Every guard these two releases add
OR NEWLY BIND, and the mutation applied to each. Rows one to four are pre-existing guards given a
driver, not new code: the fold guard and the `_withhold` dedupe both pre-date V0.26.4.

| Guard | Mutation | Result |
| --- | --- | --- |
| `matching.py` fold guard `joined in COMPASS_DIRECTIONS` | deleted | fails on `"east west east"` |
| `drill.py` `_withhold` dedupe | deleted | fails on the overwritten reason |
| `drill.py` dedupe, reason half only | log on every call | fails on the log-line count |
| `drill.py` dedupe, log half only | reason overwritten | fails on the kept reason |
| `drill.py` `_bounded_reason(str(last))` | reverted to `{last}` | fails at 3,061 characters |
| `drill.py` `bounded_reason` truncation mark | dropped, bound kept | fails on the missing mark |
| `app.js` `releasePlotRefits()` call | deleted | fails on the call ordering |
| `app.js` `releasePlotRefits()` call | moved after `clear()` | fails on the call ordering |
| `app.js` `plotRefits.push(refit)` | deleted | fails: nothing is tracked |
| `app.js` `while` in the release | narrowed to `if` | fails: the list is not drained |
| `app.js` `.disconnect()` | dropped from the pop | fails: observers dropped still live |

Loop green on all seven legs: 967 passed, 2 skipped, coverage 97.19%.

## V0.26.4 (2026-09-01)

**What.** The engineering gate's sixth round failed V0.26.3 with two majors, and both were controls
inside the changes I had just made: it ran 21 mutations against my twelve and found two that
survive inversion with the whole suite green. Its verdict on my twelve was that the claim is true
and not sufficient, which is the correct reading.

**A comment named the wrong pair, so the test written from it never reached the control.** The
spaced-compound fold added in V0.26.3 is guarded by `if joined in COMPASS_DIRECTIONS`, and deleting
that guard left 966 tests green while giving `"east west east"` full credit for an eastward drift -
a self-contradictory answer, scored correct. The root cause is not the code. The comment said the
guard exists "so `north west` stays two directions", and that is false: `"northwest"` IS in
`COMPASS_DIRECTIONS`, so `"north west"` folds like any other compound and is refused, when wrong,
by the names-another-direction rule. The guard's real domain is the pairs that form NO compound.
I wrote the test from the comment rather than from the code, so both of its cases fold and neither
reaches the guard. Group F now carries `"east west east"`, `"east west, definitely east"` and
`"north south east"`, and keeps the folding pair separately so the two paths stay distinguishable.

**A control closed with prose alone, in the release whose own entry names that pattern.** V0.26.3
answered the dedupe minor with a seven-line paragraph defending first-reason-wins and no driver for
it. Inverting the guard to last-writer-wins left all 966 tests green, and the coverage report had
already named the gap: the already-withheld branch was never taken anywhere in the suite. The
rationale was sound - `_named` does not consult the withheld set, so the case genuinely arises, and
the load-time reason is the one that explains why an item was never served - but a sound rationale
is not a test. Both halves are now driven: the reason kept is the first, and `drill.withheld`
appears once rather than once per anonymous request against an item that keeps refusing.

**A bound applied at one of two exits is a bound at neither.** The budget message added in V0.26.3
interpolated the raw refusal, which is a content-sized string, and that message reaches the
unauthenticated `/api/v1/drill/next` as a 503 detail - the exact principle `MAX_WITHHOLD_REASON`
was added for two commits earlier. Not a regression, since the code it replaced re-raised the same
unbounded error directly, and the gate could not reach the path from authored content. Bounded
anyway, and asserted at 3,000 characters.

**An inference of mine that did not follow from the code.** I recorded that the `ResizeObserver`
needed no `disconnect()`, because the observer and its frame become unreachable together when
`clear()` drops the subtree. The gate's objection is correct and I accept it: `observe()` registers
the observer on its target's Document, not on the local variable that created it, so the retaining
edge is Document to observer to target and whether it is weak is an implementation detail rather
than a guarantee. It is also per-redraw, not one-off - a fifty-drill session builds fifty observers.
The conclusion may still be right in Chromium; the reasoning did not establish it, and a
`disconnect()` is shorter than the argument. Observers are now tracked and released before each
redraw clears the frames they watch.

**A tripwire named as one.** The route-level length assertion added in V0.26.3 cannot fail on the
shipped library, because the only withheld reason is 32 characters. The bound is held by the
drill-loop test that authors an oversized parameter; this one exists so a future long reason fails
on the served body. Said plainly rather than left to read as coverage it is not.

**Where the gate was right about my method.** Twelve mutations, each killed, was a true claim about
twelve mutations and not a claim about the changed region. Two controls in that region survived
inversion. The lesson recorded for the next round: mutate every guard the range ADDS, not only the
ones a finding named.

**How it was verified.** Loop green on all seven legs: 967 passed, 2 skipped, coverage 97.19%. One
more register row, and two rows extended, because the citation sweep failed the loop until they
existed - the second round running in which that check has caught me before a reviewer did.

**Corrected at V0.26.5:** this row originally read "six mutations this round, each killed by its own
test". That was a count rather than a checkable claim, and it was wrong: this release added an
observer-release guard whose inversion survived the whole suite. The enumerated ledger is in the
V0.26.5 entry above.

## V0.26.3 (2026-09-01)

**What.** The engineering gate's sixth round failed V0.26.2 with four majors, and two of them were
mutation-proof claims I had made in that release and that did not hold. Every finding was
reproduced here before anything changed, six root causes were fixed as six commits, and three
faults the gate did not name turned up while reproducing the ones it did.

**A word count cannot tell what a denial is about.** This is the THIRD shape of the contradiction
check in three releases, and the reason is measured. A window of "up to two words before the
direction" is wide enough to jump a clause: `"not station-keeping, drifting west at 0.279 deg/day"`
scored partial, and `"no doubt drifting east"`, `"not stationary, east"`, `"rather than holding,
east"`, `"instead of holding, east"` and `"no manoeuvre, east drift"` scored nothing at all. Six
correct readings, penalised, by the fix for the version that penalised different correct readings.
The denial must now be ADJACENT to the direction across a closed vocabulary of motion words. Two
more faults in the same function, found while reproducing that one: a SPACED compound was refused
where the hyphenated one was accepted, because closing hyphens was the whole of the compound
handling and the space is the commoner spelling; and the apostrophe form of a contraction was
caught by nothing, because `normalise` renders `"isn't"` as `"isn t"`, so the `isnt` entry in
`NEGATIONS` only ever fired for an operator who omitted the apostrophe - while the docstring
claimed that exact string was caught. Three residual under-catches are now named in the module and
each was verified by driving it rather than reasoned about.

**Content does not get to set the size of an anonymous response.** A withhold reason embeds the
`repr` of the authored parameter that caused the refusal, and `content/models.py` declares no
maximum length on any value in `params`. Measured: a 3,000-character `newest_at` produces a
3,100-character reason, stored verbatim, served on the unauthenticated manifest and written to the
run log, across up to 140 items. `MAX_WITHHOLD_REASON` is 256, measured rather than chosen - the
longest reason any real content fault produces in this library is 190 characters - and a cut reason
says it was cut. The engineering gate referred this to the security gate rather than adjudicating
it, which is the correct division and is recorded here as such.

**Two claims of mine from V0.26.2 that were false.** The reasons were serialised on the route and
asserted by nothing: deleting the field left the whole suite green, which is the same fault, one
field along, as the one the commit that added it cited. And both new plot controls were deletable
with everything green - the `ResizeObserver` refit and the `getBBox` guard. Writing the assertion
for the first of those turned up a third way to lose the behaviour that no finding had named: keep
the observer and drop only the viewBox reset, and the widening ratchets until the plot disappears.
Four releases running, the pattern is the same: I write the guard, then a test for the guard's
happy path rather than for its absence.

**An unreachable line is not a control.** `serve` re-raised the last item's refusal on its final
attempt, so the trailing "no drill could be rendered within the selection budget" could never
execute; coverage had named the line and it existed for the return type. The operator was told "one
item is broken" when the fact was "four candidates refused". Three controls in that loop now have
drivers, including the named-item early raise, whose mutation two separate gate rounds found
surviving because `_named` returns the same item every call and the budget message still carries
the id the substitution test matches on. The effect is the attempt COUNT, so the count is asserted.

**A test of mine that was an identity in its own subject.** The first version of the budget
assertion read `== MAX_SELECTION_ATTEMPTS`: widening the budget to eight left it green. Found by
mutating my own new test rather than by a gate, and replaced with a literal.

**Two records of one measurement disagreed, and the source held the wrong one.** `products.py` said
an excursion factor of 2.5 "put nineteen degrees on an axis whose box is six". Nineteen is not
reproducible from anything here. Measured at the shipped seed: 2.5 draws 15.0° across a 6.0° box,
1.2 draws 7.2°, 25.0 draws 150.0°. Fifteen is what the test's own comment quotes, so the
unverifiable figure was the one in the source. `MAX_READABLE_EXCURSION_DEG` stays at 12.0 and now
discloses what it does not know: it also admits factor 2.0 at exactly 12.0°, and no entry in this
repository records a browser measurement of the excursion at any factor. A draft of that comment
claimed the shipped factor "was checked in a browser"; no entry supports it, and it was removed
before commit rather than shipped.

**A measurement harness of mine that lied, twice.** The first excursion measurement returned 7.2°
for every factor, including 25.0, because the subprocess read a stale bytecode cache. Re-run with
`__pycache__` cleared and the factor in effect printed alongside each figure. And a mypy run
scoped to two files reported six errors that the project-wide run does not raise, because the
per-file invocation bypasses the project config. Neither figure went into anything shipped, and
both are recorded because a harness that agrees with itself is not evidence.

**How it was verified.** The loop is green on all seven legs: 966 passed, 2 skipped, coverage
97.17%. Every one of the six fixes is killed by its own mutation, twelve mutations in total, each
applied with a `count(old) == 1` guard after two earlier experiments in this project silently
applied to nothing. Three new register rows, because the citation sweep failed the loop until they
existed - which is that check doing exactly what it was built for.

## V0.26.2 (2026-09-01)

**What.** The engineering gate's fifth round failed V0.26.1 with one blocker, two majors and
eight minors. Every finding was reproduced in this session before anything was changed, and two
of the gate's own claims were checked and found partly wrong - recorded below, because a reviewer
being wrong matters as much as a reviewer being right.

**The absorbing state, one door along from where it was closed.** V0.26 stopped an item with no
resolvable answer being re-served for ever. V0.26.1 then added handlers turning a renderer's
arithmetic fault into an author-facing 503 - and those refusals fed back into nothing. Selection
is a pure function of rating and due-state, and a refusal records no run and advances no schedule,
so an item whose renderer RAISES was chosen again on every request. Measured: one NaN on a content
parameter, six consecutive 503s on the same item, no progress, health green throughout. The
load-time probe cannot catch this class because it only inspects items whose answer is computed,
and this one raised while rendering. A refusal now withholds the item, the request tries the next
candidate within a bounded budget, and every withheld item is named on the served manifest with
its reason. An explicitly named item is still never substituted.

While fixing it I added the new field to `manifest()` and not to the route - the exact fault the
security gate raised one commit earlier. It was caught by driving the route rather than the
method, which is the only reason it is not in this release.

**A scoring control that was wrong in both directions.** The contradiction check searched the whole
response for any "no", "not", "never" or "neither". So it PENALISED correct answers - on real
content, "0.279 deg/day west, no reversal in the trend" scored partial with a note telling the
operator to state the direction they had just stated, and five correct prose answers scored zero -
and it MISSED the denials it existed for: "it doesn't drift east", "cannot be east", "east is
wrong" and "hardly east" all took full credit. Two latent faults sat in the same lines: a generator
emitting `("eastward",)` would have refused every correct answer, and "north-east" was refused
against a drawn "northeast" because normalisation keeps the hyphen.

The check now compares compass STEMS against a hyphen-closed response and scopes the denial rule
to a two-word window before the direction. **The residual is recorded in the test rather than
claimed closed:** open-ended denial is a semantics problem, two attempts at widening this check
have each created a worse fault than the one they closed, and over-refusing a correct reading is
the more expensive error.

**Three guards that could be reverted with the suite green.** The empty-pool refusal, the unread
census subtracting only the renderers on the board, and the composite unknown-product refusal -
the last being the stated premise of the duplicate-board design, resting on a line no test
executed. All three now have drivers. This is the fourth release in which a control existed
without one, and the pattern is that I write the guard and then the test for the guard's happy
path rather than for its absence.

**Content values reaching prose, and a threshold contradicting its own measurement.**
`{"newest_at": "sideways"}` rendered "Newest observations at the sideways."; the value is now
validated. For the top case the axis note and the panel note asserted opposite geometries on one
panel. And `MAX_READABLE_EXCURSION_DEG` was 20 degrees, which admitted the excursion factor of 2.5
that `products.py` records as rejected for illegibility - a bound that contradicted the
measurement it encoded. Set to twice the six-degree box.

**The interface guarantee only held at draw time.** The refit that makes "no clipped labels" true
ran once per draw with no resize handling at all, so dragging a window narrower restored the stale
gutter. A `ResizeObserver` now refits and resets the viewBox to nominal first, because without the
reset the widening ratchets. Verified in a browser across live resizes from 1400 down to 340 and
back: every label inside the box, and the viewBox returning to nominal rather than growing.
`getBBox` is also guarded - in Chromium it returns zeros inside a hidden container, which the
existing check skips, but other engines throw and the throw would escape the animation callback.

**Where the gate was wrong, checked rather than accepted.** It attributed the suspected flaky test
partly to `test_middleware.py`, which contains no real-clock sleep at all - all five are in
`test_http.py`. And its claim that the composite unknown-product line was wholly untested was
half right: the probe branch was covered, the composite branch was not.

**Deferred to the risk register, not fixed.** One of the gate's eight full-suite runs reported a
single failure whose name it had suppressed. I ran the timing-sensitive suites twenty consecutive
times under four competing busy loops and could not reproduce it. Per the remediation protocol an
unreproducible failure is environmental until proven otherwise, and guessing at a fix would be
worse than recording it.

**How verified.** Loop green, seven legs: 963 passed, 2 skipped, coverage 97.09%. Seven fixes
mutation-proved individually, each against a named test. Two of my own mutation experiments were
invalid on the first attempt - one replacement never applied and one mutated the bound and the
subject together - and were redone rather than counted.

## V0.26.1 (2026-09-01)

**What.** The security gate ran alone against V0.26 and failed it with two majors and three
minors. Both majors are in code V0.25 and V0.26 added, and both defeat a control this register
states as closed. Every finding was reproduced here before anything was changed.

**The fix for a crash loop caused a crash loop.** V0.24.3 closed the loader's decode faults so a
bad content file could never stop the container starting. V0.26 then added a load-time probe that
renders every sentinel drill to ask whether its answer resolves - and guarded only `LookupError`.
A single NaN in a content parameter raises `ValueError: cannot convert float NaN to integer`
straight out of that probe, `asgi.py` calls `create_app()` at import, and the worker never boots:
a crash loop with no health path to screenshot. Reproduced on four of five cases against the
shipped library, and `ephemeris` with `elapsed_min: 0` raises `ZeroDivisionError` from a plain
authored integer. The probe now treats ANY failure as "cannot resolve", which is the fail-closed
answer and is why the breadth is correct there: the item is withheld and NAMED, so nothing hides
behind it. At request time the same class of fault now earns the author-facing 503 this module
documents instead of a generic 500.

**A bound that was not a bound.** Every content-supplied count was capped at its renderer in
V0.24.3, and the comment claimed "ceilings on every content-supplied count that sizes a loop".
The composite BOARD is such a count and had none: a board naming one product thirty times
rendered 126 MB and burned seven seconds of CPU on a single unauthenticated request, and the
payload budget can only refuse that after the memory is already allocated. The fix needs no
arbitrary ceiling, which is the part worth keeping: an unknown product id already fails closed,
so duplication was the only lever left, and a board naming the same product twice is a content
fault. It is refused rather than de-duplicated, because collapsing it silently would change the
authored board. Verified: refused in 0.000s with no allocation, `products: "all"` still renders
all ten, and no board in the shipped library duplicates.

**A disclosure that reached no surface.** V0.26 said the withheld items are "named on the
manifest" and the route did not serialise them, so it was true of a method and false of every
surface an operator can reach. The test asserted `loop.manifest()`, one altitude below the thing
it was claiming. This codebase names that exact fault at `ScoredDrill.as_dict` and then repeated
it in the commit that cited it.

**Widening a matcher let a wrong answer score.** V0.26 relaxed the direction token to a word
PREFIX so "westwards" would be accepted, which it should be. It also accepted "eastwest" and
"eastasdfgh" as a correct reading of an eastward drift, and the pre-existing anywhere-in-the-
response search accepted "not east" and "east or west". Full credit for a self-contradictory
answer moves a rating nobody earned, which is worse than the pedantry the widening was fixing.
The suffix set is now named and bounded, and an answer that names a direction other than the one
drawn, or denies it, is refused.

**How verified.** Loop green, seven legs: 956 passed, 2 skipped, coverage 97.02%. All five fixes
mutation-proved individually - each mutation reverted, the full suite run, and the named test
shown failing - and the four gate findings re-measured after the fix: the container starts on
every NaN case with health 200, the board refuses with no allocation, both arithmetic edges give
a 503, and twelve direction answers score as they should.

## V0.26 (2026-09-01)

**What.** The engineering gate's fourth round failed V0.25 with two blockers and five majors.
Every finding was reproduced here before anything was changed, and one of the two blockers is a
false statement in this changelog, which is worth putting at the top rather than in a footnote.

**"Every fix mutation-proved" was not true.** V0.25 said it. Three of its controls could be
deleted with the whole suite green, confirmed by running the mutations: the authored partial and
reject entries in `match_derived_text`, the answer-key collision refusal, and the value of
`DRIFT_EXCURSION_FACTOR`. The coverage report already named those lines as unexecuted. A
fabricated verification claim in the audit record is worse than the gap it covers, because it is
the line a future reader trusts instead of re-measuring. All three now have tests and all three
mutants now fail; the claim in this entry was checked against the mutations before it was written.

**Failing an item closed ended the operator's session.** Refusing to score DRL-0008 was right, and
insufficient. `select` is a pure function of due-state and rating, and the unscored path records no
run and advances no schedule, so the same item came back on every turn: measured on the real
package at rating 1340, six consecutive serves of DRL-0008, six unscorable results, no rating
movement. V0.24.3 cost that operator six rating points; V0.25 cost them the whole sitting, which is
a worse harm than the one it fixed. An item that cannot resolve its own answer is now withheld from
SELECTION as well as from scoring, and named on the manifest so the exclusion cannot hide the
content gap. The test asserts PROGRESS across four turns, because "does not move the rating" is
exactly the assertion that let this through.

**The clipping fix reintroduced the clipping fault.** Text is sized in viewBox units so it renders
at a constant CSS size, which means it GROWS in viewBox units as the plot narrows, while the gutter
was reserved once at build time. Below roughly 680 CSS px the timestamps sheared off the left edge
again. Measured in a real browser at seven viewport widths: leftmost label x of -14, -55 and -100
viewBox units at 620, 480 and 390 px. The reserve is now a first guess only; `sizePlotText`
measures the actual overflow with `getBBox` and widens the viewBox on whichever side needs it, in
a bounded three-pass refit. Verified again in the browser from 1400 px down to 340: every text node
inside the box with a positive margin.

A screenshot at 430 px then showed the SAME fault on the other axis - the longitude labels
colliding with the caption, because their offsets below the axis were fixed while the text grew.
Both are now positioned from the size actually applied, landing on the original coordinates at the
nominal size. The gate found the first by arithmetic and could not run a browser; the second was
only visible in a picture.

**Three statements that were not true, corrected.** Two comments said `newest_at: "top"` is
"authored on one item deliberately"; no item authors it, both authoring items say "bottom", and
the claim was invention about the content. A test docstring said 129 of 140 drills carry unread
parameters; the measured figure is 135, and it sits in the docstring of the test whose job is to
keep that figure honest. And the panel note asserted "newest at the top, nearest the longitude
axis" for the top case, where the longitude axis is at the bottom.

**One label, two instants.** The synthetic timestamps omit the year and the epoch span was a full
365 days, so a window beginning in late December ran into January: 80 tick labels each denoted
either 2026 or 2027, measured across 11,000 seeds. The span is now short of a year by the longest
window a waterfall can draw, so every label denotes exactly one instant - cheaper than lengthening
every label, which would widen the axis gutter for no analytical gain. The epoch is also marked in
the header now, `From (synthetic)`, because a screenshot carries the header without the footer.

**Also.** The census subtracted the vocabulary of EVERY renderer for a composite, forgiving
parameters no product on the board reads; `generators.board_for` now resolves the board once and
both `compose` and the census read it, so the render and the disclosure cannot disagree. The dead
`MIN_BURN_DIVERGENCE` constant and its repudiated docstring are gone.

**Judgements the gate upheld, recorded because they were challenged.** The synthetic epoch does not
breach the hard rule on inventing dates: the rule governs assertions about the real world, and read
strictly it would also forbid the observation count and every longitude on a generated stimulus.
`MIN_DRIFT_LEGIBILITY = 5.0` is a loose discriminator with two orders of magnitude of headroom
against the measured ratios, not a threshold tuned to pass. And refusing to score an unreadable
manoeuvre count is the right call - the gate built two independent change-point detectors and
neither could count the burns at any burn count, including zero.

**How verified.** Loop green, seven legs: 950 passed, 2 skipped, coverage 96.97%. Four mutations
run and all four now fail. The interface behaviour was verified by driving a real browser at seven
widths; the suite asserts the mechanism only, and the test says so.

## V0.25 (2026-09-01)

**What.** Ash read a rendered waterfall and named two faults in one sentence: the time axis ran
the wrong way and its labels were bare numbers. Fixing those exposed two more in the same panel.
The engineering gate's third round then failed V0.24.3 with two blockers and six majors, five of
them in code the previous two rounds had introduced. This closes all of it.

**The time axis, from the owner's reading of the plot.** The axis already placed the largest time
at the bottom and the note already said "newest observations at the bottom" - and the recency
ramp was passed ELAPSED time, where the ramp's zero point is the most-recent stop. So the window
start, the oldest data on the plot, was drawn in red at the top while the newest end was drawn as
oldest: one panel making two opposite claims about which end is now, in a product where
red-for-recency is the first thing an analyst reads. The ramp is now age-normalised and the test
asserts the geometry and the colour together, because either alone passes while they disagree.

The vertical axis is a timeline, so it carries UTC timestamps and the header states the window.
"0.003" and "4.99" are the internals of the plot; an operator correlates a date against a pass
schedule and a provider post. The epoch is derived from the SEED and never the clock - a
timestamp read off the wall clock would relabel the same surface differently on every render and
break the replay this project gates on - and the footer says "synthetic epoch, seeded", because
it is scenario data rather than a claim about a real collection.

**Two more faults the screenshot showed and the data did not.** The interface captioned every
inverted axis "inverted, brighter upward", which is true of a magnitude axis and nonsense on a
timeline, and it had been rendered on every waterfall this product has ever drawn; an axis now
states its own reason. And the first attempt at date labels CLIPPED them - "23 Jan 09:00Z"
rendered as "Jan 09:00Z", the day sheared off the edge of the viewBox, which is worse than a bare
number because it looks complete. The gutter is measured from the longest label.

**The burn, which I claimed twice and measured never.** An along-track velocity change is nearly
PARALLEL to the velocity it modifies, so it does not turn the track: at the burn vertices the
local turn angle is smaller than at a median sample. What it changes is the subsequent drift
rate, in a discrete step. V0.24.2 claimed "a visible discontinuity", V0.24.3 claimed a test
proved legibility while that test measured global divergence - which shows the track is different,
not that three events are countable - and the item asks "how many manoeuvres are visible" at zero
tolerance. A blind change-point detector over the distance panel finds no events at any burn
count, because the natural loop dominates every local window.

So DRL-0008 now resolves no expected value and fails closed. That is a downgrade from the claim
and an upgrade on the behaviour: the previous version took six rating points off an operator whose
reading was correct. The drift-rate step IS asserted, because it is real and it is what makes
forced motion look forced. **The count needs a content decision, not more engine work.**

**A fix that created the harm it was fixing.** DRL-0004's expected rate is signed, negative for a
westward drift, and its prompt asks for the rate "and the direction". So "0.12 deg/day west" was
marked WRONG for omitting a minus sign nobody asked for, while the direction the prompt did ask
for went unscored. Before the value was wired the item refused harmlessly. Magnitude and
direction are now scored separately, with a named partial for a right rate and no direction.

**Three claims held by nothing.** Deleting the absurd-rate clamp left the whole suite green.
Setting the drift onset to 0.999 of the window drew no drift with the suite green. And the header
disclosing the clamp read "drawn to scale" - the plain assertion that the drawing represents the
figure faithfully, which is its negation, on the one item whose lesson is "distrust a figure that
cannot be right". All three are now asserted, the last two measured on the marks rather than on a
derived flag.

**Also.** `match_derived_text` discarded the item's authored partial and reject entries, so a
half-correct answer the content awards 0.5 scored zero and both authored misconceptions lost
their teaching text. `MAX_EPHEMERIS_MINUTES` bounded a renderer that draws a fixed 96 samples, so
it could only ever silently redraw an authored span - deleted, and a new test asserts no value in
the shipped library is clamped by any ceiling, because a clamp is the one bound that changes the
authored scene rather than refusing it. The composite census named parameters unread that the
renderer beneath demonstrably reads. `elapsed_ms` no longer reaches the domain at all. An
answer-key collision between two products on one board is refused rather than resolved by draw
order.

**How verified.** Loop green, seven legs: 945 passed, 2 skipped, coverage 96.56%. Every fix
mutation-proved, and one mutant survived the
first version of its test (the drift onset), which is recorded here because it is the third time
this release cycle that an assertion looked sufficient and was not.

## V0.24.3 (2026-09-01)

**What.** The security gate re-ran on V0.24.2, confirmed its two earlier majors and five of its
minors closed, and defeated two controls this register states as CLOSED using a single request
field and a single file encoding. Those are the two that matter here.

**A concession on a client-controlled value is the same hole with a nicer reason.** V0.24.1 fixed
the speed bonus by taking `min(server measured, client claimed)`, reasoning that a slow network
should not cost an operator a bonus they earned. That closed a claim of zero and left every other
value open, because `min` lets the client only ever REDUCE elapsed: posting `elapsed_ms: 1` on a
run the server had timed at 21.5 seconds against a 20 second target still bought the bonus, over
the real unauthenticated route. The test behind the register row tried only zero. The server's
measurement is now the only input; the client's figure is validated at the boundary, discarded,
and not recorded either, because a value nothing reads is better dropped than described as
telemetry. The test now drives four different claims including a negative one.

**The documented operator workflow crashed the container.** `UnicodeDecodeError` and
`RecursionError` escaped the load handler, which named `json.JSONDecodeError` alone, so a content
file that is not UTF-8 or is nested too deeply took `create_app` down and no health path answered.
This is not an exotic input: CLAUDE.md records that the owner's workstation is Windows PowerShell,
whose `Out-File` and `>` write UTF-16LE by default, and the shape-error docstring itself calls
`thresholds.local.json` "the one file an operator writes by hand". So the written-down way to edit
content produced a crash loop. `ValueError` covers both decode failures; `RecursionError` is named
separately because it is not one. The same omission is closed in the progress store, whose
docstring promised it never raises on bad stored data, and in the snapshot reader.

**A budget in a test is not a budget.** `MAX_PAYLOAD_BYTES` read as a runtime bound and was
referenced nowhere outside the suite, so it held for the shipped library and for no other content
tree - and `CONTENT_DIR` is a supported operator knob whose tree that test never runs. Capping
`headcount` alone also left nine other content-supplied counts producing 8 MB to 146 MB payloads,
and three that never finished rendering at all: a cost no byte budget can see, because it is spent
before there are any bytes to measure. Every count that sizes a loop or a mark list is now bounded
at the renderer that consumes it, and the service budget is enforced in `serve()`, which refuses
rather than returns.

**Also.** A bare-string `expected_text` was iterated character by character, so typing one letter
of "east" scored full credit - latent, because both generators emit tuples, and exactly what the
next generator author would write. The regex escape around a derived token is now pinned by a
test. `_bounded` covers the item id, procedure id and competency axis as well as the version: all
four reach the same file from the same source, and `content/models.py` sets no maximum length on
any of them.

**How verified.** Loop green, seven legs: 937 passed, 2 skipped, coverage 96.82%. Every fix
mutation-proved, and the twelve hostile content counts measured before and after.

## V0.24.2 (2026-09-01)

**What.** The engineering gate re-ran on V0.24.1, confirmed nine of the twelve original findings
fixed with mutation-killed evidence, and found three new blockers plus six majors - five of them
regressions in the code V0.24.1 added. This closes those. The pattern is worth naming: each
repair reached for a plausible parameter or a plausible constant, and the ones that were wrong
were wrong in ways only measurement could show.

**A content parameter became an unauthenticated 159 MB response.** `obs_count` was read as a
fallback for `headcount`, and DRL-0030 authors `obs_count: 18000`: 18,000 tracks, 2.6 million
points, 3.2 seconds and 159 MB of JSON from one anonymous `GET /api/v1/drill/next`. A larger
availability surface than the unbounded pending map V0.24.1 closed, introduced by the same
commit. `obs_count` is gone from the fallback, the track count is capped, and every one of the
140 drills is now served and measured against a stated byte budget.

**The manoeuvre nobody could see, scored anyway.** The burn added a fixed 4.0e-6 km/s to an
along-track rate of order 5.8e-4 - seven tenths of one percent - and the measured turn angle at
every burn was 0.00 degrees. Its only artefact was a duplicated vertex, which draws as nothing.
Meanwhile `expected_value` was set from that count, so DRL-0008 changed from refusing to score
into marking an operator wrong for reading the plot correctly: worse than the fault it replaced,
and the changelog claimed the discontinuity was visible. The burn is now sized as a fraction of
the motion, the duplicate vertex is gone, and the test measures the manoeuvred track against the
same track with no burns.

**The census that over-reported itself.** 25 of the declared `reads` names were never consumed by
the renderer declaring them, so six drills counted as fully expressed on a false declaration and
the honest figure was 5 of 140, not 11. A count that overstates its own coverage is worse than no
count, because it retires the question. Every declaration is now proved BEHAVIOURALLY: render with
the parameter, render without it, and require the surface to differ. A static check was tried
first and was vacuous - reading the class source matches the `reads` declaration itself.

**Three more contradictions between a stimulus and its key.** `drift_begins: true` was multiplied
by the window, putting the drift onset at its END, so DRL-0019 drew a perfectly held longitude
while its key says the object has stopped station-keeping. `derived_rate_deg_day: -22900000` - the
real ASTRA 1M artefact - was drawn literally across 114 million degrees, collapsing every object
into one pixel column: it is now reported verbatim in the header and drawn to a scale the panel
can express, with the clamp stated. And DRL-0030 carried the `computed_from_params` sentinel on a
free-classification item, where the sentinel check did not reach: the text matcher compared the
operator's prose against the literal string, so every real answer was marked wrong.

**All three computed items now resolve.** DRL-0004 asks for the longitude drift rate from an
altitude change, which is first-order physics the renderer can compute and now does. DRL-0008 gets
its count from the burns actually drawn. DRL-0030 gets its direction from the drift the renderer
chose. The refusal branch remains for the case where a generator supplies nothing, and is
exercised directly rather than depending on an item staying broken.

**Two register rows that named the wrong evidence.** The `item_version` cap cited a test asserting
a ROW COUNT; deleting the cap left the suite green. The contradiction row claimed a stimulus
"never" contradicts its key, which the seven-agreement table cannot prove and two counter-examples
disproved within a day. Both corrected: one with the test it needed, one narrowed to what is
actually proved. This is the third time in three releases that a register row has cited a test
that did not assert its property, which is a pattern rather than an accident.

**Also.** `FULL_CREDIT` was named in V0.24.1 and asserted nowhere, so changing it quadrupled every
partial award silently. The content's speed cap was applied against a rubric where it could never
bind, so the branch proved nothing. `unimplemented_aggregation` was computed and serialised only
by a method nothing called. The read-route closure's docstring now says which half is a proof and
which is a declared review. `CONTENT_DIR` is recorded in the deployment parameters as the only
name.

**How verified.** Loop green, seven legs: 933 passed, 2 skipped, coverage 96.4%. Every fix
mutation-proved. Process note, because it cost
real work twice: `git checkout <file>` was used to revert a mutation and took the surrounding
session's uncommitted work with it. Mutations are now backed up to a scratch copy and restored
from there, never from git.

## V0.24.1 (2026-08-31)

**What.** Both binding gates returned FAIL on V0.24 with three blockers and eleven majors between
them. This is the remediation. Nothing here is new capability; all of it is a claim made true.

**The blocker that voided the determinism gate.** `rng()` salted each product's stream with the
builtin `hash()` of the product name. Python randomises string hashing per process, so the same
seed drew a DIFFERENT surface in every process: three runs of one forty-drill render produced
three different fingerprints. Every in-process test passed, because a single interpreter always
agrees with itself. The salt is now a SHA-256 digest, and the test that could have caught it now
exists: three subprocesses under different `PYTHONHASHSEED` values must produce one fingerprint.
`scenario/determinism.py` already recorded this hazard class for set iteration; this was the same
fault reintroduced one module later, which is the argument for the cross-process assertion rather
than a note.

**The blocker underneath it: two vocabularies.** The renderers read parameters they had invented
for themselves - `centre_longitude`, `glint_phase_deg`, `state_changes`, `bounded` - while the
content authored `beta_departs`, `separation_km`, `headcount`, `geometry`. Disjoint sets, so the
authored scene was silently discarded and every drill of a given generator drew nearly the same
picture. On DRL-0034 it was worse than bland: the item states `beta_departs` with `time_stable`,
the renderer fell to its in-plane default, and the plot showed TIME departing with BETA flat -
the opposite of its own answer key, so an operator reading it correctly was marked wrong. Beta
reveals a change of orbit plane and time a change of orbit size; drawing the wrong one is not a
cosmetic fault.

Residual, TRIC and waterfall are now driven by the content's vocabulary, and every renderer
declares a `reads` set. What is not read is COUNTED rather than ignored: 11 of 140 drills fully
express their authored scene today, the number is on `/api/v1/content/manifest`, and a ratchet
test fails if it falls. A second test renders all 140 and fails if any surface contradicts its
own key. Two related repairs fell out of it: a manoeuvre is now a visible discontinuity in the
propagated track rather than a number the server picked, and `derived["expected_value"]` is
finally set, so the `computed_from_params` items are scorable at last.

**Scoring faults, all of one family: a claim the code did not keep.**
● An unscorable item scored as WRONG. The matcher refused, correctly; the loop then dropped the
  rating six points, reset the cue schedule as a miss and wrote a run row. Marking an operator
  against a question nobody could answer is worse than not serving it.
● The speed bonus was decided by the client's own `elapsed_ms`. A client posting zero collected
  it every time, while the server's `served_at` was recorded and read nowhere.
● `D-PARTIAL` scaled its award by a hardcoded `0.5` that silently equalled today's rule award.
  The composition is engine policy, so it is now a named constant that says so.
● The rubric's `aggregation` block - `weighted_sum`, a capped speed factor, a Brier weighting -
  was ignored in full. The method and the cap are applied; the calibration weight is REPORTED as
  unimplemented, because the content states a weight and no formula and inventing one would put
  a number in front of an operator that no author chose.

**Availability.** `_pending` grew by one entry per unauthenticated `GET /api/v1/drill/next` and
never shrank: 4000 serves retained 4000 entries, and the error message advertised an expiry no
code implemented. Now bounded by age and by count, and the message is true. A content file shaped
as a JSON array raised `AttributeError` out of `create_app` itself, so no health path answered -
a crash loop where the contract promises a 503 naming the fault. The realistic trigger is a typo
in `thresholds.local.json`, the one file an operator writes by hand.

**Controls that existed only on paper.** `training/scoring.py` survived the V0.24 rewrite and its
tests did not: 87% coverage, zero tests naming any of its symbols. Three mutants proved it - the
rating band removed, the Brier reduced to an absolute difference, the off-scale confidence guard
disabled - and the full suite passed with each. Ten assertions restored in
`tests/test_training_scoring.py`, all three mutants now fail. The register's claim that frozen
content models are "stronger than the previous control" cited a test that asserted no such thing;
setting `frozen=False` left the suite green. That test now exists. And the loader docstring
claimed a solvability check that has never existed, which is the exact fault that shipped: it is
recorded as a named gap.

**Also.** A read-route closure, because the state-change closure skips every GET and a read route
is the shape that leaks an answer key. One environment name for the content directory instead of
two. `item_version` length-capped before it reaches the progress file. Three comments that
overstated what their code does, corrected rather than deleted.

**How verified.** Verification loop green, seven legs: 923 passed, 2 skipped, coverage 96.40%.
Every fix above mutation-proved: the
mutation is applied, the named test is shown failing, the tree is restored and confirmed clean.
Both gates re-run at this commit, sequentially rather than in parallel - running two
mutation-testing reviewers against one worktree let each see the other's mutants, which is how
V0.24 came to be reviewed against code neither reviewer wrote.

## V0.24 (2026-08-31)

**What.** The application, built on Ash's real content package. A minor bump rather than a patch,
because the illustrative content, the illustrative drill engine and its three shaped plot
generators are all gone and what replaced them is a different thing.

**The package.** ENLIGHTENMENT training system v2.10.0, 31 August: 140 drills, 127 cues, 13
procedures, 12 scenario templates, 67 rubric rules, five expert traces, ten product definitions
with nine observed layouts, a JSON schema, three build specifications, an authoritative timing
standard and a standard-library validator. Built from a corpus of 3,124 released reports, nine
exercise sources, eleven procedures, five product screens and two years of weekly reporting. It
validates clean: 0 errors, 19 warnings, and the warnings are the standing gaps rather than faults.

**The architecture, stated because it is the whole thing.** Content is data and the engine is
code, and the test that draws the line is whether the count changes when a content author does
their job. Ten product generators does not. 140 drills does. So: no hardcoded scenario, no switch
over event types, no scoring rule in Python; and hand-written classes for the generators, the
physics, the evaluator and the scheduler. The build guidance predicted both failure modes and both
were avoided, including the over-correction of trying to express drawing logic in JSON.

**Loader.** `content/` now holds the package, and `tools/validate_content.py` runs as leg 2 of the
verification loop, before any code analyser, because the content is the asset and ten seconds of
validation is the cheapest rung that can catch a content fault. Three loader behaviours the
guidance names as content decisions that would otherwise be omitted: a scored scenario is refused
while thresholds carry placeholders, a content fault is reported rather than raised so the health
paths stay 200, and every run record carries the content hash it was scored under.

**Generators.** The canonical twelve from the `_generator_contract` block: ten renderers plus the
composite and probe composition modes. The 58 legacy names in `params` are traceability only and
are not implemented; a code-side guard refuses one. A registry keyed by product id is checked at
LOAD against every product the content references, so a drill pointing at an unbuilt product fails
before the request that needs it. `tests/test_generators.py` reads the six contract requirements
out of `product-layouts.json` rather than restating them, so a corrected layout fails a test and
names the renderer: the waterfall is observation-level scatter with real collection gaps, the
photometry axis is inverted, the relative-motion panels use independent scales, the residual scale
is tight and labels its time and beta series, the neighbourhood carries delta-v, score and days to
crossing, and the determination table runs Initial, Final, Delta with apogee before perigee.

Pass structure is real, from the owner's figures: eight passes a day in two groups for low orbit,
continuous through local night for geostationary electro-optical, essentially constant for passive
radio frequency. The sixth contract requirement, that imperfection comes from the noise model
rather than from uniform noise, is NOT satisfied: the characterisation pass has not run, so the
amplitudes are chosen rather than measured and every one is marked `PROVISIONAL` in the source and
on the rendered footer. A test asserts the marker, because making a surface convincing before that
pass runs makes the shortfall harder to see rather than smaller.

**Scoring, and a finding.** The evaluator reads award, cap, competency and explain from
`rubrics.json` and none of them appears in Python. **But the rule `when` clauses are prose, not
machine-evaluable predicates**, and nothing in the content carries a machine key, so a predicate
cannot be derived from the content. The bridge is a registry keyed by RULE ID that fails CLOSED: a
rule with no predicate is REPORTED as unimplemented rather than silently scoring zero, because
"this rule found nothing" and "nobody wired this rule up" are opposite facts. Six of 67 are
implemented, which is all of `RUB-DRILL` and therefore the whole drill layer; the other 61 belong
to the scenario runner and the argument surface and are named in every response.

**Matching.** Exact after a narrow, bounded normalisation. No fuzzy matching, because the reject
list is the load-bearing half of the key and a similarity score would award a named wrong answer
for looking like a right one. `computed_from_params` is handled as the sentinel it is: the
generator computes the expected value server-side and an item whose value cannot be resolved is
REFUSED rather than scored against a guess.

**The loop and the interface.** `POST /api/v1/drill/next` serves stimulus and prompt and nothing
else; the reveal is the response to the answer, and submission is idempotent on the run id.
Asserted on the raw response body against the real 140-item library rather than on a parsed
object. The interface renders the panel description the server sends, honouring inverted axes,
independent scales, staircases for discrete state, plus-cross scatter rather than polylines, and
colour as a variable rather than decoration. Nothing is ever assigned as markup.

**One design decision taken provisionally.** Red is reserved for RECENCY on plot surfaces and is
never used for a verdict, which is the third of the three options in `docs/PLOT-REALISM.md`. In the
operator's real toolset red means "the most recent data" in at least three views, so a red verdict
would teach one colour two unrelated ways. Reversible, and Ash's call.

**Retired, and the controls that came with them.** `training/engine.py`, `training/answers.py`,
`training/plots.py`, `tests/test_content.py` and `tests/test_training.py`. Deleting a suite for a
module that still EXISTS takes its controls with it, and `progress.py` survived: its file mode,
its capped history and its degrade-to-defaults path are restored in `tests/test_progress.py`. Two
register rows record controls that genuinely went, and one records a REVERSAL: the content models
now set `extra="allow"` deliberately, so a typo in a field the engine does not read is no longer
caught here, and the strictness moved upstream to the schema and the validator. One row records a
gap rather than a removal: rubric version pinning is not implemented, and closing it needs a
decision from the content author about where the pin lives.

**How verified.** Verification loop green, seven legs: 900 passed, 2 skipped, coverage 96.67%.
Content validator 0 errors. Four new suites, 76 tests. All 140 drills load, all 140 render
deterministically, and the application was driven in a real browser rather than only tested: the
drill surface, the reveal with its rule decomposition, and the progress surface all render, with
zero console errors and zero network requests.

## V0.23.20 (2026-08-30)

**What.** `docs/TASK-EVIDENCE.md`, and the answers to the five questions `docs/PLOT-REALISM.md`
left open. Ash supplied the Iron Stallion help manual for Sat Xzibit, the application the five
product screenshots came from. No code change.

**The material answers more than it was asked.** It closes four of the five plot questions and
lands on two of the design red team's three CRITICAL findings.

**The association types are a diagnostic rule, not a legend.** ASTAT is association status, 1 fully
associated and 2 closely. The other two are a discrimination with a physical basis: **Beta
residuals reveal orbit PLANE change, Time residuals reveal orbit SIZE change.** Neither was in our
vocabulary, because nobody here knew it.

**Residuals are a four-class classification and we already have the format for it.** The manual
gives four causes for data leaving the zero line: the state still fits, a manoeuvre moved the
object, the orbit fit is degrading, or the incoming data has a quality problem. Two of the three
non-null answers are not about the satellite at all, which is exactly the confusable alternative
an invented syllabus misses. A trainee taught only "residuals move when there is a manoeuvre" will
report a manoeuvre when the fit is stale.

**Two of the six axes stop being unmeasurable**, which is red team finding 2. Physical reasoning
becomes markable through the element-response question: which elements should have moved, given
this manoeuvre, when period, apogee, perigee and eccentricity step together while inclination and
RAAN ramp through untouched. Reporting becomes markable through the collection-planning step the
workflow actually ends at: a time window, an object list, a sensor set, a step rate, and a
phenomenology judgement about whether a sensor can physically see the object at all. Neither is
free, both need authoring, but the flight plan's claim that the axes are measurable is now
defensible for four of six rather than four with two hopes attached.

**And it contains a procedure we did not write.** The manual's recommended operator checks, of
which the second is a discipline rather than a technique: "look for agreement across providers
before assuming a trend is real". That answers the multi-source point from the other direction.
Overlaying two sources is not a pleasing visual idiom, it is a required check, and a training
surface showing one source cannot ask an operator to perform it.

**One decision for Ash before the palette is final.** Red means "the most recent data" throughout
the real toolset, consistently, in the heat map, the LAT/LON view and the light curves, with a red
line marking the present. PHOSPHOR uses red for "your call was wrong". Two unrelated meanings on
one colour, in the environment whose surface features are supposed to match the job's. Three
options are set out; the recommendation is to confine red to recency on plot surfaces and never use
it for verdicts.

**Corrections to V0.23.19.** The waterfall is not a whole-sky view with the target somewhere in it:
it shows objects within 50 km of the queried satellite, so the proposed "find the target in a
crowded field" surface is rewritten as "read the neighbourhood", which fits the rendezvous and
proximity operations discrimination the flight plan already names. Pass cadence now has real
figures from Ash: LEO eight passes a day in two periods, GEO electro-optical consistent except
solar exclusion, passive RF essentially constant.

**How verified.** Verification loop green. No source change beyond the version stamp. Nothing from
the manual or the screenshots is asserted as fact where the source is silent: ACDC is left
unexpanded and marked `TBC, re-verify`, `V Mag Assoc.` is marked as inference, and a disagreement
between the manual and a screenshot over "Solar Equinox" against "Solar Equatorial" phase angle is
recorded rather than resolved.

## V0.23.19 (2026-08-29)

**What.** `docs/PLOT-REALISM.md`, and a pointer to it from the design brief. No code change.

Ash supplied five screenshots of live KBR Space Domain Awareness tooling and asked whether the
plots this application generates are realistic. **They are not, and the gap is structural rather
than cosmetic.** Every one of the five real products is a dense, gappy, multi-source scatter that
encodes a second variable in colour. Every one of ours is a clean, evenly sampled, single-series
polyline that encodes nothing.

`plots.py` already carried the warning in its own docstring: a shaped series presented as measured
data is the clean-training-data-is-negative-training failure. That warning was right and its scope
was too small. It described the noise amplitude. The problem is the sampling, the clumping, the
second dimension, the marker glyph, the provenance and the number of sources.

**The one that changes the build.** The orbital element grid is a manoeuvre-detection drill as it
exists in the real world, and it specifies a discrimination no current surface can pose: period,
apogee, perigee and eccentricity all step together at a burn while inclination and RAAN ramp
smoothly through it, untouched, because both are dominated by natural perturbation. The skill is
not "spot a step". It is knowing which elements a burn moves and which it does not, and reading
one against the other. A single-panel longitude plot cannot ask that question; a six-panel grid
asks it on its own.

Also recorded: we have no light-curve surface at all, which is why photometric cues sit in the
progress artboard as never trained and why "specular glint" and "tumble period" are uncollected
vocabulary; real Hill-frame analysis draws three projections rather than one, because a single
projection of a three-dimensional relative track is ambiguous; and finding a target in a crowded
field is a distinct skill we do not train, because our plots put one object alone on an empty axis.

Nine changes ranked by training value, five questions for Ash that I am not going to guess at
(among them what the four association types mean, and what "interval" indexes on a light curve),
and a note that making the surfaces convincing before the characterisation pass runs makes the
shortfall harder to see rather than smaller, so the provisional marker stays on all of them.

**How verified.** Verification loop green. No source change beyond the version stamp. No datum
from the supplied screenshots has been copied into content or code: the idiom was taken, the data
was not, and the generated series stay synthetic and seeded.

## V0.23.18 (2026-08-29)

**What.** The gates ran on V0.23.17. Security returned PASS, engineering returned FAIL, and both
landed on the same thing from opposite directions: the audit-line control I had just written to
close an enumeration defect was itself an enumeration.

**A denylist cannot notice what is not on it.** The "carries no performance data" half of
`test_every_accepted_answer_emits_one_audit_line_carrying_no_performance_data` checked six literal
key names against the top level of the parsed line. `ScoredDrill` carries seventeen fields, and
the six missed the real ones. The engineering gate added `points` (the actual score),
`calibration`, `ratingAfter` and `nextDueInDays` to the audit line and the whole suite stayed
green. The security gate got a score AND the operator's own words through inside a nested `detail`
object, and defeated the `rating` check by renaming the field `newRating`, and defeated the
answer-text check with `.upper()`.

`log_event` emits `event` plus exactly the fields it is given, so the assertion is now a SET
EQUALITY over the whole key set. Every future field fails it, nested or renamed, until somebody
decides it belongs in an operational log for an unauthenticated route whose subject is a person's
performance. The two answer-text substring checks stay, case-folded, as a second layer on the four
fields that are allowed, because a set equality cannot see the answer arriving inside `itemId`.
All four mutants now die, including the two the gates used.

**Two more ways past the route walk, both fail-closed now.** The security gate found that
Starlette treats a FALSY `methods` as matching every verb, so a raw `Route(..., methods=[])`
appended to `app.router.routes` serves POST while the walk tested `is not None`, entered the loop,
iterated zero methods and continued: an ungated 200 with the suite green. The walk now tests
truthiness and raises on an empty set explicitly. The engineering gate found that
`APIRouter.frontend()` puts routes in `_low_priority_routes`, which is not in `app.routes` at all;
harmless today because `_FrontendRoute` hardcodes GET and HEAD, but that is a promise of the
pinned FastAPI rather than of this project, so the bucket is now asserted empty.

**What the limiter split does not fix, measured rather than argued.** Accepted risk 5 said the
coarse tier stays shared "because a global ceiling is what it is for", which reads as closure. The
security gate measured the residual: 240 unauthenticated drill answers still leave an
authenticated `POST /api/v1/sessions` answering 429, because the coarse tier is consumed in
middleware before any route guard runs, including on requests the drill guard then refuses. So the
split is a twelvefold mitigation, 240 requests per window where it was 20, and not an elimination.
The risk now says so and names the ingress as the remaining bound.

**And three docstrings that said the opposite of the code.** V0.23.17 split the limiter and left
`training_api.py` still describing the shared one, including "one limiter for every write in the
process, not one per route group" - which is now precisely backwards. A reviewer trusting that line
would conclude the budgets are shared and stop looking at the separation the release introduced.

**How verified.** Verification loop green. Pipeline simulation green. Six new mutants killed: four
against the audit closure, one raw `Route` with an empty method set, one low-priority route outside
`app.routes`. Continuous integration concluded `success` at `9679eaa` and again at `e2b85e1`, runs
56 and 57, after eight consecutive failures.

## V0.23.17 (2026-08-29)

**What.** Three MAJORs from the security gate and one from the engineering gate, all on V0.23.16,
all of them the same shape: a control that was claimed rather than tested.

**The closure I wrote to close a hole had the same hole.** `_state_changing_routes` read
`route.methods` and silently skipped any route object that did not have one. Both gates defeated
it independently and by different routes: on the pinned FastAPI, `include_router` appends an
`_IncludedRouter` whose `path` and `methods` are both `None`, and `app.mount` appends a `Mount`
with no `methods` either. An unauthenticated `POST` behind either answered 200 in the closed
default while the suite stayed green. It failed OPEN, which CLAUDE.md forbids outright.

It now WALKS every idiom - decorator, `include_router` (through `original_router.routes`, taking
the prefix from `include_context`), mount, sub-application, WebSocket - and RAISES on any route
object it has not been taught, so a new routing idiom fails the suite rather than passing
silently. A WebSocket cannot be probed with an HTTP verb, so it must be named in
`REVIEWED_WEBSOCKETS` with its reasoning. Four mutants now die where none did: an ungated POST
behind `include_router`, behind `app.mount`, a WebSocket route, and an opaque ASGI mount whose
routes cannot be enumerated at all.

**An open route could shut a gated one.** `POST /api/v1/drill/answer` is unauthenticated on
purpose until operator identity exists, and it shared the strict rate limiter with the
token-gated session writes. So twenty unauthenticated answers exhausted the budget and the next
authenticated `POST /api/v1/sessions` answered 429. Behind the platform gateway many callers
share one address, which is already recorded as accepted risk 4, so that was a single
unauthenticated client able to hold the team's gated write path shut. Split into `DRILL_LIMIT`,
its own bucket, same tier and same numbers. The coarse global tier stays shared, because a global
ceiling is what it is for, and the risk paragraph now says so.

**The audit line that was not a control.** `docs/SECURITY.md` cited the `drill.answered` emission
twice, once in the register and once as a compensating control for the ungated write, and
deleting it left the entire suite green. It was a claim. It is now bound by a test asserting
exactly one line per accepted answer, naming the actor and the item, carrying NEITHER the
submitted answer text NOR any score field - because the plan forbids a personal performance
figure in a log line and an operator's own words are performance data.

**And one I nearly shipped vacuously.** The first draft of the cross-limiter test asserted the
session write was "not 429". It passed against the merged-limiter mutant, because a malformed
body 422s before the rate guard ever runs. A negative assertion that a wrong request also
satisfies is not an assertion. Rewritten to require 201, and the mutant then died with the right
message.

**Also.** The digest table pinning the six vendored typefaces was correct and bound by nothing, so
a swapped `woff2` would have left the pinning claim intact and false; now recomputed by a contract
test, proved by flipping one byte and by dropping a row. The register row for the route closure
narrowed to exactly what the test guarantees. The audit row now cites `training_api.py`, where the
third route's emission actually lives. The deploy checklist's test count, stale at 898 against 905.
The last "both write routes" in the prose. The artboard harness now percent-decodes a pathname, so
a directory with a space in its name does not read as an offsite fetch.

**How verified.** Verification loop green: 905 passed, 1 skipped, coverage 96.85%. Continuous
integration concluded `success` at `9679eaa`, the first green run after eight consecutive
failures, read from run 56 rather than inferred. Nine new mutants killed across the four fixes.

## V0.23.16 (2026-08-29)

**What.** Everything both binding gates found on V0.23.15, and the red continuous integration
nobody had looked at.

**The red pipeline, which is the important one.** Continuous integration had concluded `failure`
for eight consecutive runs, 48 through 55, across V0.23.10 to V0.23.15, and nothing surfaced it
because the local loop was green throughout. Read from run 55's log, not inferred: the pipeline
simulation unpacks the App Store zip and runs this suite from inside it. The zip stages
`src tests scripts docs content .github` and deliberately NOT `tools`, because
`udl_characterise.py` reads real UDL credentials and must never ship. So nineteen tests asserted
on a file that a test three definitions above them proves must not be there. The suite
contradicted itself, and had done since the characteriser tests landed.

Closed with `_udl_tool_or_skip()`, following the doctrine `PLATFORM_MANAGED_ABSENCES` already
carries: a check that cannot run in an environment SKIPS with a written reason, never fails. The
discriminator is deliberately narrow, because a skip that fires too easily is how a deleted
control goes unnoticed: not "the file is missing" but "the whole `tools` directory is gone AND
there is no checkout", which together describe an unpacked artefact and nothing else. Delete the
tool in a repository and `.git` is still there, so the tests fail loudly. Plus the converse,
`test_the_characteriser_is_tracked_in_the_repository`, read from `git ls-files` so an untracked
stray copy does not satisfy it.

**Engineering gate, FAIL on V0.23.15, three MAJORs, all fair.**
● I silently deleted the provenance marker `synthetic ·` from a plot caption while fixing a
  header wrap. A content deletion dressed as a layout fix, and outside the declared scope.
  Restored, and the wrap solved properly: the caption now breaks BETWEEN its two labels instead
  of through the middle of "along-track and radial".
● The harness's typeface assertion was decorative. `document.fonts.check()` returns TRUE when no
  `@font-face` rule matches the family at all, so deleting the stylesheet outright read as a
  pass. Proved by deleting it. Rewritten to assert positively against `document.fonts`, and the
  allowlist of expected family names went too, because a fourth mutant walked through it:
  renaming a family to one nothing declares was silently skipped for not being on the list.
  Three mutants now die where one did.
● `docs/DESIGN-BRIEF.md` claimed the artboards and the product use "the same set of files" and
  that Segoe UI sits behind them. Both false. `src/enlightenment/ui/` declares no webfont at all,
  so today the mockups render in Saira and the product renders in Segoe UI. The brief now says
  so, and says what closes it.

**Security gate, PASS on V0.23.15, six MINORs, all taken.** The one worth reading: accepted risk
5 said "writes are gated", and the reviewer defeated that sentence in one request. With a token
configured, an unauthenticated `POST /api/v1/drill/answer` returns 200 and moves persisted state.
The behaviour is deliberate and is recorded in the code, but the security document flatly
contradicted it, and a reviewer trusting that line stops looking at exactly the route that
writes. Rewritten to name the route, the reason (flight plan step 10, identity does not exist, so
every drill write goes to the synthetic operator and no named-individual record is created before
the DPIA closes) and the two compensating controls, both verified live under attack.

Behind it, the deeper fault: the write-gating tests ENUMERATED two paths by hand, which is why a
third state-changing route shipped past them without turning anything red. Now derived from
`app.routes`, with `UNGATED_WRITES` as an explicit, reasoned opt-out. A fourth unauthenticated
write route fails the suite; so does removing the drill route from the opt-out. Both proved.

**Also.** `design/` gained the regression guard `tools/` has had since V0.23.6, after both gates
independently proved the same mutant: add `design` to the packaging allowlist and 131 kB of
third-party binaries ride into a SonarQube-scanned upload with nothing turning red. The UDL
runbook's version row, a seventh version site hand-bumped since V0.23.6 and bound by nothing, is
now bound by a test. `node_modules/` is ignored, because the new tool's own instructions create it
at the repository root. The six woff2 binaries have SHA-256 digests recorded in
`design/phosphor/fonts/DIGESTS.md`, pinned the way the lockfiles are. Five horizontal rules left
`docs/DESIGN-RED-TEAM.md`, per the house rule.

**And the figures I got wrong.** Re-measured on `9b5f028` with the vendored faces substituted in,
because the parent links a content delivery network the harness blocks and fallback metrics are
not the real ones. The worst rendered text was **7.3 px** at an 1180 px window, not the 9.0 px I
reported from a single wide measurement. Progress clipped **four of its six** radar labels, not
one, and the debrief timeline clipped its track label too. The timeline overlapped **four pairs
across seven labels**, not six labels. Corrected in `docs/DESIGN-RED-TEAM.md` and here.

**How verified.** Verification loop green. Seven new mutants killed: `design` in the upload
allowlist, `design` out of `.dockerignore`, a stale runbook version, a fourth ungated write route,
the drill route removed from the opt-out, a deleted font stylesheet, and a renamed font family.
Pipeline simulation run against the version being shipped. `design/check-artboards.mjs` passes on
all six artboards at both widths and reports 30 failing checks against `9b5f028`.

## V0.23.15 (2026-08-29)

**What.** Three things the owner asked for on the PHOSPHOR direction: vendored webfonts, a red team
against instructional-design standards, and the accessibility defect that red team found in my own
artboards, fixed.

**Webfonts.** Owner decision, overriding the design brief's "type is the system stack" rule. The
constraint was always "no external request", never "no webfont", and the interface already serves
`font-src 'self'`. So Saira, Saira Condensed and Azeret Mono now sit in `design/phosphor/fonts/` as
latin-subset woff2 under the SIL Open Font Licence 1.1, licence text carried beside them, six files
and 131 kB. Saira and Azeret Mono carry a `wght` axis, verified by reading the `fvar` table out of
the woff2 directory, so one file covers every weight and is declared as a range; Saira Condensed is
served upstream as static instances, so it is four files. Every artboard now links
`fonts/fonts.css` instead of `fonts.googleapis.com`.

**Red team.** `docs/DESIGN-RED-TEAM.md`, thirteen ranked findings against DSAT, Gagné, Merrill,
4C/ID, cognitive load theory, Kirkpatrick, deliberate practice and recognition-primed decision
making. Verdict: the learning science is above industry standard, the instructional systems
engineering around it is below it. Three criticals, all structural rather than visual: no training
needs analysis, so nothing is traceable to the job; entirely part-task practice, with two of the
six axes structurally unmeasurable; and no scaffolding fade between the worked example and
unsupported problems.

**The defect that was mine.** Finding 10 said in-plot text was carrying the lesson at 8.5 to 10.5
pixels. Measuring instead of estimating made it worse and wider. A plot drawn inside a 1.55fr
column renders *smaller* than its own coordinate system, so the true floor was 9.0 px; Progress was
clipping "PROCEDURE RECALL" off the edge of its own viewBox; and the debrief timeline, the single
most important teaching screen in the product, was overlapping six of its own labels. Fixed by
bounding every artboard's measure so the render scale is a known quantity, sizing in-plot text
against that measured scale, rebuilding the debrief label layer on two staggered rows per track
with leaders back to each marker, and giving the radar frame the margin its labels always needed.

**Why.** A contrast figure measured to two decimal places and then undermined by size is a control
that was never verified. Same for a mockup that specifies a typeface it cannot render, and for a
design document whose type rule the owner has since overruled.

**How verified.** New standing check at `design/check-artboards.mjs`: headless Chromium loads each
artboard at 1440 px and 1180 px and asserts that no text inside a plot renders below 12 CSS pixels,
none is clipped by its frame, no two labels overlap, every declared face actually loaded, and the
page makes zero network requests. All six artboards pass at both widths. It needs Node and
Playwright so it is not a leg of `scripts/verify.sh`; it is run by hand when an artboard changes.
The verification loop is green, and no application code changed: the only source edit is the
version stamp.

## V0.23.14 (2026-08-28)

**What.** A second design direction, `design/phosphor/`, after the owner's verdict on the first:
"that design does not inspire me at all". Style and colour were explicitly released from the
Bluestaq template, with the brief that trainees should WANT to engage and that the engagement
research should be the focus rather than a garnish. No application code changed; the only source
edit is the version stamp.

**The thesis, because it is the part worth keeping even if the visuals change again.** In this
domain what pulls people back is not celebration, it is CONSEQUENCE: operators lean in because
something is happening and they are the one who has to call it. So the interface is built as an
instrument rather than a quiz, and light means ATTRIBUTION - amber is the operator, cyan is the
system and the expert. That is not decoration. It solves the debrief's central information problem
at the palette level, because an expert trace blooming over yours needs no legend.

**Seven named engagement mechanisms, each with what it changes on screen.** They are annotations on
the canvas rather than a document nobody opens.

● **The open loop (Zeigarnik).** No "start next?" button; the next signal is already sweeping in and
  the run shows five marks. You do not decide to do one more.
● **Vocabulary, not badges.** Every discriminating cue has a name an analyst would say out loud -
  "the count that stops", "the impossible rate", "the snap-back". You collect phrases, eleven of
  thirty-four. Apprenticeship rather than a loyalty card, and a named pattern retrieves faster than
  an unnamed one.
● **The expert is the relatedness.** Leaderboards are banned by the plan and wrong for this
  audience, so Self-Determination Theory's third leg comes from a named, dated human instead: "Ash
  knew at 02:08." The data model already signs and dates every trace.
● **Time recorded, not threatened.** A sweep, never a countdown, and the copy says plainly that
  faster is not better - on the debrief the expert WAITED and the waiting was the skill.
● **Desirable difficulty, made visible.** "This signal sat +236 above your reach, and you took it
  on." A miss becomes evidence of range.
● **The peak-end rule.** A run has a deliberate close: the arc, the phrase added, what returns and
  when, the calibration line.
● **Competence as a shape.** Six axes as a figure with the interval drawn as a BAND, not a spike, so
  it cannot lie about a small sample; unmeasured axes sit outside the figure rather than being drawn
  as zero.

**Deliberately absent: streaks, badges, points-as-currency, confetti, leaderboards.** Two reasons,
neither squeamish. The plan's own user research says operators are motivated by competence and
mission readiness "not by trivia or streaks" and are "highly allergic to anything that feels
childish or like surveillance"; and the overjustification effect says extrinsic rewards reliably
crowd out intrinsic motivation for work someone already finds meaningful. These people already do.

**The palette was computed, not chosen.** Every accent sits at `oklch(0.845 0.145 h)` - one
lightness, one chroma, hue doing the work - measuring 10.4 to 13.0 : 1 on the ground. The figure
that shaped the whole direction: those accents are only **1.10 to 1.24 : 1 against each other**. So
hue is free to carry attribution and can never be trusted to carry meaning, which is why the
operator's trace is dashed where the expert's is solid and every status still has a glyph and a
word. Grid furniture measures 1.39:1 and therefore never carries meaning.

**I looked at it before handing it over, and found three defects.** The reach caption wrapped into a
one-word-per-line column; the inbound-signal thumbnail rendered axis numerals at forty pixels tall,
which is clutter rather than a small chart; and one incoherence of my own making - I had put
wall-clock "you called it" markers on a scenario-HOURS axis, which is two different clocks on one
scale. That last one is now what it should have been from the start: the scenario event the lesson
actually turns on, the sensor revisit, with the region before it shaded and the cue anchored to a
real point on a real trace.

**Recorded so nobody re-derives it: what I checked was the FALLBACK.** The headless browser has no
route to a font host, so the screenshots render in the fallback stack rather than in Saira
Condensed. The layout and the system hold either way, which is the useful half of that finding, but
the typography has not been seen as it will ship.

**One decision left with the owner.** The type is webfonts, so shipping means subsetting and
embedding them as woff2 data URIs - permitted under the plan's "all assets vendored" and costing
roughly 60 to 90 KB - or dropping to a pure system stack with the condensed drama coming from
letter-spacing instead. Everything else in the direction is unchanged by that choice.

**Unchanged by this direction:** no CDN, no external request at runtime, `script-src 'self'`, WCAG
2.2 AA, the 18px body floor, status never by colour alone, and `prefers-reduced-motion` honoured
with a non-motion equivalent that still marks the reveal rather than removing the signal.

**Verified.** Loop green: 898 passed, 1 skipped, coverage 96.84%, 77 pins matched, three lock files
clean. The canvas was checked as a parsable document before publishing.

## V0.23.13 (2026-08-28)

**What.** A design brief and a design canvas, so the interface can be worked on by someone other
than me. No application code changed; the only source edit is the version stamp.

**`docs/DESIGN-BRIEF.md`.** What a designer needs and nothing they do not: the product's single job
and its user's context, the shipped tokens with their measured contrast figures and the five hard
rules tests enforce, the eleven screens with each one's single job, the real payload for every
screen, the interaction and accessibility floors, the privacy design, and the five open design
questions. It opens with the constraint that matters most, because getting it wrong wastes the whole
exercise: **a design canvas may load webfonts and CDN scripts and this product may load neither**, so
the output is a visual direction that has to survive being rebuilt under `script-src 'self'` with
hand-written canvas charts and the system type stack.

**`design/canvas/`, nine artboards, published as a canvas.** Four are the built screens and five are
the ones that do not exist yet: first run, scenario run, scenario debrief, sandbox, supervisor view.
Two properties make the built four worth having on a canvas rather than as screenshots: every token,
padding, radius, control height and type size is lifted from `src/enlightenment/ui/index.html`
rather than approximated, and **every plot is generated by the product's own `plots.py`**, so the
shapes on the canvas are the shapes the application draws. They are the fidelity baseline the five
proposals extend.

**The open questions are on the canvas, not in a covering note.** Question A, the pedagogical
highlight, is a switch on the Reveal artboard: ink-bright outline against a copper-amber house-rule
exception, flippable, because it is easier to judge than to argue. The rest are sticky notes beside
the artboards they belong to.

**One design decision worth recording, because it is the biggest and the most overrulable.** The
scenario debrief puts the expert's timeline and the operator's on ONE shared clock in two lanes,
rather than two charts. The question that screen answers is "when did the expert know, and when did
I", which is a comparison along a single axis; two charts make the reader do the alignment in their
head, and that is precisely the work the screen exists to remove.

**The supervisor view spends as much space on what is never shown as on what is:** individual
answers, miss rate, sandbox activity, self-explanations. A drill miss is the mechanism by which the
product works, so reporting it would destroy the loop, and the artboard states that where a designer
will see it.

**Working files are versioned and never shipped.** `design/` is not in the packaging allowlist in
`scripts/package-appstore.sh` (which names only `src tests scripts docs content .github`), and it is
now in `.dockerignore` as well - two mechanisms, because either alone would let the directory through
the other.

**Two rule calls, both recorded rather than assumed.** The status glyphs stay Unicode `▲` and `▼`
rather than becoming inline SVG: they are the product's colour-blind-safe status encoding and a test
asserts them, so matching the application wins over a general icon preference. And an em-dash
remains in a table cell where a value is absent, because `app.js` already renders a null measure that
way; the two in prose were removed, which is where the house rule bites.

**Verified.** Loop green: 898 passed, 1 skipped, coverage 96.84%, 77 pins matched, three lock files
clean. The canvas was checked as a parsable document before publishing, and every artboard was swept
for an external reference: there are none.

## V0.23.12 (2026-08-27)

**What.** The application. Flight plan steps 6, 7 and 9 for the drill surface: a scoring engine, the
drill loop, and an interactive interface at `/ui` that an operator can actually use. Plus the v1
content set, so the loop has something to teach.

**The drill loop, which is the plan's one creative risk.** `src/enlightenment/training/`: Elo
ratings so difficulty tracks the operator, a Brier score on stated confidence so a confident error
costs more than an unsure one, and a spacing scheduler that puts a missed cue class back at the
front. Answers are PRODUCED, never picked: two free-text fields, no options list, and
`serve()` returns a payload with no answer field in it. A test asserts that on the raw response
bytes rather than on a parsed object, because a field added to the model later would slip past any
assertion that only inspected keys it already knew.

**Answer matching is the part that could have been quietly wrong.** It accepts what an examiner would
accept (case, hyphenation, "stationkeeping", "maneuver" from an allied operator, a leading
"it is a") and refuses everything else. No fuzzy distance, no stemming, no substring match, and the refusals
are what the tests spend most of their time on: a fuzzy match would accept "not a manoeuvre" for
"manoeuvre" and "uncontrolled conjunction" for "controlled proximity operations", which are the exact
discriminations the product exists to train. A near miss is a miss, and the debrief says what the
expert saw.

**Every score decomposes, because the plan makes that an acceptance test.** Each answer returns the
rules that fired, the axis each belongs to, the points available and awarded, and the evidence in
words. The interface renders that table verbatim. There is no path that produces a total without the
reasoning.

**The plots are solved, not drawn, and one of them proves it.** The RPO surfaces come from the real
Clohessy-Wiltshire solution in the physics core: the bounded item sets the along-track rate to the
no-drift value, which closes the relative track, and the drift-by item perturbs it, which opens it.
A test asserts the open track sweeps more than three times as far along-track as the closed one. Had
the shape been hand-drawn, the drill would teach operators to recognise a picture I invented rather
than a signature the orbit produces. The longitude and range surfaces ARE shaped, and that is
recorded in the module rather than left for a reader to discover: their noise amplitude is one
provisional number that the offline UDL characterisation output replaces when it lands.

**An architectural test caught a real defect while this was being built.**
`test_the_physics_core_is_unreachable_from_any_http_route` failed, because importing the physics
package aggregate pulls in `propagation`, which imported the `sgp4` extension at module level - so
the extension landed on the request path. The invariant was NARROWED rather than relaxed: the flight
plan requires the drill layer to consume the physics core ("no privileged path, no separate
physics"), so the pure closed-form helpers are now reachable on purpose, while the extension whose
measured non-determinism the test exists for is still refused. The fix is a deferred import in the
two modules that annotate `Satrec`, with the reason recorded at both.

**The interface.** `src/enlightenment/ui/`, served at `/ui`, no framework and no build step. Dark
mission-control on the measured palette: Blue 1 is a structural fill and never carries text or
status, alert red is the lightened 4.66:1 value wherever it carries text, copper-amber does not
appear. Status is a glyph and a word as well as a colour. Reduced motion gets a non-motion
equivalent that still marks the moment rather than dropping the signal. Every plot has an authored
text equivalent and a data table. Every value is written as text: no markup-parsing sink and no
dynamic-code sink anywhere in the client, asserted by grep, because content is edited without a
deployment and an authoring mistake must not become a scripting bug.

**Two deviations from the plan, both deliberate and both stated.** The interface is TWO files rather
than one, because the response sets `script-src 'self'` and the alternatives to a sibling script
were a hand-maintained CSP hash or `'unsafe-inline'`. And it is served at `/ui` rather than `/`,
because `/` is part of the App Store health contract and one route should not serve the platform
router and a browser.

**The content set is ILLUSTRATIVE and the application says so on every screen.** Three procedures
(Manoeuvre, RPO, Separation versus Breakup), twelve drill items, three scenarios, rubrics and
traces, authored from public open-source material per the plan's public-sources rule. It is not a
JCO procedure and has not been through subject-matter authoring or redaction sign-off. **The twelve
remaining procedures are NOT invented**: the flight plan names three for v1 and requires fifteen
seeded as data, but does not name the other twelve, and the interface states that gap in the library
rather than filling it. Asking is cheaper than guessing.

**Operator progress persists, in an interim store named as interim.** One atomic JSON file with the
same write-to-temporary-then-rename discipline as the session store, behind an interface narrow
enough that the SQLite swap the plan settles on is one class. Mode 0600 from `os.open`, because this
is the file that will hold personal performance data. Every caller uses one synthetic operator id,
so no named-individual record exists before the DPIA is signed, and the interface footer says so.

**Also.** `create_app` was at the seven-parameter cap the quality gate enforces, so the two rate
limiters are grouped into `Limiters` and the training paths into `TrainingPaths` - grouping two
values always supplied together, rather than a suppression that would not have made the signature
easier to read. A fifth content kind, `drills`, is one entry in `CONTENT_KINDS`. Both new test
suites are registered in the security sweep with thirteen new control rows in `docs/SECURITY.md`
and a written reason for every test not cited.

**Verified.** Loop green under the pinned toolchain: 898 passed, 1 skipped, coverage 96.84%, 77 pins
matched, three lock files clean. Driven end to end in Chromium against a real server: the drill, the
reveal, the dashboard and the library all render and the loop completes.

**Not done, and named rather than implied.** Scenario mode on the running clock (step 11), the
debrief's deterministic replay against the expert trace (step 8 proper - the reveal is the drill's
debrief, not the scenario's), identity and the supervisor audit trail (step 10), scorer validation
against expert human rating (step 12), and the guided first-run worked example. Nothing is packaged
and nothing is deployed.

## V0.23.11 (2026-08-27)

**What.** `docs/DEPENDENCY-GATE.md`: what leg six of the verification loop is, why it is built the
way it is, and what to do when it fires. Documentation only; no code changed.

**Why write it down.** The reasoning behind that leg lived in comments inside `scripts/verify.sh`
and in four tests spread across the contract suite. All of it is real and all of it is
load-bearing: the structural JSON classification rather than a grep over the log text, the
`OFFLINE=1` skip that changes the final banner, the resolved-interpreter rule, the pipe guard.
None of it was readable in one place. This repository has already lost one established fact to a context
compaction and written a `chmod` instruction for a PowerShell operator as a result, so a rule that
exists only as a comment beside its implementation is a rule that will be re-derived, and probably
re-derived wrong.

**It states its own limits, which is the part that makes it usable.** The clean path is observed
and its figures are recorded. The real-advisory branch and the unreachable-endpoint branch have
never fired in this repository, so they are described from the implementation and labelled as
designed and reviewed rather than field-tested. Also recorded: leg one is one-directional by
decision and why asserting the reverse would fail every runner; `tools/` sits outside both the
coverage gate and `sonar.sources=src`, so mutation testing at the review gates is the only check on
it; and a clean advisory scan is a statement about today, not a proof, which is why the leg runs on
every change rather than once per release.

**Verified.** Loop green under the pinned toolchain: 827 passed, 1 skipped, coverage 98.90%, 77
pins matched, three lock files clean. No source file was touched, so the figures are unchanged from
V0.23.10 by design rather than by coincidence.

## V0.23.10 (2026-08-25)

**What.** The engineering gate returned FAIL on V0.23.9 with a blocker and three majors. It
mutation-tested the remediation and found that three of the fixes were still reintroducible with all
824 tests green. Every one of those tests named the thing it was supposed to protect and tested
something adjacent to it. That is the same defect three times, so it is worth naming rather than
listing.

**The pattern: a test that exercises the plumbing and calls it the control.**

● `test_the_udl_time_field_reaches_the_request_per_entity` passed the time field to `fetch` as a
  LITERAL argument, so it pinned `Fetcher` and never touched `_live_inputs`, which is the line that
  chooses the field and the line the original defect lived on. Reverting that one line restored the
  V0.23.8 bug against a green suite. `_live_inputs` is now driven directly with the transport and
  the credentials patched, and the URLs it produced are read.
● `test_the_queryhelp_body_passes_the_boundary_guard_before_it_is_printed` called
  `assert_crossable` directly and never entered `_cmd_queryhelp`, and the only end-to-end queryhelp
  test returns 2 at `load_base_url` before the guard is reached. So deleting the guard CALL left the
  suite green, which restores the finding in full: an unvalidated remote body printed to stdout
  under a runbook promise. There is now a test that patches the transport to return a body carrying
  a catalogue-number shape, runs `main`, and asserts exit 3, empty stdout, `REFUSED` on stderr, the
  body saved locally at mode 600, and a clean body still printing at exit 0.
● `_write_private` had no test at all, so reverting it to write-then-chmod was invisible. Now
  asserted with `Path.chmod` sabotaged, so a 0600 file proves the mode came from `os.open`.

All three mutants confirmed KILLED before this row was written.

**And a real gap the mutation work exposed.** `os.open`'s mode argument applies only on CREATION, so
a pre-existing world-readable `queryhelp-<entity>.json` at a predictable path in the working
directory would be truncated, rewritten, and left readable. `os.fchmod` on the descriptor now
follows the open: on the descriptor rather than the path, so there is no window and no symlink to
race. The test covers this case separately from the fresh-file one.

**The runbook described a design that was never shipped.** It told the operator a `--queryhelp` hit
"prints CHECK BEFORE SENDING with a count" and was "reported rather than refused" - the warn design
that was replaced during the V0.23.9 work, and the string appears nowhere in the tool. The shipped
behaviour refuses, prints nothing, saves to `queryhelp-<entity>.json` and exits 3. Step 2 now says
that, and the troubleshooting table has a row for it. Operator-facing prose that describes a control
the code does not implement is worse than no prose: it teaches the operator to expect a warning and
carry on.

**The V0.23.9 audit row has been amended** to record that its own claim about the call-site test was
an overstatement, rather than leaving a release record that certifies work the diff did not contain.

**Verified.** Loop green under the pinned toolchain: 827 passed, 1 skipped, coverage 98.90%, 77 pins
matched, three lock files clean. `--self-test` 15/15. Three mutants re-run against the whole
contract suite and all three now red.

## V0.23.9 (2026-08-25)

**What.** Both binding gates returned FAIL on V0.23.8. Seven findings, three of them serious, and
one was a credential exfiltration the security reviewer reproduced end to end. All are fixed here.
The gates earned their keep on this one, so the findings are recorded rather than summarised away.

**A live credential could be sent to an attacker-chosen host, and it was demonstrated.**
`urllib.request.urlopen` uses the default opener, whose redirect handler copies every header except
content-length and content-type into the redirected request and permits http, https and ftp to ANY
host. A 302 from the configured host to `http://attacker/steal` therefore delivered a live UDL Basic
credential in cleartext and returned the attacker's body as if it were UDL's. The https allowlist on
`base_url` did not help, because it constrains hop one and says nothing about hop two, and
`--queryhelp` had just doubled the number of credentialled request paths reaching it. The tool now
builds its own opener that follows NO redirect. Refused outright rather than narrowed to
same-host-https, because this tool talks to a fixed set of documented paths on one API: there is no
legitimate redirect to tell from an illegitimate one, and a handler that permits some redirects has
to have its rule right, while a handler that permits none only has to be present. Pinned by a test
that stands up a real local server, issues a real 302, and asserts the second host was never
contacted.

**The CAPCO control had its enforcement point on the wrong side of the boundary.** V0.23.8 sent
`disableCapcoExtensions=true` and called it a boundary control. It is a request-side hint to a system
this tool does not control: rename the parameter, add an entity that ignores it, store an
already-extended marking in the field, or point `classification_marking` at another field in the
profile, and `U//PR-OWNER-DATATYPE` is emitted verbatim under the name of a distribution. The
existing guard would not object, because it hunts catalogue numbers and URLs and an owner token is
neither. The reviewer proved that by putting `U//PR-ACMEDEFENCE-EO` through it. So the shape is now
enforced at the point of emission, where it is local and testable: a marking must be uppercase
letters with slashes, spaces and commas and NO HYPHEN, the hyphenated tail being exactly what the
documented extension uses to carry an owner. Anything else is withheld and **counted**, because the
measure exists to say what proportion of the data is restricted and a silent drop would bias that
towards unrestricted, which is the wrong direction to be wrong in. The request flag stays: two
independent halves are better than either.

**An unvalidated remote body was declared safe to forward.** `--queryhelp` printed the service
response straight to stdout while the runbook told the operator it could be pasted to me. The claim
was made in four places and enforced in none, and this repository already owned the guard that tests
it. The body now goes through `assert_crossable` before printing, with the URL half switched off for
a specific reason rather than a convenient one: a JSON schema legitimately carries `$ref` addresses,
so the URL half would refuse every correct response and the guard would end up deleted rather than
relaxed. On a refusal the response is NOT printed; it is written to a file on the workstation, which
has crossed nothing and is still readable. Printing it with a caution attached is what a warning
does, and a warning is not a control, but refusing to show the operator the schema at all would block
the only route to a complete profile.

**A fallback that failed open into the defect it was added to prevent.** `elset_time_field` carried a
fallback to `time_field`, justified as "a profile written before the key existed" - a profile that
has never existed, because step 2 was blocked until the key shipped. The key is now REQUIRED. A
missing key names itself and stops.

**The headline fix from V0.23.8 had no test that could fail.** Both reviewers mutation-tested it and
found the same hole: reverting the live call site to one shared field, and making `_range` ignore its
argument, each left the suite green. The template test asserted strings, never a request. A test now
drives real fetches with the transport patched and reads the URLs, including a forced bisection so
the recursive path is exercised too. Same for the new `load_base_url`: removing its https check had
left the suite green, because the existing scheme test only reaches `Profile.load`.
**This row overstated the result and V0.23.10 corrects it:** that test passes the field to `fetch` as
a literal, so it pinned the plumbing and NOT the call site where the defect lived, which stayed
reintroducible against a green suite. See V0.23.10.

**Smaller, all real.** `base_url` was scheme-checked and nothing else, so
`https://unifieddatalibrary.com@evil.example` passed, read as the documented host and connected to
the attacker's; userinfo, a missing host, and a path, query or fragment are all now refused.
`ENTITY_NAME_PATTERN` used `$`, which matches before a trailing newline, so `"elset\n"` reached the
URL builder and produced an unhandled traceback instead of the clean refusal; `\A`/`\Z` now, with
`http.client.HTTPException` added to the top-level handler so an unreachable branch that prints a
traceback cannot quietly become reachable. `--queryhelp ""` dispatched on truthiness and fell through
to the fetch path, so the empty-string case the tests and the V0.23.8 row both claimed to cover was
unreachable; `is not None` now. `--raw-out` wrote at the ambient umask and narrowed afterwards,
leaving a window another local user could read raw UDL records in; a new `_write_private` puts the
mode in `os.open`. `TOOL_VERSION` is 1.1.0, because the emitted parameter file records it as
provenance and two files with different marking semantics must not claim one tool identity. The
template printed a `--queryhelp` command missing its `--profile`, which simply exits 2.
`.gitignore` now covers `udl-profile.ini`, `credentials.ini`, `queryhelp-*.json` and
`noise-model*.json`, since the template asks the operator to keep them out of the repository and
nothing was enforcing it.

**Verified.** Loop green under the pinned toolchain: 824 passed, 1 skipped, coverage 98.90%, 77 pins
matched, three lock files clean. `--self-test` is now 15/15, and the extra assertion is the point:
the synthetic sample's planted hyphenated marking must be absent from the emitted distribution and
present in the withheld count, so the marking control is proved with no network and no profile like
everything else in that manifest. Seven new contract tests covering the redirect refusal, the marking
allowlist, the `base_url` tightening, the queryhelp guard and its documented exemption, the
per-entity time field on the wire, and the required `elset_time_field`.

**Still needed from the owner.** Unchanged: the `--queryhelp` output for whichever observation entity
is to be characterised first.

## V0.23.8 (2026-08-25)

**What.** The owner supplied the UDL API documentation. Step 4 was blocked on facts about the API
that neither the flight plan nor I could supply, and most of them are now known, so the endpoint
profile ships mostly pre-filled and the operator's remaining task shrank from "write it from the
documentation" to one command.

**Now pre-filled in `PROFILE_TEMPLATE`.** The base address, the `/history` and `/count` path
convention, `firstResult`, `maxResults`, and the two time-field names. Pre-filled rather than
hardcoded: the profile stays the one place a fact about the API is corrected, and the parameter file
still records which profile produced it, by hash. A test pins the split - the template must be
complete on `[endpoints]` and `[query]` and blank on `[fields]` - so a drift either way fails the
loop. Pre-filling the field names would be a guess wearing the authority of a shipped default.

**New `--queryhelp <entity>` mode, which closes the last gap.** The documentation covers the query
grammar, not the per-entity schemas, so the record field names are still not guessable. The service
publishes them at `/udl/<entity>/queryhelp`, along with units, formats, and which parameters an
entity REQUIRES. The mode reads only `base_url`, because requiring a complete profile first would be
a loop: the profile needs the fields and the fields come from the service. The entity name is
validated against a bare-lowercase-token pattern and refused rather than escaped, since it goes into
a URL carrying live credentials. Its output is API metadata rather than records, so it is the one
retrieval whose result can leave the workstation.

**A real bug fixed on the way: one time field was used for two entities.** `_range` read
`[query] time_field` for both the observation and the element-set query. The documentation ranges
element sets on `epoch` and observations on `obTime`, and an unrecognised query parameter returns an
EMPTY RESULT rather than an error. So the epoch-spacing measure would have reported no element sets
in a busy window and been believed. The time field is now passed per entity, logged on each fetch,
and falls back to the observation field so a profile written before the key existed still runs.

**`disableCapcoExtensions=true` on every query, as a boundary control.** UDL extends CAPCO markings
on proprietary and limited-distribution records to `U//PR-OWNER-DATATYPE`, embedding a DATA OWNER
inside the marking string, and the marking distribution is the one measure emitted verbatim. Without
the flag the noise model would have carried the identity of every contributing provider across the
boundary under the name of a distribution. The service collapses those to `U//PR` and `U//DS`, which
preserves what the measure exists to record, the proportion of a scenario's data that is restricted,
and drops the rest. Set in the URL builder rather than the profile, because a control an operator
can switch off in a configuration file is a default, not a control. The documentation's own caveat
stands: disabling the extension does not disclaim the handling duty on any record retrieved, which is
the other reason raw records never leave the workstation.

**Also.** The time window is now documented as deliberately one `from..to` range parameter rather
than a `>` bound and a `<` bound, since two bounds can be made to disagree and a half-applied window
is a silent sampling error; the range form was already what the code sent, and the documentation
confirms it as the intended between syntax. `Fetcher._request` was extracted to a module-level
`http_get` so `--queryhelp` shares one authentication header and one error path instead of adding a
second place a credential could reach a log. The `https`-only check on `base_url` was factored into
`_checked_base_url`, shared by both profile loaders, because a check that exists twice eventually
becomes two different checks.

**Verified.** `--self-test` PASS (14/14), unchanged, which is the point: the analysis half is proved
with no network and no profile, so none of this touched it. Four new tests in
`tests/test_appstore_contract.py` assert the CAPCO flag on a built URL for both the count and the
page path, the template's complete/blank split, the elset-on-`epoch` and count-path conventions, and
that `--queryhelp` refuses a traversal, an embedded slash and an uppercase token. Loop green under
the pinned toolchain: 817 passed, 1 skipped, coverage 98.90%, 77 pins matched, three lock files
clean. **Both gates returned FAIL on this row; see V0.23.9, which is the build that answers them.**

**Still needed from the owner.** The `--queryhelp` output for whichever observation entity is to be
characterised first. That is the only remaining input for step 4 end to end.

## V0.23.7 (2026-08-25)

**What.** The step 4 tool and runbook assumed a POSIX workstation. The owner runs Windows and
PowerShell. Fixed in the code, the runbook, and `CLAUDE.md`.

**The bug, and it would have stopped step 3 dead.** `load_credentials` refused any file whose
`st_mode & 0o077` was non-zero. On Windows those bits are SYNTHETIC - `os.stat` reports 0o666 for any
writable file and 0o444 for a read-only one - so `& 0o077` is 0o066 on a perfectly well-protected
file and EVERY Windows credentials file was refused. The remedy the error printed, `chmod 600`, is
not a PowerShell command, so the message could not be followed either. The check now branches: POSIX
enforces the mode bits, and Windows enforces the control it actually has, requiring the file to sit
inside the user profile where the default access control list restricts it to that user. Neither
branch is a skip. "The bits mean nothing here" is a reason to check something else, never nothing.

**Why it happened, which is the part worth recording.** The owner's platform was established in
conversation and never written down, then lost to a context compaction. So `CLAUDE.md` now carries a
section naming both environments - Linux for the build, CI, scripts and container; Windows and
PowerShell for `docs/RUNBOOK-*.md` and `tools/` - because a fact that lives only in a transcript is a
fact that will be guessed again. This is the same failure the ask-don't-guess rule was added for, one
layer down: I did not need to ask, I needed to WRITE DOWN what I had already been told.

**The runbook is now PowerShell-first**, with the POSIX form underneath where it differs. Four
corrections beyond `chmod`: the line continuation is a backtick, not a backslash, which would
otherwise pass the next line as a separate argument; `--print-profile-template > file` writes UTF-16
under PowerShell redirection and `configparser` reads that as mojibake, so `Set-Content -Encoding
utf8` is given instead; `less` becomes `more`; and the credentials file is placed under `.config` in
the profile ROOT rather than under `Documents`, because a OneDrive-synchronised folder is inside the
profile and also copied to the cloud.

**Found by the operator running the tool on the machine it is for.** `--self-test` passed 14/14 on
Windows, which is what it is designed to prove, and it does not exercise the credentials path - only
a live fetch does. No amount of further testing on Linux would have found this.

**Verified.** Full verification loop green: 813 passed, 1 skipped, coverage 98.90%. Two new tests.
The POSIX branch is EXECUTED - a 0o640 file is refused and a 0o600 file loads - and the platform
split is asserted on the source, which is weaker than an execution and is stated as such: this suite
runs on Linux, so what it holds is that neither branch was deleted, that the Windows branch checks
something real, and that the Windows message does not mention `chmod`.

**Not yet done for this version:** the `engineering-reviewer` and `security-reviewer` gates have not
run against V0.23.5, V0.23.6 or this change.

## V0.23.6 (2026-08-25)

**What.** Flight plan step 4, everything that does not depend on a fact nobody has supplied.
`tools/udl_characterise.py` (single file, standard library only, Script mode per CONTEXT-001) plus
`docs/RUNBOOK-UDL-CHARACTERISATION.md`, the runbook for the networked workstation. Four contract
tests.

**The shape of the deliverable, because it is the decision worth explaining.** The UDL base address,
its endpoint paths, and its query-parameter and record-field names are NOT in the flight plan.
Inventing them would produce an integration that looks like it works until it is run, so they live in
an *endpoint profile* the operator writes once from the UDL API documentation, and every networked
mode refuses to run without it, naming the exact keys it needs. `--print-profile-template` writes the
blank. Everything that does NOT depend on those facts is finished and provable today: `--self-test`
proves the analyser against synthetic records with statistics known by construction, and
`--analyse-only` runs it over a saved dump. Both need no network, no credentials and no profile, so
the analysis half is verified BEFORE anything touches a live service.

**The LEARNED register is wired, not described.** `Accept: */*` on the history list; `Accept:
text/plain` on the count endpoint, which returns a bare integer; trailing-Z microsecond time ranges;
and above the 10,000 `firstResult` cap the window is BISECTED in time rather than paged past the cap.
A slice that cannot be narrowed below the cap is recorded in `provenance.unrepresented_windows` and
excluded, never silently sampled: offset pagination past the cap is the failure mode that produces a
confident answer from a third of the data.

**Only distributions cross the boundary, enforced rather than intended.** `assert_crossable` walks
the whole output and refuses any string matching the catalogue-number or URL shape, and `--emit`
returns exit 3 rather than writing. Object identifiers are replaced by a per-run salted hash before
any statistic is computed, so grouping works and no identifier can reach the file. Sensor labels are
pseudonymised BY DEFAULT, with `--sensor-labels verbatim` as the owner's explicit choice: a more
useful noise model against a less shareable one, defaulted closed.

**A real finding from the pinned linter, fixed rather than suppressed.** `S310` on the `urlopen`
call. `base_url` is operator-written text and `urlopen` honours `file:`, so a typo or a pasted path
would turn a retrieval into a local file read against a header carrying live credentials. The scheme
is now allowlisted to `https` in the profile loader, before any request is built, and refused rather
than corrected - silently rewriting `http` to `https` hides a profile that is wrong about more than
its scheme. A contract test drives a `file:///etc` profile through the command line and asserts the
refusal. Two oversized functions were split rather than exempted; `T201` is the single per-file
ignore, because a command-line tool's output is its interface.

**The self-test caught my own assertion before anything else did.** I expected a median of 5.0 on a
12-value sample; nearest-rank never invents a value, so the median is an observed 6 and the
interpolated 5.5 does not occur. The assertion was wrong, not the code. Both facts are now written
into the assertion, and a companion assertion shows the mean of the same sample is above 80, so the
median assertion is measuring outlier resistance rather than coincidence.

**Credentials.** Read from `~/.config/phase_offset/credentials.ini` with `interpolation=None`, which
is not cosmetic: a password containing a percent sign raises `InterpolationSyntaxError` under the
default parser, and the failure looks like a bad password. A credentials file readable beyond its
owner is REFUSED, not warned about - what this tool can read, another local process can read. No
credential is echoed in any error, and an HTTP error reports the path without its query string.

**It never ships.** `tools/` is excluded from the upload allowlist in
`scripts/package-appstore.sh` and from the image build context in `.dockerignore`, with one contract
test asserting both, because either exclusion alone would let the file through the other. It IS
checked at full strictness by `ruff` and `mypy` in the verification loop: it does not ship, but it is
the code that holds real credentials and writes the artefact that crosses the boundary, so it is the
last place to relax a check.

**Verified.** Full verification loop green. `--self-test` 14/14. Four new contract tests: the
double exclusion from both shipping contracts, the self-test running with no network, the refusal to
fetch without a profile, and the refusal of a non-https endpoint.

**Not yet done for this version:** the `engineering-reviewer` and `security-reviewer` gates have not
run against this change, and step 4 cannot complete end to end until the endpoint profile exists.

## V0.23.5 (2026-08-25)

**What.** Flight plan step 5, the engineering half: content schemas, loader and suite. Four
versioned content kinds (`Procedure`, `ScenarioTemplate`, `Rubric`, `ExpertTrace`) under
`src/enlightenment/content/`, a `ContentStore` that loads, validates, hashes and hot-reloads the
`content/` tree, and 30 tests in `tests/test_content.py`. The tree itself is created with its
authoring contract in `content/README.md`, baked into the image, and shipped in the upload zip.

**Why these decisions, since each is a deviation a reviewer will ask about.**

● **Pydantic rather than a `jsonschema` runtime dependency.** The plan says "JSON Schema validated
  on load". Pydantic 2 is already a runtime dependency, validates strictly with `extra="forbid"`,
  produces author-facing error paths, and EMITS JSON Schema from the same models via
  `json_schemas()`. Authors get a schema artefact to validate against; the image gains no
  dependency. One definition, two consumers, so the schema an author reads cannot drift from the
  schema the loader enforces.
● **JSON rather than YAML.** The plan permits either. JSON is in the standard library, so the choice
  costs nothing and rules out a second parser in the image.
● **A threshold's `condition` is prose, not an expression.** A threshold in a Protect and Defend
  procedure is a judgement stated in operational terms. Encoding it here would invent a semantics
  the source procedure does not have. Step 6's decision tables bind to the criterion by `name`,
  which is where machine-readable logic belongs.
● **A competency axis is a string, not an enum.** The plan says the six axes "are ours, so they are
  also revisable; version them like content". A Python enum would make a content revision a code
  deployment, which is the thing step 5 exists to prevent.
● **Step ordinals are authored, not inferred from list position**, so a reorder shows up in a diff
  as a change to the ordinals rather than as an invisible re-index. The loader asserts they are a
  contiguous run from one.
● **Content is root-owned in the image, not chowned to uid 10001.** The process reads its own
  scoring rules and can never rewrite them. Changing content is a deploy or an overlay mount, never
  a running process writing to itself.

**Safe failure, which is the behaviour worth naming.** One bad file yields NO store, not a partial
library: a partially loaded procedure library scores against whichever rules happened to parse. A
failed reload leaves the last good tree serving, so an authoring typo is not an outage. Two tests
pin exactly that, by name.

**The redaction gate runs BEFORE schema validation** and refuses four shapes anywhere in a file:
catalogue-number, url, windows-path, chat-channel. A file holding a protected-object identifier is
a disclosure risk whether or not it also parses, and reporting the schema error first would bury
the finding that matters. A finding names the rule and never echoes the offending text.

**A measured correction inside this change.** The first catalogue-number pattern excluded a
following full stop outright, to let `0.05` through, and so let `object 25544.` through as well.
Sentence-final is the more likely way an exclusion list actually gets written. The lookahead now
blocks only when a DIGIT follows the stop, verified against nine prose cases, and the
sentence-final case has a regression test of its own.

**A stated limit rather than a hidden one.** A five-digit altitude such as the geostationary belt is
refused, because a bare five-digit run is indistinguishable from a catalogue number by shape alone.
The gate fails closed; the author writes `35,786 km` or uses words.
`test_a_five_digit_altitude_is_refused_a_known_and_accepted_false_positive` pins the limit so a
later change that quietly widens the pattern has to change a test that says why.

**What this change does NOT do.** The plan's step 5 also asks for all fifteen procedures seeded as
data. The fifteen names, and the text of the three v1 procedures, are the owner's to supply and are
not inferred here. `content/README.md` records that the tree is empty and why.

**The completeness machinery caught the new suite before a gate did**, which is what it is for.
`test_every_security_test_is_cited_by_the_policy` failed on an unaccounted `tests/test_content.py`.
The suite is now SWEPT, nine content controls have register rows in `docs/SECURITY.md`, and the
thirteen content-correctness tests are exempted individually with the reason written down - including
why the draft-status and referential-integrity cases sit BELOW the line and why the version-pinning
case sits above it. Exempted per test, not per file, so a new security test in this suite still fails
the sweep until somebody decides.

Six test names lost their capitals to `N802` in the same pass. The capitals were my emphasis device;
the pinned linter does not accept them, and one of the renamed names is cited by `content/README.md`
and by this entry, so all three were updated together rather than left to drift.

**Verified.** Full verification loop green through the resolved interpreter: environment check,
`ruff format --check`, `ruff check`, `mypy` strict, 807 passed and 1 skipped with coverage 98.90%,
`pip-audit` clean on both lockfiles. 30 of those tests are new. The packaging script and the
Dockerfile both carry the content tree, with the suid sweep still the last filesystem mutation in
its stage and three contract tests holding that invariant.

**Not yet done for this version:** the `engineering-reviewer` and `security-reviewer` gates have not
run against this change.

## V0.23.4 (2026-08-24)

**What.** `docs/FLIGHT-PLAN.md` committed. The owner supplied it after I built an interface plan by
inference from the code and the DPIA, having found no plan in the repository.

**The instruction, recorded because it is a standing rule now and not a one-off:** ask for a missing
document, never infer around it. I searched, found nothing, noted the absence in a footer, and
proceeded on inference anyway. A footnote is not a question. `CLAUDE.md` now carries the rule under
the hard rules, where it survives a session boundary.

**What the plan changed, and it is not marginal.** Four things I had reasoned my way to were already
decided in it, and one recommendation of mine was a detour:

● **The physics boundary is settled.** I had framed "does the physics core become HTTP-reachable" as
  an open architectural decision with three options. The plan decided it: the server ships
  PRE-COMPUTED track segments and the client interpolates. Client-side propagation is deliberately
  not used, which removes the client/server divergence failure mode and drops `satellite.js` from
  the bundle. My "port it to JavaScript" option was the one the plan had already rejected, for the
  reason I gave for rejecting it myself.
● **SQLite is settled**, not a question: the storage add-on is confirmed writable by uid 10001, so
  operator state is a single WAL-mode SQLite file with no fallback path to maintain.
● **Identity is decided**, not open: an `IdentityProvider` adapter with `itsdangerous` and `bcrypt`.
  If the shell later passes identity in a header, that is a second implementation of the same
  adapter and nothing else changes.
● **The vocabulary was never open.** `CLAUDE.md` said the training scenario vocabulary was
  `TBC, re-verify`, which I then reported to the owner as the single biggest blocker. The plan names
  the fifteen procedures, the three wired for v1 (Manoeuvre, RPO, Separation versus Breakup), and
  all six competency axes. That line in `CLAUDE.md` was stale and is corrected: the `scenario` FIELD
  on a session record is free text, which is a different thing from the vocabulary being undecided.
● **An operator console is not the next step.** I recommended one. The plan's Phase 1 order is
  content schemas, then the scoring engine, then the drill loop, then the debrief, and the SPA at
  step 9 - after the engines it renders. Building a session-management console first would have been
  a detour that renders nothing the product needs.

**One item the plan marks as a Phase 0 prerequisite is not done:** step 4, the offline UDL
characterisation pass. It runs on the owner's networked workstation in Script mode, never in the
container, and what crosses the boundary is a noise-model parameter file rather than data. The plan
is explicit that clean training data is negative training, so this is a prerequisite and not a
refinement.

**Also corrected:** open question 1 in the plan, slug uniqueness, is now answered by observation
rather than assertion. `enlightenment` deployed and is live, so the slug is unique in the store.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. The flight plan carries no credential shape and no
userinfo URL; scanned before commit.

## V0.23.3 (2026-08-24)

**What.** 12 new issues down to 3, and all 3 closed. Two of them were V0.23.2's own fix tripping a
different rule, which is worth recording rather than glossing.

**The float guards, third form.** `separation == 0.0` was a Sonar bug class (float equality). I
replaced it with `not separation > 0.0`, which is S1940 - a negated comparison, with Sonar
suggesting `<=` instead. **Taking that suggestion literally would have opened a NaN hole**, and this
is measured, not argued:

    not nan > 0.0   ->  True    (the form Sonar flagged: refuses NaN)
    nan <= 0.0      ->  False   (Sonar's suggestion alone: lets NaN through)

A NaN separation reaching the division returns NaN as a plotted closing rate, which is the exact
class this module's docstrings exist to prevent - a plausible-looking wrong answer in a trainer
whose purpose is teaching people to distrust a plotted position. Both sites now read
`value <= 0.0 or math.isnan(value)`: no negated comparison for the analyser, and the NaN case
written out where a reader sees it. `sub_satellite_longitude_degrees` refuses a NaN projection,
proved end to end.

**The suppression comment, and the only fix that worked was not suppressing anything.** The line
was named after the token, which trips ruff's hardcoded-password rule (it keys on a variable name
containing "token"), so it carried a directive with a trailing reason. SonarQube flags a directive
with trailing prose as malformed; trimming the prose did not satisfy it either. Renaming the
constant from `TOKEN_HEADER` to `AUTH_HEADER` solved both at once - no rule triggered, so no
directive needed, so nothing for either analyser to parse. Seven references across three files; the
wire value `x-team-token` is unchanged, which is all a client can see.

A small comedy worth keeping: writing the old directive out inside the replacement comment then
tripped ruff's unused-directive rule. It is described there rather than quoted.

**Also.** Nine abandoned agent worktrees under `.claude/worktrees/` removed. They were gitignored
and never shipped, but `grep` over the tree was returning ten copies of every match.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean.

## V0.23.2 (2026-08-24)

**What.** The Code Quality gate rejected V0.23.1 on **12 new issues against a threshold of zero**.
Every one is closed, plus the Dockerfile Lint warning that does not block yet but will.

**Three bugs, all float equality, and SonarQube is right about the class.**
`relative.py:90` compared a Euclidean norm to `0.0` before dividing by it, and `times.py:233`
compared two components to `0.0` to detect a zero equatorial projection. Both now test the property
the code actually needs - `not separation > 0.0`, and `not math.hypot(x, y) > 0.0` - which takes the
same branch for every finite input AND refuses NaN, which the equality tests would have divided by.
The guard should test what the division requires, not one exact value.

**Nine code smells.**
● `healthcheck.py:74` caught `(urllib.error.URLError, TimeoutError, OSError)`. `URLError` subclasses
  `OSError`, and since Python 3.10 so does `TimeoutError`, so the tuple caught exactly what `OSError`
  alone catches while telling a reader they were separate cases. The fail-closed contract is
  unchanged: any transport failure reads UNHEALTHY.
● `auth.py:13` had `# noqa: S105 - a header name, not a credential`. SonarQube parses suppression
  comments and the trailing prose is malformed syntax to it. The reason moved to a `#:` doc comment
  above, where a reader finds it and no analyser parses it.
● `verify.sh:11` read `$1` directly inside a function. Bound to a name first.
● **Five FastAPI dependency sites now use `Annotated`** - and this one was not cosmetic. Converting
  them broke six tests: every gated write returned **422 instead of 201**. The cause is
  `from __future__ import annotations`, which turns annotations into STRINGS that FastAPI resolves
  against module globals. The route dependencies close over `require_token`, a local built inside
  `create_app`, so the string could not be resolved and `actor` was treated as a request field
  rather than a dependency. The future import is removed from `app.py`, with the reason recorded at
  the top of the file: Python 3.12 needs it for none of the syntax here, and the only thing it
  bought was the lazy evaluation that broke the injection.

**Dockerfile Lint, taken this time rather than deferred.** The suid and sgid sweep was a standalone
final `RUN`, which made it the second of two consecutive `RUN`s. It is now the last command of the
purge `RUN`, so it is still the last filesystem mutation in the stage and the warning is gone. Two
contract tests were asserting the SHAPE - `^RUN find / -xdev` - rather than the property, so they
were rewritten to match the command wherever it lives. The invariant is mutation-proved intact:
adding an instruction after the sweep, dropping `-type d`, and making the sweep fail open are all
measured dead.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Mutations 3 run, 3 killed.

## V0.23.1 (2026-08-24)

**What.** The platform's `python-test` job failed on MR 5 (`bfa3ce6`) with seven failures, none of
them a defect in the application and all of them my tests asserting things that are not answerable
in the platform's test container. Two distinct causes, and the second is the more serious.

**Cause 1: `git` is not installed in the test container.** Two tests died on
`FileNotFoundError: [Errno 2] No such file or directory: 'git'`. One of them,
`test_the_repository_tracks_no_prebuilt_binary_or_build_output`, already had `check=False` and a
written no-git fallback branch - and that branch was UNREACHABLE, because `subprocess.run` raises
before there is any exit code to inspect. A guard on the command's RESULT cannot protect against
the command not existing. Both sites now guard on `shutil.which("git")`, which is the condition
that was actually in question.

The other, `test_the_census_answer_does_not_depend_on_what_git_has_been_told`, guarded on
`.git` being ABSENT, written on the belief that the platform runs the suite against an extracted
archive. It does not: the App Store creates a GitLab repository, so `.git` is present and the branch
ran. The load-bearing half of that test - an untracked file is counted by the census - needs no git
and always ran; only the cross-check is skipped.

**Cause 2, and this is the one that matters beyond the test job: the platform's checkout does not
carry `sonar-project.properties`.** It is tracked here and it ships in the artefact, but the
platform generates and owns its own pipeline configuration, exactly as it does `.gitlab-ci.yml` -
which this suite already refused to assert about, for the same reason, and I did not generalise the
lesson. Five tests and the packaging script died on a file that exists in every environment I had
tested. `PLATFORM_MANAGED_ABSENCES` records the class, `_require_local_file` skips with a written
reason, and `scripts/package-appstore.sh` copies what is present and NAMES what is not, so a
genuine omission is still visible in the log rather than silently tolerated.

**How this was verified, because "it passes locally" is what produced the failure.** A PATH farm of
1,285 binaries with `git` removed, plus `sonar-project.properties` moved aside: the full suite runs
**zero failures, zero errors, six skips**, each naming why. That is the platform's shape, reproduced
rather than reasoned about. The local run still asserts all seven.

**What I should have done differently.** `docs/DEPLOYMENT.md` already classified `.gitlab-ci.yml` as
platform-managed and `NOT_IN_A_STOCK_PYTHON_IMAGE` at `tests/test_appstore_contract.py` already
listed `git` as absent from a stock Python image. Both facts were written down in this repository
before the upload, and neither was applied to the tests that depended on them. The pipeline
simulation runs from an extracted zip with a full PATH, so it could not see either.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Platform-shaped run: 0 failed, 0 errors.

## V0.23 (2026-08-24)

**What.** V0.22.0 was uploaded to the App Store and **failed Secret Detection**, the first of the
eight pipeline stages, which gates every stage after it: Dependencies, SAST, Dependency Scanning,
Test and Code Quality all reported Skipped. Container Build and Container Scan both **PASSED**,
which is the first independent proof of the container contract - that stage could not be verified
locally, because the registry blob endpoint is denied by this environment's network policy.

**Why this is a new version rather than another round under V0.22.** Three distinct artefacts
carried the version 0.22.0 in one day, and the platform now holds an upload record keyed to that
number against a build that failed. A version string that means two different things is the
ambiguity this project has spent nineteen rounds removing from its documentation. From here the
version bumps on **every** change, which is now recorded in `CLAUDE.md` and enforced by the six
tests that bind it across both stamps, this changelog, the deploy checklist, the submission
manifest and the artefact itself.

### Round nineteen: the platform's Secret Detection stage, and it was right

**The first real upload attempt returned 12 secret findings, and every one of them was mine.** Not
a false positive in the sense that matters: zero live credentials exist anywhere in this repository,
but twelve source lines carried a literal `scheme://user:pass@host` shape, and a scanner cannot tell
a convincing fake from the real thing. That is the whole point of the stage.

Where they were, and what they were for:

● **Six in `tests/test_appstore_contract.py`** - the test vectors for the credential-echo controls
  in `scripts/check-environment.py`. Every one an `example.invalid` or `h.invalid` host with an
  obviously synthetic password, existing solely to prove the checker never prints userinfo.
● **One in `scripts/check-environment.py`** - a comment illustrating the typo the control was
  written for.
● **Five in `docs/CHANGELOG.md`** - the record of the six times that control was bypassed, which
  quoted the bypassing shapes verbatim.

**The irony is exact and worth keeping.** These are the fixtures for the redaction control that took
six rounds to get right, and the documentation of those six rounds. The work to prove that no
credential is ever echoed itself shipped twelve credential shapes.

**`_credential_shape` already existed and already solved this**, for the `ghp_`-style provider
tokens, with its rationale written out: no fragment reaching eight characters, nothing named after a
scanner keyword, and a test asserting the result. It was never extended to URL userinfo. So
`_userinfo_url` is its sibling: it assembles the same strings at runtime, with `chr(64)` for the
at-sign so no literal in the file carries a colon pair followed by one. Verified that all four
shapes reproduce byte-for-byte, so the tests exercise exactly what they did before. The comment and
the five changelog lines now DESCRIBE the shapes instead of rendering them, which loses nothing: the
record is what was bypassed and why, not the literal string.

**What I got wrong in predicting this.** I told the owner stage 1 would pass, on the strength of the
repository's own hook and a hand-built sweep for provider-token shapes. Both were clean and both
were the wrong sweep: neither had a "Password in URL" rule. A local check that does not implement
the remote rule is not evidence about the remote rule, and I presented it as though it were. The
lesson is the one this project keeps relearning in a new position - a check is worth exactly what it
actually tests.

**Dockerfile Lint: one Low warning, explicitly non-blocking, deliberately NOT taken.** It asks to
consolidate the consecutive `RUN` at `Dockerfile:91`, which is the setuid and setgid sweep. That
sweep is a standalone final instruction on purpose, its own comment says nothing may follow it, and
three contract tests enforce exactly that - `test_the_suid_sweep_covers_files_and_directories_and_
fails_closed`, `test_nothing_follows_the_suid_sweep_in_its_stage`, and the layer-order assertion.
Merging it into the purge would satisfy a Low warning by weakening a hardening invariant that a
policy scan STOPS on, and it cannot be build-verified in this environment. Deferred to V0.23, where
the CI image job can prove the rebuild.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Zero userinfo-URL literals remain in any tracked file,
measured by sweep. The repository's own secret-scan test still passes over every tracked file.

The collected-test count, measured at each commit rather than derived: **757** at the round-two
head, **725** after the redaction rewrite, **767** at the round-eleven head, **770** at the
round-fourteen head, **772** after round fifteen, **777** now: round thirteen moved names between
two lists rather than adding tests; round fifteen added the backup-target symlink refusal and the
gated audit line; round sixteen added the audit-field sanitiser test and two model-cap cases; and
round seventeen added the two frame probes, the primitive-name check and the wrapper check. That last figure was left at 734 through one
round while its neighbours were updated - a stale number inside the paragraph whose subject is stale
numbers, caught by the gate re-deriving it. An earlier version of this row attributed
the whole first drop to "two parametrised tests covering 42 cases", which accounted for 41 of 32 and
ignored nine additions - a derived figure presented as a measured one, in the release whose subject
is exactly that. Every figure here was measured after the final edit, then again after this row was
written, because writing it edits files the contract suite reads.


## V0.22 (2026-08-20)

**What.** Both binding gates FAILED V0.21.0 (`fa21434`). Every finding is closed here. The
BLOCKER is the one worth recording, because it is about this document: **V0.21's own verification
line was fabricated.**

### BLOCKER: I published a pre-commit measurement as the commit's verification

V0.21 asserted "Loop green under the pinned toolchain: 634 passed, 1 skipped, coverage 98.93%".
The reviewer ran the loop at that commit and measured **1 failed, 633 passed, 1 skipped**. Both
figures were real numbers from a real run; the run was just not the one being described. I measured
before the last edit, committed the edit, and wrote the earlier measurement into the release record.

That is worse than a wrong number. A changelog exists so a later reader can trust a claim without
re-deriving it, and a fabricated verification line poisons every other claim in the same row. The
same fault produced the invented `SGP4_ERRORS[5]`, the invented cause in V0.19's changelog, and the
131-degree memory disagreement in V0.21: **an assertion written from recollection when the machine
was right there.**

The habit, in the reviewer's words, which I am recording verbatim because it is the operating
instruction and not a sentiment: *"every one of these is a claim that could have been checked by
running something that already exists in this repository. The habit to build is not more careful
prose, it is running the assertion before writing the sentence about it."*

So the figures in this row were measured after the last source edit and before the commit, and the
version bump was made first so the three version-guard contract tests would fail loudly if the
documents lagged. They did fail, which is the guard working: the simulation reported `3 failed,
655 passed` until `docs/DEPLOYMENT.md` and this row named 0.22.0.

### The stale gate ticks in the submission manifest

The pre-submission checklist carried `[x] engineering-reviewer PASS ... on commit 068b1c4` and the
same for the security gate, while both gates had returned FAIL at `fa21434`. Measured with `git rev-list --count` and
`git diff --shortstat`, **18 commits and 8,279 inserted lines** separate those two states, so the tick was asserting a property of an ancestor
about a descendant. Both are now unticked and both name the FAIL and its commit. A gate verdict is
evidence about the tree it ran against and nothing else.

### Findings closed from the two FAILs

**Undocumented exceptions escaping the physics boundary.** Five of them, each found by sweeping the
input domain rather than by reading the code: `mean_motion_rad_s(1e-200)` raised `ZeroDivisionError`,
`(1e300)` raised `OverflowError`, `greenwich_mean_sidereal_degrees(1e308)` raised `OverflowError`,
`no_drift_alongtrack_rate_km_s` passed non-finite arguments straight through, and
`julian_date_from_utc` validated only `second`, returning a silent NaN for a non-finite `hour` or
`minute`. All five now raise a documented `ValueError` at the boundary.

One of these is a repeat of a specific mistake: **I argued the result-finiteness guard in
`mean_motion_rad_s` was unreachable and removed it.** The argument was that division cannot
underflow while the cube stays finite. True, and irrelevant, because the failure mode is
**overflow**, and float division overflows *silently* to `inf` where `**` raises. The sweep found it
at a semi-major axis of 1e-105 on its first run. That is the third time I have removed a guard on a
reachability argument and been wrong, so the rule is now absolute: a reachability claim is proved by
a sweep that finds nothing, never by prose.

**`RunLog` was not append-only, despite V0.21 saying it was.** `events` was a public list, so item
assignment, `clear()` and wholesale replacement all worked, and a forged log compared equal to a
genuine one. A NaN payload also permanently bricked the fingerprint: accepted at `record()`, refused
at `fingerprint()`, with no way to remove it. Now `__slots__` with a private list, a read-only tuple
property, and all validation, monotonic tick, payload depth, serialisability and a 64 KiB size cap,
moved to the write path where it can still refuse.

**Two tests that could not fail.** `assert all(math.isfinite(1.0) for _ in ...)` iterated the
collection and then tested a literal, so it passed on an empty collection and on a corrupt one
alike; it is now a real JSON round-trip. And the **Earth-rotation sign was entirely unasserted**:
the test advanced a full sidereal day with right ascension advanced by 2*pi, so both operands
returned to their starting values and inverting the operator in `sub_satellite_longitude_degrees`
left the whole suite green. Parametrised by fraction of a day, a quarter day gives -0.0000 degrees
correct against -180.0000 degrees inverted. Mutation-killed.

**The opt-out census was staging-dependent.** It asked `git` for the file list, so it answered 3
before the commit (a new file being untracked) and 4 after. It now walks `src`, `tests` and
`scripts` directly, which is immune to staging and to the worktree.

### The DPIA credited controls that do not exist

`docs/DPIA.md` risk R2 listed score decomposition and a content version hash as **existing**
controls, in a row whose own text said "no scoring engine exists". The table contradicted its own
preamble. Section 2 described every accuracy measure in the present tense when none is built. Both
corrected, R8's two capacity caps are now named as partial and explicitly not retention periods, the
approver's name is `TBC, re-verify` rather than a name I do not have, and every remaining Section 5
row was checked against the source: `hmac.compare_digest` behind a length guard, `REFUSED_ORIGINS`
covering `*` and `null`, `O_NOFOLLOW` at all three open sites, `USER 10001:10001`, `flock` across
load-merge-rename, HTTP 409 on a stale revision, the anti-shrink merge, `Path.replace` after
`fsync` for the atomic write, and 0600 on backups. Every one verified by grep, not by memory. A DPIA
that credits a control it wants rather than a control it has is worse than one that admits the gap,
because the gap is what the conditions exist to close.

### Round two: both gates FAILED the first attempt at this release, and were right

The first commit of V0.22.0 was reviewed and both gates returned FAIL. Recorded here rather than
quietly fixed, because the pattern in the findings is the same pattern this release is about.

**The engineering gate's BLOCKER was an invented figure inside the paragraph about invented
figures.** The text above read "eleven commits and roughly 1,900 lines separate those two states".
Measured, `068b1c4..fa21434` is **18 commits and 8,279 inserted lines**. No derivation produces
either number I wrote. The argument the sentence supports gets STRONGER with the real figures,
which is what makes writing them from recollection so hard to defend: there was nothing to gain.
Corrected in both files, with the commands that produced them named.

**The security gate found the credential control bypassed for a fifth time.** `\s` in the URL
pattern matches sixteen Unicode space characters the neutraliser's enumeration did not cover -
NBSP, OGHAM SPACE MARK, the U+2000 to U+200A run, U+202F, U+205F, IDEOGRAPHIC SPACE. One of them
inside userinfo terminates the authority run before the `@`, and **all sixteen leaked a full token
to stderr**, measured end to end through `main()`. `pwd`, `auth`, `key`, `sig`, `authorization`,
`sas` and every `#fragment` form leaked too.

Four revisions of this control have each closed one bypass and left the shape that produced it: a
pattern that must FIND a delimiter in order to redact. So the shape is gone.

● The URL pass redacts **the whole run** from `//` to the end, terminating at an ASCII space or
  tab and nowhere else. A class that grows with the Unicode tables cannot be the edge of a
  security boundary.
● `NON_PRINTABLE` is now `[^\S \t]`, derived as the complement of what is allowed rather than
  enumerated. It cannot drift from `\s` again because it IS `\s` minus the two characters an
  operator types.
● The version echo is a **whitelist**, strict public PEP 440 or a length. This closes the class no
  pattern could: a bare token in version position has no context to find, is alphanumeric, and
  leaked through all 29 whitespace characters while the URL forms leaked none.
● The unparseable-line report **echoes no content at all**, only a length. `lockfile:number`
  beside it identifies the line exactly, and the host was never the diagnosis.
● `DANGLING_AUTHORITY` was deleted. It existed only to repair damage the truncation did to the
  userinfo pass, and removing the delimiter requirement removed the damage.

The honest part: my own first attempt at that last point echoed a leading distribution name as
"safe", and the test written in the same change caught it within minutes. `ghp_S3CRETLIVETOKEN...`
satisfies the PEP 508 name grammar exactly. A credential in the name position of a requirements
line cannot be distinguished from a name, so the name echo never shipped.

**Both gates found the same forge, one level deeper than the fix.** `Event` was a frozen
dataclass holding a plain `dict`, so freezing the REFERENCE was mistaken for freezing the payload:
`log.events[1].payload["outcome"] = "pass"` rewrote history through the public API with no private
access, and a divergent run was forged back to the genuine fingerprint. Closed three ways -
`Event.__post_init__` freezes recursively to `MappingProxyType` and tuples, the digest is captured
at the write so a later mutation can neither change nor break it, and `seed` is a read-only
property. The `events=` constructor argument, which bypassed every check `record` performed, now
goes through the same one path.

Two more from my own fix, both caught by tests written alongside it: `_freeze` recursed unbounded
and ran BEFORE the depth check, turning a guarded `ValueError` back into an unguarded
`RecursionError`; and adding the bound to `_freeze` made `_check_payload_depth` unreachable, so it
was deleted rather than left looking live.

**Physics boundaries the release claimed to have closed and had not.** `relative_acceleration_km_s2`
was added to the public `__all__` with no validation at all while every sibling had one.
`no_drift_alongtrack_rate_km_s` checked its inputs and not its result, so two finite arguments
multiplied to `-inf` silently. `julian_date_from_utc` was widened from `second` to the three
time-of-day arguments and stopped one short of `day`. `propagate_relative` overflowed `n * seconds`
into a bare `math domain error`. `sub_satellite_longitude_degrees` returned a plausible 79.539
degrees for a point on the spin axis, because `atan2(0, 0)` is 0 by convention.

And the same silent-multiplication lesson again, for the fourth time: coverage flagged the new
result guard in `relative_acceleration_km_s2` as unreached, and rather than argue it dead, a sweep
found **6,084 reaching cases**. `n**2` raises; the multiplication after it overflows in silence.

**Two tests that asserted the opposite of the behaviour they guarded.** The census docstring still
said "an untracked file is not seen" after the fix made untracked files seen, its name said
`enumerates_tracked_files`, and two of its four assertions could not fail once the walk was
restricted to three directories containing neither `.venv` nor a worktree. Renamed, rewritten
around the staging-independence property, and mutation-killed. Its first version then failed the
SIMULATION, because the extracted artefact carries no `.git` - the same fault as the no-binaries
test that died on the platform runner, caught this time by running the simulation before claiming
anything. The git half is conditional; the half that must hold everywhere needs no git.

Export completeness is now asserted in both directions for both packages, which is what would
have caught `relative_acceleration_km_s2` being public before a reviewer did.

### Round three: the sixth bypass, and deleting the control rather than revising it again

Both gates FAILED round two as well. The engineering gate's BLOCKER and the security gate's first
MAJOR were the same defect: **a sixth bypass of the credential redaction**, in three forms.

● An ASCII **space or tab** inside userinfo splits the credential out, because the whole-run
  rewrite still terminated the run at those two characters and the neutraliser deliberately spared
  them. Sixteen Unicode spaces narrowed to two, not removed.
● A **bare token in marker position**, which has no surrounding context to find at all.
● The **distribution name**, echoed raw on the parsed path: `<token>==1.0.0` printed the
  canonicalised token in full, because `canonicalise` lowercases and folds separators so a token
  comes out looking exactly like a name.

And the test written to prevent exactly this excluded the two characters that were leaking:
`hostile = [c for c in hostile if c not in " \t"]`. A property test scoped to the part of the class
already fixed, passing while the open part stayed open.

**So `redact()` is deleted.** Every revision had narrowed the class - 29 characters, then 16, then
2 - which felt like progress and was a function converging on a limit above zero. The shape was
always the same: a pattern that must FIND a delimiter before it can hide anything. No pattern finds
a secret in arbitrary text, so the answer was never a better pattern. It was to stop echoing
arbitrary text.

Every echo site now describes its input. `describe_version` is a strict PEP 440 whitelist,
`describe_line` and the marker note emit a length only, and the interpreter-probe failure reports
an exit code. `redact()`, `URL_CREDENTIALS`, `QUERY_CREDENTIALS`, `NON_PRINTABLE` and
`MAX_ECHO_LENGTH` went with it, because a control with no caller is one the next reader trusts.
Measured end to end across all 29 whitespace characters against eight line shapes covering every
echo site: **zero occurrences of the token in stdout or stderr.**

One echo cannot be reduced to a length: the divergence report has to name the distribution, or
"pinned 0.115.0, NOT INSTALLED" names nothing. That one is **bounded rather than closed** - a
canonical-shaped name up to 32 characters echoes, anything longer or oddly shaped is described - and
the residual is written into `describe_name` and asserted in its test, including the case that still
echoes. A bounded gap an operator can reason about beats a completeness claim a seventh bypass
would embarrass.

**Two more findings of my own making, both from round two's fixes.** My first attempt at the
probe-stderr echo wrapped it in `redact()`, putting arbitrary text back through the function I was
in the middle of proving unsound. And `_freeze` bounded depth but not COST: `v = "z"*10` then
`v = [v]*40` six times is a few hundred bytes, depth 7, inside the depth cap, and expands to 4.1
billion elements because every reference is the same list. The size cap measures `len(canonical)`,
which is never computed, so the write did not fail - it did not return, still allocating at a
sixty-second timeout under a 2 GiB limit. A node budget bounds the work; the refusal now takes
0.064 seconds.

**The magnitude bound the module had already learned.** `julian_date_from_utc(1e308, 1, 1)` is
finite and integral, passed both new loops, and raised a bare `OverflowError` from `math.floor`.
Worse silently: `year=1e300, month=3` returned 3.652425e+302 and `day=1e308` returned 1e+308 -
finite numbers that are not dates. `greenwich_mean_sidereal_degrees`, twenty lines below, had
applied `MAX_JULIAN_DATE` for this exact reason since the day it was written. An integer `10**400`
was worse again: `math.isfinite` itself raises on it, so the guard against undocumented exceptions
was throwing one.

**A test that could not see what its own docstring claimed.** The reverse export check filtered on
`__module__`, which an `int`, `float` or `str` does not have, so it was blind to every exported
CONSTANT while citing `MAX_PAYLOAD_BYTES` and `MAX_PAYLOAD_DEPTH` as two of the three faults it
caught. It caught neither: dropping `MAX_PAYLOAD_BYTES` from `__all__` left it green. Now derived
from each submodule's namespace with a written curation list, and it immediately caught
`MAX_PAYLOAD_NODES`, a constant added twenty minutes earlier in this same round.

Wording corrected where it overstated: `events` is immutable *through the public API*, because
`gc.get_referents()` reaches the dictionary behind a `MappingProxyType` - harmless only because the
digest is captured at the write, which is the half doing the real work. An `Event` subclass
overriding `canonical()` can still forge a fingerprint, named as outside the threat model rather
than left to be discovered. And "35 axes" was a real measurement of an ad-hoc grid, not of the
committed sweep, which reaches that branch at 2; both are now stated.

### Round four: the gates found the fix for the bypass had its own bypasses

Both gates FAILED round three. Between them: nine MAJORs, and the honest summary is that three of
them were introduced by round three's own fixes.

**The name bound was wrong twice, and the second version was worse than the first.** The comment
said 32 characters "admits every real name". Measured, it does not:
`opentelemetry-instrumentation-fastapi` is 37 characters,
`opentelemetry-exporter-otlp-proto-http` 38, `google-cloud-bigquery-datatransfer` 34 - exactly the
dependencies a FastAPI service acquires, every one of them redacted instead of named, defeating the
report's one job. And 32 is precisely the length of a hex API key, so the bound admitted the whole
of the commonest fixed-length secret format while excluding real names.

Told the figure was invented, I re-derived it from the longest name pinned in THIS repository
(`pip-requirements-parser`, 23) and set 24. That is a real measurement of the wrong population: the
bound would have started redacting real names the first time a dependency arrived.

The reading I should have reached first is that **no length separates the two populations.** Names
run 3 to 60-odd characters and credentials 20 to 45; they overlap completely. So the length cap is
now PyPI's own maximum, kept only to bound one log line, and the name echo is documented as a
RESIDUAL rather than dressed as a control: shape is refused, length is not a secrecy boundary, and a
name-shaped credential does echo. The test asserts the residual, so closing it later has to be
deliberate.

**The version echo was unbounded, because deleting the dead pattern took a live bound with it.**
`SAFE_VERSION` constrains shape and not size, so `pkg==1.<5000 nines>` printed five thousand digits
to stderr. `MAX_ECHO_LENGTH` had bounded every echo in the file and went out with `redact()`.
Deleting dead code is right; deleting a live bound because it sat next to dead code is how a fix
becomes a regression.

**The property test did not reach two of the four echo sites it claimed.** `main()` reports
unparseable lines and RETURNS before the pin report, so a body containing any unparseable line never
exercises the version echo or the name echo at all - and four of the eight shapes were unparseable.
Mutating `describe_version` or `describe_name` to return their input left the test green. It now
uses two bodies, one of which parses cleanly, and asserts POSITIVELY that both sites were reached,
so it fails if a future change stops it looking rather than passing because it stopped.

**The magnitude guard, fixed three times in three rounds.** Round one checked `second`. Round two
widened finiteness to all six arguments and magnitude to year, month and day. Round three left
`hour=1e308` returning 4.1666666666666665e+306 and `hour=10**400` raising the undocumented
`OverflowError` from the `day_fraction` arithmetic instead of from `math.floor`. The comment
directly above it states the rule it broke: widening a guard to the arguments that were REPORTED
rather than to the whole signature is how a boundary gets fixed twice. One loop over one tuple now.

**And the test for that guard had the same shape as the guard.** With the magnitude bound narrowed
back to the three date components, the whole physics-times file stayed green, because my
parametrisation enumerated only the components I had fixed. Thirteen cases now, all six arguments.

**Two dead-prose findings, both in the file whose commit message is about dead code.**
`requirement_lines` still described `redact()` "neutralising the separator as a second layer" after
`redact()` had been deleted, and a contract test still asserted the absence of a marker the script
can no longer emit - an assertion that passes forever and reads as coverage. Both re-pointed at what
is actually true now: the line number is the diagnosis, and inventing line breaks makes it wrong.

**My own mutation harness left a disabled guard in the working tree.** A shell loop restored each
file after testing it, timed out mid-iteration, and left `if False:` in place of the node-budget
check - which the engineering gate found while reviewing, and reported as a MAJOR against an
uncommitted tree. It never reached a commit, and the reason it did not is that a reviewer looked.
The deadline test that should have caught it could not: I had measured elapsed time AFTER the call,
which bounds nothing when the call never returns. It is a subprocess with a real timeout now, and
it fails in thirty seconds instead of hanging for ever.

Also closed: `versions_equal` letting a plain `ValueError` escape as an uncaught traceback on a
5,000-digit version; `record`'s docstring listing three refusals when there are four; the curation
list's stated reasons being wrong for `SGP4_ERRORS`, `TEME_OF_DATE` and `BOUNDARY_REFUSAL`, which
matters because a curation list is worth exactly what its reasons are worth; four test names still
describing the deleted control; and the comment reflow damage from the surgical edits.

### Round five: both gates found the same MAJOR, and it was the control this release added

Both gates FAILED round four and both led with the same finding: **`MAX_VERSION_ECHO` shipped with
no test able to see it.** Deleting the length check echoes a 5,002-character version to stderr with
all 734 tests green. That is byte-for-byte the shape the previous round FAILed on for
`describe_name`, applied to the control added to fix the round before that. The security gate's
phrasing is the one to keep: *the control the commit was written to add is the one control the suite
cannot see.*

Two more of the same kind. `versions_equal` had **no test at any commit**, so its `ValueError` fix
was invisible. And the integrality scoping I introduced - exempting fractional hours and seconds
from the whole-number rule - was untested in the relaxing direction: widening it back to all six
components left the entire suite green, because not one of the fifteen `julian_date_from_utc` call
sites in the suite passed a fractional time. Thirteen cases for the half that was reported to me,
none for the half I added.

**A measurement contradicting my own comment.** I wrote that two shapes in the property test "parse,
so they reach the version echo and the name echo". They do not. A pin is `name==version`, and any
whitespace inside either field makes the line unparseable, so `main()` reports it and returns before
the pin report: measured, **0 of 58 separator-bearing shapes parse**. That second body ran 29 extra
subprocesses down the identical path under a comment claiming otherwise. The whitespace class is now
swept over the sites whitespace can reach, and the two parsed sites are covered by a separator-free
body carrying a 5,002-digit version, which is the wiring test that was missing - a direct call to
`describe_version` proves nothing, as `describe_name` demonstrated a round earlier.

**The third invented figure for the same constant, and this time I measured it.** The comment
justifying `MAX_NAME_ECHO = 64` called it "PyPI's own maximum name length". PyPI has no such maximum:
its project-name validation is a pattern with no length validator, `packaging` implements the PEP 503
grammar with no length bound, and the column is free text. Measured against the live simple index on
2026-08-21: **875,180 projects, 141 with canonical names over 64 characters, the longest at 188, none
over 200.** So 64 excluded 141 real distributions exactly as 32 and 24 did.

The cap is 200 now, above every name that exists, and the assertion that pins it is the point:
reverting to 64 previously left the suite green, which is how three successive bounds shipped while
redacting real packages. It is an OUTPUT bound and is documented as not being a secrecy boundary.

**Two residuals moved into the register where a reader looks.** `docs/SECURITY.md` items 8 and 9: a
lowercase name-shaped credential in name position echoes, and a credential of 40 characters or fewer
in version position echoes. (This row said "an all-numeric credential" when it was written. That was
false then and is corrected in the V0.22 round-six note below; the class was never limited to numeric
values.) Both are accepted because the divergence report
cannot do its one job without naming the distribution and the version it found. Six revisions of
that control tried to spot a credential inside attacker-influenced text and each was bypassed; the
seventh stopped echoing arbitrary text, which closed every site except the two that must name what
they found.

**A test that could hang the run it was meant to report on.** The in-process shared-references test
ran before the deadline test and, under a mutation deleting the node budget, never returned: the file
ran 400 seconds with zero failures before being killed. So the deadline test could prove the control
while the suite still reported a budget regression as broken infrastructure, which is the outcome
that test existed to remove. Both now share one subprocess harness, and the whole file fails in
sixty seconds instead of hanging. Moving them out took the refusal branch off the coverage
measurement, so a flat 100,001-element payload exercises it in-process - and the control I first
wrote for it was wrong, asserting that a payload just under the budget is accepted when 99,998
integers serialise to three times the byte cap. For flat input the byte cap binds; the node budget
exists for input whose serialised size is never computed.

**And a process change, because this is twice now.** My mutation harness left a disabled guard in the
working tree for the second time, a shell loop timing out mid-iteration. Mutation runs go in a
throwaway `git worktree` from here on, so the primary tree cannot carry a mutation at all. Twice in
that session the harness also reported SURVIVED for mutations that were never applied, the shell
quoting having silently failed - so a mutation is now confirmed applied before its result is
believed.

### Round six: a bound asserted against itself is not asserted, and a documented hole is not closed

Both gates FAILED round five, and the two findings that matter are the same mistake in two shapes.

**Two constants were "pinned" by tests derived from the constants.** `MAX_VERSION_ECHO` was checked
with `at_limit = "1." + "9" * (MAX_VERSION_ECHO - 2)`, and `MAX_PAYLOAD_NODES` with a payload of
`MAX_PAYLOAD_NODES + 1` elements. Both self-adjust, so only the LOWERING direction was ever caught:
measured, raising the version cap to 4,000 and the node budget to 200,000 each left the whole suite
green. Raising the version cap that far re-opens the disclosure it exists to bound. And both
docstrings claimed the opposite - "neither raising nor lowering the constant passes unnoticed", and
"that pins both constants against each other" - which is prose describing a control the test does
not have, one round after that exact fault was found. Both constants are pinned to literals now, and
both raise-direction mutations are killed.

**The version echo had a real hole I had documented instead of closing.** The PEP 440 local-version
segment was unbounded, `\+[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*`, so anything alphanumeric joined by `.`
or `-` was version-shaped and echoed under the 40-character cap. Measured through the real script:
a 32-character hex key carried in a local segment, a cloud access key identifier, a base32 secret
and an underscore-free JWT segment all reached stderr
in full. Only the underscore was excluded.

Worse, the register entry I added in round five to state that residual honestly said `SAFE_VERSION`
"excludes every credential format that carries a letter, an underscore or a separator". Two of those
three clauses were false, and an operator reading it would have concluded a personal access token in
version position could not reach a log. **An accepted residual whose documented boundary is wrong is
not an accepted residual; it is an acceptance taken on a false premise.**

So the segment is bounded: eight characters per component, at most three components. Every real
local version still echoes - `+cu118`, `+cpu`, `+abcdef.1`, `+local.1` - and a longer token is
reported by length. (Both halves of that sentence were false and are retracted in the round-seven
and round-eight notes below: `+computecanada`, `+20130313144700` and `+ubuntu0.22.04.1` are real
build tags that were NOT echoed, and a token written with dots in it was.) None of the three lock files pins a local version at all, so the bound
costs nothing today.

**And the description of what remains was wrong for the third time, which the next round caught.**
The bound narrows the class by length PER COMPONENT, not by character class: three components of
eight admit 24 alphanumerics plus two separators, so a cloud access key identifier in version
position is described while the same 20-character identifier written with two dots in it still
echoes in full. Measured, both. (This paragraph said 26; three components of eight is 24 plus the
two dots, which the next round caught - arithmetic asserted rather than computed, in the sentence
whose whole purpose was to be the measured one.)
Calling the residual "all-numeric" was false before the bound and remained false after it. It is
stated accurately now, in the same words at all four places that describe it, because the previous
round's finding was precisely a retraction applied to one of two locations.

**A retraction applied to one of its two locations.** The comment at the constant said PyPI has no
name-length maximum; `describe_name`'s own docstring, forty lines below, still said the cap was set
"at PyPI's own maximum name length". The file refuted and repeated the same invented fact, and the
docstring is the half a reader trusts. Fixing one of a claim's two locations is the same fault as
installing a control at one echo site of two.

**And a third uncaught-exception site, after two were fixed in one round.** `json.loads(result.stdout)`
was unguarded, so an interpreter printing anything before the probe's output - a `sitecustomize.py`,
a `.pth` file, a wrapper on a platform runner - exited leg one with a `JSONDecodeError` traceback,
fail-closed only by the coincidence that `EXIT_MISMATCH` is 1. Guarded, and the stdout is described
rather than echoed like every other report in the file.

Also corrected: the collected-test figure, left at 734 for a round while its neighbours were updated,
inside the paragraph whose subject is stale numbers; the pre-measurement "3 to 60-odd characters"
range, contradicted by this release's own 188-character measurement; a stated 27 characters that was
26; an assertion that could not fail (`len(at_limit) == MAX_VERSION_ECHO`, true by construction); and
two node-budget tests that had become the same assertion twice.

**Verified.** Loop green under the pinned toolchain: **744 passed, 1 skipped**, coverage
**99.04%** against an 80% floor, all three lock files audited clean by `pip-audit`. All seven physics
and scenario modules at **100% line and branch coverage**. Pipeline simulation green against the
version being shipped: **741 passed, 4 skipped**. Collected: **745**. Four mutations confirmed
applied and killed this round: the local-segment bound, the `json.loads` guard, and both constants in
the raise direction that previously survived.

### Round seven: the same overstatement in four places, and the last unpinned bound

The engineering gate FAILED round six with five findings that are one factual error repeated. The
code was right; every claimed control was real and every claimed mutation kill reproduced. What was
wrong was the prose around the new bound, in four places, and it was wrong in the direction that
matters: it described a NARROWER echo class than the bound actually has.

Three components of eight characters admit 24 alphanumerics plus two separators. So a cloud access
key identifier in version position is described - the form a credential actually arrives in - while
the same 20-character identifier split across components echoes in full. Measured end to end through
the
real script. Calling that residual "all-numeric" was false before the bound and stayed false after
it, and it appeared in `SAFE_VERSION`'s comment, `describe_version`'s docstring, `SECURITY.md` item 9
and the changelog. All four now carry the same measured sentence, written in one edit, because the
round before had been about a retraction applied to one of two locations.

There is no cleaner separation to be had, and that is worth stating rather than iterating on: real
local versions and real secrets overlap in length, so no per-component or total bound separates
them. (An earlier version of this sentence gave the ranges as "3 to 13" and "16 up". Neither was
measured: `+ubuntu0.22.04.1` carries a 15-character label, past the claimed ceiling, and the same
file put the credential population at "20 to 45" fifty-seven lines away. The qualitative point was
sound and the numbers were decoration, so the numbers are gone.)
A total-length cap fails exactly as the name cap failed at 32, 24 and 64. What the bound buys is the
undotted form, which is the realistic one; what it does not buy is a character-class exclusion, and
saying so is the whole point.

**The local-segment bound was also the last echo bound in the file with no absolute pin**, in the
commit whose subject was pinning the other two. Measured: weakening the per-component limit to 19 or
the component count to 5 both left the suite green. Four boundary assertions now, both weakenings
killed.

Also corrected: "real names run 3 to 188 characters" in the constant's comment, which the same commit
had corrected to 1-to-188 in the test and not here - re-measured against the live index, minimum 1
(single-character names `0` through `9`, `M`, `T` all exist), maximum 188; a comment line duplicated
verbatim; a helper docstring still describing two callers after one was deleted; and a cross-reference
pointing at a docstring that went with the test it belonged to.

**Verified.** Loop green under the pinned toolchain: **744 passed, 1 skipped**, coverage **99.04%**
against an 80% floor, all three lock files audited clean. All seven physics and scenario modules at
**100% line and branch coverage**. Pipeline simulation green: **741 passed, 4 skipped**. Collected:
**745**. Two mutations confirmed applied and killed: both local-segment weakenings that previously
survived.

### Round eight: the local segment is gone, and so are the credential-shaped test fixtures

The security gate answered a question I had asked it rather than measured, and its answer was to
delete the thing rather than describe it better.

**The bounded local segment closed the accidental paste and left the deliberate one open.** It
measured real credential formats: each is described in its contiguous spelling, and one that fits
the three-component bound is not described when separated. (An earlier version of this sentence said
"none is" without the qualifier, which is false above 24 characters: a longer format has no
separated spelling the bound admits.) Two dots inside a 20-character cloud access key identifier put
all twenty characters back on stderr, reconstructible by deleting the dots. So the bound was worth
something, and not enough.

**So `SAFE_VERSION` no longer admits a local segment at all.** What echoes is a numeric release with
optional pre, post and dev segments. A `torch==2.1.0+cu118` pin now reports its name plus
`[REDACTED:unrecognised-version, 11 characters]`, which is enough for an operator who has to open the
lock file anyway, and no lock file here pins one. Three successive descriptions of that segment were
each wrong once - as "all-numeric", as covering "a 20-to-38-character token", and as keeping "every
real local version", which genuine build tags disprove (`+20130313144700`, `+ubuntu0.22.04.1`, and a
local label with an underscore, which PEP 440 permits). One invariant that cannot drift is worth more
than an echo that kept needing a new explanation.

**And the fixtures I wrote to prove the leak were themselves a pipeline problem.** The gate fed the
committed file to this repository's own pre-write secret-scan hook and it exited 2: two of my test
constants match its AWS and platform-token patterns. Nothing was a live credential - two are
published documentation placeholders and one is the RFC 4648 base32 example - but Secret Detection is
the FIRST of the App Store's eight stages, and a scan gate that cries wolf on a defence project is a
gate people learn to wave through. The fixtures are assembled by concatenation now, so the assertions
are byte-identical and nothing matches at rest, and the two documents describe the shapes instead of
reproducing them. The literals remain in this branch's history, which a tree-scanning stage will not
see but a history-scanning one would; flagged rather than quietly left.

**A fourth site of the uncaught-exception class, one line below the third.** Guarding
`json.loads` guarded the PARSE and not the parsed value's type, so a probe answering `["x"]`, `12345`,
`null` or `{"pkg": 12345}` reached `raw.items()` and raised `AttributeError` or `TypeError` as an
uncaught traceback - fail-closed only because Python's uncaught-exception exit code is 1. Eight
shapes measured, all eight now refused with a described report.

**One header added on the gate's recommendation.** `X-Content-Type-Options: nosniff`, on every
response the user stack produces, including one a middleware answers itself, which is why
`NoSniffMiddleware` sits outermost of the user layers. (It does not reach the unhandled-exception
500; see round nine below, and `on_unhandled` sets that one's headers itself.)
It is the one content-type header that is not inert here: a stored `title` or `notes` comes back in a
`GET /api/v1/sessions` body and a browser pointed at that URL decides what the bytes are.
Content-Security-Policy and `Referrer-Policy` stay absent and are now recorded as item 10 of the
accepted-risk register with the reason, rather than being unexplained.

Writing that test also corrected an assumption of mine: body validation runs BEFORE the token
dependency, so a malformed write is refused on its shape without the token being compared. That is
the right order, and the docstring says so rather than leaving a reader to wonder why the test
expects 422.

### Round nine: two controls shipped with no test, and a claim a reviewer had to run to disprove

Both gates FAILED, and both led with the same two blockers.

**`NoSniffMiddleware` said "every response" and could not reach a 500.** Starlette installs
`ServerErrorMiddleware` above every user middleware, and that is what renders the
unhandled-exception response - so registering outermost among user middleware still missed the one
response class carrying an error string. Measured: a 500 answered with neither
`x-content-type-options` nor `access-control-allow-origin`, while the code and three documents
claimed otherwise. "Outermost" was true and bought less than it sounded. The handler sets both
headers itself now, the cross-origin one scoped to the configured origin, and three parametrised
cases pin it. The missing CORS header was the more consequential half: a browser that cannot read a
500 reports an opaque network error, which is exactly the case an operator most needs to see.

**The JSON shape guard shipped with a changelog claiming eight measurements and no test.** Deleting
the whole guard left the suite green. I had measured the eight shapes by hand, written "all eight now
refused with a described report", and asserted none of it - which is one commit away from a
regression nobody sees. Eight parametrised cases now, mutation-killed at **eight** failures - I wrote nine, and the gate
measured eight: the eight cases and nothing else, because no other test in the repository references
that code path. Nine was the count for deleting the parse guard as well, which is a different
mutation. In the row whose own headline is that figures must be run before they are written. Its report
also named the shape it WANTED as the shape it got (`{"pkg": 12345}` said "expected an object of
strings, got dict"), so the two branches are split.

**And "nothing matches at rest" was false, for the second time in two rounds.** The security gate ran
this repository's own hook over the tracked tree and it still exited 2. My concatenation fix did not
work, and the reason is worth recording: the rule matches a variable NAME containing `token`,
`secret` or `key`, followed by any quoted run of eight or more characters. Renaming is what defeats
it, not assembling. Six sites fixed, every fragment now under eight characters, no name carrying a
scanner keyword - and, the durable part,
`test_no_tracked_file_trips_this_repositorys_own_secret_scan` walks `git ls-files` and runs the hook
over every tracked file. It immediately found two more files I had not touched. A claim a reviewer
has to check is a claim that will be wrong again; this one is now asserted.

Also corrected, all of it prose overtaking its own measurements: the cap, not the grammar, is what
limits an echoed version (`999.999.999preview1.post999.dev999999999` is 40 characters and echoes, so
"40 is generous" was wrong); `2.1.0+cu118` describes as **11** characters, not 12; "real local labels
run past fifteen characters and real secrets start below twenty" was two numeric assertions inside a
sentence calling itself qualitative, and is now numberless after four unmeasured figures in three
rounds; the universal claim that no separated spelling echoed is scoped to 24 characters, above which
the three-component bound admitted none; a paragraph recording the absence of the very header this
release added; the collected count stale for a second consecutive round; "twenty-one measured" with
no artefact recording the measurement; and "JSON-only" where `/livez`, `/ping` and `/health` return
plain text - which is exactly the sniffing case the new header covers.

**Verified.** Loop green under the pinned toolchain: **766 passed, 1 skipped**, coverage **99.06%**
against an 80% floor, all three lock files audited clean. `middleware.py` and all seven physics and
scenario modules at **100% line and branch coverage**. Pipeline simulation green against the version
being shipped: **762 passed, 5 skipped**. Collected: **767**. Two mutations confirmed applied and
killed: the JSON shape guard and the nosniff registration.

### Round ten: the security gate PASSED, and the correction had outrun its own distribution

**`security-reviewer`: PASS.** No blocker, no major. It could not defeat either fix: the 500's header
dict survived a foreign origin, `*`, `null`, an upper-cased and a trailing-slash variant, a
`<origin>.evil.example` suffix, two `Origin` headers with the foreign one first, and the `"" == ""`
case with `ALLOWED_ORIGIN` unset - and header injection is closed by construction, because
`config.py` strips non-printables from the configured value before it can ever be echoed. The
tracked tree is clean against the hook and against eight gitleaks pattern families. Five minors,
all prose or test-strength.

**`engineering-reviewer`: FAIL, entirely on documents**, and its diagnosis is the one worth keeping:
*last round the prose outran the tests; this round the correction outran its own distribution.* The
"every response" claim was corrected in the middleware, the handler and the test, and left standing
in `docs/SECURITY.md` item 10 - the one place this changelog nominates as carrying the current
position.

Its countermeasure is one line, so I ran it before writing anything: grep the claim string tree-wide.
That found **two more sites the gate had not listed**, in `app.py` and `test_http.py`. The claim had
survived at four places, not one. All four are scoped now - and the claim that "every `outermost`
now says among user middleware" was itself false when written, which the next round caught with a
thirty-second grep: five sites in source and tests still carried the bare absolute, including
`_install_cors`, which asserted an ordering fact its own green test contradicted.

The lesson is narrower and more useful than "grep before claiming". The sweep grepped the SENTENCE
about the header and missed the same absolute attached to a different layer. What has exactly one
authority here is the PROPERTY - which middleware is outermost - and that authority is
`test_the_middleware_order_puts_the_limiter_outside_the_body_cap`, asserting `app.user_middleware`
directly. Every ordering claim in the source now cites it - because outermost among user middleware is exactly what does not reach a 500.

The second MAJOR was a count contradicting its own entry ten lines away: 767 collected on one line,
755 on another. Third consecutive round of a stale figure in the paragraph whose subject is stale
figures.

Also fixed, and most of it collateral from my own edits: a blanket `token` to `needle` rename turned
gitleaks' `aws-access-token` rule into `aws-access-needle`; a substitution left "a cloud access key
identifier (a cloud access key identifier)"; "JSON-only" survived at a fourth site, in a docstring
attached to a list containing two plain-text paths; and `test_every_response_carries_nosniff` kept its
overstated name after the round that disproved it.

From the security gate: the nosniff control was tested but **uncited**, so the register's
doc-to-test sweep could not see it - two table rows now, and renaming a cited test to a
non-existent one turns that sweep red. The two-branch split of the shape report was unasserted
(reverting it left the suite green), so the two object-valued cases assert their distinguishing
message. The tracked-tree scan keyed on the string `BLOCKED` rather than the exit code, so a hook
that crashed would have read as clean. Item 9 stated the residual as an instance while
`describe_version` claimed the two carried "the same words"; item 9 now states the grammar. And the
non-HTTP scope guard is documented as behaviourally inert rather than tested a fourth time - every
non-HTTP message carries a type that is not `http.response.start`, so there is nothing observable to
assert.

One figure of mine it corrected: I wrote the shape guard as "mutation-killed at nine failures" and
the measured answer is eight. Nine is the count for deleting the parse guard as well, which is a
different mutation.

**Verified.** Loop green under the pinned toolchain: **766 passed, 1 skipped**, coverage **99.06%**,
all three lock files audited clean. Pipeline simulation green: **762 passed, 5 skipped**. Collected:
**767** - measured once and quoted from that measurement, which is the other countermeasure. Two
mutations confirmed applied and killed this round: the two-branch shape report, and a register
citation pointing at a test that does not exist.

### Round eleven: the sweep grepped the sentence, and the property was somewhere else

**`security-reviewer`: PASS on the exact head.** It proved scope rather than accepting it, parsing
all nineteen source files at both ends of the diff and hashing the AST with docstrings stripped: none
differ, so the 500 headers, the RunLog caps, the `times.py` bound and the storage, auth, CORS and
limiter controls cannot have regressed, because the code is the same code. It also corrected a figure
in my briefing - I said the two-branch revert killed nine tests and it kills eight; nine is the count
for deleting the parse guard as well. The repository already said eight.

**`engineering-reviewer`: FAIL, and the diagnosis is the most useful of the eleven rounds.** The
class did not vanish; it moved sideways one layer. My countermeasure grepped the CLAIM STRING - the
sentence about the nosniff header - and that sweep was complete. What it could not see was the same
absolute attached to a DIFFERENT layer: `_install_cors` said "Registered LAST so it is the outermost
middleware", true when written and false from the moment `NoSniffMiddleware` was registered after it,
in the very commit that created the 500-header defect the three previous rounds were spent
correcting. Five sites in source and tests still carried the bare absolute, and this changelog's own
completeness claim about the sweep was false when written.

The lesson is narrower and more useful than "grep before claiming":

**The property has exactly one authority, so cite the authority beside the claim.** Which middleware
is outermost is settled by `app.user_middleware`, asserted by
`test_the_middleware_order_puts_the_limiter_outside_the_body_cap`, which was passing green on the
correct four-layer order the entire time `_install_cors` said otherwise. A prose claim about ordering
that does not name that test is a claim with no anchor. Every ordering claim in the source now names
it, which is the one thing in this round that generalises.

**And a completeness check that was worse than none.** The reverse citation sweep the security gate
asked for - a security test with no register row - was straightforward to write and my first version
was useless: a shrinking-prefix matcher reduced a name to `test_an`, found it inside
`test_anonymous_writes_require_the_explicit_opt_in`, and reported every `test_an...` as cited.
Measured: an uncited test planted in `test_middleware.py` passed the check. Tightened to match the
policy's actual citation tokens, it flagged a further batch the loose version had masked. **That
batch was recorded three different ways in one release** - "twelve" here, "Ten more" in the
exemption list's own comment, and eleven names actually committed. Only the third is a measurement;
the other two are prose. The committed list is the record, and round twelve rebuilt it from an AST
walk anyway, so the figure is superseded rather than corrected. A checker that reports the
completeness it did not verify is the exact shape this suite keeps finding, and I wrote a fresh one
while closing an instance of it.

Also fixed: the module docstring's pipeline enumeration omitted the nosniff layer while claiming the
registration order was "the reverse of that list"; the release summary's overstatement, corrected
fifteen lines below but not at the site; the mutant ledger two rounds stale in the document whose own
thesis is that a mutation claim is worth what its run measured; and a `or exit N` fallback that could
not fire, because a crashing hook's stack trace yields a truthy fragment when split on `matches:`.

**Verified.** Loop green under the pinned toolchain: **767 passed, 1 skipped**, coverage **99.06%**,
all three lock files audited clean. Pipeline simulation green: **763 passed, 5 skipped**. Collected:
**768**. Mutations: this entry said "Three ... confirmed applied and killed" while the mutant
ledger in `docs/SECURITY.md` recorded "2 run, 2 killed" for the same round. The two figures were
written from the same session and one of them is wrong; the ledger's is the lower and the one I can
still tie to a recorded run, so **2 run, 2 killed** stands and the third is withdrawn as
unverifiable. The killed pair: the reverse citation sweep against an uncited new test, and the
tightening it needed to catch a masked name. Both were then shown insufficient in round twelve,
which is the more useful fact than either count.

**Superseded.** A paragraph here recorded the absence of Content-Security-Policy,
`X-Content-Type-Options` and `Referrer-Policy` as a deliberate choice for the owner to
confirm, and asserted that "no document claims otherwise". The round-eight note below adds
the second of those headers, so both halves went stale in the same release entry that
changed them. Item 10 of the accepted-risk register carries the current position.

### Round twelve: the completeness check could not see the keyword it was built for

**Both gates FAILED, with the same BLOCKER, and it was in the thing I built last round to close
their finding.** The reverse citation sweep matched `line.startswith("def test_")`. Seventeen of the
twenty tests in `test_middleware.py` are `async def`. So the suite whose omission from the register
motivated the entire check was the suite the check could not see. Both reviewers planted an uncited
`async def` test and both watched it pass; my own verification of the same check had held only
because I happened to write the plant as `def`.

Measured before the fix: across the four suites it named, the sweep recognised **45 of 62** tests;
in `test_middleware.py`, **3 of 20**.

**The lesson is not "handle async too".** It is that a completeness check reports a completeness,
and the report is worth exactly what the matcher can see. Two rounds, two matchers, two blind spots:
a shrinking prefix that matched inside unrelated names, then a line prefix that missed a keyword. In
both cases the check passed, said "complete", and was not. The fix is to stop pattern-matching source
text for a structural question: it walks the AST now, which sees both function kinds and survives
decorators, reflowed arguments and formatter changes, none of which a line scan does.

**What that visibility then found.** Widening the sweep from four suites to seven (`test_audit.py`,
`test_http.py` and `test_storage.py` were missing, while the register cites the 500-header test, the
middleware-order test, the symlink refusals, the atomic write, the anti-shrink merge and the
log-injection block, all of which live there) took the tests it walks from 62 to **168**, and
surfaced **74** names nothing had ever checked. Triaging them:

● **Four register rows claimed more than they cited**, and are now cited: the `==` census behind
  "no token is compared with `==`"; the 413 half of "a 413 or 429 still carries the cross-origin
  header"; `app.state` as a fourth token-exposure surface under "no secret in any response, log or
  audit line"; and the backup copy as a third symlink surface, which now has its own row. Citations
  in `docs/SECURITY.md`: **73 to 77**.
● **Seventy are exempted with a written reason**, grouped by the cited row each is a case of. The
  exemption list went from **32 entries to 100**: 2 removed, 70 added.

**Two dead exemptions, and the reason they were invisible.** `UNCITED_SECURITY_TESTS` held
`test_a_token_at_the_minimum_is_` and `test_data_dir_resolution_prefers_explicit_the`, truncation
residue from the shrinking-prefix matcher, sitting beside their real full-length names. Harmless in
effect and undetectable by anything in the suite - the register's citations had a liveness check and
this list did not. It has one now, plus three more: an exemption for a test outside the swept suites
is never read; an exemption for a test that is now cited is stale; and the one file-granularity
opt-out must still name a real, still-cited suite.

**The sweep's scope is narrowed in writing rather than quietly.** The register cites
`tests/test_appstore_contract.py` at file granularity for the Dockerfile row. Walking that suite
would pull 104 of its 113 tests into the sweep, nearly all packaging and image-shape assertions
carried by `docs/DEPLOYMENT.md` at contract granularity. A 104-entry exemption list is a list nobody
maintains, and an unmaintained exemption list is precisely the failure this check exists to catch, so
`UNSWEPT_CITED_SUITES` records the opt-out and a test asserts the suite is still cited. Any OTHER
suite the register starts citing fails the check until somebody decides which it is.

**Also closed.** The citation regex now drops `.py` stems, so `tests/test_auth.py` in the table no
longer contributes a bare `test_auth` citation that a future test of that name would inherit. The
ordering authority is cited at the five sites that still carried the bare absolute
(`app.py`, `middleware.py`, `docs/SECURITY.md` item 10, and two docstrings in `test_http.py`) -
last round's claim that "every ordering claim now cites it" was false when written, at five live
premises. `test_the_middleware_order_puts_the_limiter_outside_the_body_cap` now runs both postures
rather than only the hosted one: with an origin configured the stack is four layers, without it
three, and what must hold in both is nosniff outermost and the body cap innermost, which is the
claim the five citing sites actually depend on. A reflow had also left a three-word orphan line in
that docstring.

**Verified.** Loop green under the pinned toolchain: **769 passed, 1 skipped**, coverage **99.06%**,
all three lock files audited clean, 77 pins matched. Collected: **770**.

**Mutations: 8 run, 8 killed**, each confirmed applied before its result was believed, and each
reverted against a recorded SHA-256 digest afterwards.

| # | Mutation | Result |
|---|---|---|
| 1 | an uncited, unexempted `async def` test appended to `test_middleware.py` - the exact plant both gates used | killed |
| 2 | the same plant as `async def` with `@pytest.mark.parametrize` and its arguments reflowed across lines | killed |
| 3 | a plain `def` plant beside it | killed |
| 4 | an exemption naming no test anywhere | killed |
| 5 | an exemption naming a real test outside the swept suites | killed |
| 6 | a name both cited in the register and exempted from needing a citation | killed |
| 7 | the register made to cite `tests/test_healthcheck.py`, a suite the sweep does not walk | killed |
| 8 | every mention of `tests/test_appstore_contract.py` removed from the register, making the file-granularity opt-out stale | killed |

Recorded because it is the honest shape of the run: my first attempt at 8 replaced one of the two
mentions and the check correctly passed, because the suite was still cited. That was an inadequate
mutation, not a survivor, and the difference between those two is the whole reason a mutation must be
confirmed applied before its result is read.

### Round thirteen: the exemption reason became the hiding place

**Both gates FAILED again, both with a MAJOR on the same check, and both were right.** Round twelve
fixed the `async def` blind spot and asserted in the same docstring that the AST walk "survives
decorators, reflowing and **class nesting**". The first two were true and measured. The third was
false: `_test_names_in` iterated `tree.body`, so a test inside a `class Test...` was invisible.
Both gates planted one, pytest collected it, the sweep passed. `ast.walk` now, and measured at the
time of the fix: `ast.walk` and `tree.body` yielded the identical 435 names, so the hole was open
rather than occupied. That is the only reason this was a MAJOR and not a live gap - and it is the
third recorded instance of one fault: **a completeness check whose docstring claims more than its
matcher can see.**

**The suite-shaped hole, which WAS occupied.** The accounting guard derived cited suites from
`tests/(test_\w+\.py)` file references, so a suite the register cites by TEST NAME was neither
swept nor flagged. `docs/SECURITY.md` cites `test_a_hostile_port_is_refused_rather_than_interpolated`,
which lives in `tests/test_healthcheck.py`: twelve tests invisible, and three fail-closed branches in
`healthcheck.py` whose only killer was among them - a malformed `PORT` reading UNHEALTHY rather than
falling back to a different port, a non-200 liveness answer reading UNHEALTHY, and a transport
failure reading UNHEALTHY rather than a pass. All three have rows now, as do the `/livez` target and
the probe timeout. The guard no longer derives anything: every file matching `tests/test_*.py` must
appear in exactly one of `SWEPT_SECURITY_SUITES`, `UNSWEPT_CITED_SUITES` or a new
`NON_SECURITY_SUITES`, so adding a suite forces the same decision adding a test does. A suite
declared to hold no security property must also not be where a cited control lives.

**And the finding that matters most, because it is the class moving again.** Four register rows
asserted a property, cited a test that did not assert it, and the EXEMPTION REASON for the test that
did assert it said the property was "one behaviour" of the cited row. The reason was prose asserting
a mutation relationship, and nothing tested the assertion. The security gate tested it:

● `SECURITY.md` claimed the actor was "sanitised **and capped**". Delete `[:limit]` from
  `audit.py`, or raise either bound: every CITED test stayed green.
● It claimed a wildcard origin refuses to start "unconditionally", citing only the `*`-without-a-
  token case. Reduce `REFUSED_ORIGINS` to `{"*"}`, or drop `.casefold()`: every cited test stayed
  green. `null` is what a sandboxed iframe and a `file://` page send.
● It claimed anonymous writes "cannot combine with a token". Disable that refusal: the cited test
  stayed green.
● Reject-rather-than-truncate on an oversize operator value had no row at all, and the session
  collection cap was credited to the BACKUP retention row, a different control that survives
  disabling it.

Seven tests moved from exemption to citation, and each was then re-mutated against **its own cited
test alone** rather than against its suite, because "the suite went red" does not prove the row.
Fixing a row by writing a better reason for not citing it is the same mistake in a new position, and
this round is the one where that became clear.

**Also closed.** Citations are read from control-table ROWS only, not the whole document - one name
(`test_an_honest_oversize_declaration_is_refused_without_reading_the_body`) was cited nowhere but a
sentence in the surviving-mutant prose, and now has a row. `test_every_test_named_in_the_security_
policy_exists` uses `_all_test_names()` instead of the line scan its sibling had just withdrawn. The
dead-name and stray-name assertions are disjoint, so each message is reachable. And the `==` census
in `test_auth.py` had two undeclared holes: a non-recursive `glob` that skipped `physics/` and
`scenario/`, and a `"len(" not in rendered` exclusion that let `token == expected and len(x) > 0`
pass. It asks the structural question now - is a token VALUE an operand - and the identifier-name
blind spot that remains is declared, with the measurement showing which sibling test catches it.

**Numbers, measured after the final edit.** Sweep: 8 suites, **180** tests, up from 7 and 168.
Control rows **63 to 74**; the citations in them **76 to 89**. Exemptions **100 to 99** (7 promoted
to citations, 6 healthcheck case-level tests added). Loop: **769 passed, 1 skipped**, coverage
**99.06%**, 77 pins matched, three lock files clean.

Two of those figures were wrong when first written, and the correction is the point rather than the
numbers. I published "control rows **78**" against a measured 74, and "citations **77** to 89" using
the DOCUMENT-WIDE baseline in the release that withdrew document-wide counting - the row-only
baseline is 76. Both came from a throwaway one-liner counting pipe-prefixed lines with a backtick
in them, run before the control-table slice existed, so it counted two other tables as well. The
engineering gate re-derived them and found the discrepancy. Every figure in this paragraph is now
taken from the same slice the sweep itself uses, at three named commits, which is the only version
of this claim that a later reader can check.

**Mutations: 19 run, 19 killed.** Three against the sweep's structure (class-nested plant,
module-level plant, a citation moved from a row into prose), two more against its accounting (a
brand-new suite holding an uncited control, a cited control in a suite declared non-security),
twelve against the promoted controls, and two against the census holes. Each was confirmed applied
before its result was read and restored against a recorded SHA-256 digest.

**One error of my own, recorded because the tree is the evidence.** Mid-battery I reverted a mutant
with `git checkout docs/SECURITY.md` on a file carrying seven uncommitted register edits, and
discarded all seven. Caught immediately by a grep for one of the new rows, and re-applied from the
same script that wrote them. `git checkout` is not a revert mechanism on a dirty file; the
digest-backed restore the harness uses everywhere else is, and it is what the harness should have
been used for there too.

### Round fourteen: the table was not the only table

**`engineering-reviewer` FAIL, three MAJORs, and two of them are the same fault in the fix I had
just shipped.**

**One table along.** Round thirteen stopped reading citations from the whole document and read them
from `line.lstrip().startswith("|")` instead, with a comment saying "ONLY the control table's rows
count". That filter is every markdown table in `docs/SECURITY.md`, and the mutant ledger is one of
them - under the same heading, further down the section, its rows already naming source files and
tests. The gate proved it occupied-able in one line: delete a control row, add a ledger row naming
that row's test, and all three sweep checks go green. A control carrying no register promise reads
as cited.

My first fix was to slice from the heading to the next heading, and **that was still wrong**, which
I found by re-running the gate's own mutant against it rather than by trusting the edit: the ledger
is inside the same section. The slice is now the FIRST contiguous run of pipe-prefixed lines after
the heading, so the ledger is a later run and outside it whatever it says. Both anchor failures are
loud rather than silent: a renamed heading and an emptied table each raise their own message, because
an empty slice would report every security test as uncited and bury the real cause in the noise.

**And the exclusion was wider than its own docstring.** The `==` census's `is_token_value` returned
`False` for every `ast.Call` while the docstring said it excluded "a `len()` of one", and separately
claimed `token == expected` was caught "however the rest of the expression is written". Measured by
the gate: `str(token) == expected` and `token.strip() == expected` both survive. Any wrapper at all
hid the comparison. `len` is excluded by NAME now, and four wrapper forms are mutation-proved dead
while the legitimate `len(token) != len(expected)` guard stays allowed.

**The third MAJOR is a figure I published without measuring.** "Control rows **78**" against a
measured **74**, and "citations **77** to 89" using the document-wide baseline in the release that
withdrew document-wide counting - the row-only baseline is **76**. Both came from a throwaway
one-liner counting pipe lines with a backtick in them, written before the slice existed, so it
counted the other tables too. This is the fault the V0.22 header records as a BLOCKER and states the
rule for: run the assertion before writing the sentence about it. I did not, in the very round whose
subject was a matcher measuring something other than what it reported.

**Also closed.** `NON_SECURITY_SUITES` gave one reason - pure numeric functions - for a set that
includes `test_entrypoint.py`, which reads the environment and asserts the resolved bind address.
The classification is right and the reason did not cover it, so `test_entrypoint.py` has its own
sentence citing `config.py:158-167`, where the record already says loopback binding is deliberately
not relied on as a control. That comment is the only thing between an unswept suite and the sweep,
so a reason that does not fit its member is a gap in waiting.

**Verified.** Loop green under the pinned toolchain: **769 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Collected: **770**.

**Mutations: 9 run, 9 killed, plus one control that must SURVIVE and does.** The ledger-loophole
mutant (control row deleted, ledger row added naming its test) - killed, after the first fix was
measured insufficient against it. The heading rename and the emptied table - each raising its own
message rather than passing. Four census wrappers (`str(...)`, `.strip()`, `[:32]`, `.encode()`) -
killed. And `len(token) != len(expected)`, which must stay allowed - it does, so the fix narrowed
the exclusion without removing it.

### Round fifteen: four controls that could be deleted with the suite green

**The owner called this: close the REAL gaps, upload, and bound the sweep's claims instead of
extending it.** Fourteen rounds had been spent on the release record while the application itself
was sound, and the security gate's ninety-two-mutant campaign finally separated the two. Its live
attacks all behaved correctly against the built app - 401 on a wrong token of equal length, 422 on
`__proto__` and on `{"id":"zzz"}` with the store unchanged, 413 on an oversize body, 200 not 500 on
a 5000-digit `If-Match`, no cross-origin header for a hostile origin, no token or exact length in
diagnostics, log injection neutralised. **Seventy-four of its mutants died to a cited test.** What it
found was four controls that could be DELETED with all 769 tests green, and those are what this
round closes.

● **`storage.py` backup TARGET, and this one had a real consequence.** The existing test covered
  the SOURCE: a symlinked `training.json` cannot be read into a backup. `os.O_NOFOLLOW` on the
  target it WRITES was uncovered. A principal with write access to the data volume - the same one
  the snapshot and lock guards already assume - pre-creates the next backup path as a symlink to
  any file, and the next privileged write destroys that file. Read access escalated to arbitrary
  file overwrite. `test_a_symlinked_backup_target_cannot_overwrite_the_file_it_points_at` now
  plants exactly that and asserts the victim survives. Measured both ways: the new test kills the
  mutant, and the old source test demonstrably does NOT, which is the whole reason the row needed
  splitting into two.
● **The audit trail was entirely unasserted at the wiring level.** Replacing either
  `audit(...)` call with a no-op left the suite green, no test in `tests/` used `caplog`, and the
  one test whose NAME promised the actor asserted only `201`. Under a shared team token, accepted
  risk 1 says the token cannot distinguish who wrote - so the audit line IS the accountability
  control, and nothing checked it existed. Both routes and both actors are asserted now, including
  that no credential appears in the line, and the misnamed test does what its name says.
● **The constant-time compare fell to a decoy.** Keeping any `compare_digest` call in the module
  while returning plain `==` satisfied both cited tests: the primitive check because a call existed
  somewhere, and the `==` census because it matches identifier names and the shipped operands are
  `supplied` and `reference` - so the "declared blind spot" was the actual shipped naming, not a
  hypothetical rename. The check now requires EVERY computed `return` in `token_ok` to carry the
  primitive. Four defeats proved dead, including the gate's exact one.
● **The PATCH model's `extra="forbid"`** was load-bearing and cited by nothing that asserts it:
  without it an attacker-chosen `id` reaches the merge. Cited now.

**Nine more exemption reasons were disproved by mutation and are now rows** - the relative and
root `DATA_DIR` refusals, the out-of-range `PORT`, the nonsensical rate-limit bound, the raising
probe reading unready, the non-object snapshot, both migration rejections, and the `anonymous`
actor default. Each was killed only by an exempted test, so the register carried no row that fails
when the branch regresses.

**And the sweep's loose ends are BOUNDED rather than extended**, which was the other half of the
owner's decision. The elided-citation prefix had no floor: shortening `test_the_coarse_tier...` to
`test_the...` made an uncited control read as cited, because that prefix matches 32 of the 182
swept tests. There is now a minimum length and a resolution bound, both asserted against absolute
literals so raising one fails rather than widening the sweep. A control row cannot keep its citation
with its control cell blank or gutted to separator punctuation - the engineering gate measured the
first version of that guard passing a `---` cell, because the branch meant to recognise the table
separator recognised any row whose FIRST cell looked like one. The citation token is now
case-insensitive to stop it drifting from its sibling regex, which already was; on the register as
it stands both classes return the identical 102 citations, and the honest gain is that a
capitalised citation fails loudly rather than truncating in silence.

**One declared limit, stated rather than closed.** A control cell holding `<!-- retired -->` passes
the non-empty check, and so does a row whose text no longer describes what its test asserts. Both
need somebody to judge whether prose describes a real control, which no matcher does. It is
recorded as a limit in the code because every defeat of this sweep so far came from a comment
claiming ground the code did not hold.

**Verified.** Loop green under the pinned toolchain: **771 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Collected: **772**.

**Then the engineering gate found the fourth control still open, and it was the same mutant one
level down.** `test_the_token_comparison_uses_the_constant_time_primitive` had been tightened to
require `compare_digest` in the deciding `return` - a SUBSTRING test on the rendered return. So the
decoy moved inside it:

    return len(supplied) == len(reference) and (
        supplied == reference or hmac.compare_digest(supplied, reference)
    )

`compare_digest` is in the return, the check passes, `or` short-circuits, and plain equality decides
authentication. Green at 771. Third position of one mutant: primitive absent, decoy elsewhere in the
module, decoy inside the return. It now asks the structural question - no equality comparison in
`token_ok` may have an operand that is not a `len(...)` call - and three defeats are dead while the
legitimate length guard is measured as still allowed.

It also caught two figures in this round's own comment, published without re-measuring: 180 swept
tests against a real 182, and `test_a...` matching 89 against a real 91, both stale by exactly the
two tests this round added. And a justification that measurement falsified: the case-insensitive
citation token was recorded as fixing a live miss, but lint required the test back to lowercase
afterwards, so on the shipped register both classes return the identical 102 citations. The
measurement was true when taken and stale when published. That is the fault this file exists to
catch, committed in the round that closed four instances of it. Register, all from the same slice the
sweep reads: control rows **86**, citations in them **102**, exemptions **88**, tests swept **182**
across **8** suites.

**Mutations: 22 run. 20 killed, 2 survivors both deliberate.** The two survivors are the point
rather than an omission: the backup mutant run against the OLD source test alone had to survive, or
the new test would be redundant; and the `<!-- retired -->` cell is the declared limit above. One
of the twenty is worth naming, because it caught my own bug: the empty-control-cell guard tested
`set(control) <= {"-", " "}`, and `set("")` is a subset of everything, so the separator check
swallowed the empty cell it was written to catch. It survived, I fixed the guard, it died. A guard
written and never mutated is a guard nobody has measured.

### Round sixteen: security-reviewer PASS, and an allowlist instead of a fifth denylist

**`security-reviewer`: PASS**, on `be19697`, after a 60-mutant campaign across `src/` and a live
black-box run against a real app. No BLOCKER, no MAJOR. It confirmed all four new tests are the
**sole** killer of the control they name, that the backup-target test fails if the flag comes back
off and nothing else does, and that all nine promoted exemptions are real rather than paper. It also
recomputed every published figure independently and they matched.

**Four MINORs, and three were closed here rather than deferred**, because each is a control with no
regression test, which is exactly the scope the owner set.

**The `token_ok` check, fourth position, and why this one changes the method.** The gate broke the
tightened check four more ways. `operator.eq(supplied, reference)` is an `ast.Call`, not an
`ast.Compare`, so a filter over comparisons never sees it; `supplied in (reference,)` uses `In`
rather than `Eq`; `bool(supplied.__eq__(reference))` is a method call. And the fourth needs no
comparison at all: `if not supplied.startswith(reference[:8]): return False` sits AHEAD of an
untouched canonical return, returns a bare constant so every "deciding return" rule excludes it by
design, and leaks a prefix oracle while `compare_digest` still ships and is still reached.

Four rounds, four denylists, four defeats. **The set of ways to compare two byte strings in Python
is open**, so a denylist over it can only name the spellings somebody has already thought of. The
check now pins `token_ok`'s body against a canonical four-statement literal, docstring excluded so
prose stays free. All five positions measured dead, and a control mutation - reordering the length
guard to `len(reference) == len(supplied)`, which is behaviour-preserving - fails loudly, which is
the intended cost: any change to the four lines that decide authentication needs a human to re-read
them and update the literal in the same commit.

**Two more controls with no test.** `models.py` caps four string fields; `notes` and `id` were
asserted and `title` (200) and `scenario` (120) were deletable with the suite green - two cases
added to the same parametrised test. And `audit()` merged its extra fields RAW while `log_event()`
beside it sanitised every string, so `audit("probe", actor="a", note="x" * 10_000)` emitted all ten
thousand characters against a register row claiming "every reflected value LENGTH-CAPPED". Not
reachable from either route - the only string either passes is a session id already matched against
`SESSION_ID_PATTERN`, and a 404 raises before the call - so it was an over-claim, not an exploit.
Closed in the CODE rather than by narrowing the row, because the alternative was weakening the
register to match a weaker control.

**And two records corrected.** The surviving-mutant bullet for the constant-time control described
the position that had already been defeated and still listed a killed mutant as live - wrong in the
safe direction, which this ledger's own standard rejects. Accepted risk 3 recorded coarse rate-limit
keying and not the stronger form: `_client_key` collapsing to one constant key survives the whole
suite, which would let one caller consume everyone's budget behind the gateway. It is untested
because `TestClient` presents a single client host, so the reason is testability rather than
triviality, and that is now written down instead of absent.

**Then the engineering gate defeated the body pin twice more WITHOUT touching the body**, which is
the finding that matters most in this round. An AST pin over a function body is blind one frame out
in each direction:

● It deleted `import hmac` and bound the name to a class whose `compare_digest` is `a == b`. The
  body still matched the literal character for character; the constant-time control was entirely
  gone; the full loop was green and lint was silent.
● It decorated `token_ok` with a wrapper returning `False` unless `given` shared a four-character
  prefix with `expected`. Behaviour-preserving on every test vector, and a prefix oracle:
  `compare_digest` still ships, still matches, and is never reached for a wrong prefix.

So the pin covers the STATEMENTS and not the names they resolve to, nor what wraps the function.
Two sibling tests now check those two frames - `hmac` is the standard library module, and `token_ok`
is neither wrapped nor decorated - each with its own register row, because they guard different
things. Seven positions measured dead. Both assertions in the second test are load-bearing:
`functools.wraps` copies `__qualname__`, so a wrapped function passes the name check and fails the
unwrap check, while a naked wrapper sets no `__wrapped__` and fails the opposite one. Both forms
measured dead.

**And the figures in one comment went stale for the third consecutive commit**, so they are gone
rather than corrected again. It read "matches 32 of the 182 swept tests and `test_a...` would match
91"; both numbers change whenever a swept test is added, which this commit did twice. A count in a
comment has no mechanism keeping it true. The comment states the property, the assertion reports the
live numbers when it fires, and the claim that the widened citation class changes nothing on this
register is now an ASSERTION rather than a sentence - so a capitalised citation produces the loud
failure the widening exists to produce.

**Verified.** Loop green under the pinned toolchain: **776 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Simulation: **772 passed, 5 skipped**. Collected: **777**.
Register, from the slice the sweep reads: control rows **89**, citations in them **105**, exemptions
**88**, tests swept **185** across **8** suites.

**Mutations: 9 run, 9 killed** - the gate's four in-body positions, the plain-`==` form that had to
stay dead, the behaviour-preserving reorder that must fail loudly, and the three frame defeats: the
rebound `hmac` name, the decorated function, and the naked wrapper that only the name check sees.

### Round seventeen: an authentication bypass that passed every check I had written

**`engineering-reviewer`: FAIL, one BLOCKER, and it is the most serious finding of the whole
stretch.** The AST body pin I introduced in round sixteen parsed `auth.py`'s MODULE source and
pinned whichever `def token_ok` it found there. That is not necessarily the callable the name
reaches. The gate left the canonical `def` completely untouched, appended this after it, and
rebound the name:

    _pinned_token_ok = token_ok

    def _token_ok_with_break_glass(given, expected):
        if given == "break-glass":
            return True
        return _pinned_token_ok(given, expected)

    _token_ok_with_break_glass.__qualname__ = "token_ok"
    token_ok = _token_ok_with_break_glass

Body pin green, because the canonical `def` is still the only one in the file. `hmac` probe green.
Both wrapper assertions green - `inspect.unwrap` finds no `__wrapped__` on a naked wrapper, and
`__qualname__` was assigned. The `==` census green, because `given == "break-glass"` has no operand
whose name contains "token". Ruff, mypy and the full suite green at **776 passed**. And any request
could authenticate with a fixed string.

**A second frame in the same round.** `hmac.compare_digest = _compare` inside `auth.py` leaves
`auth.hmac is stdlib_hmac` TRUE, because both sides are the same module object and only the
attribute moved. The constant-time control is gone, the loop is green, and the primitive is poisoned
process-wide for every other importer.

**The lesson is the same one, arrived at for the fourth time, and I should have reached it sooner.**
Round fifteen: enumerating equality SPELLINGS could not work, because the set is open. Rounds
sixteen and seventeen: enumerating FRAMES cannot work either, for exactly the same reason - the body,
the names it resolves to, what wraps it, what rebinds it, what replaces an attribute on a module it
holds. I replaced one enumeration with another and called it an allowlist.

What I reached for was asking the runtime which code object the public name reaches:
`inspect.getsource(auth.token_ok)` follows `__code__.co_filename` and `co_firstlineno`, so pinning
THAT closes the naked wrapper, the `functools.wraps` wrapper, the qualname spoof, the name rebind
and a NAIVE `__code__` swap in one assertion.

**And that sentence named its own defeat as its proof, which round eighteen records.**
`co_filename` and `co_firstlineno` are writable through `types.CodeType.replace()`. Citing them as
the reason the pin is safe was the over-claim again, one round after withdrawing the last one. The primitive is checked by TYPE - the real
`compare_digest` is a C builtin and no Python-level replacement is - rather than by module identity.
The two frame probes stay, demoted honestly to what they are: cheap diagnostics that name which
frame moved when one fires, which a body diff does not.

**Also closed.** Two docstrings and three register rows claimed a closure they did not have, in the
same idiom as the "complete list" withdrawn one round earlier. The collected count read 775 in the
paragraph whose subject is stale counts, ten lines from the 777 in this round's own block. And the
`engineering-reviewer` checklist row described the round-fourteen FAIL rather than the last one, so
a reader of the submission checklist took away the wrong record of what the most recent review
found.

**Verified.** Loop green under the pinned toolchain: **776 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean. Simulation: **772 passed, 5 skipped**. Collected: **777**.

**Mutations: 5 run, 5 killed.** The two new frames - the rebound name with the spoofed qualname, and
the reassigned `compare_digest` attribute - plus three regression checks that the earlier positions
stay dead under the new pin: plain `==` replacing the primitive, a `startswith` guard inside the
body, and a source-level decorator.

### Round eighteen: the pin was handed the canonical source by a function that ignored it

**`engineering-reviewer`: FAIL, one MAJOR, and it is the fourth defeat of this one control in four
consecutive rounds.** Round seventeen's fix pinned `inspect.getsource(auth.token_ok)` on the
reasoning that it follows `__code__.co_filename` and `co_firstlineno`, so it reads the callable the
name actually reaches. Both fields are writable through `types.CodeType.replace()`. The gate forged
one:

    forged = types.FunctionType(
        _bypass.__code__.replace(
            co_filename=auth.__file__, co_firstlineno=<canonical line>, co_name="token_ok"
        ),
        auth.__dict__,
        "token_ok",
    )
    forged.__qualname__ = "token_ok"
    auth.token_ok = forged

`inspect.getsource(auth.token_ok)` returned the canonical four lines VERBATIM. All four sibling
controls passed. `token_ok("junk", "the-real-secret")` returned `True`. Total authentication bypass,
full loop green.

**And the record was worse than the hole.** Round seventeen's changelog cited `co_filename` and
`co_firstlineno` as the REASON the pin was safe. They are precisely the two forgeable fields. The
claim named its own defeat as its proof, one round after withdrawing the previous over-claim on the
same control.

**What the control is now: the executed bytecode.**
`test_the_executed_bytecode_is_the_reviewed_implementation` compiles `auth.py` from disk, finds
`token_ok`'s code object without executing anything, and compares `co_code` and `co_names` against
the callable the name reaches. A forged code object carries the bypass's bytecode whatever it claims
about its origin, so it cannot survive. `co_consts` is deliberately excluded because it holds the
docstring: measured, a docstring edit leaves `co_code` and `co_names` identical while `co_consts`
differs, so prose stays free and code does not.

Everything else in this control's stack is demoted to a diagnostic and labelled as one, including
the source pin. They stay because when one fires it names WHICH frame or statement moved, and a
bytecode diff cannot.

**Nine positions across four rounds, and the pattern is now unmistakable.** Equality spellings, then
frames, then the source a code object reports. Each fix enumerated one more surface and each was
defeated by the next surface out. Bytecode is the first assertion in the sequence that is not an
enumeration: it reads what runs.

**Also: my own guard caught my own mistake, which is the first time that has happened.** The
capital-letter citation assertion added in round seventeen fired on `..._BYTECODE_...` in the new
test's name, exactly as designed, before any gate saw it. The name is lowercase now.

**Verified.** Loop green under the pinned toolchain: **777 passed, 1 skipped**, coverage **99.06%**,
77 pins matched, three lock files clean.

**Mutations: 8 run, 6 killed, 2 deliberate survivors.** The forgery, killed - and measured surviving
the SOURCE PIN alone, which is the proof that the pin was the hole rather than a redundant check.
Five regressions all still dead: plain `==`, the or-decoy inside the return, a `startswith` guard in
the body, a reassigned `hmac.compare_digest`, and a naked wrapper with a spoofed `__qualname__`. And
a docstring-only edit, which must survive and does.

## V0.21 (2026-08-20)

**What.** Flight plan Phase 0 complete, plus the owner's decisions of today recorded and acted on.
Slug `enlightenment` confirmed available. A Data Protection Impact Assessment (DPIA) drafted.

**Sequencing, stated because it interprets an instruction.** The owner asked to build Phase 0 and
upload, and separately to implement all recommendations. Two of those recommendations, the SQLite
store and the identity adapter, are Phase 1 work, and putting them in before the upload would
roughly triple the code the SonarQube gate scans as NEW on a first submission where nothing has
ever shipped. So Phase 0 ships first and those two follow the upload. The reading is stated rather
than assumed silently.

### The lesson this release turns on: I validated against my own memory

The first version of `greenwich_mean_sidereal_degrees` was checked against a textbook reference
value **recalled rather than read**, and disagreed with it by 131 degrees. The implementation was
right and the remembered number was wrong.

That is the same failure as inventing `SGP4_ERRORS[5]`, and it would have been far worse here: a
"corrected" Earth-rotation angle would have put every plotted longitude wrong by a third of the
planet, consistently, in a trainer whose purpose is teaching people to spot exactly that.

So the golden source is now `sgp4.propagation.gstime` in the pinned wheel, which the machine
produces on demand: agreement to **1.6e-10 degrees** across five epochs spanning 46 years. Plus one
independent almanac cross-check a human can verify without trusting the library either, sidereal
time at 0h Universal Time on 1 August 1992 coming out at 20h 39m against the almanac's "about 20h
40m". Two sources beat one.

### Phase 0 step 2 completed: time, Earth rotation, and relative motion

**`physics/times.py`.** Julian Date, Greenwich Mean Sidereal Time, and sub-satellite longitude.
Two named traps documented at the boundary: **UT1 is not UTC** (they differ by up to 0.9 seconds,
which is 0.0037 degrees of longitude, small until it is compared against another source and read
as real), and **a TLE epoch is not a calendar time**. No leap-second table ships, deliberately: a
table goes stale, a stale table is worse than none, and v1 serves synthetic data with no real epoch
to reconcile.

**`physics/relative.py`.** Clohessy-Wiltshire relative motion in the Hill frame, closed form.
**Verified against fourth-order Runge-Kutta integration of its own differential equations over a
full orbit**, agreeing to better than a micrometre. That check is the point: a closed form verified
only against the algebra that produced it is verified against nothing, and it caught two errors.

● **My test expectation was wrong, not the code.** I asserted the one-orbit drift of a 1 km radial
  offset as -6*pi km. The secular term is 6(sin(nt) - nt)x0, so over one period it is -12*pi*x0,
  about 37.7 km. The drift RATE is -6*n*x0; multiplying by the period 2*pi/n gives twice what I
  wrote. Now derived in writing in the test rather than asserted from arithmetic done in my head.
● **A false claim in a constant's own comment.** `EARTH_MU_KM3_S2` was 398600.4418 under a comment
  saying it was "the one SGP4 itself uses". Measured, `sgp4.earth_gravity.wgs84.mu` is 398600.5.
  The value changed to match, because the stated rationale is sound: a chief's mean motion derived
  here and a track propagated by SGP4 should not disagree for a reason nobody can see. The
  numerical difference is 1.5e-7 relative and matters for consistency, not accuracy, and that is
  stated rather than implied. `mean_motion_from_elements` was added as the preferred path, since an
  element set already carries the rate.

The counter-intuitive behaviour the module exists to teach is asserted as a property: a purely
radial offset does not stay radial, and the no-drift condition is along-track rate equals minus
twice mean motion times radial offset. An operator who expects "I moved up, so I stay above" is
wrong in a way that compounds every orbit, and that is what competency axis four scores.

**`skyfield` and `numpy` remain deferred, with the reason now measured rather than asserted.** v1's
three procedures need Earth rotation for a GEO belt plot and small-matrix arithmetic for Hill-frame
motion. Neither needs precession, nutation, or arrays. What is NOT done is stated in
`sub_satellite_longitude_degrees`: this is TEME-of-date longitude, not J2000 and not geodetic, and
anything needing those takes a validated library rather than an implementation written from memory
here.

### Phase 0 step 3: the determinism harness

The flight plan calls it a gate, not a task: *"Prove by test that the same seed yields an identical
event log twice."* `src/enlightenment/scenario/` is the substrate, holding no content and no
physics so that it can be proved.

● **`SeededRandom`** wraps `random.Random` per run rather than the module-level functions, which
  share one global state: two scenarios in one process would draw from each other's stream, and a
  replay would depend on what else the process had done. `choice` takes a LIST, and that signature
  is the control - set iteration order depends on hash values, which are randomised per process, so
  choosing from a set is non-deterministic across processes even with the same seed, and a replay
  months later runs in a different process.
● **`ScenarioClock`** counts integer ticks and multiplies. Asserted against float accumulation:
  adding 0.1 a thousand times does not give 100.0, and two replays that grouped the additions
  differently would drift differently.
● **`RunLog`** is append-only with no remove and no update, refuses a non-monotonic tick, and
  fingerprints the seed and every event with sorted keys and `allow_nan=False`. Sorted keys stop
  two logically identical events digesting differently because a dict was built in another order;
  refusing NaN stops a fingerprint depending on a value that compares unequal to itself.

**Verified.** The same seed replays identically; twenty seeds each replay identically; a run
replays identically after other runs have happened in the same process, which is what detects a
shared global; and a different seed produces a different log, which is the control that separates
"deterministic" from "always the same". A test drives the real angle wrapper and the real
relative-motion propagator on seeded initial conditions, because a harness that only proves itself
deterministic proves nothing about a run.

### A trap worth recording: an edit that silently deleted five tests

`sed -n '/start/,/end/p'` prints to **end of file** when the end pattern never matches, and `ruff
format` had reflowed the line I was matching on. The extracted "anchor" therefore ran to EOF, and
replacing it dropped the five tests after the target function. `verified-edit.py` checks an anchor
is present and unique; it cannot know the range was wider than intended. Restored, and the habit
that catches it is checking an anchor's line count before using it.

### The DPIA

`docs/DPIA.md`. **Screening decision: MANDATORY**, on Article 35(3)(a) of the United Kingdom
General Data Protection Regulation: systematic and extensive evaluation of personal aspects based
on automated processing, including profiling. Article 4(4) names "performance at work" explicitly,
and that is precisely what six competency axes, an Elo rating, a Brier score and per-item
scheduling state constitute.

Drafted to the Article 35(7) structure. **Recommendation: proceed with conditions**, no Article 36
prior consultation with the Information Commissioner's Office required on the current facts. Nine
risks assessed, and the assessment does not credit a control that does not exist: the supervisor
access audit, the retention mechanism and the scorer validation are all named as **not built**, and
two of them are binding conditions. Four questions are the owner's to answer, and two of them
change the assessment: whether readiness output will inform shift assignment (which engages Article
22), and whether anyone outside the United Kingdom can reach the storage volume (which makes it a
restricted transfer).

**Verified.** Loop green under the pinned toolchain: **634 passed, 1 skipped**, coverage 98.93%
against a 80% floor, all three lock files audited clean. **All seven physics and scenario modules
at 100% line and branch coverage.** Pipeline simulation green: **630 passed, 4 skipped**.

## V0.20 (2026-08-20)

**What.** Both gates FAILED V0.19. The security gate's MAJOR is the one that matters: the
truncation I added in V0.18 to stop a stall turned the credential control into a credential
LEAK. The engineering gate then found a BLOCKER of the same shape one layer along - my own fix
for that leak left the suite red and I had not run the loop after writing it.

### MAJOR: my performance fix disclosed the credential it was protecting

`redact()` truncated BEFORE redacting. A cut landing inside userinfo removes the `@` the pattern
anchors on, so nothing matches and the token prints. Measured on the documented Google Artifact
Registry form, `https://oauth2accesstoken:ya29.<520 chars>@...`: **463 characters of the access
token reached stderr**, which lands in a CI log. Both gates reproduced it independently.

The truncation itself is load-bearing - 13.96s on 86KB of crafted input without it, inside leg
one of the loop - so the order is now four passes: neutralise non-printables, truncate, redact
userinfo and query credentials, then **strip the dangling authority the cut created**. That last
pass is the fix: after a cut, an unterminated authority is either a hostname or the front of a
token, and the two cannot be distinguished, so it is redacted either way. Losing a hostname from
one over-long line costs a diagnosis; printing a token costs the credential.

**Two more bypasses in the same control, both found by the gate.**

● **The split, not the pattern.** `str.splitlines()` also breaks on the vertical tab, form feed,
  NEL and the Unicode line separators, so a credential URL containing one was torn into two
  "lines" and NEITHER half held the `@`. Fixed at the cause: `requirement_lines()` splits on `\n`
  only. A requirements file has exactly one line terminator that means anything.
● **The parameter name may carry a prefix.** `X-Amz-Signature=` - the presigned-URL form, which
  is what a real object-store direct reference uses - did not match, because the pattern required
  the credential name to start immediately after `?` or `&`.

Nine credential forms are now parametrised and all nine are clean; five no-credential URLs are
the control against over-redaction; the pathological input runs in 0.0005s.

### BLOCKER: I wrote the fix and did not run the loop

The engineering gate found the suite RED in my working tree. The new query-credential pattern
correctly redacts `?token=`, which contradicted an existing case asserting no marker appears for
`?token=a@b`. The new behaviour was right and the fixture was wrong - some indexes do carry a
token as a query parameter - so the fixture now uses a non-credential parameter. But the reason
it reached a reviewer at all is that I ran targeted probes instead of the loop, in the release
whose subject is running the assertion before writing the sentence about it.

A second failure in the same tree: my "fail loudly on a broken override" change made the three
deferral tests exit 2 instead of 3, because their helper set the override to a stub that refuses
`info`. The helper now stubs both engine names on PATH and sets no override, which is the honest
test of the deferral path - discovery tries `podman` then `docker` BY NAME, and PATH resolves both
to the stubs whatever the runner has.

### MAJOR: an assertion that cannot fail, in the evidence base

`assert all(...) or True` stood in `tests/test_appstore_contract.py`. Unconditionally true, so
not a control, in the file every claim in this project rests on. Deleted rather than repaired.
It also falsified the "no dead code" row in `READINESS.md`, which is corrected there.

### MAJOR: the version guard had zero coverage

`package-appstore.sh` refuses a version that disagrees with `pyproject.toml`. Deleting the whole
block left the suite green: `_latest_artefact()` always invokes the script WITH the declared
version, so the refusal branch was unreachable from the suite. Now tested directly - exit 2, the
diagnostic on stderr, and no archive written.

### Smaller findings, all closed

● **`ALLOWED_ORIGIN=null` was accepted** while `*` was refused. `null` is the literal Origin a
  sandboxed iframe or a `file://` page sends, so admitting it names no real caller. Both refused
  now, case-folded, because `NULL` defeated the first fix.
● **"Physics is unreachable from any HTTP route" was true and unpinned.** Now asserted by
  building the app in a clean SUBPROCESS and checking what got imported. The first version cleared
  `sys.modules` in-process and proved nothing - `enlightenment.app` is already cached from earlier
  tests, so its imports never re-run, and a planted `from enlightenment.physics import ...`
  SURVIVED it. The subprocess version kills that mutant.
● **`auth.py` overclaimed.** Its docstring said the comparison "leaks neither the length nor the
  position of a mismatch". The length guard short-circuits, so length IS distinguishable by
  timing. Harmless here - the length is not a secret and `/api/v1/diagnostics` publishes a coarse
  bucket by design - but a crypto claim that overstates itself is worse than none, because it is
  the comment a reader trusts instead of the code.
● **A stale count and a stale record.** A docstring said "34 `.pyc` files", already 36 by the
  next run; it now states the property. And the V0.19 row said run 13 "was heading the same way"
  when the API had settled it as a failure.
● **The coverage-artefact guards skip on the platform**, because the artefact deliberately does
  not carry `coverage.xml`. Their docstring now says so, and names the configuration guard that
  actually carries the control.
● **Two build-time seams were undocumented.** `ENLIGHTENMENT_CONTAINER_ENGINE` and
  `ENLIGHTENMENT_PYTHON` now appear in `docs/DEPLOYMENT.md`, with an explicit note that neither
  belongs in the platform's environment tab. A changelog entry is a record, not documentation.

**Verified.** Loop green under the pinned toolchain: **558 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch. Pipeline simulation green: **555 passed, 4 skipped**. Every control added or changed here
is mutation-proved: the redaction at both echo sites and across nine forms, the version guard,
the import-graph pin, the origin refusal, the explicit-override failure.

## V0.19 (2026-08-20)

**What.** A flaky test, found by committing a red loop, plus the two App Store skills I had not
loaded.

### I pushed a red loop, and the failure was a flake

Running the loop before committing, I grepped its output for the lines I wanted and missed
`1 failed, 541 passed`. The commit and the push went out over a red suite. That is exactly the
"run the assertion before writing the sentence about it" discipline this release series exists to
build, failed at the last step, and it is worth recording plainly rather than as a fixed defect.

**The failure was `test_building_an_app_spawns_no_thread_however_the_pool_is_created`, and it was
a real flake with the worst possible shape:** it failed once, then not in 15 bare runs and 8 full
loops. Rare enough to look like noise, and certain to appear eventually in the platform's test
stage, where a red suite SKIPS every later gate.

Root cause: the assertion compared a live thread set for EQUALITY. It fails whenever a probe
thread from an earlier test exits between the two snapshots - no new thread required, and nothing
the test is about. Demonstrated directly rather than inferred: start a `probe_`-named thread,
snapshot, let it exit, snapshot again; `after == before` is False while `after - before` is empty.

**Fixed** to subtraction, which asserts exactly the property claimed - no NEW probe thread - and
is immune to an unrelated one exiting. Swept the file: every other thread assertion already used
subtraction. Ten consecutive loop runs green after the change.

### appstore-gate-compliance and deploy-recipes, which I had not used

Both were in the original skill list and I had not loaded either. That cost real cycles: I
discovered the `pytest: command not found` failure and the coverage-path problem the expensive
way, and both are what those skills exist to pre-empt.

Checked against both catalogues, **verified not assumed**: Dockerfile flat at the root with
`EXPOSE 8080`, `USER 10001:10001`, no `ENV PORT` or `ENV DATA_DIR`, `FROM scratch` with exactly
one `COPY`, suid/sgid sweep as the last mutation before the flatten; `coverage.xml` in Cobertura
at the path `sonar.python.coverage.reportPaths` reads; `pip-audit` over all three lock files;
pinned base digest; `--require-hashes`; `exec` in the CMD so SIGTERM reaches gunicorn; the
simulation adds the platform's own `.gitlab-ci.yml` and sets `GITLAB_CI=true`.

**Newly verified rather than assumed:** every shipped script is syntax-clean under `dash`, and
the loop EXECUTES under `dash` - so the platform's minimal shell cannot produce
`sh: bash: not found` at build time. That check existed as a checklist line and had never been
run here.

**One pitfall closed.** `deploy-recipes` names a framework redirect on `GET /` as one of three
failures that bite every stack. FastAPI ships `redirect_slashes=True`, so this project does have
such a normaliser: `/healthz/` answers 307. Benign, because the platform probes canonical paths,
and disabling it would make a trailing slash a 404 rather than a 307 - worse. What was unpinned is
that the CANONICAL paths never redirect, which is what a future forced-HTTPS middleware or
base-path rewrite would silently break. Six contract paths are now asserted at 200 with redirects
NOT followed and no `Location` header; a client that follows redirects reports 200 for a route
answering 307, which is how this class reaches an upload. Mutation-proved.

### The structural risk this release cannot fix

`appstore-gate-compliance` says: ship often, so the new-code window stays small. **Nothing has
ever shipped.** SonarQube scores NEW code against a zero-violations bar, and with no shipped
baseline the entire codebase is new code: 831 source statements plus the whole suite, judged at
once. The skill's own mitigation for stacked work is to run the local analyser over the WHOLE
accumulated range rather than the latest diff, which this loop already does - `ruff` runs over the
full tree every time, never a diff. That is the right mitigation and it is in place; the residual
risk is any Sonar rule class the local profile cannot express, and that is recorded rather than
claimed closed.

### CI was RED for three commits and I never looked

The readiness skill is explicit: read the ACTUAL run conclusion, because a workflow file
existing is not evidence it passed. Doing that for the first time: runs 11, 12 and 13 ALL
concluded `failure` - 13 was still in progress when I first looked and I recorded it as "heading
the same way", which the API later settled as a failure. I had been reporting "loop green" from this
machine while the pipeline was red.

**The cause was my own Podman change, one commit earlier.** Three tests prove
`build-image.sh` DEFERS with exit 3 when no engine is reachable, and fails hard on a rejected
Dockerfile. They work by putting a stub `docker` on PATH. The moment the script learned to prefer
Podman - correctly, because that is what the platform's containerize stage uses - the stub was
bypassed on any runner that HAS Podman. The GitHub runner has it; this authoring environment has
neither engine. So the tests passed here and failed there, and the local loop could not see it.

Reproduced locally rather than inferred, by putting a working fake `podman` on PATH: the three
tests fail exactly as CI reported. **Fixed** by stubbing both engine names and pinning the choice
with `ENLIGHTENMENT_CONTAINER_ENGINE`, so the assertion no longer depends on the runner's
inventory. Confirmed both ways under the simulated runner: fixed helper green, docker-only helper
red.

Two gaps that let this through are now closed. The `ENLIGHTENMENT_CONTAINER_ENGINE` seam was
added without a test, so nothing proved an override beats PATH discovery. And nothing asserted
the ORDER, which is the actual contract: Podman first because the platform builds with Podman.

**Verified.** Loop green under the pinned toolchain: **544 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch. Ten consecutive loop runs green. Loop also green executed under `dash`, and green with a
working Podman on PATH, which is the condition that broke CI.

## V0.18 (2026-08-20)

**What.** The project owner supplied the App Store's full pre-submission and pipeline check
list. Four of its requirements were unverified here, and checking them found one likely upload
failure, one near-miss that had already fooled me, and a test of my own that would have failed
the platform's test stage. Plus round four of the gate findings.

### The likely upload failure: the coverage report was machine-dependent

Gate condition two is coverage at or above 80% of changed lines, imported from `coverage.xml`.
The suite measures 98.71%, so the only way to fail that condition is for the importer to be
unable to map the report onto the source tree. The default `pytest-cov` output makes that
likely: measured, `<sources>` held the absolute path `/home/user/Enlightenement/src`, from THIS
machine, while the per-file entries were src-relative (`enlightenment/app.py`). On the platform
runner that absolute path does not exist, so the entries have nothing to resolve against,
coverage reads 0%, and a 98% suite fails the gate.

**Fixed** with `relative_files = true` in `[tool.coverage.run]`: `<sources>` becomes `src` and
the pair composes to `src/enlightenment/app.py` from any working directory.

Three guards, and one of them is the check that would have caught this without a SonarQube of my
own: `<sources>` joined with every entry must name a file that EXISTS. Whatever the importer
does, it cannot do better than the paths in the file. Removing `relative_files` turns two of
them red. What is asserted is the machine-independence; SonarQube's own resolution cannot be run
here and is not claimed.

### The near-miss: I certified a clean artefact from a nine-version-old zip

Checking the "no prebuilt binaries" criterion, I inspected `sorted(dist/*.zip)[-1]`. Version
strings do not sort lexicographically, so `0.9.0` sorts after `0.18.0`, and the archive I
declared clean was nine versions old and predated `requirements-runtime.txt` entirely.

Then, worse, the same class again: the tree declared 0.17.0 while I packaged 0.18.0 by argument,
so an inspection keyed on the declared version examined a different file from the one just
written. A mutation test planted a `.pyc` in one and asserted against the other, and reported
the guard SURVIVING. The guard was correct; the measurement was aimed at the wrong file.

**Fixed twice over.** `package-appstore.sh` now refuses a version argument that disagrees with
`pyproject.toml`, exit 2 with the reason - an archive whose name disagrees with the code inside
it is how a stale upload gets certified. And the artefact tests key on the declared version and
BUILD it when absent rather than skipping: a guard whose common case is "skipped" is not there,
and on a fresh clone - a reviewer's state, a runner's state - the rejection criteria were being
skipped while the suite reported green.

### A test of mine that would have failed the platform's test stage

The new "no prebuilt binaries" repository check used `git ls-files`, and asserted the call
succeeded. The platform runs the suite against the EXTRACTED ARCHIVE, where there is no `.git`,
so it failed in the pipeline simulation. Falling back to a tree walk then failed differently and
worse: 28 offenders, every one a `__pycache__/*.pyc` written by pytest seconds earlier. A test
about what the upload contains, failing on its own side effect.

Now: tracked files in a checkout, and in a non-git tree a walk that excludes runtime-generated
bytecode while still counting everything else - a `.so`, a `.jar`, a `dist/` in a freshly
extracted tree did come from the upload, because nothing in a test run creates one. The
simulation caught both versions, which is exactly what it is for.

### The rest of the checklist, verified item by item

Measured, not assumed. Pre-submission: `Dockerfile` at the root, present and the ONLY one in the
artefact (the Foundations baseline ships six recipe templates under `.claude/`, and the packaging
allowlist carries no `.claude` at all, so none of them ship). No tracked binary or build output.
The 0.18.0 archive: 62 entries, zero matching any rejected extension, zero `__pycache__`, zero
`dist/`, `coverage.xml` correctly absent since the platform generates it.

Stage 1, secret detection: a seven-pattern scan of the working tree and every ref found nothing
real, but five history matches on the `NAME = "long-literal"` shape - test fixtures with
self-describing placeholder values. A scanner cannot tell that from the shape, and a stage-1 hit
is a hard fail before any test runs. The two live fixtures are now COMPOSED from parts, so the
shape is gone and the intent stays legible. History retains them and cannot be rewritten on a
pushed branch; whether the platform scans history or the checkout is not something I can verify
from here.

Stage 4, the test command: `pytest --cov` run verbatim produces Cobertura `coverage.xml` at the
repository root, because `addopts` in `pyproject.toml` owns the flags rather than relying on the
invocation.

Stage 6, container build: **the platform uses Podman and `build-image.sh` used Docker**. Now
Podman first, Docker as fallback, `ENLIGHTENMENT_CONTAINER_ENGINE` to override, and the engine
actually used is echoed so a build log is never ambiguous. With neither reachable it still exits
3 behind the "THIS IS NOT A PASS" banner, verified.

Not verifiable here, and stated rather than glossed: the Anchore container scan, SonarQube's own
duplication measurement and coverage import, and whether stage 1 scans history or the checkout.

### Round four of the gate findings

● **The predicate still raised.** `element_line_checksum_ok("1"*68 + "²")` threw `ValueError`,
  because `str.isdigit()` is True for the superscript two and `int()` then fails - from EITHER
  loop, not just the checksum column. The function whose docstring says "a predicate that raises
  is not a predicate" was raising, three commits after that sentence was written. `isascii()`
  now guards both loops, and two non-ASCII cases join the parametrisation.
● **The wrong-version redaction branch was unasserted.** The existing case used a distribution
  that is not installed, so it always took the MISSING branch; the wrong-version branch is a
  second composed site and removing its `redact()` left the suite green. Same "one site of two"
  shape as the defect the control was written to fix. Now a case names an installed
  distribution and asserts the branch it reached.
● **`is not False` was unpinned.** Reverting it to truthiness left the suite green. Seven falsy
  values are now parametrised, plus the control that a literal `False` does disable the gate,
  plus the keyword-only property the changelog claimed and nothing asserted.
● **The repo-wide census was breakable by ambient files.** `rglob` over the root counted
  untracked ones: a linked worktree of this same repository double-counted every call site and
  turned the loop red, and one stray unparseable `.py` would have killed the leg with a
  `SyntaxError`. It now enumerates TRACKED files, with a `src`/`tests`/`scripts` fallback for the
  packaged tree. Reproduced the failure, fixed it, and confirmed green with the worktree still
  present.
● **Redaction bypasses.** Scheme-relative userinfo (`//user:token@host`) was not matched, and the
  authority run crossed a query string, so `https://host.invalid?token=a@b` reported
  a redacted-userinfo form with the host destroyed - over-redaction is not the safe
  direction when the report exists to say WHICH line to fix. The pattern now makes the scheme
  optional and stops the authority at `/`, `?` or `#`. Fifteen forms measured: eight must-redact
  all redact, seven must-not-touch all untouched.
● **`redact()` could be stalled.** My own optional-scheme change took the pathological case from
  6s to **21s** on 86KB, in leg one of the loop. Lock files are developer-supplied and never
  reach the HTTP edge, but a leg that can be stalled for twenty seconds by one line gets blamed
  for hanging. Echoed lines are now truncated at 500 characters with a visible marker: 21s to
  0.0001s, flat at 16MB.
● **A third echo site added without a test.** The `_marker_applies` note was redacted but
  unasserted, so removing the redaction survived - in the release whose subject was a redaction
  installed at one echo site of two. Pinned.
● **Two figures for one quantity in one commit:** the module said 19.4s under the loop, the
  changelog 22.2s. The module now records only the DELTA, because an absolute goes stale every
  time a test is added and had already been wrong twice.

**Verified.** Loop green under the pinned toolchain: **536 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch. Pipeline simulation green: **533 passed, 4 skipped**. Fourteen mutation tests across the
release, each killed by a named test. Artefact: 62 entries, nothing the upload would reject.

## V0.17 (2026-08-20)

**What.** Both gates returned FAIL on V0.16. Two MAJORs in the credential redaction that V0.16
introduced, and five in the record: docstrings and changelog lines making claims the repository
itself disproves.

**The diagnosis, in the engineering gate's own words, because it is right and it is about my
method rather than my prose:** *every one of these is a claim that could have been checked by
running something that already exists in this repository. The habit to build is not more careful
prose, it is running the assertion before writing the sentence about it.*

Three rounds running, the code has held up under attack and the record has not. So every figure
in this entry was measured immediately before it was written, and where a claim is a list rather
than a number it is now pinned in a test, because a list in a docstring cannot be checked by the
loop.

### MAJOR: the redaction missed the commonest credential form

V0.16 added `redact()` for URL userinfo. Its pattern required a colon, matching only
`user:password@`. So `https://ghp_...@github.com/org/repo.git` - a bare token with no password,
and the ordinary shape of a pip direct reference against a private repository - was never
matched at all. **The most likely real credential to reach that path was the one form the
control could not see.** Also bypassed: userinfo with an EMPTY user, percent-encoded userinfo
pip's own documentation recommends), and the tail of any password containing a raw `@`, since
userinfo runs to the LAST `@` before the authority.

Fixed by dropping the colon requirement: `(?P<scheme>...://)[^/\s]+@`. Greedy, and `[^/\s]+`
cannot cross a `/`, so an ordinary index URL and a URL with an `@` in its path are untouched -
asserted, because over-redaction is not harmless: the unreadable-line report exists to tell an
operator which line to fix.

### MAJOR: the redaction was installed at one echo site of two

`redact()` guarded the unreadable-line report only. A line the pin pattern DOES match, whose
version group is a URL, went out through the missing-and-wrong report in clear:
a pinned line whose version was a whole userinfo URL printed that URL twice in one report, NOT
INSTALLED`. That is a one-character typo (`==` for `@`) of exactly the form the redaction was
written for. The comment beside the pattern asserted this was "the one remaining path"; a
two-line lock file refuted it.

Fixed by redacting where the line is COMPOSED rather than where it is printed. Both remaining
reports were audited: they carry only an interpreter path, a lock file name, or constant text.

**Verified**, and this is the shape the earlier rounds were missing: five credential forms are
parametrised named cases, three no-credential URLs are the control against over-redaction, and
both fixes are mutation-proved. Restoring the colon-requiring pattern turns four cases red;
removing `redact()` from the composed line turns the fifth red.

### MAJOR, five times over: the record contradicted the repository

Each of these was checkable by running something already present.

● **The V0.15 antisymmetry claim, wrong twice in opposite directions.** The first draft named
  range, whole-turn and antisymmetry as the old implementation's failures. The correction said
  antisymmetry was NOT among them and that three tests catch it. Measured by reverting the
  implementation and running the suite: **five** tests go red, and antisymmetry IS one of them -
  at `math.nextafter(-180.0, 0.0)`, forward gives `-179.99999999999997` and backward `-180.0`.
  Range is genuinely not violated. The entry now lists the five test names.
● **The checksum-failure breakdown.** "Both lines of satellite 33333 and line 1 of 33334 and
  33335" enumerates four while claiming five, and mis-assigns 33335. Measured: both lines of
  33333 AND 33335, and line 1 of 33334. The total was right and the breakdown invented, in the
  docstring justifying the most important opt-out in the module. **Now pinned as
  `CHECKSUM_FAILURES` and asserted**, so it cannot be prose again.
● **The opt-out count said one in the source, three in the test, three in the changelog.** The
  function was telling a maintainer the wrong thing about itself.
● **Three live docstrings asserted the design V0.16 replaced**, in the file V0.16 edited: that
  the checksum "is not a gate in `load_elements`" and "belongs in the scenario engine's
  solvability check". One was inside a live assertion message. A stale docstring beside a
  passing test is worse than none, because the test passing is what makes the reader trust it.
● **The checksum residual quoted a rate and a characterisation that contradict each other:**
  "roughly one line in ten" beside "517 of 50,000", which is one in 97. I copied both from a
  gate report instead of running it. Measured over 200,000 samples of each shape: **1.05 per
  cent** for fully random printable-ASCII lines (about one in 94, because column 69 must happen
  to be a digit before it can be the right digit) and **9.79 per cent** for lines whose column
  69 is already a digit - the shape a mistyped field produces, and so the realistic authoring
  error. Both rates are now pinned by a seeded test with deliberately loose bounds, asserting
  the order-of-magnitude gap rather than a figure that would flake.

### A surplus opt-out, removed rather than documented

One of the three `verify_checksum=False` sites had no written reason. Removing it, its test still
passed - which is what proved it surplus, and what the count test should have caught: its own
failure message demands a written reason for each one. It also meant that test was not exercising
the default path a real caller takes. Now two opt-outs, both with reasons, and the census
**walks every Python file in the repository** rather than only its own, which is what a guard
against something spreading has to do.

### Smaller corrections

● `if verify_checksum:` was a truthiness test on a parameter documented as strict fail-closed:
  `None`, `0`, `""` and empty containers all disabled it. Now `is not False`. Keyword-only, so
  it cannot be switched off positionally.
● The broad `except` in `_marker_applies` fails closed but said nothing, leaving an operator
  looking at "NOT INSTALLED" with no way to tell a real mismatch from an unevaluable marker. It
  now names the marker, through `redact()`.
● `TemporaryDirectory` instead of `mkdtemp`: the timeout test created a directory and wrote an
  executable stub into it outside the `try`, so a write failure would have left both behind.
● An unused `import runpy` inside an inline `-c` script, where ruff cannot see it.
● Stale timing figures. Measured: this file is about 3.5s at 2,000 examples against 1.2s at the
  default 100, so the budget costs roughly 2.3s. The earlier note said "a fraction of a second
  on a suite that runs in thirteen", which was neither figure. See V0.18: the replacement then
  disagreed with the changelog by three seconds, so the module now records only the delta.

### What the gates confirmed, recorded because they were my claims

● The seam fix holds: one gate ran 40 clean-Hypothesis-database sweeps, the other 15 plus 6 of
  the full suite, all green - and one proved the sweep is SENSITIVE by restoring the
  `pytest.approx`-gated branch while keeping the new `@example`, which failed 10 of 10 on the
  first run. That is the part that matters: the sweep detects the defect it exists to detect.
● Nine and eleven mutants respectively, across both changed source files, all killed.
● `verify_checksum` cannot be disabled positionally: `load_elements(a, b, False)` is a
  `TypeError`.
● 200,000 fuzz lines through `load_elements`: every rejection is `PropagationError`, no escapes.
  The `# pragma: no cover` branch justified on 60,000 lines in V0.16 held at 200,000.
● The temp stub leaves nothing: directory diffed before and after, `find /` for the stub name
  returns nothing.

**Verified.** Loop green under the pinned toolchain: **508 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch. Pipeline simulation green: **507 passed, 2 skipped**. Repo-wide opt-out census: exactly
two call sites. Clean-Hypothesis-database sweep of the full suite: 0 failures in 12 runs, which
is a sample and is quoted as one.

## V0.16 (2026-08-20)

**What.** Both gates returned FAIL on V0.15. The security gate found a BLOCKER: the verification
loop was RED at the commit I had pushed and reported green. The engineering gate found three
MAJORs, two of them false statements in the V0.15 changelog itself.

### BLOCKER: I reported the loop green from a run that was luck

`test_reversing_a_separation_negates_it` fails deterministically from a clean Hypothesis
database in about one run in five. My runs passed; the reviewer's did not. Measured: 1 failure
in 5 clean-database runs, then reproduced 4 in 12 before the fix.

**The test was the defect, not the implementation.** Its seam branch read
`if forward == pytest.approx(-180.0)`, and `pytest.approx` defaults to a RELATIVE tolerance of
1e-6, so it claimed the exact-seam special case for a band about 1.8e-4 degrees wide and then
demanded the reverse separation also be -180. At `second = -179.99999999999997` the two
separations are exactly antisymmetric, and the general rule applies. A tolerance on a BRANCH
CONDITION is not a tolerance on a comparison: it widened an exact special case into a band where
it does not hold. Gated on exact equality; `angles.py` needed no change.

**Why it surfaced now, and the lesson that outlives it.** V0.15 widened `LONGITUDES` to the last
representable value below 180, which is what made the near-seam band reachable. The widened
domain immediately found a defect in the test that guarded it.

The lesson is about my own claim, not the test. **A property test's verdict is only as strong as
its search, and "green once" is weak evidence for a boundary this narrow.** I asserted a green
loop from a single run and pushed it. The seam properties now run 2,000 examples instead of the
default 100, the falsifying value is pinned as an explicit `@example` so the regression is
deterministic rather than one-run-in-five, and the fix was confirmed over 12 clean-database
runs. Twelve is still a sample; it is quoted as one.

### MAJOR: two false statements in the V0.15 changelog

Both are corrected in place in the V0.15 entry above, with the correction visible rather than
edited away.

● It claimed V0.14's record said the output finiteness guard was "removed as dead code,
  measured over sixteen extreme values". **V0.14's record claimed no such thing** - the guard
  did not exist in V0.14 and its removal was never recorded anywhere. I fabricated an entry in
  this project's own audit trail, in the release whose entire subject is audit-trail integrity.
  The measurement was real and happened in development; the attribution was invented.
● It claimed the pipeline simulation's extra skip is "the leg that needs the dev toolchain".
  **Nothing in the suite skips on that.** The real cause is `scripts/simulate-pipeline.sh`
  setting `GITLAB_CI=true`, which makes `ON_PLATFORM_RUNNER` true and skips the
  `.gitlab-ci.yml` assertion. Measured with `GITLAB_CI=true pytest -rs`, which names both skips.

The figures in both cases were right and the explanations were invented. That is a specific
habit worth naming: reaching for a plausible cause rather than the one the tool would have told
me, in a record whose only value is that its explanations can be trusted.

### MAJOR: a validator that raised on the input it exists to reject

`element_line_checksum_ok("")` raised `IndexError` and a non-string raised `TypeError`. **Both
binding gates found it independently** - the same defect class fixed in `load_elements` in the
very commit that introduced this, in the function beside it. A predicate that raises is not a
predicate. Guarded at entry, returning False for anything that is not a 69-column string, with
eight rejection cases and a positive control pinned.

### MAJOR: a control described in the present tense with no call site

`element_line_checksum_ok` had zero callers while its docstring said the scenario engine calls
it in the solvability check. The measured hazard was live: for a well-shaped but meaningless
element set the public wrapper returns a finite, plausible fabricated state in a majority of
cold processes, and nothing rejected it.

**Wired.** `load_elements(..., verify_checksum=True)` by default. Exactly three call sites opt
out: `_reference_propagator`, because five of the sixty-six lines in Vallado's verification file
fail the checksum and a default that refused the reference data would be a control refusing its
own authority, plus two tests that deliberately exercise the layer beneath the gate. The count of
opt-out call sites is asserted **by parsing the file, not searching its text**: the first version
counted the string and found six, because docstrings discussing the opt-out matched too. A guard
that counts mentions instead of calls measures prose.

### Controls that survived inversion, now pinned

Four mutations left the previous suite green. Each is now killed:

● `_marker_applies` inverted to fail open. Skipping an unevaluable marker is the same silent
  fail-open the extras defect demonstrated.
● `timeout=PROBE_TIMEOUT_SECONDS` deleted. Exercised against a stub interpreter that sleeps.
● The extras group deleted from the pin pattern. The old test asserted only that "uvicorn" and
  "9.9.9" appeared in stderr, which the unreadable-line report satisfies by echoing the raw
  line, so it asserted less than its docstring claimed.
● The input finiteness guard deleted. `match="finite"` was satisfied by the output guard's
  "non-finite state" too: two controls, one assertion, the weaker propping up the stronger.

### Smaller corrections

● **`InvalidMarker` was not the only failure mode.** `python_full_version ~= "banana"` raises
  `UndefinedComparison` and a 100,000-digit version literal raises `ValueError` from CPython's
  4300-digit conversion limit. Both escaped as uncaught tracebacks, fail-closed only by the
  coincidence that Python exits 1 and `EXIT_MISMATCH` is 1. Now caught broadly, with the reason
  written: `packaging` evaluates a mini-language over file content, so its failure surface is
  not enumerable from outside.
● **The fix for the fail-open branch introduced a disclosure path.** Echoing unreadable
  requirement lines is what stopped them being skipped, and a PEP 440 direct reference can
  legitimately carry a token, in the PEP 508 direct-reference form. URL userinfo is now
  rendered as `[REDACTED:credential]` before anything reaches stderr and thence a CI log.
● **`SGP4_ERRORS[6]` said "mean radius".** The library's `mrt` is the instantaneous geocentric
  radius in Earth radii, not a mean. Corrected, since the entry above it promises the phrasing
  is expanded for readability but never for meaning.
● **A dead condition** in `_is_requirement_line`: a separate `--hash` check could never return
  False, because the preceding test already excludes every line starting with a dash.
● **The width check is stricter than the library**, and the docstring now says so: the 33 line-2
  records in `SGP4-VER.TLE` are 103 or 104 columns as they appear in the file, so a caller
  reading raw records must truncate to 69 first.

### What the gates confirmed independently

Recorded because these were my claims and they are load-bearing:

● **The `sgp4` non-determinism is real.** Both gates reproduced it. One measured four of six
  cold processes returning a finite plausible state and two refusing, then consistently all-NaN
  once warm, with `epochyr=0`, `epochdays=0.0`, `bstar=0.0` after the parse: the line-1 fields
  are never assigned and the accelerated propagator runs on uninitialised memory. As an
  information-disclosure primitive it is very weak - the bytes are consumed as orbital elements
  and pushed through trig and Kepler iteration - and unreachable, since nothing outside the
  physics package imports it. The determinism breach and the fabricated plausible state are the
  live risks, and both now have a wired control.
● **5 of 66 reference lines fail the checksum**, verified against an independent implementation
  and a published ISS element set.
● **The `# pragma: no cover` on the library-refusal branch** was justified on six samples; a
  gate fuzzed 60,000 well-shaped printable-ASCII lines and `twoline2rv` raised for none. The
  justification stands on better evidence than I gave it.

**Verified.** Loop green under the pinned toolchain: **498 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch coverage. Pipeline simulation green: **497 passed, 2 skipped**. Four mutation tests
confirm the newly pinned controls fail when inverted.

## V0.15 (2026-08-20)

**What.** Closing the engineering gate's FAIL on V0.14 and the security gate's five MINORs.
Five MAJORs, and three of them were claims V0.14 certified as true that were not.

**The pattern across all three, because it is the same mistake.** In each case I measured one
axis, found nothing, and wrote the conclusion down as if I had measured the space. Property
testing found the angle defect and I fixed the end it reported. The reference file has two
identifying columns and I keyed on one. A measurement over `minutes` on a good element set
found no non-finite result, so I called the guard dead code. The fix is not "measure more"; it
is to state which axis was measured, in the record, so the gap is visible to the next reader.

### MAJOR: the angle fix closed one end of the interval and opened the other

V0.14 certified the plus-or-minus-180 seam as closed. It was closed at the low end only.

`normalise_longitude` added half a turn, folded, and subtracted it back. The ADDITION loses the
precision before the shared helper ever sees it: `179.99999999999997 + 180.0` rounds to
`360.0`, the fold correctly maps that to `0.0`, and subtracting half a turn returns `-180.0`
for an input that was already in range. Two frames one representable step apart then reported a
drift of **-359.99999999999994** degrees for 2.8e-14 degrees of real motion. `wrap_to_pi` had
the twin at plus pi, and `shortest_separation_degrees` inherited both.

So the fix for the artefact reintroduced the artefact, at the other end, and the changelog said
otherwise. Worse, the suite could not see it: the `LONGITUDES` strategy capped at `179.999`, so
the entire failing band sat outside the domain of the idempotence, separation and antisymmetry
properties. A property test is only as good as its domain, and a domain that stops short of the
boundary agrees with you about the interior.

**Fixed** by folding into `[0, 360)` FIRST and subtracting a whole turn from the upper half, so
no lossy arithmetic touches the input. Verified over 600,000 random samples plus 4,000
exhaustive representable steps either side of both ends: zero range violations, whole-turn
property holds, antisymmetry holds over the widened range.

Precisely what the old implementation fails, **measured by reverting it and running the suite**
rather than reasoned about. Five tests go red:

```
test_a_value_already_inside_the_interval_is_returned_unchanged[longitude]
test_a_value_already_inside_the_interval_is_returned_unchanged[radians]
test_two_frames_one_step_apart_near_the_high_end_report_no_drift
test_a_drift_is_the_separation_of_two_samples_never_the_difference_of_two_separations
test_reversing_a_separation_negates_it
```

It does not violate the range property, and over 2,000 representable steps either side of both
ends it returns a different value on exactly 500. It DOES violate antisymmetry, at
`math.nextafter(-180.0, 0.0)`: forward gives `-179.99999999999997` and backward `-180.0`.

Two earlier drafts of this paragraph got it wrong in opposite directions - the first named
range, whole-turn and antisymmetry as the failures, the second said antisymmetry was NOT among
them and counted three tests. Both were written from reasoning. The correct answer took one
`git stash`, one revert and three seconds of pytest.

**Also fixed:** `LONGITUDES` now runs to the last representable value below 180, and the high
ends are pinned as explicit examples. And a new test asserts the value is returned UNCHANGED,
not merely in range - the half-fix satisfied "in range" and that is how it passed.

**One thing that is not a defect, now stated as a rule.** Any half-open interval has a
discontinuity at its seam, so subtracting two normalised values across it gives about a whole
turn no matter how correct the normalisation. Chasing that is what produced the half-fix. A
drift must be computed as `shortest_separation_degrees(first_sample, second_sample)` on the raw
values, never as the difference of two separations measured against a third point. Both the
right and the wrong calculation are now asserted, because a rule without its counter-example is
a rule nobody follows.

### MAJOR: 26 published reference rows were never compared

Satellite 20413 appears TWICE in `SGP4-VER.TLE`: identical elements, two time spans of 26 and
70 rows. Both parsers keyed by satellite number, so the second occurrence overwrote the first
and 26 rows of an e=0.786 deep-space case were silently dropped. `EXPECTED_ELEMENT_SETS = 32`
and `EXPECTED_REFERENCE_ROWS = 641` then enshrined the loss, under a docstring reading "the
counts the pinned wheel actually ships" and a test named for catching a shrinking set. The
guard was measuring the shrunk total.

**Fixed** with occurrence-ordered lists instead of dicts. A dict keyed by a value the source
does not guarantee unique is a silent drop by construction. Now 33 blocks, 667 rows, 666
comparisons. **Verified**: a new test counts the file's data lines independently of the parser,
so a constant can no longer be updated to match a bug; another asserts the repeated number is
still present twice; another asserts the two files stay in the same order, since the golden
comparison pairs them by position. Worst deviations over all 666 rows are unchanged, so both
tolerances still hold.

### MAJOR: an invented cause in a diagnostic

`SGP4_ERRORS[5]` read "epoch element set was a sub-orbital trajectory". The pinned library says
"(error 5 no longer in use; it meant the satellite was underground)". I wrote a plausible cause
instead of reading the one that shipped, under a comment claiming the table came from the
library's own documentation. That is the hard rule against inventing a fact, broken inside a
diagnostic, in a trainer whose purpose is teaching diagnosis. Entry 3 also used my word
("instantaneous") where the library says "perturbed".

The existing test asserted only that each cause was non-empty and echoed in the message, so it
certified the invented text against itself.

**Fixed:** all six entries are now faithful renderings, expanded for readability (`nm` to "mean
motion") but never for meaning. A parity test asserts the key sets match the library's, so a
dependency bump that adds or retires a code fails the suite instead of leaving the table quietly
wrong. A second test pins code 5 specifically, since "no longer in use" reads oddly enough that
a future reader might tidy it into something that sounds like an orbital fault.

### MAJOR: a fail-open branch in the control everything else now rests on

`check-environment.py` required `==` immediately after the distribution name, so
`uvicorn[standard]==9.9.9` did not match, was skipped in silence, and the run printed "1 pins
checked, all match" with an unmet pin sitting in the file. The extras form is the ordinary way
to pin uvicorn. A control that silently ignores what it cannot parse is fail-open, and this is
the leg the rest of the loop's meaning depends on.

**Fixed:** the pattern accepts extras and markers; every requirement line the pattern rejects
is reported by file and line rather than dropped; a pin whose environment marker does not apply
is skipped deliberately, so a Windows-only pin is not a false failure on Linux; and versions
compare by PEP 440, so `9.1.1.0` and `9.1.1` are one release rather than a mismatch that
teaches people to skip the leg.

**Declined, with the reason recorded:** the check stays one-directional. Asserting that nothing
is installed BEYOND the lock files would fail on every runner, because `pip`, `setuptools` and
`wheel` come from the interpreter's own environment and are not all pinned here. A leg that
fails on a correct environment costs more than the latent hole it closes.

### MAJOR: the submission manifest named the wrong version

The V0.14 diff set both code files to 0.14.0 and, in the same diff, left
`docs/DEPLOYMENT.md` reading "0.13.0, matching `pyproject.toml` and
`src/enlightenment/__init__.py`". False as written, in the row a human copies into the App Store
console. The checklist still certified 307 tests and 98.72% coverage, and a simulation of
0.13.0.

Two code files were guarded by a test and the document a human actually reads was not, which is
the wrong way round: a mismatch between two code files fails a test, a mismatch between the code
and the manifest ships. **Fixed**, and two new guards now assert the manifest's Version row and
the checklist's simulation command both name the version in `pyproject.toml`.

### The security gate's five MINORs, and one finding underneath them

None were reachable from the HTTP edge; the physics core is imported nowhere outside itself and
its tests.

● **A non-finite time produced a fabricated state vector.** `sgp4_tsince(float("inf"))` returns
  code **0** with an all-NaN state, so the exact thing the wrapper exists to prevent arrived
  THROUGH the code check rather than around it. Input now guarded.
● **Three third-party exception types escaped the module's stated contract:** `ValueError` for
  an embedded NUL, `UnicodeEncodeError` for a lone surrogate, `TypeError` for a non-string. A
  caller cannot fail closed on an exception it was never told about. Element-set lines are now
  validated for width and charset at the boundary, and everything arrives as
  `PropagationError`. Nine hostile inputs are pinned, with a control test proving the library
  does not refuse them all by itself.
● **Leg one omitted `requirements-runtime.txt`,** the only lock file that ships. Now checked,
  plus an invariant asserting the lean file is a version-identical subset of the tested one,
  since the loop only catches divergence when both files' pins happen to be installed together.
● **A bare suppression and an unbounded subprocess** in `check-environment.py`: justification
  written, `timeout=60` added, and a timeout reported as a mismatch rather than raised, because
  a failure to check is never a pass.

**And the finding that came out of investigating them, which is the most serious thing in this
release.** The pinned `sgp4` extension is **not dependably deterministic** for a well-shaped but
meaningless element set. Three identical consecutive calls in one process returned an all-NaN
state, then a finite and entirely plausible one, then all-NaN again: `twoline2rv` leaves the
object partially initialised and the propagated values come from whatever was in memory. This
trainer's determinism requirement is that the same seed yields an identical event log twice, so
such an element set cannot be allowed near a scenario.

Two layers, neither claimed sufficient alone. The output finiteness guard catches the NaN
outcome. The plausible outcome is invisible at that layer - a finite wrong number looks like a
finite right one - so `element_line_checksum_ok` implements the published TLE checksum for the
scenario engine's authoring-time solvability check. Every meaningless line tried fails it.

It is deliberately **not** a gate inside `load_elements`: five of the sixty-six element-set
lines in Vallado's own verification file fail the checksum, including the deliberate error case
at 33334. They are synthetic vectors, not real element sets, and a control that refuses the
reference data is not a control. A test pins that count, so if a future wheel ships a corrected
file the checksum can be promoted.

**On the output guard, stated accurately this time.** V0.14 shipped without it and recorded no
reason. The removal happened in development during this release: I added the guard, measured it
over sixteen extreme values of `minutes` on a good element set, found the branch unreachable,
and took it out. That measurement held the element set fixed. Varying the element set instead
reaches the branch immediately, so the guard is back and the docstring names the axis the
measurement covered.

An earlier draft of this entry attributed the "removed as dead code" claim to V0.14's record.
V0.14 made no such claim. Fabricating an entry in this project's own audit trail, in the release
whose subject is audit-trail integrity, is worse than the defect it was describing.

**Verified.** Loop green under the pinned toolchain: **498 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean. Pipeline simulation green: **497
passed, 2 skipped**, same coverage.

Both figures are quoted because V0.14 quoted one that came from neither run. The two differ by
exactly one skip, and the cause is `scripts/simulate-pipeline.sh` setting `GITLAB_CI=true`,
which makes `ON_PLATFORM_RUNNER` true and skips
`test_the_platform_generates_its_own_pipeline_and_we_never_commit_one` - the platform commits
its own pipeline, so its absence is not assertable on a platform runner. An earlier draft
attributed the skip to a missing dev toolchain. Nothing in the suite skips on that. Measured
with `GITLAB_CI=true pytest -rs`, which names both skips directly.

## V0.14 (2026-08-20)

**What.** The physics core of the flight plan's Phase 0, and a defect in the verification loop
itself that was found while running it.

### The verification loop was running an unpinned toolchain

This one comes first because it changes the standing of earlier entries in this file.

`scripts/verify.sh` invoked `ruff`, `mypy`, `pytest` and `pip-audit` by bare name, so PATH
decided which versions ran. On this machine PATH held:

| tool | on PATH | pinned |
| --- | --- | --- |
| ruff | 0.15.8 | 0.16.3 |
| mypy | 1.19.1 | 2.3.1 |
| pytest | an isolated tool environment that cannot import the application's dependencies | 9.1.1 |
| pip-audit | absent | 2.10.1 |

It surfaced as a FALSE FAILURE: ruff 0.15.8 raised S310 on `healthcheck.py`, a finding the
pinned 0.16.3 does not raise. That is the lucky direction. The same gap produces a false PASS
just as readily, and every other claim in this repository rests on this loop's verdict. "The
loop is green" has to mean "green against the dependency set the container ships and the
platform installs", or it means nothing.

**Standing of the earlier rows.** Every "loop green" claim in V0.1 to V0.13 was made without a
control on which analyser ran. The code those rows describe is unchanged and re-verified at
this release under the pinned toolchain, so the conclusions hold; the METHOD behind them did
not have the guarantee the rows implied. Recorded rather than quietly corrected.

**Fixed.**

● Every leg now runs as `"$PY" -m <tool>`, where `$PY` is resolved once from
  `ENLIGHTENMENT_PYTHON`, then `.venv/bin/python`, then `$VIRTUAL_ENV/bin/python`, then
  `python3`. The interpreter is echoed at the top of every run.
● New leg one: `scripts/check-environment.py <interpreter> <lockfile>...` asserts that every
  `name==version` pin is installed at exactly that version, reporting every divergence rather
  than the first. First because a mismatch means every later leg measures the wrong thing.
● Six guards in `tests/test_appstore_contract.py`. Three assert the loop's shape: no bare tool
  name, every tool routed through `$PY`, the environment check ahead of the first analyser.
  Three EXECUTE the checker: a missing distribution fails, a wrong version fails, a matching
  pin passes. The last is the control, without which a script that always exited non-zero
  would satisfy both negative tests.
● The three shape guards were run against `git show HEAD:scripts/verify.sh` and all three
  fail on it: five bare invocations, no module routed through `$PY`, no environment check.
● The executed guards use a SYNTHETIC lock file, not the real `requirements.txt`. Pointing
  them at the real file would couple the platform's test stage to the platform's install
  fidelity, so a divergence would fail the suite instead of reporting a mismatch. A
  self-inflicted pipeline failure is the fault that broke the last upload.

`scripts/package-appstore.sh` also calls `python3`, and that stays: it uses the standard
library only (`shutil`, `zipfile`, `hashlib`), so no third-party version can drift under it.
`simulate-pipeline.sh` already used its own temporary environment's paths.

### A real defect in the angle wrappers, found by property testing on its first run

`normalise_degrees(-1.13e-78)` returned `360.0`, outside its documented `[0, 360)`. Floating
point is the cause: the exact answer is a hair under a full turn, an amount too small to
represent at that magnitude, so `%` rounds UP to the excluded end. `normalise_longitude` and
`wrap_to_pi` had the same defect one representable step below their low ends.

This is the module's own subject matter turned on itself. The operational form, measured not
argued: two samples of a near-antipodal GEO pair where the target moves 1.4e-14 degrees between
them. The naive arithmetic reports the separation as +180 then -180, so the drift between
consecutive frames reads as a full 360 degrees. That is the ASTRA 1M artefact class exactly, and
a trainer whose own maths manufactures it teaches the wrong lesson about competency axis five.

**Fixed** with one `_fold_into_turn(value, turn)` helper all three wrappers share, so the
guarantee lives in one place. **Verified** three ways: the three inputs are pinned as
`@example` cases as well as properties, because a property test only rediscovers a corner if
the search happens to reach it; a parametrised regression asserts each lands inside its
interval; and the naive expressions were run against all four new assertions, which reject
3 of 3 interval cases and the drift case.

One correction against myself: the first version of the drift test asserted in its docstring
that the naive path returned 180 degrees there. It returns 0.0. The docstring certified
something the measurement disproved, so the test was rewritten around numbers taken from the
measurement rather than from reasoning.

### SGP4 against Vallado's published output

`tests/test_physics_propagation.py` reads `SGP4-VER.TLE` and `tcppver.out` from inside the
pinned `sgp4` wheel, the AIAA 2006-6753 verification distribution. Worst deviation MEASURED,
not chosen: 1.17e-7 km in position (about 0.12 mm) and 8.53e-10 km/s in velocity.

**Superseded by V0.15.** This entry said "32 element sets, 641 reference rows, 640 comparable".
The published file holds 33 blocks and 667 rows; keying the parser by satellite number dropped
26 of them. It also said the tolerances sit "two orders above" the measurement, which is true
of position (85 times) and not of velocity (12 times). Left in place with the correction rather
than edited away, because a record that quietly repairs itself is worth less than one that shows
where it was wrong.

Reading the reference rather than transcribing a handful of vectors is the point: the hard rule
against inventing a figure applies to test data first.

Two named traps get a witness from the published data rather than a synthetic one.

● **The unchecked error code.** Satellite 33334 in the official set returns SGP4 code 3,
  perturbed eccentricity out of range. A wrapper that ignores the code returns floats that
  read as a position; this one raises. Vallado shipped the trap, which is stronger than an
  element set I would have built to fail.
● **TEME is not J2000.** The frame is carried in `StateVector` and asserted. The failure is
  silent and grows with epoch separation, so the only defence is that it is never implicit.

A guard test recounts the rows independently and asserts the comparisons actually happened,
because a per-block loop that swallows exceptions is a green suite that compared nothing. The
counts it asserted were wrong; see V0.15.

**Verified.** Loop green under the pinned toolchain. The figure recorded here was "420 passed,
1 skipped, coverage 98.61%"; the loop's own output at the time was 421 passed and 1 skipped,
and 420 passed with 2 skipped was the PIPELINE SIMULATION. The certified number mixed two runs.
Corrected here rather than silently: a release record whose headline figure came from neither
run is the kind of small inaccuracy that makes the rest of it worth less.

**Still open, and needing your decision before Phase 1** (unchanged from V0.13): SQLite on the
storage volume versus the current JSON snapshot store; the `IdentityProvider` adapter versus
the shared team token; and a signed Data Protection Impact Assessment (DPIA) before any
named-individual performance record is written.

## V0.13 (2026-08-19)

**What.** The real cause of the upload failure, read from the platform log rather than inferred,
plus the first increment of the ENLIGHTENMENT flight plan V1.0.

### The upload failure: `pytest: command not found`, exit 127

The platform's generated test stage runs exactly this:

```
pip install -r requirements.txt
pytest --cov --cov-report=xml:coverage.xml
```

It installs ONE file and knows nothing about a dev file, and the pipeline is GENERATED so it
cannot be edited to add a second install line. `requirements.txt` held runtime dependencies
only, so pytest was not there. Four of eight stages passed; Code Quality, Container Build and
Container Scan were all skipped.

**Two failures of mine, stated plainly.**

1. **The previous release fixed the wrong thing.** `unzip` in an executed script was a real
   latent defect and it is still worth having fixed, but it was NOT this failure. I diagnosed
   from the symptom instead of waiting for the log, having said in the same breath that the log
   should decide. Inference substituted for evidence and cost a cycle.
2. **The answer was in the document I had just read.** The flight plan states the contract at
   line 132: "two requirements files (`requirements.txt` carries all test tooling,
   `requirements-runtime.txt` stays lean)". I read it, noted it was the inverse of the layout in
   place, and deferred it as a separate concern. It was the fix.

**The three-file contract, now honoured:**

| File | Installed by | Contents |
|---|---|---|
| `requirements-runtime.txt` | the container image | lean runtime only |
| `requirements.txt` | the platform's test stage, and the local loop | runtime plus the test runner |
| `requirements-dev.txt` | local only | lint, types, vulnerability scan |

**And the reason the simulation missed it, which matters more than the fix.** The simulation
installed BOTH requirements files, so it was more generous than the platform: it went green while
the real stage failed. It now installs exactly what the platform installs and nothing more.
Proved by reverting the defect into a copy: the corrected simulation fails, and so does the local
loop. A simulation that helps the code along proves nothing about the platform.

Six new tests pin the contract in both directions: the test runner is present in the file the
platform installs, the image installs the LEAN file with hashes, no test tooling reaches the
image (asserted per tool), the simulation never installs the dev file, all three lock files are
audited, and all three are packaged into the artefact.

### Flight plan V1.0, Phase 0 step 2: the physics core

The flight plan is a materially different and much larger application than what is built: an
orbital warfare trainer with a physics core, a procedure library, a drill engine, a scoring
engine, a debrief engine, SQLite on the storage volume and a single-file SPA. What ships today is
a session recorder, roughly five per cent of that, and the `scenario` field is free text. So
there is no simulation-data generation to alter yet; this is new construction, and it follows the
plan's own ordering, which puts the physics first because everything scores against it.

● **`physics/angles.py`.** The plus-or-minus-180 seam isolated in one module, because the plan
  names angle wrapping as a regression trap and the LEARNED register records an ASTRA 1M case
  where a millisecond epoch gap produced a drift rate of about minus 22,900,000 degrees per day.
  `shortest_separation_degrees` is the only permitted way to difference two angles here.
● **`physics/propagation.py`.** SGP4 wrapped so nothing else touches the library. Two of the
  plan's named traps are closed by construction: the output frame is carried in the type, so TEME
  cannot be silently treated as J2000; and every non-zero SGP4 return code becomes an exception,
  because an unchecked code is a fabricated state vector and scoring an operator against one is
  worse than refusing to run.

`sgp4` is pinned with a recorded reason. `numpy` and `skyfield` are deliberately NOT added yet,
with reasons recorded in `requirements.in`: propagation and the determinism harness are scalar, and
skyfield's ephemeris dependency needs a deliberate vendoring decision under the air-gap posture.

**How verified.** Loop green, ruff and mypy strict clean over 15 modules, `pip-audit` clean over
all three lock files. Masked simulation green with the platform's exact install. The mypy override
for the untyped `sgp4` surface is narrowed to that one module, so no untyped value escapes the
wrapper.

**Not yet done, and deliberately not started:** the Vallado golden vectors (the data ships inside
the `sgp4` package as `SGP4-VER.TLE` and `tcppver.out`, so the tests will read the published
reference output rather than invented numbers), the determinism harness, and everything in Phase 1.

## V0.12 (2026-08-19)

**What.** The first real upload FAILED at the platform's Test stage: four of eight stages passed,
and Code Quality, Container Build and Container Scan were all skipped. The reported message was
"Tests failed", which points at the tests. The cause was not a test.

**`scripts/package-appstore.sh` shelled out to `unzip`, which a stock `python:3.12-slim` image
does not ship.** A contract test EXECUTES that script, so on the platform's runner it exited 127
and the test asserting a clean exit failed. Locally green, in CI green, and neither environment
reproduced the one thing that mattered: the platform's TOOL INVENTORY.

**This is a class I had already been told about and fixed one instance of.** A reviewer raised
exactly this in the previous round, naming `zip`. I removed `zip` and left `unzip`, `tar` and
`sha256sum` in the same file. Fixing the instance is not fixing the class, and this cost a real
upload cycle to learn.

**Three fixes, at three different rungs:**

1. **The script now uses nothing but a POSIX shell and `python3`.** `shutil.copytree` for the
   copy, `zipfile` for the archive and the listing, `hashlib` for the digest. The rule is stated
   at the top of the file so the next person does not reintroduce it.
2. **Two tests assert the RULE**, parametrised over the tools a stock python image lacks
   (`zip`, `unzip`, `git`, `curl`, `wget`, `jq`, `docker`), with a word-boundary match so
   `zipfile` does not read as `zip`. So the local loop now catches this class at the cheapest rung.
3. **The pipeline simulation MASKS those tools** during its test stage, replacing each with a
   stub that exits 127. The simulation previously reproduced the platform's added file and its
   environment variable, but not its tool inventory, which is why it passed while the upload
   failed.

Proved rather than assumed: reintroducing `unzip -l` into the packaging script makes the local
loop go red AND the masked simulation go red. Two independent nets, both verified against the
actual defect.

**Also widened: the platform-runner gate.** `ON_PLATFORM_RUNNER` tested `GITLAB_CI == "true"`
exactly, betting the deploy on one variable having one exact value. A negative assertion about a
file the PLATFORM ITSELF adds must never be guaranteed-false on the machine that gates the
deploy, so any credible runner signal now counts (`GITLAB_CI`, `CI`, `CI_PIPELINE_ID`,
`CI_JOB_ID`, `GITHUB_ACTIONS`).

**How verified.** Loop green, 334 tests collected (333 passed, 1 skipped locally; 332 passed and 2
skipped under the masked simulation), branch coverage 98.50%,
`pip-audit` clean over both lockfiles. Masked pipeline simulation green against the artefact on
the pinned interpreter. The masking leg proved load-bearing by reintroducing the defect.

**Caveat on the diagnosis.** The platform's own log for the failed run has not been read. `unzip`
in an executed script is a defect that produces exactly this symptom and it is fixed, but if the
new upload fails again, get "More Details" from the console: the specific assertion will name the
cause, and inference should not substitute for it twice.

## V0.11 (2026-08-19)

**What.** Both gates FAILED the V0.10 head with five MAJORs. Two were claims I had recorded as
closed and had not been, which is the third time that has been the failing finding.

● **The unparsable `If-Match` 500 was not closed.** `isascii() and isdecimal()` still lets `int()`
  raise: CPython caps integer string conversion at 4300 digits, so a 4301-digit validator returned
  500 on a real socket. A reviewer found it AFTER I recorded the class as closed. The guard is now
  three-layered: character class, a 19-digit length bound, and a guarded conversion. The third
  layer exists because a documented fail-safe should not depend on having enumerated every hostile
  input, which two rounds of this same bug proved I cannot.
● **The "binding patch-level check" checked no patch level.** Counting `Package:` lines proves the
  scanner can ENUMERATE what ships, not that anything is patched, while three places said
  otherwise. `apt-get upgrade` is deliberately fail-open, so the honest position is that patch
  assurance rests on the digest-pinned base plus the platform's own container scan, which is the
  only thing with a real CVE database. The claim is narrowed to what the check does; the check
  stays, because a well-meant cleanup of `/var/lib/dpkg` would silently blind the scanner.

● **Three CI assertions were satisfied by any mention of their marker**, so each check could be
  deleted with the suite green: the OS-package step replaced by an `echo` naming the marker, the
  bundled-wheel scan likewise, and `dpkg` in the tool list satisfied by the unrelated
  `/var/lib/dpkg/status` line. Instances sixteen to eighteen of the assert-the-prose class in one
  file. Each marker is now bound to the `docker run` step that must carry it, and the tool list is
  parsed rather than matched.
● **The artefact-building test shelled out to `zip`.** The platform runs this suite in ITS
  environment, and `zip` is not part of a stock Python image, so an absent binary would fail the
  test stage and skip quality, container build and deploy, with the diagnosis pointing at
  packaging. Packaging now builds the archive with `zipfile`, so the release path needs only the
  interpreter that is already running the suite.
● **V0.10 shipped with no audit row.** Written above, retrospectively, and a test now fails when
  the version being shipped has none.

Also: the edit helper preserved no file mode, so a scripted edit to any mode-755 script stripped
its executable bit; the security policy cited a test for the real-write control that does not kill
an existence-check mutant, because the case it covers never reaches the write; the narrowness of
the `app.state` seam was unasserted, so re-publishing the whole runtime and its plaintext token
left the suite green; and the deployment record carried a hand-copied test count that had already
been wrong twice, now removed rather than corrected again.

**How verified.** Loop green, ruff and mypy strict clean, 326 tests collected (325 passed, 1
skipped) with branch coverage at 98.50% against an 80% floor, `pip-audit` clean over both lockfiles, pipeline simulation green against the
artefact, CI green across all three jobs including the binding image leg.

## V0.10 (2026-08-19)

**What.** The container was built for the first time, and the build immediately found a defect no
local check could have.

`ensurepip` vendors a complete pip wheel, `pip-25.0.1-py3-none-any.whl`. It is not a binary, so
`command -v pip` reported nothing and the package-manager check passed, while a filesystem CVE
scanner reports pip as a shipped package. The claim "the runtime ships no package manager" was
therefore FALSE for three releases of documentation. A reviewer had hypothesised exactly this and
said plainly it could not be settled without a build; fixing the CI trigger in V0.9 is what let
the hypothesis be tested. `ensurepip` is purged in the prep stage and asserted locally and in CI.

**The lesson is not about pip.** A `PATH` check answers "what can the entrypoint run". A scanner
asks "what is in the image". Those are different questions, and the documentation asserted the
second while only ever testing the first.

**What the first build proved**, against the built filesystem rather than the Dockerfile text:
`Config.User = 10001:10001`; zero setuid or setgid paths, swept as root with stderr surfaced;
no package-manager binary on `PATH`; the dpkg database retained so the platform scanner can still
enumerate; and, after the fix, zero bundled wheels. The container also ran and answered every
platform probe on 8080.

**`/readyz` returned 503 in that run, and that is correct.** No file-storage add-on is mounted in
CI, so the non-root user cannot write the image's own default directory. The application starts,
serves every liveness path, publishes a complete diagnosis with `errno 13 EACCES` and the resolved
directory, and reports itself unready. Deliberately not softened: a writable in-image directory
would let a pod whose volume failed to mount run on ephemeral storage and lose every training
session at the next restart. A loud unready state beats silent data loss.

**How verified.** Loop green, 312 tests collected, branch coverage 98.72%, `pip-audit` clean over
both lockfiles, pipeline simulation green, and all three CI jobs green including the binding image
leg.

**This row was missing when V0.10 shipped**, and is written here retrospectively. A test now fails
if the version being shipped has no audit row, because the deploy gate reads this document and
V0.10 left it describing a three-commit-stale state.

## V0.9 (2026-08-18)

**What.** `deploy-gate` returned FAIL on V0.8.0 with three blockers. None was a defect in the
application: two were owner decisions I must not invent, and the third was a hole in my own
verification chain.

**The hole, and it is the important one.** The CI `image` job is the only thing that can build
this container, because the authoring environment's network policy denies the registry blob
endpoint. Three documents, including `docs/SECURITY.md`, name it as the binding check for
container hardening. The gate checked whether it had ever run instead of taking that on trust:
zero workflows registered on the repository, zero pull requests ever opened, `origin/main`
holding a single file, and a trigger set to `pull_request` into `main` and `push` to `main` only.
So on a release branch it had never fired once, and **the container had never been built by
anything, anywhere**, while three documents called its verification binding. A binding check that
cannot fire is not a check. The trigger now covers release branches and manual dispatch, and a
test fails if that regresses.

**Two checks only a built image can settle, added while the job was being fixed.** The
package-manager check tested binaries on `PATH`, so a vendored wheel under `ensurepip` would pass
it while a filesystem CVE scanner reports it. And nothing at all asserted the base patch level,
because the Dockerfile's `apt-get upgrade` is deliberately fail-open for runners behind a mirror.
Both now have a binding check reading the retained dpkg database, which is the reason keeping that
database was the right call rather than a tidiness loss.

**Owner decisions, recorded as decisions with their date.** Category Training / Simulation.
Visibility private to the Bluestaq Ltd team. Resource budget 1Gi request and 2Gi limit, 1 CPU
request and 2 CPU limit. The scenario vocabulary stays an open, length-capped field rather than
invented terms.

**A consequence of private-to-team worth stating loudly.** It requires the team token, and setting
the token makes `ALLOWED_ORIGIN` mandatory, so the environment tab is no longer empty for this
deployment. Two variables are set and every other row stays `[delete]`. The failure mode of
forgetting the token is a read-only service, never an open one, which is the whole point of the
fail-closed write posture.

**The withdrawal path for a first deployment, which was missing.** There is no previous version to
roll back to, and the record said so honestly but documented only the rollback that applies to
later releases. So an operator had nothing to follow if THIS deployment had to come out. Written
now: take the app out of service through the lifecycle action, do not delete the record as a first
move, and never delete-and-recreate under the same slug, because app-record residue is a known
platform failure that recovers only with a fresh slug and therefore a changed URL. Deleting is the
step that is hard to undo, not the deploy.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 311 tests
collected (310 passed, 1 skipped) with branch coverage at 98.72% against an 80% floor, Cobertura
written, `pip-audit` clean over both lockfiles. Three mutants this round, all three killed, with
the control run FIRST and confirmed green on a COMPLETE tree either side of them.

**Still not verified, and now actually reachable.** The container image build. Unchanged in this
environment, but the CI job that can do it is no longer unable to fire.

## V0.8 (2026-08-18)

**What.** Both gates PASSED at round 7 on V0.7. This closes the eleven MINORs they raised
alongside those passes, including one real bug in shipped code.

**The bug.** `If-Match: "\u00b2"` returned 500 from a path documented to IGNORE an unparsable
validator, because `isdigit()` accepts characters `int()` rejects. Reached by a reviewer on a raw
socket: uvicorn latin-1 decodes header bytes, so byte 0xB2 arrives as that character. Graded
MINOR because the route sits behind authentication, no state is written and both limiter tiers
bound it, but it is a 500 in shipped code and this project had already found and fixed the same
class in `healthcheck.resolve_port` two releases earlier. Found there, missed here. The guard is
now `isascii() and isdecimal()` in both places, and the parser is tested directly across eleven
hostile spellings plus the wire case, because a client library refuses to encode the bytes.

**Two claims corrected by measurement rather than reasoning.** The packaging test asserted that
commenting out the `rm -rf` purge would ship `.git`, `.venv`, `var/` and `dist/` in the App Store
zip. A reviewer built the artefact with the purge removed and found it clean: the real control is
the ALLOWLIST copy loop, and the purge is a defensive re-check behind it. So the test now BUILDS
the artefact and inspects the zip, and the claim says what the layers actually do. Removing either
layer alone still gives a clean artefact; removing both is what the test catches.

**Four demonstrated escapes in my own test instruments.** A trailing `#` comment on a live shell
line could delete the packaging purge with the suite green. A four-line `pytest.ini` outranks
`[tool.pytest.ini_options]`, so the coverage-flag assertion stayed green while a bare `pytest`
wrote no Cobertura, which is the exact 0%-coverage gate failure it exists to prevent. The
documentation sweep exempted elided citations, leaving 12 of 63 names unchecked. And the version
lived in two files with no parity test, which is the class the sweep was added to close.

**The edit helper reviewed as shipped code, and it needed it.** `Path.write_text` follows a
symlink, so a symlinked target wrote OUTSIDE the named directory: the same reasoning that puts
`O_NOFOLLOW` on every file this project's store opens. It also wrote before verifying, so its
`EXIT_UNVERIFIED` refusal left a half-edited file, which is the inverse of what the tool exists
to prevent. It now refuses a symlink, verifies BEFORE writing, writes atomically through a
temporary sibling, and reports an unreadable target with a documented code instead of a
traceback. Nine tests drive it.

**A process note worth recording.** The first run of this round's mutation battery reported eight
kills that were not real: my mutant copy omitted two root files, so the packaging test failed in
every run including the control, and eight mutants appeared "killed" by a test that was failing
for an unrelated reason. The control run is what caught it. Running the control FIRST, not last,
is the cheap habit that turns a mutation battery from theatre into evidence.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 307 tests
collected (306 passed, 1 skipped) with branch coverage at 98.72% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Ten mutants
this round on a COMPLETE copy with the control verified first: eight killed by the intended test,
one shown to be neutralised by a second layer rather than undetected, and that layered case then
proved detectable by removing both layers at once.

**Still not verified.** The container image build, for the same reason as every prior release: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

## V0.7 (2026-08-18)

**What.** Round 6 returned two MAJORs, and the more important one is a class rather than a bug:
**four contract assertions read their target file raw, so a comment satisfied them.** Each was
measured surviving as a commented-out line, and each protects something that matters:

| Commented out | What the suite still said | What would have happened |
|---|---|---|
| `sonar.python.coverage.reportPaths` | green | SonarQube reads no report, scores 0%, quality gate fails on upload |
| `--cov-report=xml:coverage.xml` in `addopts` | green | a bare platform `pytest` writes no Cobertura, and `verify.sh` is satisfied by a stale file |
| `.env` in `.gitignore` | green | a developer's real `.env` becomes committable |
| the packaging purge | green | `.git`, `.venv`, `var/` and `dist/` ship inside the App Store zip |

That last one is the same defect this project's own ledger already recorded once, reproduced
verbatim on a different line of the same file, in a test file that already contained two
comment-stripping readers written to prevent exactly this. Every one of these now goes through a
real parser: `tomllib` for the manifest, a `.properties` parser, and an executable-lines reader.

**The second MAJOR.** The lifespan docstring still said the pool is "created on FIRST PROBE
rather than at construction", three lines above the code that builds it eagerly, in the very
function the previous round edited. The field comment 460 lines away was rewritten at length
while this one was missed.

**A guard so the documentation cannot rot silently.** `test_every_test_named_in_the_security_policy_exists`
sweeps every backticked test name in this document and fails if one does not resolve. It found a
dangling citation the moment it was written, from a rename two commits earlier. It states its own
blind spot: it cannot see a row whose named test exists but no longer asserts the control it is
cited for, which is what the mutation ledger is for.

**Three controls that needed a better instrument, not just a test.** The single-worker pool is now
asserted as SERIALISATION, by submitting two blocking callables and proving the second cannot
start until the first returns, rather than by reading a private CPython attribute. A probe after
lifespan shutdown now fails closed instead of silently falling back to the shared default
executor, which is the starvation the dedicated pool exists to prevent. And the inspection seam
was narrowed: publishing the whole runtime put the plaintext team token within reach of any
handler through `request.app.state`, so only the pool is published.

**The edit helper is now executed, not asserted.** Five tests drive `scripts/verified-edit.py`
through its outcomes, and the unreachable third refusal it advertised is deleted rather than
claimed, on the same reasoning that removed the inert drain guard.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 286 tests
collected (285 passed, 1 skipped) with branch coverage at 98.71% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Nine mutants
this round, eight killed first time; the ninth, a post-shutdown probe silently using the shared
executor, was closed and re-proved killed.

**Still not verified.** The container image build, for the same reason as every prior release: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

## V0.6 (2026-08-18)

**What.** The security gate PASSED again on the current tree. The engineering gate FAILED on one
MAJOR, and it was the same fault line as the two rounds before it: my record certified a
mutation proof that a five-line experiment disproved.

**The disproved claim.** I said lazy probe-pool creation was closed and mutation-proved, and
gave a mechanism: "a ThreadPoolExecutor is held by a module-level registry, so building an app
and never probing it left an idle thread alive; 40 threads for 40 apps". Both reviewers measured
otherwise. A `ThreadPoolExecutor` starts NO worker until work is submitted, so 40 constructed
pools hold 0 threads, and my test counting threads passed whether the pool was built lazily or
eagerly. It asserted nothing.

Investigating properly turned up a second wrong half: a dereferenced executor's worker also
exits when the executor is collected, so creating a new pool per probe leaks nothing observable
either. Laziness was therefore unassertable in both directions. **The branch is removed, not
defended.** The pool is built eagerly, and the control that does matter, the lifespan release,
is the one that kills its mutant.

**A control the removal exposed.** Raising the pool from one worker to eight was a surviving
mutant, and single-worker serialisation is one of the two invariants `_probe_storage` names as
what keeps publication ordered. Thread counts cannot catch it, because single-flight means only
one probe runs at a time either way. It is now asserted through an explicit in-process
inspection seam (`app.state.runtime`), so the wiring is checked rather than the source grepped.

**Two more unasserted controls, both mine.** The drain bound that SHIPS was asserted by nothing,
because both drain tests injected the timeout: setting the constant to 86 400 seconds left every
test green while the deployed drain was effectively unbounded again. And the budget being TOTAL
rather than per-message was unasserted: moving the deadline inside the loop left the suite green,
and on a real socket that mutant left a client dripping one byte every 10 seconds unanswered
after 46 seconds against 15.0 for the shipped code.

**A test that hung instead of failing.** The per-message mutant made my own drain test wait
forever, because the test relied on the bound it was testing to terminate. A hanging test is not
a failing test: continuous integration reports a job timeout, which reads as infrastructure
trouble rather than as a defect. Every drain test now bounds itself as well as the code.

**Dead weight removed rather than kept.** The `remaining <= 0` guard in the drain was inert,
because `asyncio.wait_for` raises on a non-positive timeout itself, and the prose grep for the
image script's deferral is deleted now that four tests execute it.

**The process claim is now checkable.** The verified-edit helper is landed at
`scripts/verified-edit.py` instead of living only in an authoring session. It refuses a missing
anchor, an AMBIGUOUS anchor, and a replacement that is not present afterwards. A reader of this
record can run it.

**Honest residual recorded, not omitted.** The body drain is bounded, measured at 120 of 120
parked connections answered 408 with descriptors returning to baseline. A connection that stops
before the blank line ending the headers never reaches the ASGI application, so neither the
drain bound nor the rate limiter can see it: 200 such connections took a worker from 10 to 210
descriptors. That is not fixable inside an ASGI application without a custom protocol, so it is
recorded as an accepted residual with the platform ingress named as its bound.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 279 tests
collected (278 passed, 1 skipped) with branch coverage at 98.71% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Ten mutants
this round: seven killed first time, three survived and were closed by removing the unassertable
branch and asserting the two real controls, then re-proved killed.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds, and its own assertions are mutation-proved.

## V0.5 (2026-08-18)

**What.** The security gate PASSED at round 4 with four MINORs. The engineering gate FAILED,
and not on the request path: on the RELEASE RECORD. The V0.4 audit row stated in the past tense
that the single-flight docstring's two false claims had been corrected. They had not. The edit
was a string replacement whose anchor did not match, so it silently did nothing, and I wrote the
entry as though it had landed.

That is worse than the prose it failed to fix, and worse than a code defect, because a record
that certifies work not done makes every other claim in it worth less. It happened in the same
commit that added a ledger about claims running ahead of evidence.

**The process fix, not just the text fix.** Every edit now goes through a helper that reads the
file back and fails loudly on a missed anchor or an absent replacement. The first thing it did
was refuse the docstring edit and print the anchor, which is how the correction finally landed.

Corrected for real this time: `_probe_storage`'s docstring counts two properties rather than
three, and states the invariants the code actually relies on (only the caller that started a
probe publishes it, and the pool has one worker) instead of claiming single-flight makes a
publication race impossible. Two independent reviewers reproduced two coexisting probe tasks, so
the impossibility claim was simply false. A test docstring repeating the same overstatement is
corrected too. A second false mechanism claim in the V0.4 entry is corrected in place: a probe
after lifespan shutdown does NOT raise, because the lifespan sets the pool to `None` and
`_run_probe` silently builds a new one.

**Four controls that were claimed closed and were asserted by nothing**, each found by an
independent run rather than by me:

● The image script's deferral behaviour was tested by grepping for the strings
  `THIS IS NOT A PASS` and `exit 3` anywhere in the file, so rewriting the no-daemon leg to
  `echo PASS; exit 0` stayed green. That is the leg that matters most, because it is the one
  that currently cannot run for real. It is now EXECUTED against a stub `docker`, four ways: no
  daemon defers with exit 3, an unreachable registry defers, a Dockerfile the builder reached
  and refused fails hard with exit 1, and a successful build reports a pass.
● The lazy probe-pool creation and the lifespan release. Both mutants survived; both are now
  asserted by counting probe threads by IDENTITY, since every pool names its worker `probe_0`
  and a set of names silently deduplicated across apps.

**Two latent defects closed on the way.** The body cap read `scope["method"]` un-normalised, so
a lowercase `post` skipped the cap entirely: not exploitable today, because Starlette's route
match is case sensitive, but this is the third time this cap has declined to run on a scope value
the layers behind it normalise differently and the first two shipped as exploitable. And the
drain had no time bound: 200 unauthenticated requests declaring a body and sending one byte took
a listener from 8 to 207 file descriptors with none ever answering. The drain is now bounded at
15 seconds and answers 408.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 275 tests
collected (274 passed, 1 skipped) with branch coverage at 98.37% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Six fresh
mutants, all six killed first time. Re-measured on a real uvicorn socket: the round-3 header
order, a lowercase method token and mixed-case header names all return 413 with peak resident
set flat at 46 MB, and 120 parked undrained connections were all answered by the drain bound,
with the listener's file descriptors falling from 110 back to 83 and liveness answering 200
throughout.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds, and its own assertions are now themselves mutation-proved.

## V0.4 (2026-08-18)

**What.** Closed the third round. Both gates independently found the same bypass, and it was
one I introduced in the round-two fix.

● **The body cap was bypassable by header ORDER.** `_body_framed` returned from inside its
  header loop on whichever framing header appeared first, and treated `Content-Length: 0` as
  "no body". RFC 7230 section 3.3.3 makes `Transfer-Encoding` win, and h11 agrees, so
  `Content-Length: 0` sent BEFORE `Transfer-Encoding: chunked` read as no body while the
  server delivered the whole thing. Measured unauthenticated on a raw socket: 128 MB accepted,
  resident set 45 MB to 326 MB, answering 422 rather than 413. Swapping the two headers gave a
  correct 413, and that order dependence was the entire defect. So the round-two
  pre-authentication denial of service was live again, one commit after I declared it closed.
  Every header is now examined before deciding, and a declared length is ignored when a
  transfer-encoding is present, because the framing header wins and the length is then not the
  body's size. Re-measured on a real socket across four header orders: 413 every time,
  resident set flat at 46 MB.
● **My own fix had broken a control's only assertion.** Seeding the boot verdict into the probe
  cache meant the fail-closed test was served from the boot-time result, so the async handler
  never ran: inverting it to `ok=True` left all 244 tests green. The test now pins
  `cache_seconds=0.0` so the handler is actually reached. (An earlier version of this entry
  justified the fix by claiming that a probe after lifespan shutdown raises. It does not: the
  lifespan sets the pool to `None` and `_run_probe` silently builds a new one. The reason the
  fix matters is simply that a fail-open readiness handler answers `200 ready` on a pod whose
  storage was never proved, and nothing was asserting otherwise.)

Also fixed: a POST on a probe path could be parked indefinitely at zero cost, because the drain
awaits with no timeout and those paths are rate-limit exempt by design, so the cap now skips
them entirely; the snapshot was read following symlinks while the lock guarding it was opened
`O_NOFOLLOW`, so a principal with write access to the volume could have its own file served
through the API and copied into a backup; the probe pool is created on first probe rather than
at construction. (Retracted in V0.6: the stated mechanism was false. A `ThreadPoolExecutor`
starts no worker until work is submitted, so 40 constructed pools hold 0 threads, and a
dereferenced executor's worker exits on collection. The change to lazy creation was real; the
reason given for it was not, and the branch was later removed as unassertable.)

**Two claims that this entry originally recorded as corrected, and were not.** The
single-flight docstring said "two probes racing to publish is impossible" and announced three
properties while listing two. Both were left untouched: the edit was a string replacement whose
anchor did not match, so it silently did nothing, and this entry was written as though it had
landed. The fourth engineering review caught the release record asserting a source change the
diff did not contain, which is a worse defect than the prose it failed to fix. Corrected for
real in V0.5, and every edit is now applied through a helper that fails loudly on a missed
anchor.

**Three controls this release claimed were mutation-proved and were not**, each found by an
independent run rather than by me: the dedicated probe pool, the quoted bind address in the
launch command, and the dev-lockfile audit leg. All three now have tests that die under
mutation. The mutation ledger in `docs/SECURITY.md` now carries a per-round table of what was
claimed against what an independent run found, because three rounds have now shown my own
counts running ahead of the evidence.

**Two of my own tests were asserting prose, not behaviour.** The lockfile-audit test matched
the words in `verify.sh` including comments, so commenting the leg out stayed green. The
probe-path exemption test built its own middleware rather than the application's, so removing
the exemption from the real wiring stayed green. Both now exercise what executes.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 262 tests
collected (261 passed, 1 skipped) with branch coverage at 98.68% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green against the
artefact on the pinned interpreter with `GITLAB_CI=true`. Ten fresh mutants this round: eight
killed first time, two survived, were closed, then re-proved killed. The header-order bypass
was additionally re-measured on a real uvicorn socket rather than only in tests.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds.

## V0.3 (2026-08-18)

**What.** Closed the second round of gate findings. Both gates independently found the same
two MAJORs, which is the strongest possible signal that they were real.

● **The probe cache bounded nothing under concurrency.** The cache was read, awaited, then
  written, so every request arriving while a probe ran started its own. Measured at 500
  concurrent requests producing 500 real probes, and 17 400 concurrent requests producing
  228. Worse than wasted work: on a slow volume the queued probes exceeded their own 2s
  timeout, so a majority of responses were 503 against storage that was fine, and those
  paths are unauthenticated and rate-limit exempt by design, so any caller could take a
  healthy pod out of rotation. Probes are now single-flight: a caller arriving while one runs
  awaits that one. The probe also moved to its own single-thread executor, because sharing the
  default pool with the store took a legitimate listing from 1.4ms to 109ms at the median.
● **The body cap sat outside the coarse rate limiter, not inside it as documented.** Twelve
  oversize requests left the limiter's key table empty, so an unauthenticated caller could
  send unlimited 64KB-body requests without ever spending budget. Registration order is
  corrected and now asserted. The same middleware had also made every path drainable: `GET
  /livez` with a declared length and no bytes went from answering in 0.01s to parking with no
  response at all. It now reads a body only for POST, PUT and PATCH, and only when one is
  framed.
● **Two controls the code and the security policy both claimed were mutation-proved were
  asserted by nothing.** Deleting the `asyncio.to_thread` offload left all 216 tests green,
  while the reviewer measured the event-loop stall going from 4ms to 792ms; with one worker a
  stalled loop stalls the platform's own liveness probe. Replacing `hmac.compare_digest` with
  `==` also left the suite green. The first is now proved directly by asserting no running
  event loop is visible inside a store call; the second by a source assertion that the
  primitive is present and no token is compared with plain equality.

Also fixed: the PATCH existence check ran outside the store lock, so a concurrent write that
tripped the session cap between check and write turned an intended merge into an append of a
partial record; `str.isdigit()` accepted characters `int()` rejects, so a hostile PORT raised
an uncaught ValueError out of a function documented to return None, and non-ASCII decimals
would silently resolve to a different port than they look like; pre-write backups were written
0644 while the snapshot is 0600; the lock path is opened `O_NOFOLLOW`, so it cannot be planted
as a symlink to de-serialise every writer; `verify.sh` now audits the dev lockfile too, since
the platform installs and executes it on its own test stage; the limiter's dead window-reset
branch is gone; the interpolated `PORT` in the launch command is quoted; the deprecated
`on_event` shutdown hook is a lifespan handler.

**Corrections to my own record**, which matter more than the code fixes. An independent
32-mutant run found four surviving mutants where I had recorded one. `docs/SECURITY.md` cited a
test name that does not exist. The data-loss figure was out by a factor of two: reproduced
three times at 81, 83 and 84 records surviving of 160, not 40 of 80. The README claimed either
access variable alone refuses to start, when only a token without an origin does. The stated
middleware order was inverted. The deployment table still sized memory for two workers. All
corrected, and the mutation ledger in `docs/SECURITY.md` now lists every survivor with the
reason each is or is not load-bearing.

**Removed rather than left untestable.** The probe's publication-ordering guard is gone. Once
probes are single-flight only the caller that started one publishes it, so two verdicts cannot
race, and the guard became unreachable. A mutation proved no test could kill it. Unreachable
code inside a security control invites a wrong mental model, which is the same reason the
limiter's dead branch came out.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 245 tests
collected (244 passed, 1 skipped) with branch coverage at 98.04% against an 80% floor,
Cobertura written, `pip-audit` clean over BOTH lockfiles. Pipeline simulation green against the
artefact on the pinned interpreter with `GITLAB_CI=true`. Eleven fresh mutants run this round:
eight killed first time, three survived and were closed, then re-proved killed.

**Still not verified.** The container image build, for the same reason as V0.1 and V0.2: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

## V0.2 (2026-08-18)

**What.** Closed every finding from the first engineering and security gate reviews: one
engineering BLOCKER, three security BLOCKERs, nine MAJORs, and the MINORs worth acting on.

The three that mattered most, each measured rather than argued:

● **Writes were open by default.** `require_token` returned a local actor before the token
  compare ran, so with no token configured, which is the container default with an empty
  operator environment tab, an unauthenticated caller could POST and PATCH. The loopback
  binding that was supposed to mitigate it is read only by the local runner; the container
  binds every interface from its launch command. Writes now fail closed and anonymous writes
  need an explicit `ENLIGHTENMENT_ALLOW_ANONYMOUS` opt-in that cannot combine with a token.
  Reads, health, and diagnostics stay open so the posture is recoverable.
● **The body cap trusted the declared content-length.** A chunked request declares none, so
  the check was skipped and the body was buffered in full before any handler or dependency:
  one unauthenticated 256 MB POST took the worker from 52 MB to 821 MB resident and returned
  422. The cap now counts bytes actually received, in a pure ASGI middleware that drains up
  to the cap and never further, ahead of authentication.
● **Two workers destroyed the dataset.** The launch command ran `--workers 2` against a
  file-backed read-modify-write store that called itself the single writer. Two processes,
  80 writes each, every one acknowledged with a 201 and an audit line: 40 records present
  afterwards. The atomic rename is exactly why the loss left no torn file. Now one worker, an
  exclusive `fcntl.flock` across load, merge, and rename, and a monotonic revision with
  `If-Match` returning 409 instead of overwriting.

Also fixed: `seed()` escaped the boot guard, so a corrupt or root-owned snapshot made the
worker unstartable rather than unready; `PATCH` was missing from the cross-origin method list
while being a shipped route, making the anti-shrink merge unreachable from a browser; the
readiness paths performed an unbounded real write per request, so an unauthenticated flood
could exhaust volume IOPS and then trip the probe's own timeout into a restart loop, now
bounded by a five-second cache; the HEALTHCHECK interpolated `PORT` raw, so
`PORT=8080@evil.example` made it probe an attacker-controlled host and report HEALTHY; `apt`
and `dpkg` shipped in the runtime image; the rate-limit key table evicted a tracked caller on
overflow, resetting its count, and now refuses the new key instead; the diagnostics read-out
published the token's exact length and now reports a coarse band with a 24-character minimum
enforced at boot; a wildcard origin now refuses to start unconditionally rather than only
alongside a token; store input and output moved off the event loop; the image HEALTHCHECK
moved to `/livez`; the audit sanitiser now covers every reflected log value structurally; the
`pip-audit` network classifier is structural rather than a grep over log text.

Two of the binding CI image checks were themselves unsound and are corrected: the suid sweep
ran as the image's non-root user, where `find` cannot descend into an unreadable directory
and returns zero while bits still ship, and the package-manager check tested for pip alone.

**Why.** A gate FAIL is the cheapest place to learn any of this. Every one of these defects
would have surfaced as a live incident or an App Store pipeline failure instead.

**How verified.** Loop green: ruff format and check across 23 rule families, mypy strict over
12 modules, 217 tests collected (216 passed, 1 skipped) with branch coverage at 97.63% against
an 80% floor, Cobertura written to `coverage.xml`, `pip-audit` clean. Pipeline simulation green
against the actual artefact on the pinned interpreter with `GITLAB_CI=true`. Twenty-one mutants
killed across two rounds; one recorded as surviving (the constant-time compare, whose property
no functional test can assert). Two mutants were killed only after fixing a TEST that matched
explanatory prose rather than the instruction it described.

**Still not verified.** The container image build, for the same reason as V0.1: the registry
blob endpoint is denied by this environment's network policy. The CI `image` job is binding.

**Deliberately NOT done.** `/var/lib/dpkg` is kept. It is the package database, not a tool,
and it is what the platform's policy scan reads to enumerate OS packages. Deleting it would
remove the scanner's evidence rather than the risk, which is suppressing a finding. The tools
come out; the truth about what ships stays in. A test asserts it is still there.

## V0.1 (2026-08-18)

**What.** First commit. The gate-compliant Python server skeleton: the `create_app(...)`
factory, env-only validated configuration, constant-time shared-token authentication,
two-tier rate limiting, fail-closed CORS, split liveness and readiness paths with a
real-write storage probe behind a hard timeout, a secret-free diagnostics read-out, one
structured JSON audit line per privileged action, an atomic anti-shrink JSON store with
schema version and pre-write backups, hash-locked dependencies, a flattened hardened
Dockerfile pinned by digest, quality-gate scoping, and the verification loop, packaging,
and pipeline-simulation scripts.

**Why.** The Foundations baseline ships standards, not a starter application, and the App
Store contract is cheapest to satisfy at scaffold time. Retrofitting it costs one upload
cycle per pipeline stage, because the platform reveals its requirements one gate at a time.

**How verified.** `ruff format --check` and `ruff check` clean across 23 selected rule
families (`python3 -c "import tomllib,pathlib;print(len(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['tool']['ruff']['lint']['select']))"`);
`mypy` strict clean over 11 source files; 126 tests collected (125 passed, 1 skipped) with branch coverage at
97.60% against an 80% floor, Cobertura written to `coverage.xml`; `pip-audit` against the hash-locked
runtime requirements; the pipeline simulation green against the actual upload artefact in
the platform's environment (`GITLAB_CI=true`, its generated pipeline file present). Eight
mutants across the security controls were each confirmed to turn a named test red.

**Not verified here.** The container image build and the image policy posture. A Docker
daemon was started successfully, but the registry's blob endpoint is denied by the authoring
environment's network policy, so no base-image layer can be pulled and the Dockerfile is
neither proved nor disproved. `scripts/build-image.sh` distinguishes an unreachable registry
from a rejected Dockerfile and exits 3 with a "deferred to CI" banner rather than reporting a
pass; the CI `image` job is the binding check. One finding did come out of the attempt: the
`# syntax=docker/dockerfile:1` frontend directive was removed, because it makes the builder
fetch an external frontend image before reading any instruction, and the App Store runner sits
behind a registry mirror with no guaranteed public route. Every feature used is in BuildKit's
built-in frontend.

**Open with the project owner.** The training scenario vocabulary (`scenario` is an open,
length-capped string rather than an invented enumeration), the App Store category and
visibility, and the resource budget.
