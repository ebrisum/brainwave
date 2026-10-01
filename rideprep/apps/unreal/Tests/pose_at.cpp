// Native harness for the cross-renderer test: prints PoseAt for s values read from stdin.
// Usage: pose_at <route.bin> <count> <spacing> name:type:offset ... < s_values
#include "../Plugins/RidePrepRuntime/Source/RidePrepRuntime/Public/RidePrepCourseMath.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>

int main(int argc, char** argv) {
    if (argc < 5) { std::fprintf(stderr, "usage: pose_at route.bin count spacing name:type:offset...\n"); return 2; }
    std::ifstream F(argv[1], std::ios::binary);
    std::vector<uint8_t> Buf((std::istreambuf_iterator<char>(F)), std::istreambuf_iterator<char>());
    const size_t Count = std::stoul(argv[2]);
    const double Spacing = std::stod(argv[3]);
    std::vector<RidePrep::ArrayLayout> Layout;
    for (int i = 4; i < argc; ++i) {
        std::string A = argv[i];
        const size_t P1 = A.find(':'), P2 = A.rfind(':');
        Layout.push_back({ A.substr(0, P1), A.substr(P1 + 1, P2 - P1 - 1) == "float32", std::stoul(A.substr(P2 + 1)) });
    }
    const RidePrep::RouteArrays R = RidePrep::DecodeRoute(Buf.data(), Buf.size(), Count, Spacing, Layout);
    double S;
    while (std::cin >> S) {
        const RidePrep::RoutePose P = RidePrep::PoseAt(R, S);
        const RidePrep::Vec3d U = RidePrep::EnuToUe(P.X, P.Y, P.Z);
        std::printf("%.6f %.6f %.6f %.6f %.3f %.3f %.3f\n", P.X, P.Y, P.Z, P.HeadingRad, U.X, U.Y, U.Z);
    }
    return 0;
}
