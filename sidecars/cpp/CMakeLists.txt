cmake_minimum_required(VERSION 3.16)
project(aio_sidecar LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Threads REQUIRED)

add_library(aio_sidecar INTERFACE)
target_include_directories(
    aio_sidecar INTERFACE
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/third_party")
target_compile_features(aio_sidecar INTERFACE cxx_std_17)
target_link_libraries(aio_sidecar INTERFACE Threads::Threads)

set(
    ECHO_DESCRIPTOR_FIXTURE
    "${CMAKE_CURRENT_SOURCE_DIR}/../conformance/fixtures/echo.descriptor.json")
file(READ "${ECHO_DESCRIPTOR_FIXTURE}" ECHO_DESCRIPTOR_JSON)
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/examples/echo_descriptor.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/echo_descriptor.hpp"
    @ONLY)

add_executable(echo_engine examples/echo.cpp)
target_include_directories(
    echo_engine PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(echo_engine PRIVATE aio_sidecar)
