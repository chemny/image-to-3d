# Installation and first-use verification

Core-first setup: load the Skill in the intended Agent, run read-only diagnosis, prepare only missing core requirements with user authorization, then run a synthetic first-use check. Optional automation and Blender remain independent capabilities. See the [Chinese command guide](installation.zh.md) for both platforms and troubleshooting.

| Layer | Dependencies | Requirement |
|---|---|---|
| Core generation/check/export | Python 3.10+, Pillow >=9, NumPy >=1.24, complete Skill package | Required |
| Manual viewing | Browser supporting the page's WebGL/decompression APIs; local HTTP service | Required to verify visuals/interactions manually |
| Automated browser capture | Node.js >=18, existing Playwright JS module, compatible Chromium/Chrome/Edge | Optional; absent tools do not block core use |
| Blender import verification | Existing Blender executable | Optional; GLB export itself does not require Blender |
| Host features | Agent Skill loading and image understanding; image generation when selected | Supplied by the host, not verified by this CLI |

Vehicle tools/templates are bundled. Do not install the retired vehicle-configurator Skill or automatically copy this Skill into other Agent directories. No optional application belongs in requirements.txt.

## One entry point: diagnose, confirm, prepare, verify

After placing the complete Skill in the intended Agent directory, run the launcher. It prepares runtime dependencies; it does not copy the Skill across Agents or prove host discovery.

```sh
# macOS; install.command can also be double-clicked
bash ./install.command
bash ./install.command --check-only
```

```powershell
# Windows: double-click or invoke from an existing terminal
.\install.cmd
.\install.cmd --check-only
```

The launcher locates Python 3.10+, then reuses environment.py doctor and first-use. If core requirements already pass, installation is skipped. Otherwise, it displays the exact environment, packages and commands before requiring approval. Noninteractive core setup does not approve installation. --check-only never creates environments, installs or generates samples.

If Python is absent, macOS offers an existing Homebrew's `brew install python@3.13`; Windows offers an existing winget's `winget install --id Python.Python.3.13 --exact --source winget --scope user`. Approval is required before either runs. Package managers themselves are never installed. Installer/license prompts remain for the user; Windows installer defaults may affect the user Python registration/launcher/PATH. No automatic agreement flags, elevation or PowerShell execution-policy changes are used. Without the manager, report the missing prerequisite and direct the user to python.org, then rerun; this is a guided fallback, not guaranteed zero-interaction setup on an empty machine.

Core library installation uses an owned isolated venv outside the Skill, binary wheels and an explicit PyPI index, without upgrading pip or using global pip. A new venv needs both Pillow and NumPy even if one exists in system Python; an existing managed venv only repairs missing/outdated core libraries. Unknown/linked environments are not overwritten. Failed partial files and receipts are retained; no automatic cleanup, source compilation, alternate mirror or endless retry.

Default data directories: macOS `~/.local/share/image-to-3d`, Windows `%LOCALAPPDATA%\image-to-3d` (or the user's AppData/Local fallback). Use `--data-dir "NEW_OR_MANAGED_DIRECTORY"` to choose another location. `IMAGE_TO_3D_PYTHON` accepts a full executable path, not a shell command. The console prints the interpreter and fresh first-use/setup report paths; use that interpreter for later work. No environment activation is required.

Exit 0 means the requested check/smoke passed; 1 means core failure, declined core library install or unavailable explicitly requested optional capability; 2 covers missing/cancelled Python bootstrap or argument errors. Missing wheels, permissions, network, venv or pip stop with a failure. Data generation is synthetic and does not certify visual fidelity.

Pass existing optional tool paths via --capability automation or --capability blender as shown below; neither optional tool is installed by this launcher. The Windows arguments are the same, with quoted paths.

**Evidence:** macOS launcher, read-only mode and real core first-use were run. Approval/refusal/installation failure paths have simulated regressions, not a clean-machine online install. Windows Python-side path/argument tests and CMD source review are not Windows execution: the CMD launcher, winget bootstrap and Windows first-use remain untested on a real machine. Homebrew bootstrap was not actually triggered either. Do not automatically remove macOS quarantine attributes or bypass OS security prompts.

Bootstrap identifiers: [Homebrew formula](https://formulae.brew.sh/formula/python%403.13), [Microsoft winget manifests](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/13).


## Read-only diagnosis

Run from the installed Skill directory:

```sh
# macOS, with an already available Python
python3 -X utf8 scripts/environment.py doctor
```

```powershell
# Windows PowerShell; use the actual Python executable if py is unavailable
py -3 -X utf8 scripts/environment.py doctor
```

The doctor prints JSON, returns 0/1, and writes no report. It checks the current interpreter, actual core-library imports/versions, package files and bundled template hashes. PATH and platform application paths are detection hints, not proof an application launches. macOS app bundles and Windows Program Files/LocalAppData paths are supported; custom locations can be supplied explicitly. It does not install, modify PATH/registry, scan other users' caches, or launch a GUI. If Python itself is unavailable, report that and agree on preparation before proceeding.

## Prepare missing core libraries only

Do not run installation commands until authorized. Prefer an isolated environment outside the Skill; activation and global configuration changes are unnecessary.

```sh
# macOS
skill_dir="/path/to/image-to-3d"
env_dir="/path/to/image-to-3d-env"
python3 -m venv "$env_dir"
"$env_dir/bin/python" -m pip install -r "$skill_dir/requirements.txt"
"$env_dir/bin/python" -X utf8 "$skill_dir/scripts/environment.py" doctor
```

```powershell
# Windows PowerShell
$Skill = "C:\path\to\image-to-3d"
$Venv = "C:\path\to\image-to-3d-env"
py -3 -m venv "$Venv"
& "$Venv\Scripts\python.exe" -m pip install -r "$Skill\requirements.txt"
& "$Venv\Scripts\python.exe" -X utf8 "$Skill\scripts\environment.py" doctor
```

Reuse an existing interpreter when it already passes. Stop on missing pip, download, wheel or permission failures; do not elevate, rewrite global settings, select untrusted package sources or retry indefinitely. Core CLI examples enable UTF-8 for Windows locale portability.

## First-use check without optional tools

```sh
"$env_dir/bin/python" -X utf8 "$skill_dir/scripts/environment.py" first-use --out "/path/to/first-use-new"
```

```powershell
& "$Venv\Scripts\python.exe" -X utf8 "$Skill\scripts\environment.py" first-use --out "C:\path\to\first-use-new"
```

The output directory must be new and outside the Skill. The check generates only synthetic data: a PNG, editable Three.js preview, losslessly transported scene, sample.glb and first-use-report.json. It verifies image roundtrip, actual geometry generation, scene roundtrip and GLB header integrity. It neither processes user models nor certifies fidelity, production approval or host Skill discovery. Failed partial output remains for diagnosis; it is never overwritten automatically.

For manual viewing, start the returned HTTP command, choose a free port, then inspect the visible sample, part/color controls, views/actions and loading errors:

```sh
"$env_dir/bin/python" -m http.server 8000 --bind 127.0.0.1 --directory "/path/to/first-use-new/preview"
```

```powershell
& "$Venv\Scripts\python.exe" -m http.server 8000 --bind 127.0.0.1 --directory "C:\path\to\first-use-new\preview"
```

Open http://127.0.0.1:8000/ rather than file://. Do not terminate existing servers to free a port. Manual or equivalent host-browser evidence is distinct from passing the Playwright capture command.

## Optional automation

Supply existing installations; paths are passed as argument lists, including spaces and Unicode. --playwright-module accepts an index.mjs/index.js file or its package directory.

```sh
python3 -X utf8 scripts/environment.py doctor --capability automation --node "/path/to/node" --playwright-module "/path/to/playwright" --browser "/path/to/chrome"
python3 -X utf8 scripts/environment.py first-use --capability automation --node "/path/to/node" --playwright-module "/path/to/playwright" --browser "/path/to/chrome" --out "/path/to/automation-first-use-new"
```

On Windows use `py -3 -X utf8` or the venv executable with the same options. Diagnosis checks Node version, module import and executable existence without launching a browser. First-use actually runs capture.mjs against the synthetic local page, checks WebGL and saves captures. Missing optional requirements fail only the explicitly requested capability; core_ready remains independent.

When installation is explicitly requested, `npm install --prefix TOOL_DIR playwright` keeps the package separate. Download Playwright's Chromium only if needed using the existing Node executable and `TOOL_DIR/node_modules/playwright/cli.js install chromium`; an existing compatible Chrome/Edge may avoid that download. No implicit npx download, global install or Node/npm setup is performed.

## Optional Blender

```sh
python3 -X utf8 scripts/environment.py doctor --capability blender --blender "/path/to/blender"
python3 -X utf8 scripts/environment.py first-use --capability blender --blender "/path/to/blender" --out "/path/to/blender-first-use-new"
```

Diagnosis runs --version only. Explicit first-use launches background Blender, imports the synthetic GLB using the existing exchange checker and verifies its manifest. It never opens/saves a user project. Blender is not a pip dependency. Request installation separately if missing. Multiple --capability options can be combined.

## Honest readiness reporting

Report Agent loading, core diagnosis, core smoke, manual viewing, browser automation and Blender import separately. A skipped capability or a version/path check is not an actual-use pass. macOS execution evidence and Windows simulated discovery/argument tests are different evidence levels. Until real Windows testing is available, state that Windows detection is implemented but actual OS use remains unverified. These commands do not install/register a Skill, create automation or publish anything.
