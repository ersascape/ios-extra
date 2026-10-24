/* SPDX-License-Identifier: MIT */
/* The one entry point from the GPU bring-up code into the AdrenoGPU IOKit shell (iokit/Kernel/arm/AdrenoGPU.cpp).
 *
 * Nothing calls it today: the shell adds no boot-time behaviour. When the hardware backend (bsd/dev/sweet_gpu.c)
 * has a GPU that runs, it fills struct adrenogpu_hw_ops and struct adrenogpu_hw_info (adrenogpu_dev.h) and calls
 * adrenogpu_iokit_start(). The call is a no-op unless the boot argument adrenogpu=1 is present. */
#ifndef ADRENOGPU_IOKIT_H
#define ADRENOGPU_IOKIT_H

#ifdef __cplusplus
extern "C" {
#endif
#include "adrenogpu_dev.h"

#define ADRENOGPU_IOKIT_STARTED 0
#define ADRENOGPU_IOKIT_DISABLED 1 /* boot argument adrenogpu=1 absent: nothing was done */
#define ADRENOGPU_IOKIT_EEXIST -1  /* already started */
#define ADRENOGPU_IOKIT_EFAIL -2   /* bad tables or IOKit refused; nothing is left registered */

/* Copies both tables (the ring and the fence word stay borrowed and must live as long as the GPU does). Must be
 * called from a context that may allocate and take mutexes, after IOKit has started (IOResources exists). */
int adrenogpu_iokit_start(const struct adrenogpu_hw_ops *hw, const struct adrenogpu_hw_info *info);

#ifdef __cplusplus
}
#endif
#endif
