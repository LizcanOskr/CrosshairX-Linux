cmake_minimum_required(VERSION 3.20)
project(crosshair_overlay LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)
find_package(LayerShellQt REQUIRED)
find_package(KF6GlobalAccel REQUIRED)
find_package(KF6WindowSystem REQUIRED)

add_executable(crosshair-overlay main.cpp)
target_link_libraries(crosshair-overlay PRIVATE
    Qt6::Core Qt6::Gui Qt6::Widgets LayerShellQt::Interface
    KF6::GlobalAccel KF6::WindowSystem)
