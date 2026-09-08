# Single-player C-stick controls mod

Working branch: `mod/single-player-cstick`.

This repository contains source and build/packaging helpers only. Supply the
original `orig/GALE01/sys/main.dol` and disc image from your own US v1.02 copy.
Do not commit or upload original or rebuilt game files. See the
[upstream setup instructions](../.github/README.md#building) for extraction.

## Play

In Dolphin, use **File → Open** and select:

```text
build/cstick/Melee-Single-Player-C-Stick.iso
```

Start a **fresh game/match**, not a savestate from the original executable.
The disc retains GALE01/revision 2, so it uses the same normal save files and
Dolphin game settings. Do not use this modified image for stock netplay or
competitive verification. The source disc image is unchanged.

## Behavior

- Controller C-stick input is enabled in single-player using the existing
  Versus input/action handling: grounded smashes, directional aerials, and the
  existing contextual C-stick actions.
- The retail gameplay camera's manual zoom multiplier is held at its normal
  value of 1, and its manual-zoom timer is cleared. Automatic tracking, framing,
  stage behavior, and camera shake remain intact.
- CPU-generated C-stick input and debug-level controls are unchanged.
- Pause/debug camera handling is not replaced with a fixed camera.
- The shared single-player-mode predicate remains unchanged, protecting match
  rules, results, pause behavior, and progression.

Source changes are confined to:

- `src/melee/ft/fighter.c`: remove the single-player restriction only from the
  controller-input C-stick branch.
- `src/melee/cm/camera.c`: reset manual zoom at retail debug levels, before the
  existing single-player zoom code.

## Build

The helper assumes a completed stock build and a local macOS toolchain:
`.venv`, WiBo 1.0.3 at `build/tools/wibo-1.0.3`, and the upstream build tools
under `build/`. Configure the stock build with
`python configure.py --wrapper build/tools/wibo-1.0.3` on the upstream `master`
branch and run `ninja` before switching back to this mod branch. On other
platforms, adapt the helper's wrapper/tool paths to your environment.

Run from the repository root:

```sh
sh tools/build_cstick.sh
```

Output: `build/cstick/GALE01/main.dol`.

The helper retains the stock code-generation flags, including `MUST_MATCH`,
to avoid unrelated alternate code paths. It builds the explicit DOL target,
not the stock SHA-1 verification/progress targets: a modified executable must
not be claimed to match the original hash. It also disables automatic symbol
application. Use this helper on the mod branch rather than plain `ninja`.

The root `build.ninja`, `objdiff.json`, and `compile_commands.json` now refer to
the separate mod build. The previously verified `build/GALE01/main.dol` and
`orig/GALE01/sys/main.dol` remain untouched. Existing stock generated includes
under `build/GALE01/include` are used by upstream compiler flags; do not delete
that directory before building the mod.

## Package a rebuilt executable

Stop this image in Dolphin before replacing it. Convert the original CISO into
our generated ISO copy (this replaces only the generated image in `build/cstick`):

```sh
build/tools/dtk disc convert \
  '/path/to/your/original-melee-us-v1.02.ciso' \
  build/cstick/Melee-Single-Player-C-Stick.iso
.venv/bin/python tools/package_cstick.py
```

The packaging helper checks the complete stock disc SHA-1 and embedded original
DOL, validates rebuilt DOL sections and entry point, and refuses an executable
that would overlap the filesystem table. It only writes the rebuilt DOL into
this generated image. It refuses to repatch an already-modified image: rerun the
conversion first. It does not patch the user's source disc.

## Verification completed

- Full source build succeeded; subsequent incremental build reported no work.
- All 1130 compiled source objects were compared to the preserved matching
  build: only `melee/cm/camera.o` and `melee/ft/fighter.o` differ.
- Disassembly confirmed the controller branch's mode gate was removed while
  the CPU branch retains its mode gate, and the camera resets manual zoom.
- Rebuilt DOL is 4,425,184 bytes, fitting within its original disc allocation.
- Embedded DOL bytes match the rebuilt file exactly.
- Hashing the modded disc with the original DOL substituted back reproduces the
  known stock disc SHA-1, proving all other disc bytes are unchanged.
- Original input and matching-build DOL hashes still match stock.
- Shell/Python helpers passed syntax checks; `git diff --check` passed.

Hashes:

```text
Original DOL: 08e0bf20134dfcb260699671004527b2d6bb1a45
Modded DOL:   9bf1a264df76b541a12dab71656523e441a40c5a
Stock ISO:    d4e70c064cc714ba8400a849cf299dbd1aa326fc
```

Machine-readable verification: `build/cstick/verification.json`.

The image was sent to Dolphin to open. Gameplay has **not** been independently
verified yet. Test Classic/Adventure/Training with grounded and aerial inputs,
then confirm Versus and ordinary camera tracking still behave normally.
