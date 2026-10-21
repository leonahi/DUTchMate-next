#ifndef TEST_DEVICE_H
#define TEST_DEVICE_H

#include <stdbool.h>

struct device {
	int unused;
};

extern const struct device test_uart;
#define DT_NODELABEL(name) 0
#define DEVICE_DT_GET(node) (&test_uart)
bool device_is_ready(const struct device *dev);

#endif
