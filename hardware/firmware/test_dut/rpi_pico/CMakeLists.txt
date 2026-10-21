cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr 4.4.0 EXACT REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(dutchmate_test_dut_rpi_pico)

if(NOT BOARD STREQUAL "rpi_pico" OR NOT BOARD_QUALIFIERS STREQUAL "rp2040")
  message(FATAL_ERROR "This fixture supports only rpi_pico/rp2040")
endif()

target_sources(app PRIVATE src/main.c)
target_compile_options(app PRIVATE -Wall -Wextra -Werror)
