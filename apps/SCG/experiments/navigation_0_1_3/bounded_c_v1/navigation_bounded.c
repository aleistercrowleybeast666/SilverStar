#include "navigation_bounded.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static const double Navigation_Pi = 3.141592653589793238462643383279502884;
static int Memory_Overlaps(const void *a, size_t alen, const void *b, size_t blen)
{
    uintptr_t av=(uintptr_t)a, bv=(uintptr_t)b;
    if(a==NULL || b==NULL) { return 0; }
    return bv>=av ? bv-av<alen : av-bv<blen;
}
static int Workspace_Aliases(const NavigationWorkspace *w, const void *input, size_t size)
{
    return Memory_Overlaps(w,sizeof(*w),input,size);
}
static int Model_Size(NavigationModel model)
{
    return model == NavigationInEkf15 ? 15 : 20;
}
static int Array_Finite(const double *a, int count)
{
    int i;
    for (i = 0; i < count; ++i) { if (!isfinite(a[i])) { return 0; } }
    return 1;
}
static void Matrix_Identity(double *a, int n)
{
    int i;
    memset(a, 0, 400U * sizeof(double));
    for (i = 0; i < n; ++i) { a[i * 20 + i] = 1.0; }
}
/* Output must not alias either input; transpose applies only to b. */
static void Matrix_Multiply(const double *a, const double *b, double *out, int n, int transpose)
{
    int i, j, k;
    memset(out, 0, 400U * sizeof(double));
    for (i = 0; i < n; ++i) {
        for (j = 0; j < n; ++j) {
            double sum = 0.0;
            for (k = 0; k < n; ++k) { sum += a[i*20+k] * (transpose ? b[j*20+k] : b[k*20+j]); }
            out[i*20+j] = sum;
        }
    }
}
/* Dynamics_Build's fixed support, sorted by the original dense k order.
 * B has only the navigation rotation/force/bias/integration entries below.
 * Values may themselves be zero; only structural zeros are omitted. */
static const unsigned char Flow_RowCount[9]={3,3,3,5,5,5,3,3,3};
static const unsigned char Flow_RowIndex[9][5]={
    {1,2,9,0,0},{0,2,10,0,0},{0,1,11,0,0},
    {1,2,4,5,12},{0,2,3,5,13},{0,1,3,4,14},
    {3,7,8,0,0},{4,6,8,0,0},{5,6,7,0,0}};
static const unsigned char Flow_ColumnCount[15]={4,4,4,3,3,3,2,2,2,1,1,1,1,1,1};
static const unsigned char Flow_ColumnIndex[15][4]={
    {1,2,4,5},{0,2,3,5},{0,1,3,4},
    {4,5,6,0},{3,5,7,0},{3,4,8,0},
    {7,8,0,0},{6,8,0,0},{6,7,0,0},
    {0,0,0,0},{1,0,0,0},{2,0,0,0},
    {3,0,0,0},{4,0,0,0},{5,0,0,0}};
/* B is finite and has exactly Dynamics_Build's support. A nonfinite Taylor
 * term must fail before skipping 0*Inf/NaN could conceal the dense failure.
 * These helpers are used only in Flow_Discretize, never for reset or P. */
static int Flow_MultiplyLeft(const double *b, const double *a, double *out, int n)
{
    int i,j,t;
    if(!Array_Finite(a,400)) { return 0; }
    memset(out,0,400U*sizeof(double));
    for(i=0;i<9;++i) { for(j=0;j<n;++j) {
        double sum=0.0;
        for(t=0;t<5;++t) { if(t<Flow_RowCount[i]) {
            int k=Flow_RowIndex[i][t]; sum+=b[i*20+k]*a[k*20+j];
        } }
        out[i*20+j]=sum;
    } }
    return 1;
}
static int Flow_MultiplyRight(const double *a, const double *b, double *out, int n, int transpose)
{
    int i,j,t,columns=transpose?9:15;
    if(!Array_Finite(a,400)) { return 0; }
    memset(out,0,400U*sizeof(double));
    for(i=0;i<n;++i) { for(j=0;j<columns;++j) {
        double sum=0.0;
        for(t=0;t<5;++t) {
            if(transpose && t<Flow_RowCount[j]) {
                int k=Flow_RowIndex[j][t]; sum+=a[i*20+k]*b[j*20+k];
            } else if(!transpose && t<Flow_ColumnCount[j]) {
                int k=Flow_ColumnIndex[j][t]; sum+=a[i*20+k]*b[k*20+j];
            }
        }
        out[i*20+j]=sum;
    } }
    return 1;
}
static void Matrix_Symmetric(double *p, int n)
{
    int i, j;
    for (i = 0; i < n; ++i) {
        for (j = 0; j < i; ++j) { double v = 0.5*p[i*20+j]+0.5*p[j*20+i]; p[i*20+j]=v; p[j*20+i]=v; }
    }
}
static int Matrix_Cholesky(const double *p, double *l, int n, int stride)
{
    int i, j, k;
    memset(l, 0, (size_t)(stride*n) * sizeof(double));
    for (i=0; i<n; ++i) {
        for (j=0; j<=i; ++j) {
            double v=p[i*stride+j];
            if (!isfinite(v) || !isfinite(p[j*stride+i]) ||
                fabs(v-p[j*stride+i]) > 1e-12*fmax(fabs(v),fabs(p[j*stride+i]))) { return 0; }
            for (k=0; k<j; ++k) { v-=l[i*stride+k]*l[j*stride+k]; }
            if (i==j) { if (!(v>0.0) || !isfinite(v)) { return 0; } l[i*stride+j]=sqrt(v); }
            else { l[i*stride+j]=v/l[j*stride+j]; if (!isfinite(l[i*stride+j])) { return 0; } }
        }
    }
    return 1;
}
static void Small_Multiply(const double *a, const double *b, double *out)
{
    int i,j,k;
    for(i=0;i<3;++i) { for(j=0;j<3;++j) {
        out[i*3+j]=0.0;
        for(k=0;k<3;++k) { out[i*3+j]+=a[i*3+k]*b[k*3+j]; }
    } }
}
static void Small_Vector(const double *a, const double *v, double *out)
{
    int i;
    for(i=0;i<3;++i) { out[i]=a[i*3]*v[0]+a[i*3+1]*v[1]+a[i*3+2]*v[2]; }
}
static void Small_Skew(const double *v, double *out)
{
    out[0]=0; out[1]=-v[2]; out[2]=v[1]; out[3]=v[2]; out[4]=0;
    out[5]=-v[0]; out[6]=-v[1]; out[7]=v[0]; out[8]=0;
}
static int Rotation_Valid(const double *r)
{
    int i,j,k;
    double det=r[0]*(r[4]*r[8]-r[5]*r[7])-r[1]*(r[3]*r[8]-r[5]*r[6])+r[2]*(r[3]*r[7]-r[4]*r[6]);
    if (!Array_Finite(r,9) || fabs(det-1.0)>1e-10) { return 0; }
    for(i=0;i<3;++i) { for(j=0;j<3;++j) {
        double v=0.0;
        for(k=0;k<3;++k) { v+=r[k*3+i]*r[k*3+j]; }
        if(fabs(v-(i==j ? 1.0:0.0))>1e-10) { return 0; }
    } }
    return 1;
}
/* E=exp([phi]), J=integral exp(s[phi]), J2=integral(1-s)exp(s[phi]). */
static int Rotation_Functions(const double *phi, double *e, double *j, double *j2)
{
    double k[9],k2[9],t2=phi[0]*phi[0]+phi[1]*phi[1]+phi[2]*phi[2];
    double a,b,c,d; int i;
    if (!isfinite(t2) || t2>4096.0) { return 0; }
    if(t2<1e-4) {
        a=1.0-t2/6.0+t2*t2/120.0-t2*t2*t2/5040.0;
        b=0.5-t2/24.0+t2*t2/720.0-t2*t2*t2/40320.0;
        c=1.0/6.0-t2/120.0+t2*t2/5040.0-t2*t2*t2/362880.0;
        d=1.0/24.0-t2/720.0+t2*t2/40320.0-t2*t2*t2/3628800.0;
    } else {
        double t=sqrt(t2); a=sin(t)/t; b=(1.0-cos(t))/t2;
        c=(1.0-a)/t2; d=(0.5-b)/t2;
    }
    Small_Skew(phi,k); Small_Multiply(k,k,k2);
    for(i=0;i<9;++i) {
        double identity=(i%4==0 ? 1.0:0.0);
        e[i]=identity+a*k[i]+b*k2[i]; j[i]=identity+b*k[i]+c*k2[i];
        j2[i]=0.5*identity+c*k[i]+d*k2[i];
    }
    return 1;
}
NavigationResult Navigation_Validate(const NavigationState *s, NavigationWorkspace *w)
{
    if(s==NULL || w==NULL || Workspace_Aliases(w,s,sizeof(*s))) { return NavigationInvalidInput; }
    if(s->model!=NavigationEskf20 && s->model!=NavigationInEkf15 && s->model!=NavigationInEkf20) { return NavigationInvalidInput; }
    if(!Rotation_Valid(s->rotation) || !Array_Finite(s->position,3) || !Array_Finite(s->velocity,3) ||
       !Array_Finite(s->gyro_bias,3) || !Array_Finite(s->accel_bias,3) || !isfinite(s->time_s) || s->time_s<0) { return NavigationInvalidInput; }
    if(s->model!=NavigationInEkf15 && (!Rotation_Valid(s->installation) || !isfinite(s->inclination) ||
       !isfinite(s->declination) || fabs(s->inclination)>Navigation_Pi/2.0)) { return NavigationInvalidInput; }
    return Matrix_Cholesky(s->covariance,w->matrix[7],Model_Size(s->model),20) ? NavigationOk:NavigationInvalidInput;
}
/* B is F*dt, L is Qc*dt. Rotation blocks alone repeat in powers of F;
 * force/bias/integration blocks form finite acyclic paths. Scale the repeated
 * diagonal blocks to <=1/4, take 24 terms, then at most 8 doublings. */
static int Flow_Discretize(NavigationWorkspace *w, int n)
{
    double *b=w->matrix[0], *l=w->matrix[1], *e=w->matrix[2], *q=w->matrix[3];
    double *term=w->matrix[4], *tmp=w->matrix[5], *right=w->matrix[6];
    double norm=0.0,scale=1.0; int i,j,k,s=0;
    if(!Array_Finite(b,400) || !Array_Finite(l,400)) { return 0; }
    for(i=0;i<n;++i) {
        double row=0.0;
        for(j=0;j<n;++j) { if(i/3==j/3) { row+=fabs(b[i*20+j]); } }
        norm=fmax(norm,row);
    }
    if(!isfinite(norm) || norm>64.0) { return 0; }
    for(k=0;k<8;++k) { if(norm>0.25) { norm*=0.5; scale*=0.5; ++s; } }
    for(i=0;i<400;++i) { b[i]*=scale; l[i]*=scale; }
    Matrix_Identity(e,n); Matrix_Identity(term,n);
    for(k=1;k<=24;++k) {
        if(!Flow_MultiplyRight(term,b,tmp,n,0)) { return 0; }
        for(i=0;i<400;++i) { term[i]=tmp[i]/(double)k; e[i]+=term[i]; }
    }
    memcpy(q,l,400U*sizeof(double)); memcpy(term,l,400U*sizeof(double));
    for(k=1;k<=24;++k) {
        if(!Flow_MultiplyLeft(b,term,tmp,n) || !Flow_MultiplyRight(term,b,right,n,1)) { return 0; }
        for(i=0;i<400;++i) { term[i]=(tmp[i]+right[i])/(double)(k+1); q[i]+=term[i]; }
    }
    for(k=0;k<8;++k) { if(k<s) {
        Matrix_Multiply(e,q,tmp,n,0); Matrix_Multiply(tmp,e,right,n,1);
        for(i=0;i<400;++i) { q[i]+=right[i]; }
        Matrix_Multiply(e,e,tmp,n,0); memcpy(e,tmp,400U*sizeof(double));
    } }
    Matrix_Symmetric(q,n);
    return Array_Finite(e,400) && Array_Finite(q,400);
}
static void Dynamics_Build(NavigationWorkspace *w, const double *omega, const double *a, const double *density, double dt, int eskf)
{
    double sw[9],sa[9]; int i,j,b;
    memset(w->matrix[0],0,400U*sizeof(double)); memset(w->matrix[1],0,400U*sizeof(double));
    Small_Skew(omega,sw); Small_Skew(a,sa);
    for(i=0;i<3;++i) { for(j=0;j<3;++j) {
        for(b=0;b<3;++b) { w->matrix[0][(b*3+i)*20+b*3+j]=-sw[i*3+j]*dt; }
        w->matrix[0][(3+i)*20+j]=-sa[i*3+j]*dt;
    } }
    for(i=0;i<3;++i) {
        int gyro=eskf?i+3:i, accel=eskf?i:i+3;
        w->matrix[0][i*20+9+i]=-dt; w->matrix[0][(3+i)*20+12+i]=-dt; w->matrix[0][(6+i)*20+3+i]=dt;
        w->matrix[1][i*20+i]=density[gyro]*density[gyro]*dt;
        w->matrix[1][(3+i)*20+3+i]=density[accel]*density[accel]*dt;
        w->matrix[1][(9+i)*20+9+i]=density[6+i]*density[6+i]*dt;
        w->matrix[1][(12+i)*20+12+i]=density[9+i]*density[9+i]*dt;
    }
}
static void Coordinates_Build(const double *r, double *t, int inverse)
{
    int i,j;
    Matrix_Identity(t,20);
    for(i=0;i<15;++i) { t[i*20+i]=0.0; }
    for(i=0;i<3;++i) { for(j=0;j<3;++j) {
        if(inverse) { t[(6+i)*20+j]=-r[j*3+i]; t[(3+i)*20+3+j]=-r[j*3+i]; }
        else { t[i*20+6+j]=-r[i*3+j]; t[(3+i)*20+3+j]=-r[i*3+j]; }
    } }
    for(i=0;i<3;++i) { t[(inverse?i:6+i)*20+(inverse?6+i:i)]=-1.0; t[(9+i)*20+9+i]=-1.0; t[(12+i)*20+12+i]=-1.0; }
}
static int Nominal_Propagate(NavigationState *s, const double *omega, const double *a, const double *g, double dt)
{
    double phi[3],e[9],j[9],j2[9],r[9],dv[3],dp[3],body[3]; int i;
    for(i=0;i<3;++i) { phi[i]=omega[i]*dt; }
    if(!Rotation_Functions(phi,e,j,j2)) { return 0; }
    Small_Vector(j,a,body); Small_Vector(s->rotation,body,dv);
    Small_Vector(j2,a,body); Small_Vector(s->rotation,body,dp);
    Small_Multiply(s->rotation,e,r);
    for(i=0;i<3;++i) { s->position[i]+=s->velocity[i]*dt+(dp[i]+0.5*g[i])*dt*dt; s->velocity[i]+=(dv[i]+g[i])*dt; }
    memcpy(s->rotation,r,sizeof(r)); s->time_s+=dt;
    return 1;
}
static NavigationResult Candidate_Publish(NavigationState *s, NavigationWorkspace *w)
{
    NavigationState *c=&w->candidate; int n=Model_Size(s->model);
    Matrix_Symmetric(c->covariance,n);
    if(!Rotation_Valid(c->rotation) || !Array_Finite(c->position,3) || !Array_Finite(c->velocity,3) ||
       !Array_Finite(c->gyro_bias,3) || !Array_Finite(c->accel_bias,3) || !isfinite(c->time_s) ||
       (n==20 && (!Rotation_Valid(c->installation) || !isfinite(c->inclination) || !isfinite(c->declination))) ||
       !Matrix_Cholesky(c->covariance,w->matrix[7],n,20)) { return NavigationNumericError; }
    *s=*c;
    return NavigationOk;
}
NavigationResult Navigation_Predict(NavigationState *s, NavigationWorkspace *w, const double gyro[3],
    const double accel[3], const double gravity[3], const double density[12], double dt)
{
    double omega[3],a[3]; int i,n;
    if(Workspace_Aliases(w,gyro,3U*sizeof(double)) || Workspace_Aliases(w,accel,3U*sizeof(double)) ||
       Workspace_Aliases(w,gravity,3U*sizeof(double)) || Workspace_Aliases(w,density,12U*sizeof(double)) ||
       Navigation_Validate(s,w)!=NavigationOk || gyro==NULL || accel==NULL || gravity==NULL || density==NULL ||
       !Array_Finite(gyro,3) || !Array_Finite(accel,3) || !Array_Finite(gravity,3) || !Array_Finite(density,12) ||
       !isfinite(dt) || dt<=0.0 || dt>0.02 || !isfinite(s->time_s+dt) || s->time_s+dt<=s->time_s) { return NavigationInvalidInput; }
    for(i=0;i<12;++i) { if(density[i]<0.0) { return NavigationInvalidInput; } }
    n=Model_Size(s->model); w->candidate=*s;
    for(i=0;i<3;++i) { omega[i]=gyro[i]-s->gyro_bias[i]; a[i]=accel[i]-s->accel_bias[i]; }
    if(!Array_Finite(omega,3) || !Array_Finite(a,3) ||
       fabs(omega[0]*dt)+fabs(omega[1]*dt)+fabs(omega[2]*dt)>64.0) { return NavigationInvalidInput; }
    if(!Nominal_Propagate(&w->candidate,omega,a,gravity,dt)) { return NavigationNumericError; }
    Dynamics_Build(w,omega,a,density,dt,s->model==NavigationEskf20);
    if(!Flow_Discretize(w,n)) { return NavigationNumericError; }
    if(s->model==NavigationEskf20) {
        Coordinates_Build(s->rotation,w->matrix[0],1);
        Matrix_Multiply(w->matrix[0],s->covariance,w->matrix[4],n,0);
        Matrix_Multiply(w->matrix[4],w->matrix[0],w->matrix[1],n,1);
    } else { memcpy(w->matrix[1],s->covariance,400U*sizeof(double)); }
    Matrix_Multiply(w->matrix[2],w->matrix[1],w->matrix[4],n,0);
    Matrix_Multiply(w->matrix[4],w->matrix[2],w->matrix[5],n,1);
    for(i=0;i<400;++i) { w->matrix[5][i]+=w->matrix[3][i]; }
    if(s->model==NavigationEskf20) {
        Coordinates_Build(w->candidate.rotation,w->matrix[0],0);
        Matrix_Multiply(w->matrix[0],w->matrix[5],w->matrix[4],n,0);
        Matrix_Multiply(w->matrix[4],w->matrix[0],w->candidate.covariance,n,1);
    } else { memcpy(w->candidate.covariance,w->matrix[5],400U*sizeof(double)); }
    return Candidate_Publish(s,w);
}
/* Integral exp(ad delta): scaling, 24 Taylor terms, at most 8 doublings.
 * Unlike a block-diagonal SO3 approximation this retains SE23 cross terms. */
static int Reset_Integral(NavigationWorkspace *w, int n)
{
    double norm=0.0,scale=1.0; int i,j,k,s=0;
    if(!Array_Finite(w->matrix[0],400)) { return 0; }
    /* SE23 translation blocks are nilpotent and occur only linearly in every
     * power. Only repeated rotation diagonal blocks control Taylor convergence;
     * a large translation must not create an arbitrary rejection threshold. */
    for(i=0;i<n;++i) {
        double row=0.0;
        for(j=0;j<n;++j) { if(i/3==j/3) { row+=fabs(w->matrix[0][i*20+j]); } }
        norm=fmax(norm,row);
    }
    if(!isfinite(norm) || norm>64.0) { return 0; }
    for(k=0;k<8;++k) { if(norm>0.25) { norm*=0.5; scale*=0.5; ++s; } }
    for(i=0;i<400;++i) { w->matrix[0][i]*=scale; }
    Matrix_Identity(w->matrix[2],n); Matrix_Identity(w->matrix[3],n); Matrix_Identity(w->matrix[4],n);
    for(k=1;k<=24;++k) {
        Matrix_Multiply(w->matrix[4],w->matrix[0],w->matrix[5],n,0);
        for(i=0;i<400;++i) {
            w->matrix[4][i]=w->matrix[5][i]/(double)k;
            w->matrix[2][i]+=w->matrix[4][i]; w->matrix[3][i]+=w->matrix[4][i]/(double)(k+1);
        }
    }
    for(k=0;k<8;++k) { if(k<s) {
        Matrix_Multiply(w->matrix[2],w->matrix[3],w->matrix[5],n,0);
        for(i=0;i<400;++i) { w->matrix[3][i]=0.5*(w->matrix[3][i]+w->matrix[5][i]); }
        Matrix_Multiply(w->matrix[2],w->matrix[2],w->matrix[5],n,0);
        memcpy(w->matrix[2],w->matrix[5],400U*sizeof(double));
    } }
    return Array_Finite(w->matrix[3],400);
}
static void Reset_Build(NavigationWorkspace *w, NavigationModel model, const double *d)
{
    double k[9],v[3]; int i,j,b;
    memset(w->matrix[0],0,400U*sizeof(double));
    if(model!=NavigationEskf20) {
        for(b=0;b<3;++b) {
            Small_Skew(d+3*b,k);
            for(i=0;i<3;++i) { for(j=0;j<3;++j) {
                if(b==0) { int c; for(c=0;c<3;++c) { w->matrix[0][(3*c+i)*20+3*c+j]=k[i*3+j]; } }
                else { w->matrix[0][(3*b+i)*20+j]=k[i*3+j]; }
            } }
        }
    } else {
        for(i=0;i<3;++i) { v[i]=-d[6+i]; } Small_Skew(v,k);
        for(i=0;i<3;++i) { for(j=0;j<3;++j) { w->matrix[0][(6+i)*20+6+j]=k[i*3+j]; } }
    }
    if(model!=NavigationInEkf15) {
        for(i=0;i<3;++i) { v[i]=-d[15+i]; } Small_Skew(v,k);
        for(i=0;i<3;++i) { for(j=0;j<3;++j) { w->matrix[0][(15+i)*20+15+j]=k[i*3+j]; } }
    }
}
static NavigationResult Retraction_Apply(NavigationWorkspace *w, const double *d)
{
    NavigationState *s=&w->candidate; double phi[3],e[9],j[9],j2[9],r[9],v[3],local[3];
    int i,offset=s->model==NavigationEskf20?6:0;
    double angle=hypot(hypot(d[offset],d[offset+1]),d[offset+2]);
    if(angle>0.35 || (s->model!=NavigationInEkf15 && (hypot(hypot(d[15],d[16]),d[17])>0.35 ||
        fabs(s->inclination-d[18])>Navigation_Pi/2.0))) { return NavigationRejectedCorrection; }
    for(i=0;i<3;++i) { phi[i]=(s->model==NavigationEskf20?1.0:-1.0)*d[offset+i]; }
    if(!Rotation_Functions(phi,e,j,j2)) { return NavigationNumericError; }
    if(s->model==NavigationEskf20) {
        for(i=0;i<3;++i) { s->position[i]+=d[i]; s->velocity[i]+=d[3+i]; s->gyro_bias[i]+=d[9+i]; s->accel_bias[i]+=d[12+i]; }
    } else {
        for(i=0;i<3;++i) { v[i]=-d[3+i]; } Small_Vector(j,v,local); Small_Vector(s->rotation,local,v);
        for(i=0;i<3;++i) { s->velocity[i]+=v[i]; }
        for(i=0;i<3;++i) { v[i]=-d[6+i]; } Small_Vector(j,v,local); Small_Vector(s->rotation,local,v);
        for(i=0;i<3;++i) { s->position[i]+=v[i]; s->gyro_bias[i]-=d[9+i]; s->accel_bias[i]-=d[12+i]; }
    }
    Small_Multiply(s->rotation,e,r); memcpy(s->rotation,r,sizeof(r));
    if(s->model!=NavigationInEkf15) {
        for(i=0;i<3;++i) { phi[i]=-d[15+i]; }
        if(!Rotation_Functions(phi,e,j,j2)) { return NavigationNumericError; }
        Small_Multiply(e,s->installation,r); memcpy(s->installation,r,sizeof(r));
        s->inclination-=d[18]; s->declination-=d[19];
    }
    return NavigationOk;
}
static NavigationResult Reset_Apply(NavigationState *s, NavigationWorkspace *w, const double *d)
{
    NavigationResult result; int n=Model_Size(s->model);
    result=Retraction_Apply(w,d); if(result!=NavigationOk) { return result; }
    Reset_Build(w,s->model,d); if(!Reset_Integral(w,n)) { return NavigationNumericError; }
    Matrix_Multiply(w->matrix[3],w->candidate.covariance,w->matrix[4],n,0);
    Matrix_Multiply(w->matrix[4],w->matrix[3],w->candidate.covariance,n,1);
    return Candidate_Publish(s,w);
}
NavigationResult Navigation_Inject(NavigationState *s, NavigationWorkspace *w, const double correction[20])
{
    if(Workspace_Aliases(w,correction,20U*sizeof(double)) || Navigation_Validate(s,w)!=NavigationOk ||
       correction==NULL || !Array_Finite(correction,Model_Size(s->model))) { return NavigationInvalidInput; }
    memcpy(w->correction,correction,(size_t)Model_Size(s->model)*sizeof(double)); w->candidate=*s;
    return Reset_Apply(s,w,w->correction);
}
static void Small_Solve(const double *l, const double *b, double *x)
{
    double y[3]; int i,j;
    for(i=0;i<3;++i) { y[i]=b[i]; for(j=0;j<i;++j) { y[i]-=l[i*3+j]*y[j]; } y[i]/=l[i*3+i]; }
    for(i=2;i>=0;--i) { x[i]=y[i]; for(j=i+1;j<3;++j) { x[i]-=l[j*3+i]*x[j]; } x[i]/=l[i*3+i]; }
}
static NavigationResult Update_Apply(NavigationState *s, NavigationWorkspace *w, double gate)
{
    double l[9],rhs[3],x[3]; int i,j,k,n=Model_Size(s->model);
    for(i=0;i<n;++i) { for(j=0;j<3;++j) {
        double v=0.0; for(k=0;k<n;++k) { v+=s->covariance[i*20+k]*w->observation[j*20+k]; } w->gain[i*3+j]=v;
    } }
    for(i=0;i<3;++i) { for(j=0;j<3;++j) {
        double v=w->noise[i*3+j]; for(k=0;k<n;++k) { v+=w->observation[i*20+k]*w->gain[k*3+j]; } w->innovation[i*3+j]=v;
    } }
    for(i=0;i<3;++i) { for(j=0;j<i;++j) { double v=0.5*w->innovation[i*3+j]+0.5*w->innovation[j*3+i]; w->innovation[i*3+j]=v; w->innovation[j*3+i]=v; } }
    if(!Matrix_Cholesky(w->innovation,l,3,3)) { return NavigationNumericError; }
    Small_Solve(l,w->residual,x); w->nis=0.0;
    for(i=0;i<3;++i) { w->nis+=w->residual[i]*x[i]; }
    if(!isfinite(w->nis) || w->nis<0.0) { return NavigationNumericError; }
    if(gate>0.0 && w->nis>gate) { return NavigationRejectedNis; }
    for(i=0;i<n;++i) {
        memcpy(rhs,w->gain+i*3,sizeof(rhs)); Small_Solve(l,rhs,x); w->correction[i]=0.0;
        for(j=0;j<3;++j) { w->gain[i*3+j]=x[j]; w->correction[i]+=x[j]*w->residual[j]; }
    }
    if(!Array_Finite(w->correction,n)) { return NavigationNumericError; }
    Matrix_Identity(w->matrix[0],n);
    for(i=0;i<n;++i) { for(j=0;j<n;++j) {
        for(k=0;k<3;++k) { w->matrix[0][i*20+j]-=w->gain[i*3+k]*w->observation[k*20+j]; }
    } }
    Matrix_Multiply(w->matrix[0],s->covariance,w->matrix[1],n,0);
    Matrix_Multiply(w->matrix[1],w->matrix[0],w->matrix[2],n,1); w->candidate=*s;
    for(i=0;i<n;++i) { for(j=0;j<n;++j) {
        double v=w->matrix[2][i*20+j]; int c;
        for(k=0;k<3;++k) { for(c=0;c<3;++c) { v+=w->gain[i*3+k]*w->noise[k*3+c]*w->gain[j*3+c]; } }
        w->candidate.covariance[i*20+j]=v;
    } }
    return Reset_Apply(s,w,w->correction);
}
static void Noise_Transform(const double *r, const double *cov, double *out)
{
    double rt[9],tmp[9]; int i,j;
    for(i=0;i<3;++i) { for(j=0;j<3;++j) { rt[i*3+j]=r[j*3+i]; } }
    Small_Multiply(r,cov,tmp); Small_Multiply(tmp,rt,out);
    for(i=0;i<3;++i) { for(j=0;j<i;++j) { double v=0.5*out[i*3+j]+0.5*out[j*3+i]; out[i*3+j]=v; out[j*3+i]=v; } }
}
NavigationResult Navigation_UpdateVector(NavigationState *s, NavigationWorkspace *w, const double measured[3],
    const double covariance[9], NavigationVectorKind kind, double time_s, double gate)
{
    double l[9],rt[9],v[3]; const double *nominal; int i,j,offset;
    if(Workspace_Aliases(w,measured,3U*sizeof(double)) || Workspace_Aliases(w,covariance,9U*sizeof(double)) ||
       Navigation_Validate(s,w)!=NavigationOk || (kind!=NavigationPosition && kind!=NavigationVelocity) ||
       !isfinite(time_s) || time_s!=s->time_s || !isfinite(gate) || gate<0.0) { return NavigationInvalidInput; }
    if(measured==NULL) { return NavigationNoObservation; }
    if(covariance==NULL || !Array_Finite(measured,3) || !Matrix_Cholesky(covariance,l,3,3)) { return NavigationInvalidInput; }
    nominal=kind==NavigationPosition?s->position:s->velocity;
    memset(w->observation,0,sizeof(w->observation));
    offset=kind==NavigationPosition?(s->model==NavigationEskf20?0:6):3;
    for(i=0;i<3;++i) { w->observation[i*20+offset+i]=1.0; v[i]=nominal[i]-measured[i]; }
    if(s->model==NavigationEskf20) {
        for(i=0;i<3;++i) { w->residual[i]=-v[i]; } memcpy(w->noise,covariance,9U*sizeof(double));
    } else {
        for(i=0;i<3;++i) { for(j=0;j<3;++j) { rt[i*3+j]=s->rotation[j*3+i]; } }
        Small_Vector(rt,v,w->residual); Noise_Transform(rt,covariance,w->noise);
    }
    return Update_Apply(s,w,gate);
}
static void Magnetic_Field(double inclination, double declination, double *h, double *di, double *dd)
{
    double si=sin(inclination),ci=cos(inclination),sd=sin(declination),cd=cos(declination);
    if(fabs(inclination)==Navigation_Pi/2.0) { si=copysign(1.0,inclination); ci=0.0; }
    h[0]=sd*ci; h[1]=cd*ci; h[2]=-si;
    di[0]=-sd*si; di[1]=-cd*si; di[2]=-ci;
    dd[0]=cd*ci; dd[1]=-sd*ci; dd[2]=0.0;
}
NavigationResult Navigation_UpdateMagnetic(NavigationState *s, NavigationWorkspace *w,
    const NavigationMagneticSample *sample, double gate)
{
    double l[9],transform[9],cov[9],measured[3],h[3],di[3],dd[3],skew[9],hr[9]; int i,j,offset;
    if(Workspace_Aliases(w,sample,sizeof(*sample)) || Navigation_Validate(s,w)!=NavigationOk ||
       s->model==NavigationInEkf15 || !isfinite(gate) || gate<0.0) { return NavigationInvalidInput; }
    if(sample==NULL) { return NavigationNoObservation; }
    if(sample->sensor_frame!=1U || sample->calibration!=1U || !isfinite(sample->time_s) || sample->time_s!=s->time_s ||
       !isfinite(sample->reference_strength_uT) || sample->reference_strength_uT<=0.0 ||
       !Array_Finite(sample->corrected_sensor_uT,3) || !Matrix_Cholesky(sample->covariance_sensor_uT2,l,3,3)) { return NavigationInvalidInput; }
    for(i=0;i<3;++i) { measured[i]=sample->corrected_sensor_uT[i]/sample->reference_strength_uT; }
    for(i=0;i<9;++i) { cov[i]=sample->covariance_sensor_uT2[i]/sample->reference_strength_uT/sample->reference_strength_uT; }
    if(!Array_Finite(measured,3) || !Matrix_Cholesky(cov,l,3,3)) { return NavigationNumericError; }
    Small_Multiply(s->rotation,s->installation,transform); Small_Vector(transform,measured,w->residual);
    Magnetic_Field(s->inclination,s->declination,h,di,dd); Small_Skew(h,skew); Small_Multiply(skew,s->rotation,hr);
    memset(w->observation,0,sizeof(w->observation)); offset=s->model==NavigationEskf20?6:0;
    for(i=0;i<3;++i) {
        w->residual[i]-=h[i]; w->observation[i*20+18]=-di[i]; w->observation[i*20+19]=-dd[i];
        for(j=0;j<3;++j) { w->observation[i*20+offset+j]=(s->model==NavigationEskf20?1.0:-1.0)*hr[i*3+j]; w->observation[i*20+15+j]=-hr[i*3+j]; }
    }
    Noise_Transform(transform,cov,w->noise);
    return Update_Apply(s,w,gate);
}
