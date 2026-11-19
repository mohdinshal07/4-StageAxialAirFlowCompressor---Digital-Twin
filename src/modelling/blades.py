import numpy as np
from eng import *
def is_prime(n): return n>1 and all(n%k for k in range(2,int(n**.5)+1))
def next_prime(n):
    while not is_prime(n): n+=1
    return n
def carter(inl,outl,sig):
    m=0.23+0.1*abs(outl)/50.;th=(inl-outl)/(1-m/np.sqrt(sig));return th,th-(inl-outl),m
def DFr(b1,b2,sig):
    b1,b2=np.radians(b1),np.radians(b2);return 1-np.cos(b1)/np.cos(b2)+(np.tan(b1)-np.tan(b2))*np.cos(b1)/(2*sig)
def build(cfg):
    n,PR,rpm,Ca,eta,DHr,arep=[cfg[k] for k in ('n','PR','rpm','Ca','eta','DHr','arep')]
    st,mdot,om=design(n,PR,rpm,Ca,eta=eta,DHr=DHr,arep=arep)
    C=cfg['chord']/1000.;DFT=cfg['DFT']
    used=set();rows=[];prevZ=[None]
    def rv(s,r):
        U=om*r;f=s['rm']/r
        ta1=np.tan(np.radians(s['a1']))*f;ta2=np.tan(np.radians(s['a2']))*f;ta3=np.tan(np.radians(s['a3']))*f
        return dict(a1=np.degrees(np.arctan(ta1)),a2=np.degrees(np.arctan(ta2)),a3=np.degrees(np.arctan(ta3)),b1=np.degrees(np.arctan(U/Ca-ta1)),b2=np.degrees(np.arctan(U/Ca-ta2)),Lam=1-(Ca/(2*U))*(ta1+ta2),U=U)
    for s in st:
        m=rv(s,s['rm'])
        for kind in ('rotor','stator'):
            a,b=(m['b1'],m['b2']) if kind=='rotor' else (m['a2'],m['a3'])
            ar,br=np.radians(a),np.radians(b)
            sig=(np.tan(ar)-np.tan(br))*np.cos(ar)/(2*(DFT-1+np.cos(ar)/np.cos(br)))
            Zreq=2*np.pi*s['rm']*sig/C
            Zmin=2*np.pi*s['rm']*0.85/C          # solidity floor 0.85 (avoid very sparse rows)
            Z=int(np.ceil(max(Zreq,Zmin)))
            while Z in used or (prevZ[0] is not None and np.gcd(Z,prevZ[0])!=1): Z+=1
            used.add(Z);prevZ[0]=Z
            rha,rhb=((s['rh1'],s['rh2']) if kind=='rotor' else (s['rh2'],s['rh3']))
            rh=0.5*(rha+rhb);secs=[]
            for f in np.linspace(0,1,5):
                r=rh+f*(RT-rh);v=rv(s,r)
                inl,outl=(v['b1'],v['b2']) if kind=='rotor' else (v['a2'],v['a3'])
                sg=C*Z/(2*np.pi*r);th,dl,mm=carter(inl,outl,sg)
                if kind=='rotor': DF=DFr(v['b1'],v['b2'],sg)
                else: DF=DFr(v['a2'],v['a3'],sg)
                secs.append(dict(f=f,r=r,inl=inl,outl=outl,sig=sg,theta=th,delta=dl,m=mm,k1=inl,k2=outl-dl,xi=inl-th/2,DF=DF,Lam=v['Lam'],pitch=2*np.pi*r/Z,W1=Ca/np.cos(np.radians(inl)) if kind=='rotor' else None))
            rows.append(dict(stage=s['stage'],kind=kind,Z=Z,Zreq=Zreq,sig_req=sig,h=RT-rh,r_h=rh,chord=C,secs=secs))
    return st,mdot,om,rows
CFG={'A':dict(name='5-stage',n=5,PR=1.15,rpm=25000,Ca=40.,eta=0.70,DHr=0.72,arep=8.,chord=14.,DFT=0.45),
     'B':dict(name='4-stage',n=4,PR=1.12,rpm=20000,Ca=50.,eta=0.70,DHr=0.66,arep=8.,chord=14.,DFT=0.45)}
if __name__=="__main__":
    for k,cfg in CFG.items():
        st,mdot,om,rows=build(cfg)
        print('=====',k,cfg['name'],'mdot %.4f'%mdot,'Ut %.1f'%(om*RT),'P kW %.3f'%(mdot*cp*sum(s['dT0'] for s in st)/1e3),'dT %.2f'%sum(s['dT0'] for s in st))
        for s in st: print(s['stage'],'rm %.2f U %.1f a1 %.1f b1 %.1f b2 %.1f a2 %.1f a3 %.1f dT %.3f pi %.4f L %.3f DHr %.3f DHs %.3f hubD %.2f/%.2f/%.2f'%(s['rm']*1e3,s['U'],s['a1'],s['b1'],s['b2'],s['a2'],s['a3'],s['dT0'],s['pi'],s['Lam'],s['DHr'],s['DHs'],2e3*s['rh1'],2e3*s['rh2'],2e3*s['rh3']))
        for r in rows:
            q=r['secs']
            print(r['stage'],r['kind'],'Z',r['Z'],'(req %.1f sig %.2f)'%(r['Zreq'],r['sig_req']),'DF h/m/t %.2f %.2f %.2f'%(q[0]['DF'],q[2]['DF'],q[4]['DF']),'theta m %.1f xi m %.1f'%(q[2]['theta'],q[2]['xi']),'Lam h %.2f'%q[0]['Lam'])
