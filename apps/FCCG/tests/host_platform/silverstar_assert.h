#ifndef __SILVERSTAR_ASSERT_H
#define __SILVERSTAR_ASSERT_H

#define SILVERSTAR_ASSERT_MODULE_PLATFORM 1U
#define SILVERSTAR_ASSERT_OBJECT(object_, type_, module_id_) \
    do \
    { \
        (void)(object_); \
        (void)sizeof(type_); \
        (void)(module_id_); \
    } while (0)

#endif /* __SILVERSTAR_ASSERT_H */
