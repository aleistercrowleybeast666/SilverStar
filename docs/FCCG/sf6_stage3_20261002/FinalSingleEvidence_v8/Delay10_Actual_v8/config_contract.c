#include "system_user_flight_config.h"
_Static_assert(SYSTEM_FLIGHT_DEPLOY_DELAY_MS == 10000U, "actual candidate must use Delay10");
_Static_assert(SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK == SYSTEM_DEPLOY_TRIGGER_DELAY, "actual candidate must enable Delay only");
