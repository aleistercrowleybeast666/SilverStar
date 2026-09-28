#ifndef __SILVERSTAR_COMPILER_H
#define __SILVERSTAR_COMPILER_H

#if defined(__GNUC__) || defined(__clang__)
#define SILVERSTAR_NORETURN __attribute__((noreturn))
#define SILVERSTAR_WARN_UNUSED_RESULT __attribute__((warn_unused_result))
#else
#define SILVERSTAR_NORETURN
#define SILVERSTAR_WARN_UNUSED_RESULT
#endif

#endif /* __SILVERSTAR_COMPILER_H */
