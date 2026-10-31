#include "system_installation_active_if.h"
#include "installation_capture.h"
#include "common_format.h"
#include <string.h>

typedef struct { char *part[5]; } ActiveWireTokens;
static uint8_t s_read_sid[16];
static uint8_t ActiveWire_Split(char *text,ActiveWireTokens *tokens,uint8_t maximum,char separator)
{
    uint16_t i;uint8_t count=0U,inside=0U;
    for(i=0U;i<192U;i++){
        if(text[i]=='\0'){return count;}
        if(text[i]==separator){text[i]='\0';inside=0U;}
        else if(!inside){if(count>=maximum){return 0U;}tokens->part[count++]=&text[i];inside=1U;}
    }
    return 0U;
}
static uint8_t ActiveWire_Nibble(char value)
{
    if(value>='0'&&value<='9'){return (uint8_t)(value-'0');}
    if(value>='a'&&value<='f'){return (uint8_t)(value-'a'+10);}
    if(value>='A'&&value<='F'){return (uint8_t)(value-'A'+10);}
    return UINT8_MAX;
}
static uint8_t ActiveWire_Unhex(const char *text,uint8_t *bytes,uint16_t length)
{
    uint16_t i;
    for(i=0U;i<length;i++){
        uint8_t high,low;if(text[2U*i]=='\0'||text[2U*i+1U]=='\0'){return 0U;}
        high=ActiveWire_Nibble(text[2U*i]);low=ActiveWire_Nibble(text[2U*i+1U]);
        if(high>15U||low>15U){return 0U;}bytes[i]=(uint8_t)(high*16U+low);
    }
    return (uint8_t)(text[length*2U]=='\0');
}
static void ActiveWire_Hex(char *text,const uint8_t *bytes,uint16_t length)
{
    static const char digits[]="0123456789abcdef";uint16_t i;
    for(i=0U;i<length;i++){text[2U*i]=digits[bytes[i]>>4U];text[2U*i+1U]=digits[bytes[i]&15U];}
    text[2U*length]='\0';
}
static uint8_t ActiveWire_U32(const char *text,uint32_t *value)
{
    uint8_t i;uint32_t result=0U;
    for(i=0U;i<11U;i++){
        uint32_t digit;if(text[i]=='\0'){if(i==0U){return 0U;}*value=result;return 1U;}
        if(text[i]<'0'||text[i]>'9'){return 0U;}digit=(uint32_t)(text[i]-'0');
        if(result>(UINT32_MAX-digit)/10U){return 0U;}result=result*10U+digit;
    }
    return 0U;
}
static uint8_t ActiveWire_Context(const char *context,const uint8_t *record)
{
    uint8_t bytes[16];
    if(context[0]=='B'&&context[1]=='-'){
        return (uint8_t)(ActiveWire_Unhex(&context[2],bytes,15U)&&memcmp(bytes,&record[84],15U)==0);
    }
    return (uint8_t)(ActiveWire_Unhex(context,bytes,16U)&&memcmp(bytes,s_read_sid,16U)==0);
}
static void ActiveWire_Result(char *out,uint16_t capacity,const char *operation,const char *sid,
    uint32_t rid,SystemInstallationActiveResult result)
{
    SystemInstallationActiveStatus status;
    if(SystemInstallationActive_StatusGet(&status)!=SystemInstallationActiveResult_Ok){return;}
    if(result==SystemInstallationActiveResult_Ok||result==SystemInstallationActiveResult_Pending){
        (void)CommonFormat_Print(out,capacity,"%s INSTALL %s sid=%s rid=%lu applied_generation=%lu saved_generation=%lu active=%u saved=%u loaded=%u pending=%u valid=%u",
            result==SystemInstallationActiveResult_Ok?"OK":"PENDING",operation,sid,(unsigned long)rid,
            (unsigned long)status.applied_generation,(unsigned long)status.saved_generation,
            status.active,status.saved,status.loaded,status.pending,status.valid);
    }else{
        (void)CommonFormat_Print(out,capacity,"ERR INSTALL %s sid=%s rid=%lu code=%lu reason=%s",operation,sid,
            (unsigned long)rid,(unsigned long)result,
            result==SystemInstallationActiveResult_Unsupported?"SOURCE_QUALIFICATION":"ACTIVE_TRANSACTION_REJECTED");
    }
}
static SystemInstallationActiveResult ActiveWire_Upload(const uint8_t sid[16],uint32_t rid,char *declaration,uint64_t now_us)
{
    ActiveWireTokens fields;uint32_t length,crc=0U;uint8_t sha[32],crc_bytes[4],i;
    if(ActiveWire_Split(declaration,&fields,3U,':')!=3U||!ActiveWire_U32(fields.part[0],&length)||
        length!=SYSTEM_INSTALLATION_ACTIVE_BYTES||!ActiveWire_Unhex(fields.part[1],crc_bytes,4U)||
        !ActiveWire_Unhex(fields.part[2],sha,32U)){return SystemInstallationActiveResult_Invalid;}
    for(i=0U;i<4U;i++){crc=(crc<<8U)|crc_bytes[i];}
    return SystemInstallationActive_UploadBegin(sid,rid,crc,sha,now_us);
}
static SystemInstallationActiveResult ActiveWire_Put(const uint8_t sid[16],uint32_t rid,char *declaration,uint64_t now_us)
{
    ActiveWireTokens fields;uint32_t offset;uint8_t bytes[48];uint16_t count;
    if(ActiveWire_Split(declaration,&fields,2U,':')!=2U||!ActiveWire_U32(fields.part[0],&offset)||
        offset>SYSTEM_INSTALLATION_ACTIVE_BYTES){return SystemInstallationActiveResult_Invalid;}
    for(count=0U;count<97U;count++){if(fields.part[1][count]=='\0'){break;}}
    if(count==0U||count>96U||(count%2U)!=0U||!ActiveWire_Unhex(fields.part[1],bytes,(uint16_t)(count/2U)))
    {return SystemInstallationActiveResult_Invalid;}
    return SystemInstallationActive_UploadWrite(sid,rid,(uint16_t)offset,bytes,(uint16_t)(count/2U),now_us);
}
static void ActiveWire_Inspect(const ActiveWireTokens *tokens,uint8_t count,char *out,uint16_t capacity)
{
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],sha[32];char digest[65],token[33],hex[97];
    SystemInstallationActiveStatus status;uint32_t offset;uint16_t length;
    if(SystemInstallationActive_RecordGet(record)!=SystemInstallationActiveResult_Ok||
        !ActiveWire_Context(tokens->part[2],record)||
        SystemInstallationActive_StatusGet(&status)!=SystemInstallationActiveResult_Ok){return;}
    if(InstallationCapture_Hash(record,sizeof(record),sha)!=InstallationCaptureResult_Ok){return;}
    ActiveWire_Hex(digest,sha,32U);token[0]='S';token[1]='-';ActiveWire_Hex(&token[2],sha,15U);
    if(strcmp(tokens->part[1],"STATUS")==0&&count==4U){
        if(strcmp(tokens->part[3],"ACTIVE:0")!=0&&!(strcmp(tokens->part[3],"SAVED:0")==0&&status.saved)){return;}
        (void)CommonFormat_Print(out,capacity,"OK INSTALL STATUS context=%s token=%s length=228 sha256=%s applied_generation=%lu saved_generation=%lu active=%u saved=%u loaded=%u valid=%u",
            tokens->part[2],token,digest,(unsigned long)status.applied_generation,(unsigned long)status.saved_generation,
            status.active,status.saved,status.loaded,status.valid);
    }else if(strcmp(tokens->part[1],"READ")==0&&count==5U&&strcmp(tokens->part[3],token)==0&&
            ActiveWire_U32(tokens->part[4],&offset)&&offset<SYSTEM_INSTALLATION_ACTIVE_BYTES){
        length=(uint16_t)(SYSTEM_INSTALLATION_ACTIVE_BYTES-offset);if(length>48U){length=48U;}
        ActiveWire_Hex(hex,&record[offset],length);
        (void)CommonFormat_Print(out,capacity,"OK INSTALL READ context=%s token=%s offset=%lu data=%s next=%lu end=%u",
            tokens->part[2],token,(unsigned long)offset,hex,(unsigned long)(offset+length),
            offset+length==SYSTEM_INSTALLATION_ACTIVE_BYTES?1U:0U);
    }
}
uint8_t SystemInstallationActive_ExecuteLine(const char *line,char *out,uint16_t capacity,uint64_t now_us)
{
    char text[192];ActiveWireTokens tokens;uint16_t i;uint8_t count,sid[16];uint32_t rid;
    SystemInstallationActiveResult result=SystemInstallationActiveResult_Invalid;
    if(line==NULL||out==NULL||capacity<511U){return 0U;}
    for(i=0U;i<192U;i++){text[i]=line[i];if(line[i]=='\0'){break;}}if(i==192U){return 0U;}
    count=ActiveWire_Split(text,&tokens,5U,' ');
    if(count<4U||strcmp(tokens.part[0],"INSTALL")!=0){return 0U;}
    if(strcmp(tokens.part[1],"STATUS")==0&&strcmp(tokens.part[3],"STATE:0")==0){return 0U;}
    if(strcmp(tokens.part[1],"READ")==0||strcmp(tokens.part[1],"STATUS")==0){
        (void)CommonFormat_Print(out,capacity,"ERR INSTALL %s code=NOT_READY reason=ACTIVE_RECORD_OR_CONTEXT",tokens.part[1]);
        ActiveWire_Inspect(&tokens,count,out,capacity);return 1U;
    }
    if(count!=5U||!ActiveWire_Unhex(tokens.part[2],sid,16U)||!ActiveWire_U32(tokens.part[3],&rid)){return 0U;}
    if(strcmp(tokens.part[1],"UPLOAD")==0){result=ActiveWire_Upload(sid,rid,tokens.part[4],now_us);
        if(result==SystemInstallationActiveResult_Ok){(void)memcpy(s_read_sid,sid,16U);}
    }else if(strcmp(tokens.part[1],"PUT")==0){result=ActiveWire_Put(sid,rid,tokens.part[4],now_us);
    }else if(strcmp(tokens.part[1],"DO")==0){
        if(strcmp(tokens.part[4],"APPLY")==0){result=SystemInstallationActive_Apply(sid,rid,now_us);}
        else if(strcmp(tokens.part[4],"SAVE")==0){result=SystemInstallationActive_Save(sid,rid,now_us);}
        else if(strcmp(tokens.part[4],"CANCEL")==0||strcmp(tokens.part[4],"UPLOAD_CANCEL")==0){
            result=SystemInstallationActive_Cancel(sid,rid);if(result==SystemInstallationActiveResult_Stale){return 0U;}
        }else{return 0U;}
    }else{return 0U;}
    ActiveWire_Result(out,capacity,tokens.part[1],tokens.part[2],rid,result);
    if(result==SystemInstallationActiveResult_Ok&&strcmp(tokens.part[1],"DO")==0&&
        (strcmp(tokens.part[4],"CANCEL")==0||strcmp(tokens.part[4],"UPLOAD_CANCEL")==0)){
        uint16_t used=(uint16_t)strlen(out);
        if(used<capacity){(void)CommonFormat_Print(&out[used],(uint16_t)(capacity-used)," cleanup_complete=1");}
    }
    return 1U;
}
