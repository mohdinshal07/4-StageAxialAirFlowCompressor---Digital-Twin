import numpy as np
g=1.4;R=287.;cp=g*R/(g-1);T01=288.15;P01=101325.
RT=0.05;RH1=0.0375
LAM_ALL=[0.98,0.93,0.88,0.83,0.83,0.83,0.83]
def stat(T0,P0,C):
    T=T0-C**2/(2*cp);P=P0*(T/T0)**(g/(g-1));return P/(R*T),T,P
def design(n,PRc,rpm,Ca,eta=0.70,DHr=0.72,arep=12.0,rt=RT,rh1=RH1):
    lam=LAM_ALL[:n-1]+[LAM_ALL[3]] if n>4 else (LAM_ALL[:3]+[0.83])
    if n==5: lam=[0.98,0.93,0.88,0.83,0.83]
    if n==4: lam=[0.98,0.93,0.88,0.83]
    om=rpm*2*np.pi/60
    rho1,_,_=stat(T01,P01,Ca);mdot=rho1*Ca*np.pi*(rt**2-rh1**2)
    def hub(T0,P0,C):
        rho,T,P=stat(T0,P0,C);A=mdot/(rho*Ca);return np.sqrt(rt**2-A/np.pi),rho
    T=T01;P=P01;a1=0.;pr=1;out=[];rh_in=rh1
    for i in range(n):
        rh3=rh_in+0.0005
        for it in range(60):
            rm=(rt+0.5*(rh_in+rh3))/2;U=om*rm
            tb1=U/Ca-np.tan(a1)
            if i<n-1:
                x=DHr**2*(1+tb1**2)-1
                if x<0: return None
                tb2=np.sqrt(x);dT=lam[i]*U*Ca*(tb1-tb2)/cp;pi=(1+eta*dT/T)**(g/(g-1))
            else:
                pi=PRc/pr
                if pi<=1: return None
                dT=T/eta*(pi**((g-1)/g)-1);tb2=tb1-cp*dT/(lam[i]*U*Ca)
            ta2=U/Ca-tb2;al2=np.arctan(ta2)
            if i<n-1:
                a3=np.radians(arep)
                if np.cos(al2)/np.cos(a3)>=1.0 and a3>=al2: return None
            else: a3=0.
            C1=Ca/np.cos(a1);C2=Ca/np.cos(al2);C3=Ca/np.cos(a3)
            T02=T+dT;P02=P*(1+eta*dT/T)**(g/(g-1));P03=P*pi
            h1,r1=hub(T,P,C1);h2,r2=hub(T02,P02,C2);h3n,r3=hub(T02,P03,C3)
            if abs(h3n-rh3)<1e-10: break
            rh3=h3n
        b1=np.arctan(tb1);b2=np.arctan(tb2)
        out.append(dict(stage=i+1,T01=T,P01=P,a1=np.degrees(a1),b1=np.degrees(b1),b2=np.degrees(b2),a2=np.degrees(al2),a3=np.degrees(a3),dT0=dT,pi=pi,Lam=Ca/(2*U)*(tb1+tb2),DHr=np.cos(b1)/np.cos(b2),DHs=np.cos(al2)/np.cos(a3),lam=lam[i],U=U,rm=rm,Ca=Ca,rh1=h1,rh2=h2,rh3=h3n,rho=(r1,r2,r3),T03=T02,P03=P03,P02=P02,C=(C1,C2,C3),W=(Ca/np.cos(b1),Ca/np.cos(b2))))
        T=T02;P=P03;pr*=pi;a1=a3;rh_in=h3n
    return out,mdot,om
if __name__=="__main__":
    import sys
    for n,PR,rpm in ((5,1.15,25000),(4,1.12,20000)):
        print('=====',n,PR,rpm)
        for eta in (0.70,0.75):
          for DHr in (0.72,0.70,0.68,0.66,0.64,0.62):
            for arep in (8,10,12,15):
              for Ca in range(20,61,5):
                r=design(n,PR,rpm,Ca,eta=eta,DHr=DHr,arep=arep)
                if not r: continue
                o,md,om=r;l=o[-1]
                if l['DHr']>=DHr-0.001 and min(s['DHs'] for s in o)>=0.70 and l['a2']<55 and all(s['Lam']>0.5 for s in o):
                    P=md*cp*sum(s['dT0'] for s in o)/1e3
                    print('eta',eta,'DHr',DHr,'arep',arep,'Ca',Ca,'PRs',[round(s['pi'],4) for s in o],'DHs',[round(s['DHs'],2) for s in o],'DHr_last',round(l['DHr'],2),'P',round(P,2))
