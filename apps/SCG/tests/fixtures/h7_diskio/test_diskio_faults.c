/* Test-only scheduler/BSP boundary around the actual owning diskio source. */
#include "sd_diskio.h"
#include "queue.h"
#include "task.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void BSP_SD_AbortCallback(void);
static QueueHandle_t s_queue;
static TickType_t s_ticks;
static unsigned s_mode;
static unsigned s_state_calls;
static unsigned s_started;
static uint32_t *s_buffer;
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c); exit(1); } } while (0)
TickType_t xTaskGetTickCount(void) { return s_ticks; }
BaseType_t xTaskGetSchedulerState(void) { return taskSCHEDULER_RUNNING; }
void vTaskDelay(TickType_t ticks) { s_ticks += ticks; }
void Fixture_CriticalEnter(void) { }
void Fixture_CriticalExit(void) { }
QueueHandle_t xQueueCreateStatic(UBaseType_t count,UBaseType_t size,uint8_t *storage,StaticQueue_t *control)
{ (void)storage; CHECK(count==1U && size==2U); memset(control,0,sizeof(*control)); s_queue=control; return control; }
BaseType_t xQueueReset(QueueHandle_t queue) { queue->count=0U; return pdPASS; }
BaseType_t xQueueSendFromISR(QueueHandle_t queue,const void *data,BaseType_t *woken)
{ *woken=pdFALSE; if(queue->count) return pdFALSE; memcpy(queue->data,data,2U); queue->count=1U; return pdPASS; }
BaseType_t xQueueReceive(QueueHandle_t queue,void *data,TickType_t ticks)
{ (void)ticks; if(s_buffer){memset(s_buffer,0x5a,512U);s_buffer=NULL;BSP_SD_ReadCpltCallback();}
  if(!queue->count) { return pdFALSE; }
  memcpy(data,queue->data,2U);queue->count=0U;return pdPASS; }
uint8_t BSP_SD_Init(void) { if(s_mode==3U)BSP_SD_AbortCallback(); return MSD_OK; }
uint8_t BSP_SD_GetCardState(void)
{ s_state_calls++; if(s_mode==1U)s_ticks+=30001U;
  if(s_mode==2U && s_state_calls==2U) { BSP_SD_AbortCallback(); }
  return SD_TRANSFER_OK; }
void BSP_SD_GetCardInfo(BSP_SD_CardInfo *info)
{ info->LogBlockNbr=16U;info->LogBlockSize=512U;if(s_mode==4U)BSP_SD_AbortCallback(); }
uint8_t BSP_SD_ReadBlocks_DMA(uint32_t *buffer,uint32_t sector,uint32_t count)
{ CHECK(sector==0U && count==1U);s_started++;s_buffer=buffer;return MSD_OK; }
uint8_t BSP_SD_WriteBlocks_DMA(uint32_t *buffer,uint32_t sector,uint32_t count)
{ return BSP_SD_ReadBlocks_DMA(buffer,sector,count); }
int main(int argc,char **argv)
{
    BYTE output[512];
    unsigned mode=argc>1?(unsigned)strtoul(argv[1],NULL,10):0U;
    if(mode==3U) {
        s_mode=mode;
        CHECK(SD_Driver.initialize(0U)==STA_NOINIT);
        CHECK(SD_Driver.status(0U)==STA_NOINIT);
        puts("init-error refused READY");return 0;
    }
    CHECK(SD_Driver.initialize(0U)==0U);
    s_mode=mode;s_state_calls=0U;
    if(mode==4U) {
        DWORD sectors=0U;
        CHECK(SD_Driver.ioctl(0U,GET_SECTOR_COUNT,&sectors)==RES_ERROR);
        CHECK(sectors==0U && SD_Driver.status(0U)==STA_NOINIT);
        puts("card-info error refused success");return 0;
    }
    if(mode==0U) {
        CHECK(SD_Driver.read(0U,output,0U,1U)==RES_OK);
        CHECK(output[0]==0x5aU && output[511]==0x5aU && s_started==1U);
        puts("normal transfer passed");return 0;
    }
    CHECK(SD_Driver.read(0U,output,0U,1U)==RES_ERROR);
    CHECK(s_started==(mode==1U?0U:1U));
    CHECK(SD_Driver.status(0U)==STA_NOINIT);
    s_mode=0U;
    CHECK(SD_Driver.initialize(0U)==STA_NOINIT);
    CHECK(SD_Driver.read(0U,output,0U,1U)==RES_NOTRDY);
    puts("late deadline/error quarantine passed");return 0;
}
