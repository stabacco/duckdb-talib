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

# Link the TA-Lib archive by path so talib_* targets do not list ta-lib-static as an
# exported dependency (DuckDBExports requires every linked target to be in the export set).
add_dependencies(${EXTENSION_NAME} ta-lib-static)
add_dependencies(${LOADABLE_EXTENSION_NAME} ta-lib-static)
if(WIN32 AND MSVC)
  set(_talib_basename "${CMAKE_STATIC_LIBRARY_PREFIX}ta-lib-static${CMAKE_STATIC_LIBRARY_SUFFIX}")
  if(CMAKE_CONFIGURATION_TYPES)
    target_link_libraries(
      ${EXTENSION_NAME}
      debug "${CMAKE_BINARY_DIR}/ta-lib-build/Debug/${_talib_basename}"
      optimized "${CMAKE_BINARY_DIR}/ta-lib-build/Release/${_talib_basename}")
    target_link_libraries(
      ${LOADABLE_EXTENSION_NAME}
      debug "${CMAKE_BINARY_DIR}/ta-lib-build/Debug/${_talib_basename}"
      optimized "${CMAKE_BINARY_DIR}/ta-lib-build/Release/${_talib_basename}")
  else()
    set(_talib_lib "${CMAKE_BINARY_DIR}/ta-lib-build/${_talib_basename}")
    target_link_libraries(${EXTENSION_NAME} "${_talib_lib}")
    target_link_libraries(${LOADABLE_EXTENSION_NAME} "${_talib_lib}")
  endif()
else()
  set(_talib_lib
      "${CMAKE_BINARY_DIR}/ta-lib-build/${CMAKE_STATIC_LIBRARY_PREFIX}ta-lib${CMAKE_STATIC_LIBRARY_SUFFIX}")
  target_link_libraries(${EXTENSION_NAME} "${_talib_lib}")
  target_link_libraries(${LOADABLE_EXTENSION_NAME} "${_talib_lib}")
endif()
target_include_directories(${EXTENSION_NAME}
                           PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../ta-lib/include)
target_include_directories(${LOADABLE_EXTENSION_NAME}
                           PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../ta-lib/include)

install(
  TARGETS ${EXTENSION_NAME}
  EXPORT "${DUCKDB_EXPORT_SET}"
  LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
  ARCHIVE DESTINATION "${INSTALL_LIB_DIR}")
