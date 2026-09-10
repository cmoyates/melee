# Showboat Falcon — development handoff

**Resume here in a new context.** Checkpoint: after the fifth recorded playtest
(2026-09-09 UTC), platform safeguard validation and Kirby analyzer labels.
Read this document, then `docs/showboat_ai.md` and the latest live review before
changing behavior. Verify the actual checkout/process state rather than treating
this snapshot as a permanent guarantee.

## Repository and current state

- User-owned public fork: **https://github.com/cmoyates/melee**.
- Active/default branch: **`mod/showboat-ai`**. The older
  `mod/single-player-cstick` branch and upstream history remain intact.
- Origin: `git@github.com:cmoyates/melee.git`; upstream: `doldecomp/melee`.
- Tracking issue: **https://github.com/cmoyates/melee/issues/1**.
- GitHub's displayed README is **`.github/README.md`**, not a root README.
- **Always specify `--repo cmoyates/melee` with `gh` issue/repository commands.**
  Unqualified `gh repo view` has resolved to the upstream fork parent.
- Latest implementation/review: **`638794a67`**, Kirby motion labels and fifth
  playtest review. Latest gameplay change: **`7f6ee7c6e`**, platform safeguard.
  Subsequent documentation commits do not imply a new gameplay binary.
- **Dolphin is closed.** No further launch is approved. Delayed background or
  subagent completion messages have already been incorporated; they are not
  instructions to relaunch or duplicate changes. No development job remains.

First checks:

```sh
git status --short
git log -5 --oneline
git remote -v
gh repo view cmoyates/melee --json nameWithOwner,url,defaultBranchRef
pgrep -ix 'Dolphin|dolphin-emu|dolphin-emu-qt2'
```

`pgrep` exit1 means no match; other errors must not be treated as clearance.
Its name-based check is point-in-time, not a process lock.

## Goal and non-negotiable constraints

Build a playable, capable, rules-legal Captain Falcon CPU with conspicuous but
safe showboating: technical execution and real opportunities take precedence
over ego. Retain native fallback and the original single-player C-stick mod.

- Gameplay assistance uses **ordinary controller inputs only**. Never modify
  fighter physics, damage, hitboxes, facing, position/velocity, motion states,
  animation lag, shield health or game input timers. No forced hits/recoveries.
- Keep native targeting, recovery, DI/SDI, techs and genuine punishes. Main
  eligibility is primary Falcon, mode4/level9, singles, with target/spawn identity
  checks and no live secondary/ally ambiguity. Other configurations remain native.
- Mod-owned sidecars and exact ownership matter. A native priority number alone
  does **not** establish free action, a fresh VM or permission to erase an attack.
  Preserve replacement scripts, cached attacks and unowned input channels.
- Recorder probes observe actual executed branches/output, never rerun mutating
  planners or RNG. The separate safety filter runs before the snapshot.
- Native floor queries may refresh pre-existing broad-phase cache/flags. Added
  static-map getters are read-only; this is not a fighter-physics or recorder write.
- **Fresh explicit tester readiness before every launch/restart.** Closing a
  match or granting development permission does not approve another launch.
- Never replace an active virtual-disc DOL. Building alone does not stage it.
  Quickstart leaves character/stage selection manual and does not reset choices
  after results/Back/cancel. Preserve the user's controller mapping/profile.
- No assets, original/rebuilt DOLs, disc images or raw captures in Git/releases.
  Keep local evidence and previous reports; create new reports rather than
  overwriting historical analysis.

## What is implemented

See `docs/showboat_ai.md` for exact eligibility, ownership and tuning constants.

- Six personality sidecars, ego/HUD, state-confirmed taunts, dancing/swagger,
  selective Punch and narrow huge-lead up-air preference. No guaranteed mercy.
- Independent controller-only combat: standing grab, airborne Knee/up-air
  interception, analog L-cancel overlay. No offensive short-hop chase planner.
- Legal wavedash sequence with observed jumpsquat/airdodge/landing acknowledgment,
  conservative current/coast geometry and native preemption.
- Fresh-native-defense selective hardshield. Only verified native fighter
  powershield contact earns PERFECT/ego; GuardReflect alone is not contact.
- Optional native save-load unlocks and boot-only normal Versus quickstart:
  P1 human/unselected, P2 Falcon9. External Captain CSS kind0 differs from
  internal FighterKind2.
- Stateless native throw-follow-up side-B filter, described below.
- Recorder v2, immutable launch provenance plus separate completion manifest,
  bounded offline analyzer and native common/Falcon/Kirby labels.

Gameplay sources: `src/melee/mod/showboat_{ai,combat,movement,defense,safety,
hud,recorder}.c/.h`. Six existing native hook files are `fighter.c`, `player.c`,
`ftcpuattack.c`, `ftCo_0A01.c`, `gmmain_lib.c`, `gmboot.c`; modules link through
`configure.py`/`tools/project.py`. Do not add retail split/symbol churn.

### Current side-B policy

After the actual native VM output, with no active custom tactic, consider only
fresh B-only/full-horizontal/neutral-Y output from grounded Wait/Walk, native
priority9/cache0, eligible normal Falcon and current target. Rival hitstun is
allowed; target-offstage position is not required.

Require the complete conservative whiff footprint on the **current certified
floor**:61 forward/11 backward raw model units times normal scale.97, plus6
world units reserve each side —65.17 forward/16.67 backward, strictly exceeded.
Ground startup's backward windup matters. On failure clear **only B and CPU X**;
retain native VM/cursors/cache/priority, release/wait55 and all later inputs.
No delayed B restoration, ego reward or forced motion changes.

- Main floors: Battlefield31 (`GrNBa.dat`) and FD32 (`GrNLa.dat`), with actual
  connected ledges and native extended-support seam equivalence.
- Battlefield platforms: left line2[-57.6,-20] at27.2; top line3[-18.8,18.8]
  at54.4; right line4[20,57.6] at27.2. Static map/joint/source/flags/support
  certificate; no bound transforms/callbacks/dynamic lines/adjacency.
- Every platform is37.6 wide versus required81.84, so **all otherwise eligible
  priority9 side-B pulses there are vetoed in either direction**. This deliberately
  forgoes potentially safe inward drops/lower-floor landings, which are not modeled.
- Priority2 moves, airborne/current specials and recovery are outside this
  policy. Unknown geometry yields to native; do not label it safe.
- Event128 means input rejection, not a hit, successful recovery or saved stock.

Details: `research/showboat_side_b_safety.md` (original checkpoint),
`research/showboat_platform_side_b_safety.md` (extension).

## Latest live evidence and what to do next

Read **`research/showboat_recorder_playtest_5.md`**. Capture:
`build/showboat/recordings/20260909T233801.009817Z-d81a4dff4f9c4760a39b3ac8be45e045/`.
Clean launch source7f6ee7c6e; exit0. **2,686 records accepted, zero rejected**:
1,671 samples,1,007 gates,4 begin/end pairs. All gate/end totals balance to7,324
updates/tactic. Battlefield/Time, Falcon2/Kirby4. Coverage is still sparse/qualified.

Three real vetoes:

| Frame | Episode and observed continuation |
|---:|---|
| 94 | Main-floor left veto atx−17.52. Wait→jump/up-B→top-platform landing234, Wait263, unchanged self0%. No rival damage during tail. |
| 4323 | **Left-platform right/inward veto**, x−38.63,y27.2. Jump4379/up-B4400→landing4484; Stone-consistent **+18% during landing lag4501**. |
| 5058 | Main-floor left veto atx−60.56. Up-B→actual SpecialHiCatch/rivalCaptureCaptain5147→throw→platform landing5230, unchanged self102.5%. |

Each jump pulse occurs56 frames after veto. The platform admission works in
this one inward case; it does not prove outward death prevention or every
platform/direction. Retained tails are **not uniformly useful or useless**.

The actual self-death is a different mistake: late native dash-grab6551,
CatchDash6552, then DamageFlyLw6557 (110.5→137.5%) opposite **Kirby433,
`ftKb_MS_CaSpecialN`**, copied Falcon Punch; DeadUpStar6601, Rebirth6776.
This is strong contact-consistent evidence, not explicit hit-source/KO credit.
No sampled eligible priority9 bypass/platform-origin unvetoed ground side-B
appears. Several out-of-scope priority2 side-Bs fail the conservative envelope
but return grounded, so do not blindly broaden the priority whitelist.

One custom grab acknowledgment5010 is followed by actual capture5016/native
downthrow5018. Nine L-cancel samples, not nine proven lag reductions. No custom
wavedash/aerial/PS/Punch/dance/taunt starts. Defense records7,219 native-priority
rejections,101 grouped-input/state rejections,2 target,2 unevaluated — **not** a
missed-block rate. No defense geometry/start bin was reached.

### Recommended next development, not already implemented

1. **Context-sensitive continuation after a veto.** One up-B tail is useful;
   another exposes landing lag. Research actual script identity/ownership and
   target context before cancelling/replacing any tail. No blind native-VM reset
   or universal up-B suppression; recordings omit VM cursors/buffers.
2. **Pre-commitment slow-special awareness.** At6532 Falcon is in Wait about
   32.23 units from Kirby's Punch at animation29; by CatchDash he cannot freely
   cancel. Local `PlKb.dat` script timer52 gives conventional frame53 onset,
   not43. Current defense requires fresh7, Wait/Walk, ordinary common normals
   and initialized hitboxes — widening a motion whitelist alone cannot fix it.
   Research reaction, facing/range/closing speed, safe spacing/ordinary shield,
   and fresh-neutral/before-builder ownership. A ten-update shield started too
   early can expire before the hit. Do not turn every episode into a powershield.
3. **Bounded first-failure diagnostics** for compound personality/defense gates,
   if needed before policy changes. Probe actual branches; preserve short-circuit
   evaluation and RNG count; avoid mutating planner reruns and log floods.
4. Further strength/overhead/controlled technique benchmarks remain unperformed.
   Quiet personality and jab dependence warrant investigation, not random tuning.

The last review intentionally changed **only offline labels/tests/docs**, not
this working gameplay binary. A new context should not assume those next steps
were implemented or that another emulator launch is already approved.

## Telemetry trust rules

- **Every v1 sample-derived metric remains quarantined**, even plausible rows.
  Do not salvage shifted fields or filter bad rows and trust the rest. Preserve
  legacy reports/raw evidence. Valid integer gate accounting has separate caveats.
- V2 float fields are exact eight-digit binary32 hex words, with required
  `float_encoding`. Snapshot serialization is bounded and string-only
  `OSReport("%s", buffer)`; do not reintroduce mixed numeric varargs.
- A queued input ≠ acknowledged motion ≠ actual contact ≠ useful outcome.
  Recording segments, death states, metadata and Time stocks do not establish
  winner, official SD/KO credit or hit counts.
- Gate counts are updates, not unique frames or actionable opportunities.
  Sample durations and percent deltas require continuity; airborne ≠ offstage.
- Native Kirby labels341–543 are kind4-only;433 is copied Punch. The latest
  `named-report.*` removes520 name warnings while leaving integrity/scan totals
  unchanged. Recovery-name context is still a heuristic, not offstage proof.

For the latest capture, `report.*` is the original analysis; `named-report.*`
is the separately preserved labeled analysis; `reviewed-summary.json` is the
bounded manual summary. Raw runtime SHA-256:
`16adadec74e88c188fa41cabc120193ae289d559397d097929e21fea30951c75`.

## Local build, run and verification

The existing local checkout has `.venv`, Ninja, pinned MWCC/tools and
`build/tools/wibo-1.0.3`. Preserve stock generated includes under
`build/GALE01/include`. A fresh clone requires original US1.02 data and the
stock/toolchain setup documented in `.github/README.md` and
`docs/single-player-cstick.md`; the helper is not a bootstrap installer.

```sh
sh tools/build_showboat.sh
.venv/bin/python tools/verify_showboat.py
.venv/bin/python -m unittest discover -s tools/tests -p 'test_showboat*.py' -v
```

Helper defaults enable AI/HUD/debug, recorder, unlocks and quickstart; raw
configure defaults off. Opt-outs include `--no-showboat-recorder`,
`--no-showboat-quickstart`, `--no-showboat-unlock-all`, with corresponding
verifier `--no-recorder`, `--no-quickstart`, `--no-unlocks`. Match configuration
when verifying; restore enabled defaults before testing that build.

**Only after readiness and confirming no running Dolphin:**

```sh
sh tools/run_showboat.sh '/path/to/your/original-melee-us-v1.02.ciso'
```

Use the user's existing local disc path; do not download assets. Launcher uses
`build/showboat/disc/sys/main.dol`, original virtual-disc assets/apploader and
`build/showboat/dolphin-user`. Bare standalone-DOL loading previously failed
DVD reads. Do not load stock savestates. Use a background terminal for the
noninteractive launcher; record the new archive/process identity and verify
`launch.json`/staged hash. On requested shutdown, inspect the current process
identity, TERM Dolphin, confirm completion metadata and preserve raw output.

```sh
.venv/bin/python tools/analyze_showboat.py 'build/showboat/recordings/<capture>' \
  --json 'build/showboat/recordings/<capture>/new-report.json' \
  --markdown 'build/showboat/recordings/<capture>/new-report.md'
```

### Verified identities and tests

- Build **and staged** DOL:4,522,912 bytes,
  SHA-1 **`7384b2f1dadc18b996e324a4c3add40221963290`**.
- Safety object: `616447ffefa3b6c3b8ed820641cf44310c5b9d74`, identical recorder off/on.
- Recorder-off DOL:4,503,264 bytes, `246c8bf41cb1191126c5104747253711d48dda7c`;
  enabled build restored before the latest capture.
- Stock DOL: `08e0bf20134dfcb260699671004527b2d6bb1a45`, unchanged.
- Controller: **`SDL/0/Nintendo Switch Pro Controller`**, port1;
  isolated `Config/GCPadNew.ini` SHA-1 **`00dc2b7a5339493fe11fcf93e3adba16e93e0451`**.
- Profile/save backup: `build/showboat/profile-backups/20260909-053023-pre-unlocks/`
  and `build/showboat/unlock-profile-backup.json`. Normal Dolphin saves were not
  changed; isolated unlock progression persists unless restored/reset deliberately.
- **461 tests pass**:242 retained/main,43 safety,56 recorder,101 analyzer,
  16 capture,3 config/verifier. Includes12,122 full-Fighter safety guards and
  130 main cases×four recorder/debug combinations. Native verifier passes.
- Platform implementation also passed28 native warning configurations and six
  disabled-hook/C-stick object comparisons. Only safety.o changed from the
  preceding main-floor binary; the latest label/review change alters no C objects.
- Logs: `build/showboat-playtest-5-{tests,verify}.log`,
  `build/showboat-platform-{tests,checks,final-build,final-verify,off-build,off-verify}.log`.
  Baseline binaries/object hashes: `build/showboat/platform-safety-baseline/`.

## Key history / further reading

| Commit | Checkpoint |
|---|---|
| `638794a67` | Latest live review; bounded Kirby labels,461 tests |
| `7f6ee7c6e` | Static-platform side-B extension,452 tests |
| `67c7d1e54` | Main-floor veto live review; platform departure identified |
| `b52670cc5` | Original output-only native side-B safeguard,442 tests |
| `55dfa532d` | First valid v2 live review; unsafe native side-B identified |
| `ee3c8bab7` | Recorder v2 serialization repair; v1 quarantine |
| `435836d5e` | Original recorder/capture/analyzer pipeline (v1 snapshots untrusted) |
| `ad404a694` | Stronger ego and selective precision shield |

Other design references: `research/showboat_v2.md`, `showboat_wavedash.md`,
`showboat_ego_v3.md`, `showboat_recorder_repair.md`, and playtest reviews1–5.
All these filenames are under `research/`. Latest detailed issue update:
https://github.com/cmoyates/melee/issues/1#issuecomment-5610436041.

Keep the README, main guide, research, handoff and issue current after the next
verified checkpoint. Commit/push source/docs/tests only; never force-add ignored
build outputs or captures. Do not represent static/host checks as live success.
