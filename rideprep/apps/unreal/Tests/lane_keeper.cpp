// Native harness for the lane-keeper cross test: replays a ride (dt s v crank per line on stdin) through
// RidePrep::LaneKeeper and prints "offset yaw lean" per step, for comparison with apps/client/src/engine/LaneKeeper.ts.
// Usage: lane_keeper <route.bin> <count> <spacing> <keepRight|racing> name:type:offset ... < steps
#include "../Plugins/RidePrepRuntime/Source/RidePrepRuntime/Public/RidePrepLaneKeeper.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>

int main(int argc, char** argv) {
    if (argc < 6) { std::fprintf(stderr, "usage: lane_keeper route.bin count spacing keepRight|racing name:type:offset...\n"); return 2; }
    std::ifstream F(argv[1], std::ios::binary);
    std::vector<uint8_t> Buf((std::istreambuf_iterator<char>(F)), std::istreambuf_iterator<char>());
    const size_t Count = std::stoul(argv[2]);
    const double Spacing = std::stod(argv[3]);
    const std::string Line = argv[4];
    std::vector<RidePrep::ArrayLayout> Layout;
    for (int i = 5; i < argc; ++i) {
        std::string A = argv[i];
        const size_t P1 = A.find(':'), P2 = A.rfind(':');
        Layout.push_back({ A.substr(0, P1), A.substr(P1 + 1, P2 - P1 - 1) == "float32", std::stoul(A.substr(P2 + 1)) });
    }
    const RidePrep::RouteArrays R = RidePrep::DecodeRoute(Buf.data(), Buf.size(), Count, Spacing, Layout);
    RidePrep::LaneKeeper K(R, Line == "racing" ? RidePrep::LaneKeeper::ELine::Racing : RidePrep::LaneKeeper::ELine::KeepRight);
    double Dt, S, V, Crank;
    while (std::cin >> Dt >> S >> V >> Crank) {
        K.Update(Dt, S, V, Crank);
        std::printf("%.9f %.9f %.9f\n", K.Offset, K.Yaw, K.Lean);
    }
    return 0;
}
