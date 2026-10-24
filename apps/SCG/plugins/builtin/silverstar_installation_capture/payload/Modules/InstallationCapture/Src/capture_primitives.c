#include "capture_internal.h"
#include "ryu/ryu.h"
#include <stddef.h>
#include <string.h>

static const uint32_t s_sha_k[64] = {
    0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
    0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
    0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
    0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
    0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
    0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
    0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
    0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U
};

static uint32_t Sha_Ror(uint32_t value, uint8_t shift)
{ return (value >> shift) | (value << (32U-shift)); }

static void Sha_Block(CaptureSha *ctx)
{
    uint32_t w[16], a=ctx->h[0], b=ctx->h[1], c=ctx->h[2], d=ctx->h[3];
    uint32_t e=ctx->h[4], f=ctx->h[5], g=ctx->h[6], h=ctx->h[7];
    uint32_t index, t1, t2, x, y;
    for (index=0U; index<16U; index++) {
        const uint8_t *p=&ctx->block[index*4U];
        w[index]=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
    }
    for (index=0U; index<64U; index++) {
        if (index>=16U) {
            x=w[(index+1U)&15U]; y=w[(index+14U)&15U];
            w[index&15U]+=(Sha_Ror(x,7U)^Sha_Ror(x,18U)^(x>>3))+
                w[(index+9U)&15U]+(Sha_Ror(y,17U)^Sha_Ror(y,19U)^(y>>10));
        }
        t1=h+(Sha_Ror(e,6U)^Sha_Ror(e,11U)^Sha_Ror(e,25U))+((e&f)^((~e)&g))+s_sha_k[index]+w[index&15U];
        t2=(Sha_Ror(a,2U)^Sha_Ror(a,13U)^Sha_Ror(a,22U))+((a&b)^(a&c)^(b&c));
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    ctx->h[0]+=a;ctx->h[1]+=b;ctx->h[2]+=c;ctx->h[3]+=d;
    ctx->h[4]+=e;ctx->h[5]+=f;ctx->h[6]+=g;ctx->h[7]+=h;
}

void CaptureSha_Init(CaptureSha *ctx)
{
    static const uint32_t initial[8]={0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
        0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    (void)memcpy(ctx->h,initial,sizeof(initial));ctx->bytes=0U;ctx->used=0U;
}

void CaptureSha_Byte(CaptureSha *ctx, uint8_t value)
{
    ctx->block[ctx->used++]=value;ctx->bytes++;
    if (ctx->used==64U) { Sha_Block(ctx);ctx->used=0U; }
}

void CaptureSha_Finish(CaptureSha *ctx, uint8_t output[32])
{
    uint64_t bits=ctx->bytes*8U;
    uint8_t count=(ctx->used<56U)?(uint8_t)(56U-ctx->used):(uint8_t)(120U-ctx->used);
    uint8_t index;
    CaptureSha_Byte(ctx,0x80U);
    for (index=1U;index<count;index++) { CaptureSha_Byte(ctx,0U); }
    for (index=0U;index<8U;index++) { CaptureSha_Byte(ctx,(uint8_t)(bits>>(56U-8U*index))); }
    for (index=0U;index<32U;index++) { output[index]=(uint8_t)(ctx->h[index/4U]>>(24U-8U*(index%4U))); }
}

/* Ryu provides shortest round-trip digits. This wrapper applies Python JSON's
 * fixed/scientific threshold, exponent padding, and explicit floating .0.
 * All input values are finite; IEEE bit tests retain negative zero. */
InstallationCaptureResult CaptureNumber_Write(double value, char output[32], uint16_t *length)
{
    union {double f;uint64_t u;} bits;
    char ryu[32], digits[17];
    int n, exponent=0, sign=1, decimal;
    uint16_t i=0U, count=0U, used=0U, start=0U;
    bits.f=value;
    if ((output==NULL)||(length==NULL)||(((bits.u>>52)&2047U)==2047U)) { return InstallationCaptureResult_Invalid; }
    n=d2s_buffered_n(value,ryu);
    if ((n<3)||(n>31)) { return InstallationCaptureResult_Failed; }
    if (ryu[0]=='-') {output[used++]='-';i=1U;}
    for (;i<(uint16_t)n && ryu[i]!='E';i++) {
        if (ryu[i]!='.') {
            if (count>=17U||ryu[i]<'0'||ryu[i]>'9') {return InstallationCaptureResult_Failed;}
            digits[count++]=ryu[i];
        }
    }
    if ((i>=(uint16_t)n)||(count==0U)) {return InstallationCaptureResult_Failed;}
    i++;
    if ((i<(uint16_t)n)&&(ryu[i]=='-')) {sign=-1;i++;}
    if(i>=(uint16_t)n){return InstallationCaptureResult_Failed;}
    for (;i<(uint16_t)n;i++) {
        if(ryu[i]<'0'||ryu[i]>'9'||exponent>324){return InstallationCaptureResult_Failed;}
        exponent=exponent*10+(ryu[i]-'0');
    }
    if(exponent>324){return InstallationCaptureResult_Failed;}
    exponent*=sign;decimal=exponent+1;
    if ((exponent>=-4)&&(exponent<16)) {
        if (decimal<=0) {output[used++]='0';output[used++]='.';for (i=0U;i<(uint16_t)(-decimal);i++) {output[used++]='0';}}
        for (i=0U;i<count;i++) {if ((decimal>0)&&((int)i==decimal)) {output[used++]='.';}output[used++]=digits[i];}
        if (decimal>=(int)count) {
            for (i=count;i<(uint16_t)decimal;i++) {output[used++]='0';}
            output[used++]='.';output[used++]='0';
        }
    } else {
        output[used++]=digits[0];
        if (count>1U) {output[used++]='.';for (i=1U;i<count;i++) {output[used++]=digits[i];}}
        output[used++]='e';output[used++]=(exponent<0)?'-':'+';
        if (exponent<0) {exponent=-exponent;}
        if (exponent>=100) {output[used++]=(char)('0'+exponent/100);start=1U;}
        if ((exponent>=10)||(start==0U)) {output[used++]=(char)('0'+(exponent/10)%10);}
        output[used++]=(char)('0'+exponent%10);
    }
    if (used>=32U) {return InstallationCaptureResult_Failed;}
    output[used]='\0';*length=used;return InstallationCaptureResult_Ok;
}
