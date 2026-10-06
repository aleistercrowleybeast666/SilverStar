#ifndef __SILVERSTAR_BUILD_MODE_H
#define __SILVERSTAR_BUILD_MODE_H

/* Constant C branches preserve the ordinary mode without source-side #if.
 * Do not define SILVERSTAR_COMPACT_MODE in ordinary projects: some generated
 * contracts intentionally distinguish an absent compact configuration. */
#if defined(SILVERSTAR_COMPACT_MODE) && (SILVERSTAR_COMPACT_MODE != 0)
#define SILVERSTAR_BUILD_COMPACT_ENABLED 1U
#else
#define SILVERSTAR_BUILD_COMPACT_ENABLED 0U
#endif

#endif /* __SILVERSTAR_BUILD_MODE_H */
