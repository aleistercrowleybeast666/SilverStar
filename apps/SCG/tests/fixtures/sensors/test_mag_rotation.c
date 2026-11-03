#include "mag_rotation.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void Increment(const float omega[3],float dt,float q[4])
{
    float omega_norm=sqrtf(omega[0]*omega[0]+omega[1]*omega[1]+omega[2]*omega[2]);
    q[0]=cosf(0.5f*dt*omega_norm);
    for(int i=0;i<3;i++){q[i+1]=sinf(0.5f*dt*omega_norm)*omega[i]/omega_norm;}
}

static void Run(float sign,int observable)
{
    MagRotationFit fit;MagRotation_Reset(&fit);
    float axis[3]={0.3f,-0.4f,0.5f}, target[4], inverse[4];
    Increment(axis,sign*0.51f,target);inverse[0]=target[0];
    for(int i=0;i<3;i++){inverse[i+1]=-target[i+1];}
    float field[3]={24.0f,-17.0f,37.0f}, sensor[3];
    unsigned accepted=0U,unobservable=0U;
    for(unsigned i=0;i<1000U;i++){
        float t=(float)i*0.05f;
        float w[3]={1.3f*sinf(2.1f*t),1.0f*cosf(2.9f*t),1.4f*cosf(1.3f*t)};
        if(!observable){w[0]=0.0f;w[1]=0.0f;w[2]=1.0f;}
        float dq[4];Increment(w,-0.05f,dq);MagRotation_VectorRotate(dq,field,field);
        MagRotation_VectorRotate(inverse,field,sensor);
        MagRotationResult result=MagRotation_Step(&fit,1000000ULL+50000ULL*i,sensor,w);
        if(result==MagRotationResult_Accepted){accepted++;}
        if(result==MagRotationResult_Unobservable){unobservable++;}
    }
    float dot=0.0f;for(int k=0;k<4;k++){dot+=fit.q[k]*target[k];}
    printf("known signed rotation %.3f, accepted=%u unobservable=%u qdot=%.8f rms=%.6f\n",
        (double)sign,accepted,unobservable,(double)dot,(double)fit.relative_rms);
    if(observable){assert(accepted>0U&&fabsf(dot)>0.99995f);}
    else{assert(accepted==0U&&unobservable>0U);}
    float w[3]={0.0f,0.0f,0.0f};
    assert(MagRotation_Step(&fit,10ULL,sensor,w)==MagRotationResult_Stale);
    assert(fit.previous_us==0ULL&&fit.good_windows==0U);
    sensor[0]=NAN;
    assert(MagRotation_Step(&fit,1000ULL,sensor,w)==MagRotationResult_Disturbed);
}

int main(void)
{
    Run(1.0f,1);Run(-1.0f,1);Run(1.0f,0);
    for(unsigned i=0;i<4U;i++){
        float q[4]={0}, decoded[4];q[i]=-1.0f;
        MagRotation_Decode(MagRotation_Encode(q),decoded);assert(decoded[i]==1.0f);
    }
    return 0;
}
