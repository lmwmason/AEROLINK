#pragma once
#if defined(USE_AEROLINK) && ENABLE_SIMULATOR
#include "common/time.h"
void aerolinkSitlInit(void);
void aerolinkSitlTask(timeUs_t currentTimeUs);
#endif
