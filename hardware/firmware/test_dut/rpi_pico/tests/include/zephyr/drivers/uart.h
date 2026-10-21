#ifndef TEST_UART_H
#define TEST_UART_H

#include <stdint.h>
#include <zephyr/device.h>

enum {
	UART_CFG_PARITY_NONE = 0,
	UART_CFG_STOP_BITS_1 = 1,
	UART_CFG_DATA_BITS_8 = 3,
	UART_CFG_FLOW_CTRL_NONE = 0,
};

struct uart_config {
	uint32_t baudrate;
	uint8_t parity;
	uint8_t stop_bits;
	uint8_t data_bits;
	uint8_t flow_ctrl;
};

int uart_configure(const struct device *dev, const struct uart_config *config);
int uart_poll_in(const struct device *dev, unsigned char *byte);
void uart_poll_out(const struct device *dev, unsigned char byte);

#endif
