# Designed development assets

These four small explicit scene specs exercise software behavior, not image reconstruction. Every material is designed, units are relative, and quality scope is `synthetic-software-test`. There are no source photos or image fidelity claims.

- `car-wheel.json`: independent tyre and hub, two rim assembly variants with separate rings and spokes, scoped material controls, wheel rotation. Rim replacement leaves tyre and hub present.
- `bicycle.json`: tube frame and handlebars, independent wheel assemblies, steering and wheel rotation.
- `motorcycle.json`: simplified box fairing, two torus wheels and steering. This is deliberately schematic.
- `toy.json`: fixed body, shoulder hinge moving the arm assembly and hand, head explode.

Run `python3 -m unittest discover -s tests -p test_asset_runtime.py -v` from the skill root. Node tests use the bundled Three.js runtime. The browser test uses locally available Chrome with a temporary profile and localhost server; it skips explicitly if Chrome is unavailable. No dependencies are downloaded.
