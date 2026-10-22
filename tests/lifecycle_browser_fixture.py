"""Explicit real-browser lifecycle fixture, entirely in a TemporaryDirectory.
Run with configured --node, --playwright, --browser and a new --out result file.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import version_lifecycle as v


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['node', 'playwright', 'browser', 'out']:parser.add_argument('--'+name, required=True)
    args = parser.parse_args();output = Path(args.out)
    if output.exists():raise ValueError('output must be new')
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):pass
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);(root/'trial').mkdir();(root/'active').mkdir()
        (root/'trial/model.bin').write_bytes(b'fixture-mesh')
        original=b'<html><body>original<script>fetch("model.bin").then(r=>r.arrayBuffer()).then(()=>window.modelLoaded=true)</script></body></html>'
        (root/'trial/index.html').write_bytes(original)
        (root/'cases.js').write_text("current='active/'")
        (root/'decision.json').write_text('{"decision":"reject"}')
        ledger={'version':1,'coverage_complete':True,'scan_files':['cases.js'],
                'protected_paths':['active'],
                'units':[{'id':'trial','path':'trial/model.bin','status':'retired','reason':'test rejected sample',
                          'dependencies':[], 'retirement_evidence':{'path':'decision.json','sha256':v.digest((root/'decision.json').read_bytes())}}],
                'retirements':[{'path':'trial/index.html','kind':'html','unit_ids':['trial'],'current_url':'/active/'}]}
        (root/'ledger.json').write_text(json.dumps(ledger));plan=v.plan(root,root/'ledger.json');v.write_new(root/'plan.json',plan)
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=temp))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        checks=[]
        def browser(mode):
            result=subprocess.run([args.node,str(Path(__file__).with_name('lifecycle_browser_check.mjs')),args.playwright,args.browser,
                                   'http://127.0.0.1:'+str(server.server_port)+'/trial/',mode],capture_output=True,text=True,timeout=45)
            if result.returncode:raise ValueError(result.stderr)
            checks.append(json.loads(result.stdout))
        try:
            browser('before')
            q=v.quarantine(root,root/'plan.json',plan['plan_sha256']);browser('retired')
            v.restore(root,q['transaction']);assert (root/'trial/index.html').read_bytes()==original
            browser('restored')
        finally:
            server.shutdown();server.server_close();thread.join()
    v.write_new(output,{'passed':True,'temporary_fixture_only':True,'checks':checks,
                        'limits':'Browser proves HTML retirement suppresses payload load and restoration reinstates it; not current production case validation.'})
    print('Lifecycle browser fixture: before, retired, restored all passed')


if __name__=='__main__':main()
