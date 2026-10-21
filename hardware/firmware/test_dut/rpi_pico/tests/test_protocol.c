/* Execute the real fixture loop; substitute only hardware and uptime. */
#include <errno.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zephyr/drivers/uart.h>

#define main fixture_main
#include "../src/main.c"
#undef main

#define CHECK(condition) do { \
	if (!(condition)) { \
		fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
		exit(EXIT_FAILURE); \
	} \
} while (0)

const struct device test_uart = {0};
static jmp_buf finished;
static int64_t uptime_ms;
static int64_t stop_ms = 30;
static int64_t spacing_ms;
static const unsigned char *input = (const unsigned char *)"";
static size_t input_size;
static size_t input_pos;
static char output[4096];
static size_t output_size;
static bool ready = true;
static bool configured;
static bool jump_clock;
static int configure_result;

bool device_is_ready(const struct device *dev)
{
	CHECK(dev == &test_uart);
	return ready;
}

int uart_configure(const struct device *dev, const struct uart_config *config)
{
	CHECK(dev == &test_uart);
	CHECK(ready && !configured && output_size == 0);
	CHECK(config->baudrate == 115200);
	CHECK(config->parity == UART_CFG_PARITY_NONE);
	CHECK(config->stop_bits == UART_CFG_STOP_BITS_1);
	CHECK(config->data_bits == UART_CFG_DATA_BITS_8);
	CHECK(config->flow_ctrl == UART_CFG_FLOW_CTRL_NONE);
	configured = configure_result == 0;
	return configure_result;
}

int uart_poll_in(const struct device *dev, unsigned char *byte)
{
	CHECK(dev == &test_uart && configured);
	if (input_pos == input_size || uptime_ms < (int64_t)input_pos * spacing_ms) {
		return -1;
	}
	*byte = input[input_pos++];
	return 0;
}

void uart_poll_out(const struct device *dev, unsigned char byte)
{
	CHECK(dev == &test_uart && configured);
	CHECK(output_size + 1 < sizeof(output));
	output[output_size++] = (char)byte;
	output[output_size] = '\0';
}

int64_t k_uptime_get(void)
{
	return uptime_ms;
}

int32_t k_msleep(int32_t ms)
{
	CHECK(ms == 1);
	uptime_ms += ms;
	if (jump_clock && uptime_ms == 100) {
		uptime_ms = 3500;
	}
	if (uptime_ms >= stop_ms) {
		longjmp(finished, 1);
	}
	return 0;
}

int main(int argc, char **argv)
{
	static const char banner[] =
		"DUTCHMATE-TEST-DUT rpi_pico fw=1.0.0 protocol=1\r\n";
	static const char malformed[] =
		"ping\r\nPING\nPING \r\nPING\r\r\n\0PING\r\n\r\nSILENT\nPING\r\n";
	static unsigned char flood[10012];
	const char *tail = "";
	int expected_return = 0;

	CHECK(argc == 2);
	if (strcmp(argv[1], "ticks") == 0) {
		stop_ms = 2100;
		tail = "TICK 0000000000\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "ping") == 0) {
		input = (const unsigned char *)"PING\r\n";
		input_size = 6;
		tail = "PONG\r\n";
	} else if (strcmp(argv[1], "repeat") == 0) {
		input = (const unsigned char *)"PING\r\nSILENT\r\nPING\r\n";
		input_size = 20;
		tail = "PONG\r\nPONG\r\n";
	} else if (strcmp(argv[1], "silent") == 0) {
		input = (const unsigned char *)"SILENT\r\n";
		input_size = 8;
		stop_ms = 2100;
		tail = "TICK 0000000000\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "fragmented") == 0) {
		input = (const unsigned char *)"PING\r\n";
		input_size = 6;
		spacing_ms = 300;
		stop_ms = 2100;
		tail = "TICK 0000000000\r\nPONG\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "unfinished") == 0) {
		input = (const unsigned char *)"PING\r";
		input_size = 5;
		stop_ms = 2100;
		tail = "TICK 0000000000\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "boundary") == 0) {
		input = (const unsigned char *)"PING\r\n";
		input_size = 6;
		spacing_ms = 200;
		stop_ms = 1100;
		tail = "PONG\r\nTICK 0000000000\r\n";
	} else if (strcmp(argv[1], "late_tick") == 0) {
		jump_clock = true;
		stop_ms = 4600;
		tail = "TICK 0000000000\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "malformed") == 0) {
		input = (const unsigned char *)malformed;
		input_size = sizeof(malformed) - 1;
		tail = "PONG\r\n";
	} else if (strcmp(argv[1], "overlong") == 0) {
		memset(flood, 'A', 10000);
		memcpy(flood + 10000, "PING\r\nPING\r\n", 12);
		input = flood;
		input_size = sizeof(flood);
		stop_ms = 2100;
		tail = "TICK 0000000000\r\nPONG\r\nTICK 0000000001\r\n";
	} else if (strcmp(argv[1], "counter") == 0) {
		configured = true;
		emit_tick(UINT32_MAX);
		emit_tick(0);
		CHECK(strcmp(output, "TICK 4294967295\r\nTICK 0000000000\r\n") == 0);
		return EXIT_SUCCESS;
	} else if (strcmp(argv[1], "not_ready") == 0) {
		ready = false;
		expected_return = -ENODEV;
	} else if (strcmp(argv[1], "configure_failure") == 0) {
		configure_result = -EIO;
		expected_return = -EIO;
	} else {
		CHECK(strcmp(argv[1], "boot") == 0);
	}

	if (setjmp(finished) == 0) {
		CHECK(fixture_main() == expected_return);
		CHECK(expected_return != 0);
	} else {
		CHECK(expected_return == 0);
	}
	if (expected_return != 0) {
		CHECK(output_size == 0 && !configured);
	} else {
		CHECK(input_pos == input_size);
		CHECK(output_size == strlen(banner) + strlen(tail));
		CHECK(memcmp(output, banner, strlen(banner)) == 0);
		CHECK(strcmp(output + strlen(banner), tail) == 0);
	}
	return EXIT_SUCCESS;
}
