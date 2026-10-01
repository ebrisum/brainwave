// RidePrepCourseMath.h — engine-independent course maths shared by the Unreal plugin and the native test harness.
// Mirrors packages/course-format/src/position.ts (poseAt) and gpx2course/coords.py exactly; covered by the
// cross-renderer consistency test (spec §16.8): the same s must give the same rider position (±2 cm).
#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace RidePrep {

struct RouteArrays {
    double SpacingM = 5.0;
    std::vector<float> S, X, Y, Z, GradePct, HeadingRad, RadiusM, CrrMultiplier;
    std::vector<uint8_t> SurfaceCode, RoadWidthM;
    size_t Count() const { return X.size(); }
};

struct RoutePose { double X, Y, Z, HeadingRad; };

// Decodes route.bin given the array offsets from manifest.json (all arrays little-endian, `count` elements).
struct ArrayLayout { std::string Name; bool IsFloat; size_t Offset; };

inline RouteArrays DecodeRoute(const uint8_t* Data, size_t Size, size_t Count, double Spacing, const std::vector<ArrayLayout>& Layout) {
    RouteArrays R;
    R.SpacingM = Spacing;
    for (const ArrayLayout& A : Layout) {
        const size_t Bytes = Count * (A.IsFloat ? 4 : 1);
        if (A.Offset + Bytes > Size) throw std::runtime_error("route.bin too small for " + A.Name);
        if (A.IsFloat) {
            std::vector<float> V(Count);
            std::memcpy(V.data(), Data + A.Offset, Bytes);  // little-endian hosts (x86, ARM)
            if (A.Name == "s") R.S = V; else if (A.Name == "x") R.X = V; else if (A.Name == "y") R.Y = V;
            else if (A.Name == "z") R.Z = V; else if (A.Name == "gradePct") R.GradePct = V; else if (A.Name == "headingRad") R.HeadingRad = V;
            else if (A.Name == "radiusM") R.RadiusM = V; else if (A.Name == "crrMultiplier") R.CrrMultiplier = V;
        } else {
            std::vector<uint8_t> V(Data + A.Offset, Data + A.Offset + Count);
            if (A.Name == "surfaceCode") R.SurfaceCode = V; else if (A.Name == "roadWidthM") R.RoadWidthM = V;
        }
    }
    return R;
}

inline RoutePose PoseAt(const RouteArrays& C, double S) {
    const size_t Last = C.Count() - 1;
    double Fi = S / C.SpacingM;
    if (Fi < 0) Fi = 0;
    if (Fi > double(Last)) Fi = double(Last);
    size_t I = size_t(std::floor(Fi));
    if (I > Last - 1) I = Last - 1;
    const double T = Fi - double(I);
    const size_t J = I + 1;
    const double Hx = std::sin(C.HeadingRad[I]) * (1 - T) + std::sin(C.HeadingRad[J]) * T;
    const double Hy = std::cos(C.HeadingRad[I]) * (1 - T) + std::cos(C.HeadingRad[J]) * T;
    const double TwoPi = 6.283185307179586;
    double H = std::fmod(std::atan2(Hx, Hy) + TwoPi, TwoPi);
    return { C.X[I] + (double(C.X[J]) - C.X[I]) * T, C.Y[I] + (double(C.Y[J]) - C.Y[I]) * T, C.Z[I] + (double(C.Z[J]) - C.Z[I]) * T, H };
}

// ENU metres (right-handed) → Unreal centimetres (left-handed, Z-up): X = E·100, Y = −N·100, Z = U·100.
struct Vec3d { double X, Y, Z; };
inline Vec3d EnuToUe(double E, double N, double U) { return { E * 100.0, -N * 100.0, U * 100.0 }; }
inline Vec3d UeToEnu(double X, double Y, double Z) { return { X / 100.0, -Y / 100.0, Z / 100.0 }; }

// Compass bearing (rad, clockwise from north) → Unreal yaw (deg, from +X toward +Y).
inline double CompassToUeYawDeg(double BearingRad) { return BearingRad * 57.29577951308232 - 90.0; }

// Rider lean (rad) for speed v (m/s) and radius r (m).
inline double LeanAngle(double V, double R) { return (std::isfinite(R) && R > 0) ? std::atan(V * V / (9.80665 * R)) : 0.0; }

}  // namespace RidePrep
