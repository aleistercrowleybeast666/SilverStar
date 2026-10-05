#include "navigation_quality.h"
#include "navigation_eskf_replay.h"
unsigned char size_window[sizeof(NavigationWindowContext)];
unsigned char size_state[sizeof(NavigationEskfState)];
unsigned char size_workspace[sizeof(NavigationEskfWorkspace)];
unsigned char size_history[sizeof(NavigationEskfReplay)];
unsigned char size_body[sizeof(NavigationEskfHistoryInput)];
unsigned char size_event[sizeof(NavigationEskfReplayEvent)];
