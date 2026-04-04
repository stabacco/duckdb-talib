cmake_minimum_required(VERSION 3.5)

set(TARGET_NAME talib)
set(EXTENSION_NAME ${TARGET_NAME}_extension)
set(LOADABLE_EXTENSION_NAME ${TARGET_NAME}_loadable_extension)

project(${TARGET_NAME})
include_directories(src/include)

set(BUILD_DEV_TOOLS
    OFF
    CACHE BOOL "TA-Lib gen_code / regtest" FORCE)
add_subdirectory(
  ${CMAKE_CURRENT_LIST_DIR}/../ta-lib ${CMAKE_BINARY_DIR}/ta-lib-build
  EXCLUDE_FROM_ALL)

set(EXTENSION_SOURCES src/talib_extension.cpp)

build_static_extension(${TARGET_NAME} ${EXTENSION_SOURCES})
build_loadable_extension(${TARGET_NAME} " " ${EXTENSION_SOURCES})

target_link_libraries(${EXTENSION_NAME} PRIVATE ta-lib-static)
target_link_libraries(${LOADABLE_EXTENSION_NAME} PRIVATE ta-lib-static)
target_include_directories(${EXTENSION_NAME}
                           PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../ta-lib/include)
target_include_directories(${LOADABLE_EXTENSION_NAME}
                           PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../ta-lib/include)

install(
  TARGETS ${EXTENSION_NAME}
  EXPORT "${DUCKDB_EXPORT_SET}"
  LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
  ARCHIVE DESTINATION "${INSTALL_LIB_DIR}")
