#!/usr/bin/env python3
"""Densify explicit +X sections using bounded monotone cubic interpolation.
No image inference or existing-asset UV/topology preservation. Standard library.
"""
import argparse,copy,json,math
from pathlib import Path
from loft_sections import geometry

def slopes(x,y):
    h=[b-a for a,b in zip(x,x[1:])];d=[(b-a)/s for a,b,s in zip(y,y[1:],h)]
    if len(x)==2:return [d[0],d[0]]
    m=[0.]*len(x)
    for i in range(1,len(x)-1):
        if d[i-1]*d[i]>0:
            w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1];m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i])
    def endpoint(h0,h1,d0,d1):
        v=((2*h0+h1)*d0-h0*d1)/(h0+h1)
        if v*d0<=0:return 0.
        if d0*d1<0 and abs(v)>3*abs(d0):return 3*d0
        return v
    m[0]=endpoint(h[0],h[1],d[0],d[1]);m[-1]=endpoint(h[-1],h[-2],d[-1],d[-2]);return m

def densify(plan,max_step):
    geometry(plan) # Reuse finite/ordered/common-topology/winding validation.
    if type(max_step) not in (int,float) or not math.isfinite(max_step) or max_step<=0:raise ValueError('Finite positive station step required')
    raw=plan['sections'];x=[s['station'] for s in raw];counts=[math.ceil((b-a)/max_step) for a,b in zip(x,x[1:])]
    if sum(counts)+1>10000:raise ValueError('More than 10000 sections; choose explicit coarser step')
    columns=[[s['profile'][j][k] for s in raw] for j in range(len(raw[0]['profile'])) for k in range(2)];derivatives=[slopes(x,y) for y in columns];out=[]
    for i,count in enumerate(counts):
        out.append(copy.deepcopy(raw[i]));h=x[i+1]-x[i]
        for n in range(1,count):
            t=n/count;a=2*t**3-3*t*t+1;b=t**3-2*t*t+t;c=-2*t**3+3*t*t;d=t**3-t*t
            p=[a*y[i]+b*h*m[i]+c*y[i+1]+d*h*m[i+1] for y,m in zip(columns,derivatives)]
            out.append({'station':x[i]+h*t,'profile':[p[j:j+2] for j in range(0,len(p),2)]})
    out.append(copy.deepcopy(raw[-1]));result={**copy.deepcopy(plan),'sections':out,'section_sampling':{'method':'bounded_monotone_cubic','max_station_step':max_step,'control_sections':len(raw)}};geometry(result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--max-step',type=float,required=True);a=p.parse_args()
    try:
        result=densify(json.loads(a.input.read_text()),a.max_step)
        with a.out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        print(json.dumps({'sections':len(result['sections']),'out':str(a.out)}))
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
