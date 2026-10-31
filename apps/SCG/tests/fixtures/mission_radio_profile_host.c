#include <assert.h>
#include <string.h>
#include "mission_radio_profile.h"

int main(void)
{
    uint8_t snapshot[100]={0}, expected[15]={1U,2U,3U,4U,5U,6U,7U,8U,9U,10U,11U,12U,13U,14U,15U};
    const uint8_t nrf[18]={1U,1U,14U,0U,73U,1U,0U,0xE7U,0xE7U,0xE7U,0xE7U,1U,3U,3U,2U,32U,61U,1U};
    MissionRadioProfile profile, before;
    unsigned int length;
    memcpy(snapshot,"SSMS",4U);snapshot[4]=2U;snapshot[6]=6U;
    memcpy(snapshot+66U,expected,15U);
    assert(MissionRadioProfile_Read(snapshot,81U,&profile)==MissionRadioProfileResult_Ok);
    assert(profile.schema==2U && profile.length==15U && profile.backend==MissionRadioBackend_Sx128x);
    assert(memcmp(profile.bytes,expected,15U)==0);
    snapshot[4]=3U;memcpy(snapshot+66U,nrf,18U);
    assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_Ok);
    assert(profile.schema==3U && profile.length==14U && profile.backend==MissionRadioBackend_Nrf24);
    assert(memcmp(profile.bytes,nrf+4U,14U)==0);before=profile;
    for(length=0U;length<84U;length++)
    {
        assert(MissionRadioProfile_Read(snapshot,(uint16_t)length,&profile)!=MissionRadioProfileResult_Ok);
        assert(memcmp(&profile,&before,sizeof(profile))==0);
    }
    snapshot[4]=5U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_UnsupportedSchema);snapshot[4]=3U;
    snapshot[66]=3U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_UnsupportedBackend);snapshot[66]=1U;
    snapshot[67]=2U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_UnsupportedVersion);snapshot[67]=1U;
    snapshot[68]=15U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_Invalid);snapshot[68]=14U;
    snapshot[81]=33U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_Invalid);snapshot[81]=32U;
    snapshot[83]=2U;assert(MissionRadioProfile_Read(snapshot,84U,&profile)==MissionRadioProfileResult_Invalid);
    assert(memcmp(&profile,&before,sizeof(profile))==0);
    const uint8_t sx1278[20]={2U,1U,16U,0U,1U,0x40U,0x0EU,0xCFU,0x19U,
        7U,0x48U,0xE8U,1U,0U,5U,16U,0U,61U,0U,17U};
    memcpy(snapshot+66U,sx1278,sizeof(sx1278));
    assert(MissionRadioProfile_Read(snapshot,86U,&profile)==MissionRadioProfileResult_Ok);
    assert(profile.backend==MissionRadioBackend_Sx1278 && profile.length==16U && profile.bytes[0]==1U);
    before=profile;
    for(length=66U;length<86U;length++)
    {
        assert(MissionRadioProfile_Read(snapshot,(uint16_t)length,&profile)!=MissionRadioProfileResult_Ok);
        assert(memcmp(&profile,&before,sizeof(profile))==0);
    }
    snapshot[70]=2U;
    assert(MissionRadioProfile_Read(snapshot,86U,&profile)==MissionRadioProfileResult_Invalid);
    assert(memcmp(&profile,&before,sizeof(profile))==0);
    snapshot[4]=4U;snapshot[66]=3U;
    memcpy(snapshot+67U,sx1278,sizeof(sx1278));
    assert(MissionRadioProfile_Read(snapshot,87U,&profile)==MissionRadioProfileResult_Ok);
    assert(profile.schema==4U && profile.backend==MissionRadioBackend_Sx1278);
    before=profile;
    for(length=0U;length<87U;length++)
    {
        assert(MissionRadioProfile_Read(snapshot,(uint16_t)length,&profile)!=MissionRadioProfileResult_Ok);
        assert(memcmp(&profile,&before,sizeof(profile))==0);
    }
    snapshot[66]=2U;memcpy(snapshot+67U,expected,15U);
    assert(MissionRadioProfile_Read(snapshot,82U,&profile)==MissionRadioProfileResult_Ok);
    assert(profile.schema==4U && profile.backend==MissionRadioBackend_Sx128x);
    assert(memcmp(profile.bytes,expected,15U)==0);
    return 0;
}
