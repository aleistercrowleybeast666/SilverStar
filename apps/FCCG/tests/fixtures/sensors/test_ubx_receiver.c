#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ubx_receiver.h"

typedef struct
{
    uint8_t sent[80];
    uint16_t sent_length;
    uint32_t host_baud;
    uint32_t device_baud;
    uint32_t values[3][12];
    uint32_t writes;
    uint32_t nvm_writes;
    uint8_t key_writes[3][12];
    uint32_t sends;
    uint8_t legacy[5][64];
    uint8_t corrupt_readback;
    uint8_t nak;
    uint8_t drop_ack;
} MockReceiver;

static const uint32_t keys[12] = {0x10730001U,0x10740001U,0x10740002U,
    0x30210001U,0x20910007U,0x20110021U,0x30210002U,
    0x1031001FU,0x10310022U,0x10310021U,0x10310025U,0x40520001U};

static uint32_t U32_Read(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1]<<8U | (uint32_t)p[2]<<16U | (uint32_t)p[3]<<24U;
}

static void U32_Write(uint8_t *p, uint32_t v)
{
    for (uint8_t i=0U;i<4U;i++) { p[i]=(uint8_t)(v>>(8U*i)); }
}

static UbxReceiverResult Mock_Send(void *ctx,const uint8_t *frame,uint16_t length)
{
    MockReceiver *mock=ctx;
    assert(length<=sizeof(mock->sent));
    mock->sends++;
    if(mock->host_baud!=mock->device_baud) { return UBX_RECEIVER_OK; }
    memcpy(mock->sent,frame,length); mock->sent_length=length;
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult Mock_SetBaud(void *ctx,uint32_t baud)
{
    MockReceiver *mock=ctx; mock->host_baud=baud; return UBX_RECEIVER_OK;
}

static UbxReceiverResult Mock_Reply(UbxReceiver *receiver,uint8_t cls,uint8_t id,
    const uint8_t *p,uint16_t length)
{
    uint8_t frame[520]; uint16_t n;
    assert(UbxReceiver_FrameBuild(cls,id,p,length,frame,sizeof(frame),&n)==UBX_RECEIVER_OK);
    /* Byte-by-byte delivery deliberately exercises every parser boundary. */
    UbxReceiverResult result=UBX_RECEIVER_BUSY;
    for(uint16_t i=0;i<n;i++)
    {
        UbxReceiverResult next=UbxReceiver_Feed(receiver,&frame[i],1U,receiver->now_us);
        if(next!=UBX_RECEIVER_BUSY) { result=next; }
    }
    return result;
}

static void Mock_Identity(UbxReceiver *receiver,const char *model)
{
    uint8_t payload[100]={0};
    memcpy(payload,"ROM CORE",8U);
    memcpy(&payload[30],"HW VERSION",10U);
    snprintf((char *)&payload[40],30U,"MOD=%s",model);
    snprintf((char *)&payload[70],30U,"%s00",receiver->profile->protocol_version);
    UbxReceiverResult r=Mock_Reply(receiver,0x0AU,0x04U,payload,sizeof(payload));
    assert(r==UBX_RECEIVER_OK || r==UBX_RECEIVER_WRONG_MODEL);
}

static void Mock_Ack(UbxReceiver *receiver,MockReceiver *mock,uint8_t id)
{
    uint8_t payload[2]={6U,id};
    if(mock->drop_ack!=0U) { return; }
    UbxReceiverResult r=Mock_Reply(receiver,5U,mock->nak==0U?1U:0U,payload,2U);
    assert(r==UBX_RECEIVER_OK || r==UBX_RECEIVER_BUSY || r==UBX_RECEIVER_NAK);
}

static void Mock_Modern(UbxReceiver *receiver,MockReceiver *mock)
{
    uint8_t *p=&mock->sent[6];
    uint32_t key=U32_Read(&p[4]); uint8_t item=12U;
    uint8_t width=0U;
    for(uint8_t i=0U;i<12U;i++) { if(keys[i]==key) { item=i; } }
    assert(item<12U);
    assert(receiver->profile->glonass_supported || item != 10U);
    width=(key>>28U)<=2U?1U:((key>>28U)==3U?2U:4U);
    if(mock->sent[3]==0x8AU)
    {
        uint8_t layer=p[1]==1U?0U:(p[1]==2U?1U:2U);
        uint32_t value=0U;
        assert(p[0]==0U && p[2]==0U && p[3]==0U);
        if(mock->nak!=0U) { Mock_Ack(receiver,mock,0x8AU); return; }
        for(uint8_t i=0U;i<width;i++) { value|=(uint32_t)p[8U+i]<<(8U*i); }
        mock->values[layer][item]=value; mock->writes++;
        mock->key_writes[layer][item]++;
        if(layer!=0U) { mock->nvm_writes++; }
        if(layer==0U && item==11U) { mock->device_baud=value; }
        Mock_Ack(receiver,mock,0x8AU);
    }
    else
    {
        uint8_t reply[12]={1U,0U,0U,0U}; uint8_t layer=p[1];
        assert(layer<=2U); reply[1]=layer;
        U32_Write(&reply[4],key);
        U32_Write(&reply[8],mock->values[layer][item]+((mock->corrupt_readback && receiver->state==UBX_RECEIVER_VERIFY_PERSISTENT)?1U:0U));
        if(mock->nak!=0U) { Mock_Ack(receiver,mock,0x8BU); return; }
        UbxReceiverResult r=Mock_Reply(receiver,6U,0x8BU,reply,8U+width);
        assert(r==UBX_RECEIVER_OK || r==UBX_RECEIVER_VERIFY_FAILED);
    }
}

static void Mock_Legacy(UbxReceiver *receiver,MockReceiver *mock)
{
    const uint8_t ids[5]={8U,1U,0x24U,0x3EU,0U};
    const uint8_t sizes[5]={6U,8U,36U,36U,20U};
    uint8_t item=5U; uint16_t n=(uint16_t)(mock->sent_length-8U);
    for(uint8_t i=0U;i<5U;i++) { if(ids[i]==mock->sent[3]) { item=i; } }
    assert(item<5U);
    if(n==sizes[item])
    {
        memcpy(mock->legacy[item],&mock->sent[6],n); mock->writes++;
        if(item==4U) { mock->device_baud=U32_Read(&mock->legacy[4][8]); }
        Mock_Ack(receiver,mock,ids[item]);
    }
    else
    {
        UbxReceiverResult reply = Mock_Reply(receiver,6U,ids[item],mock->legacy[item],sizes[item]);
        assert(reply == UBX_RECEIVER_OK || (receiver->read_only && reply == UBX_RECEIVER_VERIFY_FAILED));
    }
}

static void Mock_Pump(UbxReceiver *receiver,MockReceiver *mock)
{
    if(mock->sent_length==0U) { return; }
    if(mock->sent[2]==0x0AU) { Mock_Identity(receiver,receiver->profile->model); }
    else if(receiver->profile->legacy_configuration!=0U) { Mock_Legacy(receiver,mock); }
    else { Mock_Modern(receiver,mock); }
    mock->sent_length=0U;
}

static UbxReceiverResult Mock_Pvt(UbxReceiver *receiver,uint32_t epoch)
{
    uint8_t p[92]={0U};
    U32_Write(p,epoch); p[20]=3U; p[21]=1U; p[23]=4U;
    U32_Write(&p[24],1160000000U); U32_Write(&p[28],400000000U);
    U32_Write(&p[32],123000U); U32_Write(&p[36],100000U);
    U32_Write(&p[40],500U); U32_Write(&p[44],900U);
    U32_Write(&p[48],1000U); U32_Write(&p[52],2000U); U32_Write(&p[56],3000U);
    U32_Write(&p[68],100U);
    return Mock_Reply(receiver,1U,7U,p,sizeof(p));
}

static void Mock_Factory(MockReceiver *mock,const UbxReceiverProfile *profile)
{
    memset(mock,0,sizeof(*mock)); mock->device_baud=profile->factory_baud;
    mock->values[0][0]=1U; mock->values[0][1]=1U; mock->values[0][2]=1U;
    mock->values[0][3]=1000U; mock->values[0][6]=1U; mock->values[0][11]=profile->factory_baud;
    mock->legacy[0][0]=0xE8U; mock->legacy[0][1]=3U;
    mock->legacy[0][2]=1U; mock->legacy[0][4]=1U;
    mock->legacy[1][0]=1U; mock->legacy[1][1]=7U;
    mock->legacy[3][1]=32U; mock->legacy[3][2]=32U; mock->legacy[3][3]=4U;
    const uint8_t ids[4]={0U,2U,3U,6U};
    for (uint8_t i=0U;i<4U;i++)
    { mock->legacy[3][4U+8U*i]=ids[i]; mock->legacy[3][5U+8U*i]=4U; mock->legacy[3][6U+8U*i]=16U; mock->legacy[3][10U+8U*i]=1U; }
    mock->legacy[4][0]=1U; mock->legacy[4][4]=0xD0U; mock->legacy[4][5]=8U;
    U32_Write(&mock->legacy[4][8],profile->factory_baud);
    mock->legacy[4][12]=3U; mock->legacy[4][14]=3U;
}

static void Mock_Run(UbxReceiver *receiver,MockReceiver *mock)
{
    for(uint16_t i=0U;i<400U;i++)
    {
        UbxReceiverResult r=UbxReceiver_Process(receiver,receiver->now_us+100000U);
        assert(r==UBX_RECEIVER_BUSY || r==UBX_RECEIVER_OK || receiver->state==UBX_RECEIVER_FAILED);
        Mock_Pump(receiver,mock);
        if(receiver->state==UBX_RECEIVER_VERIFY_SAMPLE)
        {
            assert(receiver->state!=UBX_RECEIVER_READY);
            assert(Mock_Pvt(receiver,1000U)==UBX_RECEIVER_OK);
        }
        if(receiver->state==UBX_RECEIVER_READY || receiver->state==UBX_RECEIVER_FAILED) { return; }
    }
    assert(0 && "bounded startup did not terminate");
}

static void Model_Test(UbxReceiverModel model)
{
    UbxReceiver receiver; MockReceiver mock; UbxReceiverPort port;
    const UbxReceiverProfile *profile=UbxReceiver_ProfileGet(model);
    uint8_t layer=profile->legacy_configuration?0U:1U;
    Mock_Factory(&mock,profile); port=(UbxReceiverPort){&mock,Mock_Send,Mock_SetBaud};
    assert(UbxReceiver_Init(&receiver,&port,model,1U,layer,0U)==UBX_RECEIVER_BUSY);
    Mock_Run(&receiver,&mock);
    assert(receiver.state==UBX_RECEIVER_READY);
    assert(receiver.readback.baud == profile->target_baud);
    assert(receiver.readback.measurement_ms == profile->measurement_ms);
    assert(receiver.readback.constellation_mask == 7U);
    assert(receiver.readback.protocol_in == 1U && receiver.readback.protocol_out == 1U);
    assert(receiver.latest.satellites==4U && receiver.latest.valid_solution==1U);
    assert(receiver.latest.velocity_enu_mmps[0]==2000 && receiver.latest.velocity_enu_mmps[1]==1000);
    assert(receiver.latest.velocity_enu_mmps[2]==-3000);
    assert(receiver.latest.height_ellipsoid_mm-receiver.latest.height_msl_mm==23000);
    assert(Mock_Pvt(&receiver,1000U)==UBX_RECEIVER_DUPLICATE_EPOCH);
    assert(Mock_Pvt(&receiver,999U)==UBX_RECEIVER_TIME_ERROR);
    assert(Mock_Pvt(&receiver,604799999U)==UBX_RECEIVER_OK);
    assert(Mock_Pvt(&receiver,10U)==UBX_RECEIVER_OK);
    assert(receiver.latest.epoch_ms==604800010ULL);
    uint32_t nvm_writes=mock.nvm_writes;
    mock.writes=0U;
    assert(UbxReceiver_Init(&receiver,&port,model,1U,layer,0U)==UBX_RECEIVER_BUSY);
    Mock_Run(&receiver,&mock);
    assert(receiver.state==UBX_RECEIVER_READY);
    assert(mock.nvm_writes==nvm_writes && receiver.nvm_write_count==0U && mock.writes==0U);
    uint32_t writes_before_read = mock.writes;
    assert(UbxReceiver_ConfigReadStart(&receiver, receiver.now_us) == UBX_RECEIVER_BUSY);
    assert(receiver.readback.valid_items == 0U);
    Mock_Run(&receiver, &mock);
    assert(receiver.state == UBX_RECEIVER_READY && mock.writes == writes_before_read);
    assert(receiver.readback.measurement_ms == profile->measurement_ms);
    if (profile->legacy_configuration) { mock.legacy[0][0] = 0xE8U; mock.legacy[0][1] = 3U; }
    else { mock.values[0][3] = 1000U; }
    assert(UbxReceiver_ConfigReadStart(&receiver, receiver.now_us) == UBX_RECEIVER_BUSY);
    Mock_Run(&receiver, &mock);
    assert(receiver.result == UBX_RECEIVER_VERIFY_FAILED && mock.writes == writes_before_read);
    assert(receiver.readback.measurement_ms == 1000U);
    printf("%s: factory baud/config/readback/SI/week/reboot zero-write PASS\n",profile->model);
}

int main(void)
{
    assert(UbxReceiver_ProfileGet((UbxReceiverModel)-1) == NULL);
    assert(UbxReceiver_ProfileGet(UBX_RECEIVER_MODEL_COUNT) == NULL);
    uint8_t frame[8]; uint16_t n;
    const uint8_t golden[8]={0xB5U,0x62U,0x0AU,0x04U,0U,0U,0x0EU,0x34U};
    assert(UbxReceiver_FrameBuild(0x0AU,0x04U,NULL,0U,frame,8U,&n)==UBX_RECEIVER_OK);
    assert(n==8U && memcmp(frame,golden,8U)==0);
    for(int i=0;i<UBX_RECEIVER_MODEL_COUNT;i++) { Model_Test((UbxReceiverModel)i); }
    UbxReceiver receiver; MockReceiver mock;
    Mock_Factory(&mock,UbxReceiver_ProfileGet(UBX_RECEIVER_NEO_F10N));
    UbxReceiverPort port={&mock,Mock_Send,Mock_SetBaud};
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_MAX_M10S,1U,2U,0U)==UBX_RECEIVER_UNSUPPORTED_LAYER);
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_NEO_F10N,0U,0U,0U)==UBX_RECEIVER_INVALID_ARGUMENT);
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_NEO_F10N,1U,2U,0U)==UBX_RECEIVER_BUSY);
    Mock_Identity(&receiver,"NEO-M8N"); assert(receiver.result==UBX_RECEIVER_WRONG_MODEL);
    Mock_Factory(&mock,UbxReceiver_ProfileGet(UBX_RECEIVER_NEO_F10N));
    mock.drop_ack=1U;
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_NEO_F10N,1U,2U,0U)==UBX_RECEIVER_BUSY);
    Mock_Run(&receiver,&mock); assert(receiver.state==UBX_RECEIVER_READY);
    /* Nine nonzero F10 values differ from the empty Flash fixture: the three
     * newly configured constellations add three real writes. No key repeats. */
    assert(mock.nvm_writes == 9U);
    for (uint8_t i=0U; i<12U; i++) { assert(mock.key_writes[2][i] <= 1U); }
    Mock_Factory(&mock,UbxReceiver_ProfileGet(UBX_RECEIVER_NEO_F10N)); mock.corrupt_readback=1U;
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_NEO_F10N,1U,2U,0U)==UBX_RECEIVER_BUSY);
    Mock_Run(&receiver,&mock); assert(receiver.result==UBX_RECEIVER_VERIFY_FAILED);
    Mock_Factory(&mock,UbxReceiver_ProfileGet(UBX_RECEIVER_NEO_F10N)); mock.nak=1U;
    assert(UbxReceiver_Init(&receiver,&port,UBX_RECEIVER_NEO_F10N,1U,0U,0U)==UBX_RECEIVER_BUSY);
    Mock_Run(&receiver,&mock); assert(receiver.result==UBX_RECEIVER_NAK);
    puts("UBX model session suite PASS (HARDWARE_UNVERIFIED)");
    return 0;
}
