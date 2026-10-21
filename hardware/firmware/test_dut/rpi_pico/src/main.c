/* Deterministic test-DUT protocol v1, exclusively on RP2040 hardware UART0. */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>

static const struct device *const uart = DEVICE_DT_GET(DT_NODELABEL(uart0));

static void emit_record(const char *record, size_t length)
{
	for (size_t i = 0; i < length; i++) {
		uart_poll_out(uart, (unsigned char)record[i]);
	}
}

static void emit_tick(uint32_t counter)
{
	char record[] = "TICK 0000000000\r\n";

	for (int i = 14; i >= 5; i--) {
		record[i] = (char)('0' + counter % 10U);
		counter /= 10U;
	}
	emit_record(record, sizeof(record) - 1);
}

int main(void)
{
	static const char banner[] =
		"DUTCHMATE-TEST-DUT rpi_pico fw=1.0.0 protocol=1\r\n";
	static const char ping[] = "PING\r\n";
	static const char pong[] = "PONG\r\n";
	const struct uart_config config = {
		.baudrate = 115200,
		.parity = UART_CFG_PARITY_NONE,
		.stop_bits = UART_CFG_STOP_BITS_1,
		.data_bits = UART_CFG_DATA_BITS_8,
		.flow_ctrl = UART_CFG_FLOW_CTRL_NONE,
	};
	unsigned char request[8];
	size_t used = 0;
	bool discard = false;
	uint32_t counter = 0;

	if (!device_is_ready(uart)) {
		return -ENODEV;
	}
	int result = uart_configure(uart, &config);

	if (result != 0) {
		return result;
	}
	emit_record(banner, sizeof(banner) - 1);
	int64_t next_tick = k_uptime_get() + 1000;

	for (;;) {
		/* Bound RX work so even excessive input cannot starve ticks. */
		for (unsigned int batch = 0; batch < 8U; batch++) {
			unsigned char byte;

			if (uart_poll_in(uart, &byte) != 0) {
				break;
			}
			if (!discard) {
				if (used < sizeof(request)) {
					request[used++] = byte;
				} else {
					discard = true;
				}
			}
			if (byte == '\n') {
				if (!discard && used == sizeof(ping) - 1 &&
				    memcmp(request, ping, used) == 0) {
					emit_record(pong, sizeof(pong) - 1);
				}
				/* SILENT and unknown records intentionally have no reply. */
				used = 0;
				discard = false;
			}
		}
		int64_t now = k_uptime_get();

		if (now >= next_tick) {
			emit_tick(counter++);
			next_tick = now + 1000;
		}
		k_msleep(1);
	}
}
