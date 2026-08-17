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

# macOS: AppleClang ships no OpenMP runtime, and Homebrew's libomp sits outside
# the default include/library search paths, so the plain search above reports
# "not found" even with libomp installed -- the Mac build silently went serial.
# Point FindOpenMP at the Homebrew prefix and ask again.
#
# Guarded on APPLE, so nothing here runs on Linux: the Docker build finds
# OpenMP natively through GCC and is untouched.
if(APPLE AND NOT OpenMP_CXX_FOUND)
    set(OMP_PREFIX_CANDIDATES "")

    # Ask brew first: it knows the real prefix under either Homebrew layout,
    # and covers a non-default HOMEBREW_PREFIX.
    find_program(BREW_EXECUTABLE brew)
    if(BREW_EXECUTABLE)
        execute_process(
            COMMAND "${BREW_EXECUTABLE}" --prefix libomp
            OUTPUT_VARIABLE BREW_LIBOMP_PREFIX
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
        if(BREW_LIBOMP_PREFIX)
            list(APPEND OMP_PREFIX_CANDIDATES "${BREW_LIBOMP_PREFIX}")
        endif()
    endif()

    # Conventional locations, for when brew is not on PATH (Apple Silicon, Intel).
    list(APPEND OMP_PREFIX_CANDIDATES /opt/homebrew/opt/libomp /usr/local/opt/libomp)

    foreach(OMP_PREFIX IN LISTS OMP_PREFIX_CANDIDATES)
        if(EXISTS "${OMP_PREFIX}/include/omp.h" AND
           EXISTS "${OMP_PREFIX}/lib/libomp.dylib")
            message(STATUS "Retrying OpenMP with Homebrew libomp at ${OMP_PREFIX}")
            # FindOpenMP honors these as hints and skips its own flag search.
            set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp -I${OMP_PREFIX}/include")
            set(OpenMP_CXX_LIB_NAMES "omp")
            set(OpenMP_omp_LIBRARY "${OMP_PREFIX}/lib/libomp.dylib")
            find_package(OpenMP)
            if(OpenMP_CXX_FOUND)
                break()
            endif()
        endif()
    endforeach()

    if(NOT OpenMP_CXX_FOUND)
        message(STATUS
            "No usable Homebrew libomp found - install it with 'brew install libomp' "
            "for parallel execution")
    endif()
endif()

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
