"""Leg-by-leg race analysis from Vakaros VKX logs.

Wind is taken from the event's measured per-leg figures, so VMG here is
wind-referenced rather than a straight-line proxy.
"""
import os, sys, math, glob, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vkx

R = math.pi/180
# measured winds, ib-sailing race reports (deg true, direction wind is FROM)
WIND = {1:{'mean':317,'legs':[317,323,313,317]}, 2:{'mean':314,'legs':[314,321,313,313]}}
# boat name <- filename, for the 8 Sep fleet
NAME = {
 'vakaros 8-9-2026':'Team Sweden','Bábá 08-09-2026':'Ba ba','Dime Piece 9-8-2026':'Dime Piece',
 'Florida 65 9-8-2026':'Florida 65','GTG New 2026 9-8-2026':'GTG New 2026',
 'J70 Let it be  8-9-2026':'J70 Let it be','Lady in red 2 9-8-2026':'Lady in red 2',
 'Mag 9-8-2026':'Mag','Patakin_3 8-9-2026':'Patakin 3','Phantom7 8.9.2026':'Phantom7',
 'Yupi 8-9-2026':'Yupi','joust70 08-09-2026':'joust70','noticia 9-8-2026':'noticia',
 'MLC USA 26 primary 9-8-2026':'MidlifeCrisis',
}

def load(day='2026-09-08'):
    out={}
    for f in glob.glob(os.path.expanduser('~/Downloads/*.vkx')):
        b=os.path.basename(f)[:-4]
        if '(1)' in b or '(2)' in b or b not in NAME: continue
        fx=[x for x in vkx.track(f)]
        if not fx or fx[0]['t'].strftime('%Y-%m-%d')!=day: continue
        out[NAME[b]]=fx
    return out

def along(fx, twd, lat0, lon0):
    """Progress toward the wind, in metres. Increasing = going upwind."""
    c=math.cos(lat0*R)
    n=(fx['lat']-lat0)*60*1852
    e=(fx['lon']-lon0)*60*1852*c
    return n*math.cos(twd*R)+e*math.sin(twd*R)

def smooth(v,k=31):
    out=[];h=k//2
    for i in range(len(v)):
        a=max(0,i-h); b=min(len(v),i+h+1)
        out.append(sum(v[a:b])/(b-a))
    return out

def legs_for(fx, twd, t0, t1):
    """Split a windward/leeward race into four legs at the mark roundings.

    On a W/L course the along-wind coordinate rises to the windward mark, falls
    to the leeward gate, rises again and falls again — so the roundings are
    successive global extrema of that coordinate, which is far more robust than
    hunting for local turning points in a track full of tacks.
    """
    seg=[x for x in fx if t0<=x['t']<=t1]
    if len(seg)<400: return None,None
    lat0,lon0=seg[0]['lat'],seg[0]['lon']
    u=smooth([along(x,twd,lat0,lon0) for x in seg],61)
    n=len(u)
    w1=max(range(int(n*0.25),int(n*0.55)), key=lambda i:u[i])          # windward 1
    l1=min(range(w1+120,int(n*0.78)),     key=lambda i:u[i])           # leeward 1
    w2=max(range(l1+120,int(n*0.97)),     key=lambda i:u[i])           # windward 2
    l2=n-1                                                            # finish
    bounds=[0,w1,l1,w2,l2]
    if not all(bounds[i]<bounds[i+1] for i in range(4)): return None,None
    return seg,bounds

def manoeuvres(seg, twd):
    """Tacks and gybes from a settled crossing of the wind axis, with speed cost.

    The raw heading oscillates constantly, especially surfing downwind, so the
    off-wind angle is smoothed and a crossing only counts once the boat has
    settled past 20 deg on the new side.
    """
    rel=smooth([((x['cog_deg']-twd+180)%360)-180 for x in seg], 31)
    res={'tack':[], 'gybe':[]}
    side=1 if rel[0]>0 else -1
    for i in range(1,len(rel)):
        s2=1 if rel[i]>0 else -1
        if s2!=side and abs(rel[i])>20:
            a0=max(0,i-120); b0=min(len(rel),i+120)
            pos=sum(abs(r) for r in rel[a0:b0])/(b0-a0)   # mean angle off the wind
            kind='tack' if pos<90 else 'gybe'
            a=max(0,i-40); b=min(len(seg),i+40)
            entry=max(y['sog_kn'] for y in seg[a:i]) if i>a else 0
            low=min(y['sog_kn'] for y in seg[a:b])
            exit_=max(y['sog_kn'] for y in seg[i:b]) if b>i else 0
            if entry>2.5:
                res[kind].append({'i':i,'loss':round(entry-low,2),
                                  'entry':round(entry,2),'exit':round(exit_,2),
                                  'at':seg[i]['t'].strftime('%H:%M:%S')})
            side=s2
    return res

def analyse(day, race_no, t0, t1):
    twd=WIND[race_no]['mean']; legw=WIND[race_no]['legs']
    boats=load(day); rows=[]
    for name,fx in boats.items():
        seg,bounds=legs_for(fx,twd,t0,t1)
        if seg is None: continue
        lat0,lon0=seg[0]['lat'],seg[0]['lon']
        man=manoeuvres(seg,twd)
        legs=[]
        for k in range(min(4,len(bounds)-1)):
            a,b=bounds[k],bounds[k+1]
            part=seg[a:b]
            if len(part)<40: continue
            w=legw[k] if k<len(legw) else twd
            up = k%2==0
            sp=[x['sog_kn'] for x in part]
            # wind-referenced VMG: speed component along the wind axis
            comp=[x['sog_kn']*math.cos(((x['cog_deg']-w+180)%360-180)*R) for x in part]
            vmg=[c if up else -c for c in comp]   # both positive when making good progress
            dt=(part[-1]['t']-part[0]['t']).total_seconds()/60
            mn=[m for m in man['tack' if up else 'gybe'] if a<=m['i']<b]
            # best / worst rolling 60 s of VMG
            win=120  # 60 s at 2 Hz
            best=worst=None
            if len(vmg)>win:
                means=[sum(vmg[i:i+win])/win for i in range(0,len(vmg)-win,20)]
                bi=max(range(len(means)),key=lambda i:means[i]); wi=min(range(len(means)),key=lambda i:means[i])
                best={'vmg':round(means[bi],2),'at':part[bi*20]['t'].strftime('%H:%M:%S')}
                worst={'vmg':round(means[wi],2),'at':part[wi*20]['t'].strftime('%H:%M:%S')}
            legs.append({'leg':k+1,'type':'upwind' if up else 'downwind','wind':w,
                'min':round(dt,2),'avg_sog':round(sum(sp)/len(sp),2),'max_sog':round(max(sp),2),
                'avg_vmg':round(sum(vmg)/len(vmg),2),
                'n':len(mn),'loss':round(sum(m['loss'] for m in mn)/len(mn),2) if mn else 0,
                'best':best,'worst':worst,
                'end_t':part[-1]['t'].strftime('%H:%M:%S'),
                'end_u':round(along(part[-1],twd,lat0,lon0))})
        rows.append({'boat':name,'legs':legs,
                     'tacks':len(man['tack']),'gybes':len(man['gybe'])})
    # places at each leg boundary: rank by elapsed time to that rounding
    for k in range(4):
        elig=[r for r in rows if len(r['legs'])>k]
        elig.sort(key=lambda r:r['legs'][k]['end_t'])
        for pos,r in enumerate(elig,1): r['legs'][k]['place']=pos
    for r in rows:
        for k,l in enumerate(r['legs']):
            l['gained']= (r['legs'][k-1]['place']-l['place']) if k>0 else None
    return rows

if __name__=='__main__':
    out={}
    for n,(a,b) in {1:('12:34:52','13:51:30'), 2:('14:24:52','15:41:30')}.items():
        d=datetime.date(2026,9,8); U=datetime.timezone.utc
        t0=datetime.datetime.combine(d,datetime.time(*map(int,a.split(':'))),U)
        t1=datetime.datetime.combine(d,datetime.time(*map(int,b.split(':'))),U)
        out[n]=analyse('2026-09-08',n,t0,t1)
        print(f"race {n}: {len(out[n])} boats, legs per boat: "
              f"{sorted(set(len(r['legs']) for r in out[n]))}")
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'legs.json'),'w'))
    r1=out[1]
    ts=[r for r in r1 if r['boat']=='Team Sweden']
    if ts:
        print("\nTeam Sweden, race 1:")
        for l in ts[0]['legs']:
            print(f"  leg {l['leg']} {l['type']:8s} wind {l['wind']}  {l['min']:5.1f} min  "
                  f"sog {l['avg_sog']:.2f}  VMG {l['avg_vmg']:.2f}  "
                  f"{l['n']:2d} manoeuvres @ -{l['loss']:.2f} kn  place {l['place']}"
                  + (f" ({l['gained']:+d})" if l['gained'] is not None else ""))
