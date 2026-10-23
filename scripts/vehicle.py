"""Dispatch bundled vehicle tools in an isolated Python process.

Tool arguments and authorization requirements are unchanged. No install or network
operation is performed by this dispatcher itself.
"""
from pathlib import Path
import subprocess
import sys

MODULE = Path(__file__).resolve().parents[1]/'domains/vehicle'
TOOLS = ('project','prepare_model','asset_manifest','locked_configurator','feature_guard',
         'fit_camera','reference_pack','loft_sections','surface_patch','section_curves',
         'silhouette_review','modeling_path','optimization_review','first_version_gate',
         'fidelity_loop','blender_pipeline','blender_stage','inspect_model',
         'prepare_model_blender','render_panorama','meshy','tripo','image_reconstruction')


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool',choices=TOOLS)
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    script=MODULE/'scripts'/(args.tool+'.py')
    if not script.is_file():parser.error('bundled vehicle tool missing: '+args.tool)
    forwarded=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    return subprocess.run([sys.executable,str(script),*forwarded]).returncode


if __name__=='__main__':raise SystemExit(main())
