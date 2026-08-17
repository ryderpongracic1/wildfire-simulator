cmake_minimum_required(VERSION 3.15)
project(WildfireSimulator VERSION 1.0 LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler flags for optimization
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra")
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -march=native")

# Find required packages
find_package(GDAL REQUIRED)

# Try to find OpenMP (optional - will work without it)
find_package(OpenMP)

# JSON library (header-only)
include(FetchContent)
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

# Include directories
include_directories(
    ${PROJECT_SOURCE_DIR}/include
    ${GDAL_INCLUDE_DIRS}
)

# Source files
set(SOURCES
    src/main.cpp
    src/FireSpreadModel.cpp
    src/GeoDataLoader.cpp
)

# Executable
add_executable(wildfire_simulator ${SOURCES})

# Link libraries
target_link_libraries(wildfire_simulator
    ${GDAL_LIBRARIES}
    nlohmann_json::nlohmann_json
)

# Link OpenMP if found
if(OpenMP_CXX_FOUND)
    target_link_libraries(wildfire_simulator OpenMP::OpenMP_CXX)
    message(STATUS "✓ OpenMP enabled - parallel execution available")
else()
    message(STATUS "⚠ OpenMP not found - will run in serial mode (slower but works)")
    # Define empty macro so code compiles without OpenMP
    target_compile_definitions(wildfire_simulator PRIVATE NO_OPENMP)
endif()

# Tests (model core only -- no GDAL dependency)
enable_testing()
add_executable(model_test tests/model_test.cpp src/FireSpreadModel.cpp)
if(OpenMP_CXX_FOUND)
    target_link_libraries(model_test OpenMP::OpenMP_CXX)
else()
    target_compile_definitions(model_test PRIVATE NO_OPENMP)
endif()
add_test(NAME model_test COMMAND model_test)

# Install target
install(TARGETS wildfire_simulator DESTINATION bin)

# Print build configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ Compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "GDAL include: ${GDAL_INCLUDE_DIRS}")
message(STATUS "GDAL libraries: ${GDAL_LIBRARIES}")
