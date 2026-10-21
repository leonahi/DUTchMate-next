cmake_minimum_required(VERSION 3.20)
project(rpi_pico_protocol_tests C)
enable_testing()

add_executable(test_protocol test_protocol.c)
target_include_directories(test_protocol PRIVATE include)
target_compile_features(test_protocol PRIVATE c_std_11)
target_compile_options(test_protocol PRIVATE
  -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes)

foreach(case IN ITEMS boot ticks ping repeat silent fragmented unfinished boundary
                      late_tick malformed overlong counter not_ready configure_failure)
  add_test(NAME ${case} COMMAND test_protocol ${case})
endforeach()
