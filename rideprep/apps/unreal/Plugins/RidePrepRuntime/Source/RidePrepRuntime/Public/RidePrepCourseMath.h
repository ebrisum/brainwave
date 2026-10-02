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
    std::vector<float> S, X, Y, Z, GradePct, HeadingRad, RadiusM, CrrMultiplier, BankDeg;  // BankDeg: + = right edge lower (may be empty)
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
            else if (A.Name == "bankDeg") R.BankDeg = V;
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

// Course frame (transverse Mercator at the origin, k0 = 1, WGS84) → latitude/longitude in degrees.
// Mirrors packages/course-format/src/geo.ts (Snyder 1987); sub-millimetre within ±200 km of the origin.
inline void LocalToLatLon(double Lat0, double Lon0, double X, double Y, double& OutLat, double& OutLon) {
    const double A = 6378137.0, F = 1 / 298.257223563, E2 = F * (2 - F), EP2 = E2 / (1 - E2), Rad = 3.141592653589793 / 180.0;
    auto Arc = [&](double Phi) {
        const double E4 = E2 * E2, E6 = E4 * E2;
        return A * ((1 - E2 / 4 - 3 * E4 / 64 - 5 * E6 / 256) * Phi - (3 * E2 / 8 + 3 * E4 / 32 + 45 * E6 / 1024) * std::sin(2 * Phi)
                    + (15 * E4 / 256 + 45 * E6 / 1024) * std::sin(4 * Phi) - (35 * E6 / 3072) * std::sin(6 * Phi));
    };
    const double M = Arc(Lat0 * Rad) + Y;
    const double Mu = M / (A * (1 - E2 / 4 - 3 * E2 * E2 / 64 - 5 * E2 * E2 * E2 / 256));
    const double E1 = (1 - std::sqrt(1 - E2)) / (1 + std::sqrt(1 - E2));
    const double Phi1 = Mu + (3 * E1 / 2 - 27 * std::pow(E1, 3) / 32) * std::sin(2 * Mu) + (21 * E1 * E1 / 16 - 55 * std::pow(E1, 4) / 32) * std::sin(4 * Mu)
                        + (151 * std::pow(E1, 3) / 96) * std::sin(6 * Mu) + (1097 * std::pow(E1, 4) / 512) * std::sin(8 * Mu);
    const double S1 = std::sin(Phi1), C1 = std::cos(Phi1), T1v = std::tan(Phi1);
    const double Cc = EP2 * C1 * C1, T1 = T1v * T1v;
    const double N1 = A / std::sqrt(1 - E2 * S1 * S1);
    const double R1 = A * (1 - E2) / std::pow(1 - E2 * S1 * S1, 1.5);
    const double D = X / N1;
    const double Lat = Phi1 - (N1 * T1v / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * Cc - 4 * Cc * Cc - 9 * EP2) * std::pow(D, 4) / 24
                                                + (61 + 90 * T1 + 298 * Cc + 45 * T1 * T1 - 252 * EP2 - 3 * Cc * Cc) * std::pow(D, 6) / 720);
    const double Lon = (D - (1 + 2 * T1 + Cc) * std::pow(D, 3) / 6 + (5 - 2 * Cc + 28 * T1 - 3 * Cc * Cc + 8 * EP2 + 24 * T1 * T1) * std::pow(D, 5) / 120) / C1;
    OutLat = Lat / Rad;
    OutLon = Lon0 + Lon / Rad;
}

// Grid convergence at a course-frame point: azimuth (deg, clockwise from true north) of grid north.
// A georeference whose ENU north must line up with the course grid is yawed by −convergence in UE.
inline double GridConvergenceDeg(double Lat0, double Lon0, double X, double Y) {
    double La0, Lo0, La1, Lo1;
    LocalToLatLon(Lat0, Lon0, X, Y, La0, Lo0);
    LocalToLatLon(Lat0, Lon0, X, Y + 100.0, La1, Lo1);
    const double Rad = 3.141592653589793 / 180.0;
    const double DE = (Lo1 - Lo0) * std::cos(La0 * Rad), DN = La1 - La0;
    return std::atan2(DE, DN) / Rad;
}

}  // namespace RidePrep
